import fitz  # PyMuPDF
import numpy as np

def process_hybrid_pdf(pdf_bytes: bytes, ocr_reader) -> str:
    """
    يستقبل ملف PDF كبايتات في الذاكرة ويقوم باستخراج النص.
    يستخدم المنطق الهجين: إذا كانت الصفحة مصورة، يتم تحويلها للذكاء الاصطناعي.
    """
    extracted_text = []
    doc = None
    
    try:
        # 1. القراءة في الذاكرة العشوائية: لا مساس بالقرص الصلب
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 2. المحاولة السريعة: استخراج النص الأصلي
            page_text = page.get_text("text").strip()
            
            # 3. عتبة التمييز (Threshold): إذا كان النص أقل من 20 حرفاً، نعتبرها صورة
            if len(page_text) < 20:
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
                ocr_result = ocr_reader.readtext(img_array, detail=0)
                page_text = " ".join(ocr_result)
                
                # 4. التدمير الإجباري للمتغيرات الضخمة لمنع اختناق الذاكرة
                del pix
                del img_array
                
            extracted_text.append(f"--- صفحة {page_num + 1} ---\n{page_text}")
            
        return "\n\n".join(extracted_text)
        
    except Exception as e:
        # تغليف الخطأ لكي يلتقطه الـ main.py بسلاسة
        raise Exception(f"انهيار في المحرك الهجين للـ PDF: {str(e)}")
        
    finally:
        # 5. التنظيف الإجباري: إغلاق الملف وتحرير الموارد حتى لو حدث خطأ
        if doc:
            doc.close()