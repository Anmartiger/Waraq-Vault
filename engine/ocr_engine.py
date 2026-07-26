import easyocr
import logging
import os

# إعداد نظام تسجيل احترافي
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _detect_gpu():
    """
    فحص العتاد مرة واحدة عند الإقلاع (يُخزَّن القرار في متغيرات الوحدة).
    أي فشل في الفحص يعني CPU — الفحص نفسه لا يُسقط التطبيق أبداً.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return True, torch.cuda.get_device_name(0)
    except Exception as e:
        logger.warning(f"⚠️ GPU probe failed, falling back to CPU: {e}")
    return False, None

GPU_AVAILABLE, GPU_NAME = _detect_gpu()

# على المعالج: نترك نواة حرة للخادم حتى لا تتجمد الواجهة أثناء الـ OCR
_CPU_THREADS = max(1, (os.cpu_count() or 2) - 1)
if not GPU_AVAILABLE:
    try:
        import torch
        torch.set_num_threads(_CPU_THREADS)
    except Exception:
        pass

def _make_reader(use_gpu: bool):
    return easyocr.Reader(['ar', 'en'], gpu=use_gpu, verbose=False)

logger.info("⏳ جاري تحميل نماذج EasyOCR في الذاكرة...")
# وضع التحميل العام هنا قرار ذكي جداً للهاكاثون لتجنب خنق الذاكرة (Memory Leak).
try:
    reader = _make_reader(GPU_AVAILABLE)
except Exception as e:
    if GPU_AVAILABLE:
        # بطاقة موجودة لكن التهيئة فشلت (تعريفات ناقصة، ذاكرة ممتلئة...) → CPU بدون انهيار
        logger.error(f"❌ GPU init failed, retrying on CPU: {e}")
        GPU_AVAILABLE, GPU_NAME = False, None
        reader = _make_reader(False)
    else:
        raise

OCR_DEVICE = f"GPU ({GPU_NAME})" if GPU_AVAILABLE else f"CPU ({_CPU_THREADS} threads)"
logger.info(f"✅ OCR engine ready on {OCR_DEVICE}")

def _is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "cuda" in msg and ("out of memory" in msg or "memory" in msg)

def run_ocr(image) -> list:
    """
    تشغيل OCR على صورة (مسار ملف، بايتات، أو مصفوفة numpy) وإعادة قائمة النصوص.
    إذا امتلأت ذاكرة البطاقة أثناء العمل، ننتقل نهائياً إلى المعالج في نفس الجلسة
    ونعيد محاولة الصورة نفسها — لا انهيار ولا فقدان بيانات.
    """
    global reader, GPU_AVAILABLE, OCR_DEVICE
    try:
        return reader.readtext(image, detail=0)
    except Exception as e:
        if GPU_AVAILABLE and _is_cuda_oom(e):
            logger.error(f"❌ CUDA out of memory — switching to CPU for this session: {e}")
            GPU_AVAILABLE = False
            OCR_DEVICE = f"CPU ({_CPU_THREADS} threads, GPU OOM fallback)"
            try:
                import torch
                torch.cuda.empty_cache()
                torch.set_num_threads(_CPU_THREADS)
            except Exception:
                pass
            reader = _make_reader(False)
            return reader.readtext(image, detail=0)
        raise

def extract_text_from_image(image_source) -> str:
    """يستقبل مسار الصورة أو بايتاتها ويعيد النص المستخرج أو ينهار بخطأ واضح"""
    try:
        results = run_ocr(image_source)
        return " \n ".join(results)
    except Exception as e:
        logger.error(f"OCR Engine Crash: {str(e)}")
        # نرفع الخطأ ولا نخفيه كنص عادي!
        raise ValueError(f"فشل محرك الذكاء الاصطناعي في قراءة الصورة: {str(e)}")
