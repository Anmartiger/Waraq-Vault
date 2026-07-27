from fastapi import FastAPI, Request, UploadFile, File, Form, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from engine import ocr_engine
from engine import jobs
from engine.jobs import JobCancelled
from engine.pdf_engine import process_hybrid_pdf
from engine.docx_engine import process_docx
from engine.text_engine import process_txt
from engine.database import (
    init_db, insert_document, search_documents, find_duplicate,
    delete_documents, list_documents, delete_document_by_id,
)
from contextlib import asynccontextmanager
from typing import Annotated
import uvicorn
import io
import os
import zipfile
import hashlib

@asynccontextmanager
async def lifespan(app: FastAPI):
    # تهيئة قاعدة البيانات وبناء جداول FTS5 فور إقلاع الخادم
    init_db()
    yield

app = FastAPI(title="WaraqVault API", lifespan=lifespan)

# 1. ربط مجلد الواجهة الذي صممه Tiger
app.mount("/static", StaticFiles(directory="ui"), name="static")

# إعداد محرك القوالب لكي يفهم الأقواس {{ }}
templates = Jinja2Templates(directory="ui")

# 2. عرض الصفحة الرئيسية
@app.get("/")
async def serve_ui(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "Q": "",
            "STATUS": "جاهز للعمل",
            "RESULTS": ""
        }
    )

_DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")
_MAX_BATCH = 5   # الحد الأقصى للملفات في عملية رفع واحدة

# نوع افتراضي يُخزَّن في قاعدة البيانات إذا لم يرسل المتصفح content_type
_FALLBACK_TYPES = {
    "pdf": "application/pdf",
    "docx": _DOCX_TYPE,
    "txt": "text/plain",
    "image": "image/png",
}

def _sniff_kind(head: bytes) -> str | None:
    """
    التعرف على نوع الملف من محتواه الفعلي (Magic Bytes) عندما يفشل الاسم والترويسة.
    هذا يحل مشكلة الملفات النصية بلا امتداد (مثل "هندسة_AI") التي يرسلها المتصفح
    بنوع application/octet-stream.
    """
    if not head:
        return None
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n") or head.startswith(b"\xff\xd8\xff") \
       or head.startswith(b"BM") or head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[:4] == b"PK\x03\x04":
        # أرشيف ZIP — نتأكد أنه DOCX فعلاً وليس أي ملف مضغوط آخر
        try:
            with zipfile.ZipFile(io.BytesIO(head)) as z:
                if any(n.startswith("word/") for n in z.namelist()):
                    return "docx"
        except Exception:
            pass
        return None
    # نص محتمل: لا بايتات صفرية + قابل لفك الترميز بأحد ترميزات المشروع
    sample = head[:4096]
    if b"\x00" in sample:
        return None
    for encoding in ("utf-8", "cp1256"):
        try:
            sample.decode(encoding)
            return "txt"
        except UnicodeDecodeError:
            continue
    return None

