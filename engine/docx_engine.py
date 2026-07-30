from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
import io
import zipfile

from engine.jobs import JobCancelled
from engine.textflow import join_ocr

# أنماط Word التي تُعرِّف العنوان صراحةً — معلومة دقيقة لا تخمين
_HEADING_STYLES = ("heading", "title", "subtitle", "عنوان")

# احتياطي فقط: عندما لا يستخدم كاتب المستند أنماطاً (كل شيء Normal)
_MIN_BLOCK_WORDS = 3

def _is_heading(paragraph, text: str) -> bool:
    """
    تحديد العنوان من نمط Word نفسه أولاً (Heading 1، Title، ...) لأنه إعلان صريح
    من كاتب المستند، ثم الرجوع إلى عدد الكلمات فقط للمستندات التي لا تستخدم أنماطاً.
    الفارق عملي: عنوان من ست كلمات بنمط Heading كان يُعامَل سابقاً كفقرة عادية.
    """
    try:
        style = (paragraph.style.name or "").strip().lower()
    except Exception:
        style = ""
    if style.startswith(_HEADING_STYLES):
        return True
    return len(text.split()) < _MIN_BLOCK_WORDS

def _count_page_breaks(element) -> int:
    """
    عدّ فواصل الصفحات داخل عنصر معيّن:
    - lastRenderedPageBreak: ترقيم Word الحقيقي المحفوظ عند آخر مرة عرض فيها المستند
    - w:br type=page: فاصل صفحة يدوي أدرجه كاتب المستند
    """
    breaks = len(element.findall(".//" + qn("w:lastRenderedPageBreak")))
    for br in element.findall(".//" + qn("w:br")):
        if br.get(qn("w:type")) == "page":
            breaks += 1
    return breaks

def _row_text(row) -> str:
    """نص صف الجدول مع تجاهل تكرار الخلايا المدمجة."""
    cells = []
    for cell in row.cells:
        text = cell.text.strip()
        # الخلايا المدمجة تتكرر في row.cells لذلك نتجاهل التكرار المتتالي
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)

# ── Inline image OCR (document-order interleaving) ──────────────────────────

def _ocr_inline_images(para_elm, document, docx_zip, ocr_fn) -> list:
    """
    استخراج الصور المضمَّنة داخل فقرة XML (سواء رسمية حديثة w:drawing أو
    قديمة w:pict) وقراءتها فوراً بمحرك OCR في موضعها الحقيقي من المستند.
    """
    texts = []
    # DrawingML — modern inline / floating images
    for drawing in para_elm.findall(".//" + qn("w:drawing")):
        for blip in drawing.findall(".//" + qn("a:blip")):
            _ocr_image_by_rid(blip.get(qn("r:embed")), document, docx_zip, ocr_fn, texts)
    # VML — legacy picture format
    for pict in para_elm.findall(".//" + qn("w:pict")):
        for imagedata in pict.findall(".//" + qn("v:imagedata")):
            _ocr_image_by_rid(imagedata.get(qn("r:id")), document, docx_zip, ocr_fn, texts)
    return texts

def _ocr_image_by_rid(rId, document, docx_zip, ocr_fn, texts):
    """حلّ معرف علاقة الصورة، قراءة بايتاتها من الـ ZIP، و OCR فوري."""
    if not rId:
        return
    try:
        rel = document.part.rels[rId]
        target = rel.target_ref
        # حماية من اختراق المسار
        if ".." in target or target.startswith("/"):
            return
        data = docx_zip.read(f"word/{target}")
        ocr_text = join_ocr(ocr_fn(data))
        if ocr_text:
            texts.extend(line for line in ocr_text.split("\n") if line.strip())
    except Exception:
        pass  # صورة تالفة أو علاقة مفقودة — نتجاوز بصمت

# ── Main engine ─────────────────────────────────────────────────────────────

