import fitz  # PyMuPDF
import numpy as np

from engine.jobs import JobCancelled
from engine.textflow import join_ocr, smart_join

def page_paragraphs(page) -> list:
    """
    استخراج الفقرات الحقيقية من طبقة النص باستخدام تحليل التخطيط في PyMuPDF.

    get_text("text") يعيد حساءً من الأسطر بلا بنية، بينما get_text("dict") يعطي
    كتلاً (blocks) وأسطراً ومقاطع مع إحداثياتها — والكتلة هنا هي الفقرة فعلياً.
    هذا يلغي التخمين: لا نحتاج إلى استنتاج أين تنتهي الفقرة.
    """
    paragraphs = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:      # 0 = نص، غير ذلك صور
            continue
        line_texts = []
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text:
                line_texts.append(text)
        if line_texts:
            # أسطر الكتلة الواحدة تُدمج في فقرة واحدة قابلة للبحث
            paragraphs.append(" ".join(line_texts))
    return paragraphs

# عتبة التمييز: صفحة نصّها أقل من هذا العدد من الحروف تُعتبر مصورة وتحتاج OCR
TEXT_LAYER_THRESHOLD = 20

# حدّ أمان المعالج: أقصى عدد صفحات تُرسَل إلى محرك OCR داخل استدعاء واحد.
# يُرفع ValueError عند تجاوزه إلا إذا مرّر المستخدم تأكيداً صريحاً (confirmed=True)
# أو حدّد صفحات بعينها — وفي الحالتين يُمرَّر None لإلغاء القيد.
# بلا حد لعدد الصفحات: حماية المعالج تتم بموافقة صريحة من المستخدم (نافذة التأكيد
# مع تقدير الوقت وإمكانية اختيار الصفحات) وبطابور خلفي يمكن إلغاؤه في أي لحظة،
# لا برفض الملفات الكبيرة. يبقى المعامل متاحاً لمن أراد فرض سقف صراحةً.
_MAX_OCR_PAGES = None

def pdf_precheck(pdf_bytes: bytes) -> dict:
    """
    فحص سريع بلا أي OCR: كم صفحة في الملف، وأيها مصوَّر (بلا طبقة نصية).
    يُستخدم قبل قبول الرفع لعرض نافذة التأكيد وتقدير الوقت للمستخدم.
    """
    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        scanned = []
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text").strip()
            if len(text) < TEXT_LAYER_THRESHOLD:
                scanned.append(page_num + 1)
        return {"total_pages": len(doc), "scanned_pages": scanned}
    finally:
        if doc:
            doc.close()

def parse_page_selection(spec: str, total_pages: int) -> list:
    """
    تحويل نص اختيار الصفحات ("1-5,8,12") إلى قائمة أرقام صفحات صحيحة ومرتّبة.
    يرفع ValueError برسالة واضحة عند أي صيغة غير سليمة أو رقم خارج النطاق.
    """
    pages = set()
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, _, end_s = part.partition("-")
            start, end = int(start_s.strip()), int(end_s.strip())
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    if not pages:
        raise ValueError("لم يتم تحديد أي صفحة.")
    bad = [p for p in pages if p < 1 or p > total_pages]
    if bad:
        raise ValueError(f"صفحات خارج نطاق الملف ({total_pages} صفحة): {sorted(bad)}")
    return sorted(pages)

