import easyocr
import logging
import os
import platform
import shutil
import subprocess
import threading

# إعداد نظام تسجيل احترافي
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# على المعالج: نترك نواة حرة للخادم حتى لا تتجمد الواجهة أثناء الـ OCR
_CPU_THREADS = max(1, (os.cpu_count() or 2) - 1)

def _probe_nvidia() -> dict:
    """
    كشف وجود بطاقة NVIDIA فعلية عبر nvidia-smi — يعمل على ويندوز ولينكس معاً.

    مهم: هذا مستقل تماماً عن PyTorch. وجود البطاقة لا يعني أن torch يستطيع
    استخدامها (نسخة torch قد تكون CPU-only)، والتفريق بين الحالتين هو ما يسمح
    لنا بإخبار المستخدم بالسبب الحقيقي بدل الوقوع بصمت على المعالج.
    """
    binary = shutil.which("nvidia-smi")
    if not binary and platform.system() == "Windows":
        candidate = r"C:\Windows\System32\nvidia-smi.exe"
        binary = candidate if os.path.exists(candidate) else None
    if not binary:
        return {"present": False, "name": None, "memory": None, "driver": None}
    try:
        result = subprocess.run(
            [binary, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=8,
        )
        line = (result.stdout or "").strip().splitlines()
        if result.returncode == 0 and line:
            parts = [p.strip() for p in line[0].split(",")]
            return {
                "present": True,
                "name": parts[0] if parts else None,
                "memory": parts[1] if len(parts) > 1 else None,
                "driver": parts[2] if len(parts) > 2 else None,
            }
    except Exception as e:
        logger.warning(f"⚠️ nvidia-smi probe failed: {e}")
    return {"present": False, "name": None, "memory": None, "driver": None}

def _torch_info() -> dict:
    """حالة PyTorch: هل بُني أصلاً مع CUDA، وهل يرى البطاقة الآن."""
    try:
        import torch
        return {
            "version": torch.__version__,
            "built_with_cuda": torch.version.cuda,       # None يعني نسخة CPU فقط
            "cuda_available": bool(torch.cuda.is_available()),
            "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except Exception as e:
        logger.warning(f"⚠️ torch probe failed: {e}")
        return {"version": None, "built_with_cuda": None, "cuda_available": False, "device_name": None}

def _cuda_install_hint() -> str:
    """أمر التثبيت الصحيح لتفعيل CUDA — يختلف بين ويندوز ولينكس."""
    if platform.system() == "Windows":
        return ("pip install --force-reinstall torch torchvision "
                "--index-url https://download.pytorch.org/whl/cu130")
    return ("pip install --force-reinstall torch torchvision "
            "--index-url https://download.pytorch.org/whl/cu130   "
            "(على لينكس غالباً تكفي نسخة PyPI الافتراضية لأنها تتضمن CUDA)")

NVIDIA = _probe_nvidia()
TORCH = _torch_info()

def _gpu_reason() -> str:
    """سبب عدم استخدام البطاقة، بصيغة صالحة للعرض مباشرة في الواجهة."""
    if TORCH["cuda_available"]:
        return ""
    if not NVIDIA["present"]:
        return "لا توجد بطاقة NVIDIA على هذا الجهاز — المعالجة على المعالج المركزي."
    if not TORCH["built_with_cuda"]:
        return (f"تم العثور على {NVIDIA['name']} لكن النسخة المثبّتة من PyTorch "
                f"({TORCH['version']}) بلا دعم CUDA. أعد تثبيتها لتفعيل البطاقة.")
    return (f"تم العثور على {NVIDIA['name']} وPyTorch يدعم CUDA {TORCH['built_with_cuda']}، "
            f"لكن البطاقة غير متاحة الآن (تعريف قديم أو بطاقة مشغولة).")

GPU_AVAILABLE = TORCH["cuda_available"]
GPU_NAME = TORCH["device_name"] or NVIDIA["name"]
GPU_REASON = _gpu_reason()

# auto = استخدم البطاقة إن توفّرت، وإلا المعالج. gpu/cpu = اختيار صريح من المستخدم.
DEVICE_MODE = "auto"

_reader_lock = threading.Lock()

def _apply_cpu_threads():
    try:
        import torch
        torch.set_num_threads(_CPU_THREADS)
    except Exception:
        pass

def _make_reader(use_gpu: bool):
    return easyocr.Reader(['ar', 'en'], gpu=use_gpu, verbose=False)

def _device_label(on_gpu: bool) -> str:
    if on_gpu:
        return f"GPU ({GPU_NAME})" if GPU_NAME else "GPU"
    return f"CPU ({_CPU_THREADS} threads)"

reader = None
ACTIVE_GPU = GPU_AVAILABLE
OCR_DEVICE = _device_label(ACTIVE_GPU)

def _ensure_reader():
    """
    يبني قارئ EasyOCR عند أول استخدام فعلي فقط، بدل وقت استيراد الوحدة.
    كان البناء يجري مباشرة عند الاستيراد فيحجب إقلاع uvicorn بالكامل ريثما
    يكتمل تحميل/تنزيل النماذج (قد يستغرق دقائق على جهاز جديد) — ما يتجاوز
    مهلة استعداد غلاف Tauri لسطح المكتب فيظهر خطأ "تعذّر تشغيل الخادم" رغم
    أن الخادم كان لا يزال يُقلع فعلياً. التأجيل هنا يجعل /status يستجيب فوراً.
    """
    global reader, ACTIVE_GPU, OCR_DEVICE, GPU_AVAILABLE, GPU_REASON
    if reader is not None:
        return
    with _reader_lock:
        if reader is not None:
            return
        logger.info("⏳ جاري تحميل نماذج EasyOCR في الذاكرة...")
        if NVIDIA["present"]:
            logger.info(f"🖥️ NVIDIA detected: {NVIDIA['name']} ({NVIDIA['memory']}, driver {NVIDIA['driver']})")
        if not GPU_AVAILABLE:
            _apply_cpu_threads()
            if GPU_REASON:
                logger.warning(f"⚠️ {GPU_REASON}")
                if NVIDIA["present"] and not TORCH["built_with_cuda"]:
                    logger.warning(f"👉 {_cuda_install_hint()}")

        try:
            built = _make_reader(GPU_AVAILABLE)
            active_gpu = GPU_AVAILABLE
        except Exception as e:
            if GPU_AVAILABLE:
                # بطاقة موجودة لكن التهيئة فشلت (تعريفات ناقصة، ذاكرة ممتلئة...) → CPU بدون انهيار
                logger.error(f"❌ GPU init failed, retrying on CPU: {e}")
                GPU_AVAILABLE = False
                GPU_REASON = f"فشلت تهيئة البطاقة: {e}"
                _apply_cpu_threads()
                built = _make_reader(False)
                active_gpu = False
            else:
                raise

        reader = built
        ACTIVE_GPU = active_gpu
        OCR_DEVICE = _device_label(active_gpu)
        logger.info(f"✅ OCR engine ready on {OCR_DEVICE}")

def device_status() -> dict:
    """كل ما تحتاجه الواجهة لعرض حالة العتاد والسماح باختياره."""
    return {
        "mode": DEVICE_MODE,                 # auto | gpu | cpu
        "active": "gpu" if ACTIVE_GPU else "cpu",
        "device": OCR_DEVICE,
        "gpu_usable": bool(GPU_AVAILABLE),   # هل يستطيع torch استخدامها فعلاً
        "gpu_present": bool(NVIDIA["present"]),
        "gpu_name": GPU_NAME,
        "gpu_memory": NVIDIA["memory"],
        "driver": NVIDIA["driver"],
        "torch_version": TORCH["version"],
        "torch_cuda": TORCH["built_with_cuda"],
        "reason": GPU_REASON,
        "install_hint": (_cuda_install_hint()
                         if NVIDIA["present"] and not TORCH["built_with_cuda"] else ""),
        "cpu_threads": _CPU_THREADS,
    }

def set_device(mode: str) -> dict:
    """
    تبديل عتاد المعالجة أثناء التشغيل. إعادة بناء القارئ تستغرق ثوانٍ،
    لذا تُستدعى من خيط منفصل، ويحميها قفل حتى لا تتصادم مع مهمة جارية.
    """
    global reader, DEVICE_MODE, ACTIVE_GPU, OCR_DEVICE

    mode = (mode or "auto").lower()
    if mode not in ("auto", "gpu", "cpu"):
        raise ValueError("الوضع المسموح: auto أو gpu أو cpu")

    # يضمن بناء القارئ أولاً حتى يعكس GPU_AVAILABLE نتيجة تهيئة فعلية مؤكدة
    # لا مجرد فحص مبدئي (torch.cuda.is_available() قد يعد بالبطاقة ثم تفشل
    # التهيئة الفعلية لاحقاً).
    _ensure_reader()

    if mode == "gpu" and not GPU_AVAILABLE:
        raise ValueError(GPU_REASON or "البطاقة غير متاحة على هذا الجهاز.")

    want_gpu = (mode == "gpu") or (mode == "auto" and GPU_AVAILABLE)
    with _reader_lock:
        if want_gpu != ACTIVE_GPU:
            if not want_gpu:
                _apply_cpu_threads()
            reader = _make_reader(want_gpu)
            ACTIVE_GPU = want_gpu
            OCR_DEVICE = _device_label(want_gpu)
            logger.info(f"🔀 OCR device switched to {OCR_DEVICE}")
        DEVICE_MODE = mode
    return device_status()

def _is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "cuda" in msg and ("out of memory" in msg or "memory" in msg)

def _read(image, detail: int):
    """
    نداء المحرك الفعلي مع صمام أمان الذاكرة: إذا امتلأت ذاكرة البطاقة أثناء العمل،
    ننتقل نهائياً إلى المعالج في نفس الجلسة ونعيد محاولة الصورة نفسها —
    لا انهيار ولا فقدان بيانات.
    """
    global reader, ACTIVE_GPU, OCR_DEVICE
    _ensure_reader()
    with _reader_lock:
        current = reader
    try:
        return current.readtext(image, detail=detail)
    except Exception as e:
        if ACTIVE_GPU and _is_cuda_oom(e):
            logger.error(f"❌ CUDA out of memory — switching to CPU for this session: {e}")
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            _apply_cpu_threads()
            with _reader_lock:
                reader = _make_reader(False)
                ACTIVE_GPU = False
                OCR_DEVICE = f"CPU ({_CPU_THREADS} threads, GPU OOM fallback)"
                current = reader
            return current.readtext(image, detail=detail)
        raise

def run_ocr(image) -> list:
    """
    تشغيل OCR على صورة (مسار ملف، بايتات، أو مصفوفة numpy) وإعادة قائمة النصوص.
    العقد الأصلي محفوظ كما هو: قائمة سلاسل نصية.
    """
    return _read(image, detail=0)

def run_ocr_boxes(image) -> list:
    """
    نفس المحرك لكن مع الإحداثيات: [(bbox, text, confidence), ...].

    الإحداثيات هي المعلومة التي كنا نرميها سابقاً (detail=0)، وهي التي تسمح
    بتجميع الأسطر والفقرات هندسياً بدل تخمينها من علامات الترقيم.
    ملاحظة: لا نُعيد ترتيب الصناديق هنا إطلاقاً — ترتيب المحرك يبقى كما هو
    حفاظاً على سلوك العربية (RTL) الموثّق في /status.
    """
    return _read(image, detail=1)

def extract_text_from_image(image_source) -> str:
    """يستقبل مسار الصورة أو بايتاتها ويعيد النص المستخرج أو ينهار بخطأ واضح"""
    from engine.textflow import smart_join
    try:
        # دمج ذكي: مربعات القراءة تتحول لفقرات مترابطة بدل التمزيق الأعمى
        return smart_join(run_ocr(image_source))
    except Exception as e:
        logger.error(f"OCR Engine Crash: {str(e)}")
        # نرفع الخطأ ولا نخفيه كنص عادي!
        raise ValueError(f"فشل محرك الذكاء الاصطناعي في قراءة الصورة: {str(e)}")