def process_docx(file_bytes: bytes, force_ocr: bool = False, ocr_fn=None,
                 is_cancelled=None):
    """
    يستقبل ملف DOCX كبايتات في الذاكرة ويعيد (النص النظيف، خريطة الصفحات).

    قواعد النظافة (لا قمامة في فهرس البحث):
    - لا فواصل صفحات وهمية داخل النص — الترقيم يعيش في خريطة منفصلة.
    - الأسطر الفارغة تُتجاهل ولا ترفع عدّاد الفقرات.
    - العناوين القصيرة (أقل من 3 كلمات) تُدمَج مع الفقرة التالية ككتلة واحدة
      ذات معنى، فلا ترى الواجهة قفزات عشوائية في أرقام الفقرات.
    - force_ocr مع ocr_fn: تُقرأ الصور المدمجة في موضعها الطبيعي داخل
      المستند، لا في نهايته (ترتيب قراءة بصري سليم).
    """
    try:
        document = Document(io.BytesIO(file_bytes))

        # إذا لم يحمل المستند أي إشارة ترقيم نكتفي بأرقام الفقرات بدل تخمين الصفحات
        paginated = _count_page_breaks(document.element.body) > 0

        blocks = []           # كل عنصر = سطر واحد في النص النهائي
        page_map = []         # [[أول_سطر, رقم_الصفحة], ...]
        para_map = []         # [[أول_سطر, رقم_الصفحة, رقم_الفقرة], ...]
        current_page = 1
        para_on_page = 0      # عداد الفقرات يعود إلى 1 مع كل صفحة جديدة
        past_first_element = False  # فاصل الصفحة في أول عنصر وهمي — نتجاهله فقط
        pending_heading = []  # عناوين قصيرة بانتظار الفقرة التالية

        # فتح الـ ZIP للوصول المباشر إلى الصور المضمَّنة (فقط عند الحاجة)
        zip_buffer = io.BytesIO(file_bytes)
        docx_zip = zipfile.ZipFile(zip_buffer) if (force_ocr and ocr_fn is not None) else None

        def append_block(text):
            nonlocal para_on_page
            if paginated:
                if not page_map or page_map[-1][1] != current_page:
                    page_map.append([len(blocks) + 1, current_page])
                    para_on_page = 1
                else:
                    para_on_page += 1
            else:
                para_on_page += 1
            para_map.append([len(blocks) + 1, current_page, para_on_page])
            blocks.append(text)

        def flush_pending():
            if pending_heading:
                append_block(" — ".join(pending_heading))
                pending_heading.clear()

        def _process_paragraph(para_elm):
            nonlocal current_page, past_first_element
            para = Paragraph(para_elm, document)
            text = para.text.strip()

            # lastRenderedPageBreak يظهر في بداية أول فقرة من الصفحة الجديدة،
            # لا في نهاية آخر فقرة من الصفحة القديمة. لكن أول عنصر في المستند
            # قد يحمله قبل أي محتوى — نكشفه ونتجاهله فقط في العنصر الأول.
            breaks = _count_page_breaks(para_elm)
            if breaks and past_first_element:
                current_page += breaks
            past_first_element = True

            # الصور المضمَّنة في هذه الفقرة — تُقرأ في موضعها الحقيقي
            image_texts = _ocr_inline_images(para_elm, document, docx_zip, ocr_fn) if docx_zip else []

            if text:
                if _is_heading(para, text):
                    pending_heading.append(text)
                else:
                    merged = " — ".join(pending_heading + [text]) if pending_heading else text
                    pending_heading.clear()
                    append_block(merged)
            elif image_texts:
                # فقرة بلا نص لكنها تحمل صورة — أفرغ العناوين المعلقة أولاً
                flush_pending()

            for img_text in image_texts:
                append_block(img_text)

        def _process_table(tbl_elm):
            nonlocal current_page
            table = Table(tbl_elm, document)

            # فحص فواصل الصفحات أولاً كما نفعل مع الفقرات
            breaks = _count_page_breaks(tbl_elm)
            if breaks:
                current_page += breaks

            flush_pending()
            for row in table.rows:
                row_text = _row_text(row)
                # تفحّص خلايا الجدول عن صور مضمَّنة أيضاً
                if docx_zip is not None:
                    for cell in row.cells:
                        for p_elm in cell._tc.findall(".//" + qn("w:p")):
                            for t in _ocr_inline_images(p_elm, document, docx_zip, ocr_fn):
                                row_text = (row_text + " | " + t) if row_text else t
                if row_text:
                    append_block(row_text)

        def _process_sdt(sdt_elm):
            """فك تغليف عناصر التحكم بالمحتوى (Content Controls)."""
            content = sdt_elm.find(qn("w:sdtContent"))
            if content is not None:
                for sub in content.iterchildren():
                    _process_element(sub)

        def _process_element(elm):
            if is_cancelled and is_cancelled():
                raise JobCancelled()
            if isinstance(elm, CT_P):
                _process_paragraph(elm)
            elif isinstance(elm, CT_Tbl):
                _process_table(elm)
            elif elm.tag == qn("w:sdt"):
                _process_sdt(elm)

        try:
            # المرور على جسم المستند بعناصره الحقيقية (وليس قائمتين منفصلتين)
            for child in document.element.body.iterchildren():
                _process_element(child)
        finally:
            if docx_zip is not None:
                docx_zip.close()
            zip_buffer.close()

        flush_pending()

        return "\n".join(blocks), page_map, para_map

    except JobCancelled:
        raise

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في محرك قراءة DOCX: {str(e)}")
