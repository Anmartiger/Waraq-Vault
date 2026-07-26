import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

class JobCancelled(Exception):
    """يُرفَع داخل العامل عندما يلغي المستخدم المهمة."""

# منفّذ واحد للمعالجة الثقيلة: مهمة OCR واحدة في كل لحظة.
# قارئ EasyOCR ليس آمناً للخيوط المتوازية، والتسلسل يمنع استنزاف الذاكرة
# (كل قارئ إضافي يستهلك ~1GB). المهام تصطف في طابور وتُخدَم بالترتيب.
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="waraq-job")

_registry: dict = {}
_lock = threading.RLock()
_MAX_FINISHED_KEPT = 100   # نحتفظ بآخر المهام المنتهية فقط حتى لا تتضخم الذاكرة

def create_job(label: str, item_names: list) -> str:
    """تسجيل مهمة جديدة وإعادة معرّفها (لا تبدأ المعالجة هنا)."""
    job_id = uuid.uuid4().hex
    with _lock:
        _registry[job_id] = {
            "id": job_id,
            "label": label,
            "state": "queued",           # queued | processing | done | cancelled | error
            "items": [{"name": n, "status": "queued", "detail": ""} for n in item_names],
            "done_units": 0,
            "total_units": max(len(item_names), 1),
            "current": "",
            "cancel_requested": False,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
        }
    return job_id

def submit(job_id: str, fn) -> None:
    """إرسال دالة المعالجة إلى طابور التنفيذ."""
    _EXECUTOR.submit(_run, job_id, fn)

def _run(job_id: str, fn) -> None:
    with _lock:
        job = _registry.get(job_id)
        if job is None:
            return
        if job["cancel_requested"]:
            job["state"] = "cancelled"
            job["finished_at"] = time.time()
            return
        job["state"] = "processing"
        job["started_at"] = time.time()
    try:
        result = fn()
        with _lock:
            job["result"] = result
            job["state"] = "done"
            job["done_units"] = job["total_units"]
    except JobCancelled:
        with _lock:
            job["state"] = "cancelled"
    except Exception as e:
        # سجل الخادم فقط — لا تُسرَّب التفاصيل الداخلية للواجهة
        print(f"CRITICAL JOB ERROR [{job_id}]: {e}")
        with _lock:
            job["state"] = "error"
            job["error"] = "فشل الخادم في معالجة الملف. المحتوى تالف أو غير مقروء."
    finally:
        with _lock:
            job["finished_at"] = time.time()
            job["current"] = ""
        _cleanup()

def set_item(job_id: str, index: int, status: str, detail: str = "") -> None:
    """تحديث حالة عنصر واحد داخل المهمة (لعرض الحالة لكل صورة على حدة)."""
    with _lock:
        job = _registry.get(job_id)
        if job and 0 <= index < len(job["items"]):
            job["items"][index]["status"] = status
            job["items"][index]["detail"] = detail

def add_progress(job_id: str, done: int = None, total: int = None, current: str = None) -> None:
    """تحديث عدّادات التقدم — تُستدعى من أحداث إنجاز حقيقية (صفحة/صورة)، لا من مؤقّت."""
    with _lock:
        job = _registry.get(job_id)
        if not job:
            return
        if total is not None:
            job["total_units"] = max(total, 1)
        if done is not None:
            job["done_units"] = done
        if current is not None:
            job["current"] = current

def cancel(job_id: str) -> bool:
    """طلب إلغاء مهمة. المهام المصطفة تُلغى فوراً، والجارية تتوقف عند أقرب نقطة فحص."""
    with _lock:
        job = _registry.get(job_id)
        if not job or job["state"] in ("done", "error", "cancelled"):
            return False
        job["cancel_requested"] = True
        if job["state"] == "queued":
            job["state"] = "cancelled"
            job["finished_at"] = time.time()
        return True

def is_cancelled(job_id: str) -> bool:
    with _lock:
        job = _registry.get(job_id)
        return bool(job and job["cancel_requested"])

def get(job_id: str) -> dict:
    """لقطة آمنة من حالة المهمة لإرسالها للواجهة."""
    with _lock:
        job = _registry.get(job_id)
        if job is None:
            return None
        snapshot = {k: v for k, v in job.items() if k != "cancel_requested"}
        snapshot["items"] = [dict(i) for i in job["items"]]
        if job["state"] == "done":
            snapshot["percent"] = 100
        elif job["total_units"]:
            snapshot["percent"] = round(job["done_units"] / job["total_units"] * 100)
        else:
            snapshot["percent"] = None
        # ترتيب المهمة في الطابور (0 = تُعالَج الآن أو التالية مباشرة)
        queue_position = 0
        if job["state"] == "queued":
            queue_position = sum(
                1 for other in _registry.values()
                if other["state"] in ("queued", "processing")
                and other["created_at"] < job["created_at"]
            )
        snapshot["queue_position"] = queue_position
        return snapshot

def _cleanup() -> None:
    with _lock:
        finished = [j for j in _registry.values() if j["state"] in ("done", "error", "cancelled")]
        if len(finished) <= _MAX_FINISHED_KEPT:
            return
        finished.sort(key=lambda j: j["finished_at"] or 0)
        for victim in finished[:len(finished) - _MAX_FINISHED_KEPT]:
            _registry.pop(victim["id"], None)