def process_hybrid_pdf(pdf_bytes: bytes, ocr_fn, force_ocr: bool = False, pages: list = None,
                       progress=None, is_cancelled=None, max_ocr_pages: int | None = _MAX_OCR_PAGES):
    """
    يستقبل ملف PDF كبايتات في الذاكرة ويعيد (النص، خريطة الصفحات).

    - لا يُحطة منفصلة
      [[أول_سطر, رقم_الصفحة], ...] حتى يبقى فهرس البحث نظيفاً.
    - pages: معالجة صفحات بعينها فقط (اختيار المستخدم من نافذة التأكيد)،
      مع الحفاظ على أرقام الصفحات الحقيقية في الخريطة.
    - نصوص OCR تُدمَج دمجاً ذكياً (فقرات مترابطة) بدل التمزيق الأعمى.
    - progress(done, total, label): حدث تقدم حقيقي بعد كل صفحة.
    - is_cancelled(): تُفحص قبل كل صفحة — الإلغاء يوقف العمل عند أقرب نقطة آمنة.
    - max_ocr_pages: أقصى عدد صفحات تُعالَج بـ OCR (None = بلا حد). التجاوز يرفع
      ValueError فوراً لحماية الخادم من استنزاف الموارد.
    """
    lines = []
    page_map = []
    para_map = []
    doc = None
    ocr_pages_done = 0
    native_pages_done = 0

    try:
        # 1. القراءة في الذاكرة العشوائية: لا مساس بالقرص الصلب
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        selected = pages if pages else list(range(1, total_pages + 1))
        total_selected = len(selected)
        if progress:
            progress(0, total_selected, f"فتح الملف — {total_selected} صفحة للمعالجة")

        for done, real_page_no in enumerate(selected, start=1):
            # نقطة فحص الإلغاء: بين الصفحات، حيث لا توجد موارد معلّقة
            if is_cancelled and is_cancelled():
                raise JobCancelled()

            page = doc[real_page_no - 1]

            # 2. المحاولة السريعة: استخراج النص الأصلي
            page_text = page.get_text("text").strip()

            # 3. عتبة التمييز — و force_ocr يتجاوزها لمعالجة الملفات الهجينة
            if force_ocr or len(page_text) < TEXT_LAYER_THRESHOLD:
                # فحص حد الصفحات المصورة — صمام أمان المعالج قبل أي عمل ثقيل
                if max_ocr_pages is not None and ocr_pages_done >= max_ocr_pages:
                    raise ValueError(
                        f"Maximum allowed OCR pages ({max_ocr_pages}) exceeded. "
                        f"Please split the file."
                    )

                # تكبير الدقة (Matrix 2x2) لتوضيح الحروف لمحرك EasyOCR
                zoom = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=zoom)

                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img_array = img_array[:, :, :3]

                # تجميع هندسي: إحداثيات الصناديق تبني الأسطر والفقرات بدقة
                page_lines = [l for l in join_ocr(ocr_fn(img_array)).split("\n") if l.strip()]
                ocr_pages_done += 1

                # التدمير الإجباري للمتغيرات الضخمة لمنع اختناق الذاكرة
                del pix
                del img_array
            else:
                # طبقة نصية موجودة: نأخذ الفقرات من تحليل التخطيط مباشرة
                page_lines = page_paragraphs(page)
                if page_lines:
                    native_pages_done += 1
            if page_lines:
                # دمج الأسطر المتجاورة في فقرات حقيقية — الفقرة وحدها تحصل على رقم،
                # وليس كل سطر بمفرده. هذا يمنع التمزيق (para 2, para 5, para 8...).
                # ترقيم الفقرات يبقى سليماً لكل صفحة (نصية أو OCR) — الملفات
                # الهجينة لا تتأثر إطلاقاً؛ إخفاء المؤشر للمستندات المصوَّرة بالكامل
                # قرار على مستوى المستند كله (is_pure_ocr أدناه)، لا لكل صفحة.
                merged = smart_join(page_lines)
                paragraphs = [p for p in merged.split("\n") if p.strip()]
                page_map.append([len(lines) + 1, real_page_no])
                for idx, block_text in enumerate(paragraphs, start=1):
                    para_map.append([len(lines) + idx, real_page_no, idx])
                lines.extend(paragraphs)

            if progress:
                progress(done, total_selected, f"page {real_page_no} ({done}/{total_selected})")

        # وثيقة "OCR بحت": كل صفحة فيها جاءت من التصوير الضوئي، بلا طبقة نص
        # حقيقية إطلاقاً — عندها فقط تُخفى أرقام الفقرات في الواجهة، لأنها لا
        # تعكس أي حدود فقرة حقيقية. أي صفحة نصية واحدة تكفي لإبقاء المستند
        # "هجيناً" وترقيمه سليماً بالكامل، بما فيه صفحاته المصوَّرة.
        is_pure_ocr = ocr_pages_done > 0 and native_pages_done == 0
        return "\n".join(lines), page_map, para_map, is_pure_ocr

    except JobCancelled:
        # الإلغاء ليس خطأ — يُمرَّر كما هو ليتعامل معه نظام المهام
        raise

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في المحرك الهجين للـ PDF: {str(e)}")

    finally:
        # التنظيف الإجباري: إغلاق الملف وتحرير الموارد حتى لو حدث خطأ
        if doc:
            doc.close()
