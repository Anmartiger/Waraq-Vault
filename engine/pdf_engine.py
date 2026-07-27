import fitz  # PyMuPDF
import numpy as np

from engine.jobs import JobCancelled
from engine.textflow import smart_join

# عتبة التمييز: صفحة نصّها أقل من هذا العدد من الحروف تُعتبر مصورة وتحتاج OCR
TEXT_LAYER_THRESHOLD = 20

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
                       progress=None, is_cancelled=None):
    """
    يستقبل ملف PDF كبايتات في الذاكرة ويعيد (النص، خريطة الصفحات).

    - لا يُحقَن أي فاصل وهمي في النص: أرقام الصفحات تعيش في خريطة منفصلة
      [[أول_سطر, رقم_الصفحة], ...] حتى يبقى فهرس البحث نظيفاً.
    - pages: معالجة صفحات بعينها فقط (اختيار المستخدم من نافذة التأكيد)،
      مع الحفاظ على أرقام الصفحات الحقيقية في الخريطة.
    - نصوص OCR تُدمَج دمجاً ذكياً (فقرات مترابطة) بدل التمزيق الأعمى.
    - progress(done, total, label): حدث تقدم حقيقي بعد كل صفحة.
    - is_cancelled(): تُفحص قبل كل صفحة — الإلغاء يوقف العمل عند أقرب نقطة آمنة.
    """
    lines = []
    page_map = []
    doc = None

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
                # تكبير الدقة (Matrix 2x2) لتوضيح الحروف لمحرك EasyOCR
                zoom = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=zoom)

                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                if pix.n == 4:
                    img_array = img_array[:, :, :3]

                # دمج ذكي: مربعات القراءة تتحول لفقرات متصلة قابلة للبحث
                page_text = smart_join(ocr_fn(img_array))

                # التدمير الإجباري للمتغيرات الضخمة لمنع اختناق الذاكرة
                del pix
                del img_array

            page_lines = [l for l in page_text.split("\n") if l.strip()]
            if page_lines:
                page_map.append([len(lines) + 1, real_page_no])
                lines.extend(page_lines)

            if progress:
                progress(done, total_selected, f"page {real_page_no} ({done}/{total_selected})")

        return "\n".join(lines), page_map

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
