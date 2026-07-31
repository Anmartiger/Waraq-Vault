from fastapi import APIRouter, HTTPException

from engine import jobs

router = APIRouter()


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    """حالة مهمة معالجة: النسبة، العنصر الحالي، وحالة كل ملف في الدفعة."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="مهمة غير معروفة — ربما أُعيد تشغيل الخادم.")
    return job


@router.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: str):
    """إلغاء مهمة جارية أو مصطفة. الجارية تتوقف عند أقرب نقطة فحص (بين الصفحات/الصور)."""
    if jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="مهمة غير معروفة.")
    return {"cancelled": jobs.cancel(job_id)}
