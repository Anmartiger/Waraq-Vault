import easyocr
import logging

# إعداد نظام تسجيل احترافي
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("⏳ جاري تحميل نماذج EasyOCR في الذاكرة...")
# وضع التحميل العام هنا قرار ذكي جداً للهاكاثون لتجنب خنق الذاكرة (Memory Leak).
reader = easyocr.Reader(['ar', 'en'], gpu=False) 

def extract_text_from_image(image_path: str) -> str:
    """يستقبل مسار الصورة ويعيد النص المستخرج منها أو ينهار بخطأ واضح"""
    try:
        results = reader.readtext(image_path, detail=0) 
        return " \n ".join(results)
    except Exception as e:
        logger.error(f"OCR Engine Crash: {str(e)}")
        # نرفع الخطأ ولا نخفيه كنص عادي!
        raise ValueError(f"فشل محرك الذكاء الاصطناعي في قراءة الصورة: {str(e)}")