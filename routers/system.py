from typing import Annotated

from fastapi import APIRouter, Body, HTTPException
from fastapi.concurrency import run_in_threadpool

from engine import ocr_engine

router = APIRouter()


@router.get("/status")
async def system_status():
    """مسار لتتبع حالة النظام وتوجيه الفريق"""
    return {
        "ingestion_pipeline": f"Online — OCR device: {ocr_engine.OCR_DEVICE}",
        "search_engine": "Online - SQLite FTS5 index is active and receiving data.",
        "gpu": ocr_engine.GPU_AVAILABLE,
        "device": ocr_engine.device_status(),
        "feedback": (
            "OCR text is stored verbatim. Never reverse characters or re-sort boxes: "
            "indexing and querying use identical normalisation, so token order does not "
            "affect matching, while reversing characters makes a document unfindable."
        )
    }


@router.get("/ocr/progress")
async def ocr_progress():
    """تقدّم تجهيز محرك OCR (تنزيل/تحميل النماذج) — لا يُطلق البناء بنفسه أبداً."""
    return ocr_engine.load_progress()


@router.get("/device")
async def get_device():
    """حالة العتاد: أي جهاز يعمل الآن، وهل توجد بطاقة، ولماذا لا تُستخدم إن وُجدت."""
    return ocr_engine.device_status()


@router.post("/device")
async def set_device(mode: Annotated[str, Body(embed=True)]):
    """
    اختيار عتاد المعالجة: auto أو gpu أو cpu.
    إعادة بناء القارئ تستغرق ثوانٍ، لذا تجري في خيط منفصل حتى لا يتجمّد الخادم.
    """
    try:
        return await run_in_threadpool(ocr_engine.set_device, mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
