import easyocr

# تحذير: نقوم بتعريف القارئ هنا خارج الدوال لكي يتم تحميله في الذاكرة "مرة واحدة" فقط عند بدء التشغيل
# إذا وضعه داخل الدالة، سينهار الخادم لأنه سيحمل النماذج مع كل ملف جديد يتم رفعه!
print("⏳ جاري تحميل نماذج EasyOCR في الذاكرة... قد يستغرق هذا بعض الوقت في المرة الأولى.")
reader = easyocr.Reader(['ar', 'en'], gpu=False) # استخدمنا False بافتراض عدم وجود GPU معدّ

def extract_text_from_image(image_path: str) -> str:
    """يستقبل مسار الصورة ويعيد النص المستخرج منها"""
    try:
        # detail=0 تعيد النصوص فقط كقائمة بدون إحداثيات المربعات
        results = reader.readtext(image_path, detail=0) 
        return " \n ".join(results)
    except Exception as e:
        return f"An error occurred during extraction: {str(e)}"