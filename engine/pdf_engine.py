import fitz  # PyMuPDF
import numpy as np

from engine.jobs import JobCancelled

def process_hybrid_pdf(pdf_bytes: bytes, ocr_fn, force_ocr: bool = False,
                       progress=None, is_cancelled=None) -> str:
    """
    يستقبل ملف PDF كبايتات في الذاكرة ويقوم باستخراج النص.
    يستخدم المنطق الهجين: إذا كانت الصفحة مصورة، يتم تحويلها للذكاء الاصطناعي.

    - ocr_fn: دالة OCR (تستقبل مصفوفة numpy وتعيد قائمة نصوص) — تختار العتاد بنفسها.
    - force_ocr: معالجة كل الصفحات كصور حتى لو احتوت طبقة نصية (لملفات الـ PDF الهجينة).
    - progress(done, total, label): حدث تقدم حقيقي بعد كل صفحة (لا يعتمد على مؤقت).
    - is_cancelled(): تُفحص قبل كل صفحة — الإلغاء يوقف العمل عند أقرب نقطة آمنة.

    لا يوجد سقف لعدد الصفحات: المعالجة تجري في طابور خلفي متسلسل مع تقدم مرئي
    وإمكانية إلغاء، وهذا هو تقييد الموارد الفعلي بدل رفض الملفات الكبيرة.
    """
    extracted_text = []
    doc = None

    try:
        # 1. القراءة في الذاكرة العشوائية: لا مساس بالقرص الصلب
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_pages = len(doc)
        if progress:
            progress(0, total_pages, f"فتح الملف — {total_pages} صفحة")

        for page_num in range(total_pages):
            # نقطة فحص الإلغاء: بين الصفحات، حيث لا توجد موارد معلّقة
            if is_cancelled and is_cancelled():
                raise JobCancelled()

            page = doc[page_num]

            # 2. المحاولة السريعة: استخراج النص الأصلي
            page_text = page.get_text("text").strip()

            # 3. عتبة التمييز (Threshold): إذا كان النص أقل من 20 حرفاً، نعتبرها صورة.
            #    force_ocr يتجاوز العتبة لمعالجة الملفات الهجينة (نص + صور مدمجة).
            if force_ocr or len(page_text) < 20:
                # تكبير الدقة (Matrix 2x2) لتوضيح الحروف لمحرك EasyOCR
                zoom = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=zoom)

                # تحويل الصورة إلى مصفوفة أرقام (Numpy Array) ليفهمها محرك الذكاء الاصطناعي
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

                # إزالة قناة الشفافية (Alpha) إذا كانت موجودة لأن EasyOCR يفضل RGB
                if pix.n == 4:
                    img_array = img_array[:, :, :3]

                # استدعاء محرك الذكاء الاصطناعي
                # detail=0 ترجع النصوص فقط كقائمة بدون الإحداثيات المزعجة
                ocr_result = ocr_fn(img_array)
                page_text = " ".join(ocr_result)

                # 4. التدمير الإجباري للمتغيرات الضخمة لمنع اختناق الذاكرة
                del pix
                del img_array

            extracted_text.append(f"--- صفحة {page_num + 1} ---\n{page_text}")

            # حدث تقدم حقيقي: صفحة اكتملت فعلاً
            if progress:
                progress(page_num + 1, total_pages, f"page {page_num + 1}/{total_pages}")

        return "\n\n".join(extracted_text)

    except JobCancelled:
        # الإلغاء ليس خطأ — يُمرَّر كما هو ليتعامل معه نظام المهام
        raise

    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في المحرك الهجين للـ PDF: {str(e)}")

    finally:
        # 5. التنظيف الإجباري: إغلاق الملف وتحرير الموارد حتى لو حدث خطأ
        if doc:
            doc.close()