def detect_kind(filename: str, content_type: str, file_bytes: bytes = b"") -> str | None:
    """
    تحديد نوع الملف على ثلاث مراحل: الامتداد ← ترويسة content_type ← بصمة المحتوى.
    المتصفحات لا ترسل نوعاً موحداً لملفات DOCX والنصوص، والملفات بلا امتداد
    تصل كـ octet-stream — لذلك لا نعتمد على مصدر واحد أبداً.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    ctype = (content_type or "").lower()

    if ext == ".pdf" or ctype == "application/pdf":
        return "pdf"
    if ext == ".docx" or ctype == _DOCX_TYPE:
        return "docx"
    if ext == ".txt" or ctype.startswith("text/"):
        return "txt"
    if ext in _IMAGE_EXTS or ctype.startswith("image/"):
        return "image"
    return _sniff_kind(file_bytes)

@app.get("/status")
async def system_status():
    """مسار لتتبع حالة النظام وتوجيه الفريق"""
    return {
        "ingestion_pipeline": f"Online — OCR device: {ocr_engine.OCR_DEVICE}",
        "search_engine": "Online - SQLite FTS5 index is active and receiving data.",
        "gpu": ocr_engine.GPU_AVAILABLE,
        "feedback": "OCR extracts RTL Arabic text in reverse order. DO NOT FIX IT. Tokens are valid for indexing."
    }

@app.get("/search")
async def search(q: str, doc_id: Annotated[list[int] | None, Query()] = None):
    if not q or len(q) < 2:
        return {"results": []}
    results = search_documents(q, doc_ids=doc_id)
    return {"query": q, "count": len(results), "results": results, "scope": doc_id or []}

@app.get("/documents")
async def documents():
    """قائمة المستندات المفهرسة — تغذي مرشِّح النطاق وخيار الحذف في الواجهة."""
    docs = list_documents()
    return {"count": len(docs), "documents": docs}

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """حذف مستند واحد. الزناد في قاعدة البيانات يزيله من فهرس البحث تلقائياً."""
    deleted = delete_document_by_id(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="المستند غير موجود — ربما حُذف مسبقاً.")
    return {"deleted": deleted, "id": doc_id}

@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    """حالة مهمة معالجة: النسبة، العنصر الحالي، وحالة كل ملف في الدفعة."""
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="مهمة غير معروفة — ربما أُعيد تشغيل الخادم.")
    return job

@app.post("/jobs/{job_id}/cancel")
async def job_cancel(job_id: str):
    """إلغاء مهمة جارية أو مصطفة. الجارية تتوقف عند أقرب نقطة فحص (بين الصفحات/الصور)."""
    if jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="مهمة غير معروفة.")
    return {"cancelled": jobs.cancel(job_id)}

def _process_upload_job(job_id: str, prepared: list, paged: bool):
    """
    جسم المهمة الخلفية: يعالج كل ملفات الدفعة بالتسلسل ويحدّث التقدم بعد كل
    صفحة/صورة مكتملة فعلياً. يعمل داخل منفّذ المهام (خيط واحد) فلا يجمّد الخادم
    ولا الواجهة مهما كان حجم الملف — وهذا بديل سقف الصفحات السابق.
    """
    indexed, skipped, failed = [], [], []
    replaced = 0

    for idx, item in enumerate(prepared):
        if jobs.is_cancelled(job_id):
            jobs.set_item(job_id, idx, "cancelled")
            raise JobCancelled()

        name = item["name"]
        if item["skip"]:
            jobs.set_item(job_id, idx, "skipped", "مفهرس مسبقاً (مكرر)")
            skipped.append(name)
            if not paged:
                jobs.add_progress(job_id, done=idx + 1)
            continue

        jobs.set_item(job_id, idx, "processing")
        jobs.add_progress(job_id, current=name)

        try:
            # الاستبدال يزيل النسخ القديمة بالاسم وبالبصمة معاً قبل الفهرسة الجديدة
            if item["overwrite_dup"]:
                replaced += delete_documents(filename=name, file_hash=item["hash"])

            kind = item["kind"]
            if kind == "pdf":
                def _page_progress(done, total, label):
                    jobs.add_progress(job_id, done=done, total=total, current=f"{name} — {label}")
                extracted_text = process_hybrid_pdf(
                    item["bytes"], ocr_engine.run_ocr,
                    force_ocr=item["force_ocr"],
                    progress=_page_progress,
                    is_cancelled=lambda: jobs.is_cancelled(job_id),
                )
            elif kind == "docx":
                extracted_text = process_docx(item["bytes"])
            elif kind == "txt":
                extracted_text = process_txt(item["bytes"])
            else:
                # الصور تُمرَّر كبايتات مباشرة — لا ملفات مؤقتة على القرص إطلاقاً
                extracted_text = " \n ".join(ocr_engine.run_ocr(item["bytes"]))

            insert_document(name, item["stored_type"], extracted_text, item["hash"])
            jobs.set_item(job_id, idx, "indexed")
            indexed.append(name)

        except JobCancelled:
            jobs.set_item(job_id, idx, "cancelled")
            raise
        except Exception as e:
            # <--- منع تسريب الأخطاء للواجهة: التفاصيل للسجل، رسالة عامة للمستخدم --->
            print(f"CRITICAL BACKEND ERROR [{name}]: {e}")
            detail = ("الملف تالف أو لا يحتوي على بيانات صورة صالحة رغم امتداده."
                      if item["kind"] == "image" else "الملف تالف أو غير مقروء.")
            jobs.set_item(job_id, idx, "failed", detail)
            failed.append(name)
        finally:
            if not paged:
                jobs.add_progress(job_id, done=idx + 1)

    return {"indexed": indexed, "skipped": skipped, "failed": failed, "replaced": replaced}

@app.post("/upload")
async def upload_document(
    file: list[UploadFile] = File(...),
    overwrite: bool = Form(False),
    force_ocr: bool = Form(False),
):
    """
    يستقبل ملفاً واحداً (أي صيغة مدعومة) أو دفعة صور حتى 5 صور، ويعيد فوراً
    معرّف مهمة (202). المعالجة الثقيلة تجري في طابور خلفي، والواجهة تتابع
    التقدم عبر GET /jobs/{id} وتستطيع الإلغاء عبر POST /jobs/{id}/cancel.
    """
    if not file:
        raise HTTPException(status_code=400, detail="لم يُرفَع أي ملف.")
    if len(file) > _MAX_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"الحد الأقصى {_MAX_BATCH} ملفات في الرفعة الواحدة (أُرسل {len(file)})."
        )

    # 1. الفحص والقراءة والرفض السريع (Fail Fast) قبل أي معالجة ثقيلة
    prepared = []
    for f in file:
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"الملف فارغ (0 بايت): {f.filename}")

        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext == ".doc" or f.content_type == "application/msword":
            raise HTTPException(
                status_code=400,
                detail="صيغة .doc القديمة غير مدعومة. يرجى حفظ الملف بصيغة .docx ثم رفعه."
            )

        kind = detect_kind(f.filename, f.content_type, data)
        if kind is None:
            raise HTTPException(
                status_code=400,
                detail=f"الملف غير مدعوم: {f.filename}. النظام يدعم PDF و Word (DOCX) والملفات النصية والصور."
            )

        prepared.append({
            "name": f.filename,
            "bytes": data,
            "hash": hashlib.sha256(data).hexdigest(),
            "kind": kind,
            "stored_type": f.content_type or _FALLBACK_TYPES[kind],
            "force_ocr": force_ocr,
            "skip": False,
            "overwrite_dup": False,
        })

    # 2. قاعدة الدفعات: الرفع المتعدد مخصص للصور فقط (حتى 5 صور في المرة)
    if len(prepared) > 1 and any(p["kind"] != "image" for p in prepared):
        raise HTTPException(
            status_code=400,
            detail="الرفع المتعدد مخصص للصور فقط (حتى 5 صور). ملفات PDF و DOCX والنصوص تُرفَع واحداً واحداً."
        )

    # 3. فحص التكرار يسبق المعالجة حتى لا ينتظر المستخدم OCR بلا فائدة
    for p in prepared:
        duplicate = find_duplicate(p["name"], p["hash"])
        if not duplicate:
            continue
        if overwrite:
            p["overwrite_dup"] = True
        elif len(prepared) == 1:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "duplicate",
                    "match": duplicate["match"],          # "content" أو "filename"
                    "filename": duplicate["filename"],
                    "indexed_at": duplicate["created_at"],
                }
            )
        else:
            # داخل دفعة: نتخطى المكرر ونكمل الباقي، وتظهر حالته في تقرير المهمة
            p["skip"] = True

    # 4. إنشاء المهمة وإرسالها للطابور — الرد فوري ولا ينتظر المعالجة
    paged = len(prepared) == 1 and prepared[0]["kind"] == "pdf" and not prepared[0]["skip"]
    job_id = jobs.create_job(
        label=prepared[0]["name"] if len(prepared) == 1 else f"{len(prepared)} صور",
        item_names=[p["name"] for p in prepared],
    )
    jobs.submit(job_id, lambda: _process_upload_job(job_id, prepared, paged))

    return JSONResponse(status_code=202, content={
        "job_id": job_id,
        "queued": [p["name"] for p in prepared],
    })

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
