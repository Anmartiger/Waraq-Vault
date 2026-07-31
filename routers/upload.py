from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from engine import jobs
from services.upload_pipeline import prepare_upload_batch, process_upload_job
from services.workspace import sanitize_workspace_name

router = APIRouter()

_MAX_BATCH = 50  # الحد الأقصى للملفات النصية/PDF في الرفعة الواحدة


@router.post("/upload")
async def upload_document(
    file: list[UploadFile] = File(...),
    overwrite: bool = Form(False),
    force_ocr: bool = Form(False),
    workspace: str = Form("Default"),
    pages: str | None = Form(None),
    confirmed: bool = Form(False),
):
    """
    يستقبل حتى 50 ملفاً نصياً (PDF/DOCX/TXT) أو حتى 5 صور في الدفعة، ويعيد فوراً
    معرّف مهمة (202). حماية المعالج تجري هنا في الخلفية: الملفات المصوَّرة الكبيرة
    تتطلب تأكيداً صريحاً من المستخدم (مع تقدير زمني وخيار تحديد صفحات بعينها)
    بدل حظر المستخدم أو خنق الخادم.
    """
    if not file:
        raise HTTPException(status_code=400, detail="لم يُرفَع أي ملف.")
    if len(file) > _MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"الحد الأقصى {_MAX_BATCH} ملفاً في الرفعة الواحدة (أُرسل {len(file)})."
        )

    workspace = sanitize_workspace_name(workspace)

    prepared = await prepare_upload_batch(
        file, overwrite=overwrite, force_ocr=force_ocr,
        workspace=workspace, pages=pages, confirmed=confirmed,
    )

    paged = len(prepared) == 1 and prepared[0]["kind"] == "pdf" and not prepared[0]["skip"]
    job_id = jobs.create_job(
        label=prepared[0]["name"] if len(prepared) == 1 else f"{len(prepared)} ملفات",
        item_names=[p["name"] for p in prepared],
    )
    jobs.submit(job_id, lambda: process_upload_job(job_id, prepared, paged))

    return JSONResponse(status_code=202, content={
        "job_id": job_id,
        "queued": [p["name"] for p in prepared],
        "workspace": workspace,
    })
