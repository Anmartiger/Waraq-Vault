from docx import Document
from docx.document import Document as _Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
import io
import os
import zipfile

from engine.jobs import JobCancelled
from engine.textflow import smart_join

# العناوين وشبه الفقرات: أقل من هذا العدد من الكلمات لا يُحتسب فقرة مستقلة
_MIN_BLOCK_WORDS = 3

# صيغ الصور النقطية داخل word/media القابلة للقراءة بمحرك OCR
_MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")

def _blocks_from(child, parent):
    """تحويل عنصر XML إلى فقرة أو جدول، مع فك أغلفة عناصر التحكم بالمحتوى."""
    if isinstance(child, CT_P):
        yield Paragraph(child, parent)
    elif isinstance(child, CT_Tbl):
        yield Table(child, parent)
    elif child.tag == qn("w:sdt"):
        # عناصر التحكم بالمحتوى (Content Controls) تغلّف فقرات وجداول حقيقية،
        # وتجاهلها يعني ضياع نصها وفواصل صفحاتها من الفهرسة
        content = child.find(qn("w:sdtContent"))
        if content is not None:
            for sub in content.iterchildren():
                yield from _blocks_from(sub, parent)

def _iter_blocks(parent):
    """
    المرور على الفقرات والجداول بترتيب ظهورها الفعلي داخل المستند،
    لأن python-docx يعيدها في قائمتين منفصلتين ويضيع الترتيب الأصلي.
    """
    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise ValueError("عنصر غير مدعوم للمرور عليه")

    for child in parent_elm.iterchildren():
        yield from _blocks_from(child, parent)

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

def _extract_media_ocr(file_bytes: bytes, ocr_fn, progress=None, is_cancelled=None) -> list:
    """
    استخراج الصور النقطية المدمجة من word/media وقراءتها بمحرك OCR.
    صورة تالفة واحدة لا تُسقط المستند كاملاً — تُتجاهل ويستمر الباقي.
    """
    blocks = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        media = sorted(
            n for n in archive.namelist()
            if n.startswith("word/media/") and os.path.splitext(n)[1].lower() in _MEDIA_EXTS
        )
        for index, name in enumerate(media, start=1):
            if is_cancelled and is_cancelled():
                raise JobCancelled()
            if progress:
                progress(index, len(media), f"embedded image {index}/{len(media)}")
            try:
                text = smart_join(ocr_fn(archive.read(name)))
                if text:
                    blocks.extend(l for l in text.split("\n") if l.strip())
            except JobCancelled:
                raise
            except Exception:
                # صورة مشوهة أو صيغة لا يفهمها المحرك — نتجاوزها بصمت مدروس
                continue
    return blocks

def process_docx(file_bytes: bytes, force_ocr: bool = False, ocr_fn=None,
                 progress=None, is_cancelled=None):
    """
    يستقبل ملف DOCX كبايتات في الذاكرة ويعيد (النص النظيف، خريطة الصفحات).

    قواعد النظافة (لا قمامة في فهرس البحث):
    - لا فواصل صفحات وهمية داخل النص — الترقيم يعيش في خريطة منفصلة.
    - الأسطر الفارغة تُتجاهل ولا ترفع عدّاد الفقرات.
    - العناوين القصيرة (أقل من 3 كلمات) تُدمَج مع الفقرة التالية ككتلة واحدة
      ذات معنى، فلا ترى الواجهة قفزات عشوائية في أرقام الفقرات.
    - force_ocr مع ocr_fn: تُقرأ الصور المدمجة (word/media) وتُلحق نصوصها.
    """
    try:
        document = Document(io.BytesIO(file_bytes))

        # إذا لم يحمل المستند أي إشارة ترقيم نكتفي بأرقام الفقرات بدل تخمين الصفحات
        paginated = _count_page_breaks(document.element.body) > 0

        blocks = []           # كل عنصر = سطر واحد في النص النهائي
        page_map = []         # [[أول_سطر, رقم_الصفحة], ...]
        current_page = 1
        pending_heading = []  # عناوين قصيرة بانتظار الفقرة التالية

        def append_block(text):
            if paginated and (not page_map or page_map[-1][1] != current_page):
                page_map.append([len(blocks) + 1, current_page])
            blocks.append(text)

        def flush_pending():
            if pending_heading:
                append_block(" — ".join(pending_heading))
                pending_heading.clear()

        for block in _iter_blocks(document):
            if isinstance(block, Paragraph):
                text = block.text.strip()
                if text:
                    if len(text.split()) < _MIN_BLOCK_WORDS:
                        # عنوان قصير: يُدمج مع الكتلة التالية بدل فقرة مستقلة
                        pending_heading.append(text)
                    else:
                        merged = " — ".join(pending_heading + [text]) if pending_heading else text
                        pending_heading.clear()
                        append_block(merged)
                breaks = _count_page_breaks(block._p)
            else:
                # الجداول: كل صف كتلة مستقلة (بياناتها الرسمية تعيش في صفوف)
                flush_pending()
                for row in block.rows:
                    row_text = _row_text(row)
                    if row_text:
                        append_block(row_text)
                breaks = _count_page_breaks(block._tbl)

            if breaks:
                current_page += breaks

        flush_pending()

        # قراءة الصور المدمجة عند طلب المستخدم صراحة (Force OCR)
        if force_ocr and ocr_fn is not None:
            media_blocks = _extract_media_ocr(file_bytes, ocr_fn, progress, is_cancelled)
            if media_blocks:
                if page_map:
                    # ما بعد هذا السطر ليس له صفحة معروفة — نوقف نسب الصفحات
                    page_map.append([len(blocks) + 1, None])
                blocks.extend(media_blocks)

        return "\n".join(blocks), page_map

    except JobCancelled:
        raise

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في محرك قراءة DOCX: {str(e)}")
