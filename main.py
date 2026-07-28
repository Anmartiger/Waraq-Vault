from fastapi import FastAPI, Request, UploadFile, File, Form, Query, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from engine import ocr_engine
from engine import jobs
from engine.jobs import JobCancelled
from engine.pdf_engine import process_hybrid_pdf, pdf_precheck, parse_page_selection
from engine.docx_engine import process_docx
from engine.text_engine import process_txt
from engine.textflow import join_ocr
from engine.database import (
    init_db, insert_document, search_documents, find_duplicate,
    delete_documents, list_documents, delete_document_by_id,
    delete_documents_by_ids, list_workspaces, delete_workspace,
    get_document, referenced_stored_names,
)
from engine import storage
from contextlib import asynccontextmanager
from typing import Annotated
import uvicorn
import io
import os
import re
import zipfile
import hashlib
from urllib.parse import quote

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

# سياسة الدفعات: الاستخراج النصي سريع فلا داعي لخنق المستخدم بملف واحد،
# أما الصور (OCR ثقيل) فتبقى محدودة، و Force OCR يعيد التقييد الصارم.
_MAX_BATCH = 50            # الحد الأقصى للملفات النصية/PDF في الرفعة الواحدة
_MAX_IMAGES_PER_BATCH = 5  # الحد الأقصى للصور في الرفعة الواحدة
_CONFIRM_SCANNED_PAGES = 5    # فوق هذا العدد نسأل المستخدم (ولا نرفض أبداً)
_EST_SEC_PER_PAGE_GPU = 1.5   # تقدير تقريبي لزمن OCR للصفحة الواحدة
_EST_SEC_PER_PAGE_CPU = 15.0

# نوع افتراضي يُخزَّن في قاعدة البيانات إذا لم يرسل المتصفح content_type
_FALLBACK_TYPES = {
    "pdf": "application/pdf",
    "docx": _DOCX_TYPE,
    "txt": "text/plain",
    "image": "image/png",
}

def _zip_flavor(data: bytes) -> str | None:
    """تمييز نكهة ملف ZIP: docx أو odt أو zip عادي — لرسائل خطأ صادقة."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if any(n.startswith("word/") for n in names):
                return "docx"
            if "mimetype" in names:
                mimetype = z.read("mimetype")[:100].decode("ascii", "replace")
                if "opendocument.text" in mimetype:
                    return "odt"
            return "zip"
    except Exception:
        return None

def _sniff_kind(data: bytes) -> str | None:
    """
    التعرف على نوع الملف من محتواه الفعلي (Magic Bytes) — لا ثقة بالاسم وحده.
    """
    if not data:
        return None
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff") \
       or data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    # BMP: توقيع "BM" وحده ضعيف (نص يبدأ بـ BMW مثلاً) — نتحقق من الحقول المحجوزة
    if data.startswith(b"BM") and len(data) > 26 and data[6:10] == b"\x00\x00\x00\x00":
        return "image"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    if data[:4] == b"PK\x03\x04":
        return "docx" if _zip_flavor(data) == "docx" else None
    # نص محتمل: لا بايتات صفرية + قابل لفك الترميز بأحد ترميزات المشروع
    sample = data[:4096]
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
    تحديد نوع الملف: الامتداد ← ترويسة content_type ← بصمة المحتوى.
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

def _verify_content_matches(kind: str, data: bytes, filename: str) -> None:
    """
    صمام أمان الامتدادات المزيفة: الامتداد ادّعى نوعاً، والمحتوى يجب أن يثبته.
    ملف ODT مسمّى .pdf يُرفض هنا برسالة واضحة بدل تلويث قاعدة البيانات بسجل تالف.
    """
    sniffed = _sniff_kind(data)
    if sniffed == kind:
        return
    flavor = _zip_flavor(data) if data[:4] == b"PK\x03\x04" else None
    actual = {"odt": "ملف OpenDocument (ODT)", "zip": "أرشيف ZIP", "docx": "ملف Word"}.get(
        flavor, {"pdf": "ملف PDF", "image": "صورة", "txt": "ملف نصي", None: "محتوى غير معروف"}.get(sniffed, "محتوى غير معروف")
    )
    raise HTTPException(
        status_code=400,
        detail=f"الامتداد لا يطابق المحتوى الحقيقي للملف {filename}: المحتوى الفعلي {actual}. "
               f"أعد تسمية الملف بامتداده الصحيح أو حوّله للصيغة المدعومة."
    )

_WS_CLEAN = re.compile(r"[\\/\r\n\t]+")

def _sanitize_workspace(name: str) -> str:
    """تنظيف اسم مساحة العمل: بلا فواصل مسارات، بطول معقول، والافتراضي Default."""
    name = _WS_CLEAN.sub("-", (name or "").strip())
    name = re.sub(r"\s{2,}", " ", name)
    return name[:40] or "Default"

@app.get("/status")
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

@app.get("/device")
async def get_device():
    """حالة العتاد: أي جهاز يعمل الآن، وهل توجد بطاقة، ولماذا لا تُستخدم إن وُجدت."""
    return ocr_engine.device_status()

@app.post("/device")
async def set_device(mode: Annotated[str, Body(embed=True)]):
    """
    اختيار عتاد المعالجة: auto أو gpu أو cpu.
    إعادة بناء القارئ تستغرق ثوانٍ، لذا تجري في خيط منفصل حتى لا يتجمّد الخادم.
    """
    try:
        return await run_in_threadpool(ocr_engine.set_device, mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/search")
async def search(q: str, doc_id: Annotated[list[int] | None, Query()] = None,
                 workspace: str | None = None):
    if not q or len(q) < 2:
        return {"results": []}
    results = search_documents(q, doc_ids=doc_id, workspace=workspace)
    return {"query": q, "count": len(results), "results": results,
            "scope": doc_id or [], "workspace": workspace}

@app.get("/documents")
async def documents(workspace: str | None = None):
    """قائمة المستندات المفهرسة — تغذي مدير الملفات في الواجهة."""
    docs = list_documents(workspace=workspace)
    return {"count": len(docs), "documents": docs}

@app.get("/documents/{doc_id}/open")
async def open_document(doc_id: int):
    """
    فتح الملف الأصلي كما رُفع. النسخة محفوظة محلياً في مجلد storage/،
    وتُقدَّم inline ليعرضها المتصفح مباشرة (PDF وصور) بدل تنزيلها.
    """
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="المستند غير موجود.")
    path = storage.path_for(doc["stored_name"])
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="لا توجد نسخة محفوظة من هذا الملف — رُفع قبل تفعيل ميزة الفتح. "
                   "أعد رفعه ليصبح قابلاً للفتح."
        )
    # ترميز RFC 5987 ليصمد اسم الملف العربي في ترويسة HTTP
    disposition = f"inline; filename*=UTF-8''{quote(doc['filename'] or 'document')}"
    return FileResponse(
        path,
        media_type=doc["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": disposition},
    )

@app.get("/workspaces")
async def workspaces():
    """مساحات العمل (المجموعات) وعدد مستندات كل واحدة."""
    spaces = list_workspaces()
    return {"count": len(spaces), "workspaces": spaces}

@app.delete("/workspaces/{name}")
async def remove_workspace(name: str):
    """حذف مجموعة كاملة بضربة واحدة — بديل المجلدات المتداخلة بلا تعقيد شجري."""
    deleted = delete_workspace(name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="لا توجد مجموعة بهذا الاسم.")
    storage.prune(referenced_stored_names())
    return {"deleted": deleted, "workspace": name}

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """حذف مستند واحد. الزناد في قاعدة البيانات يزيله من فهرس البحث تلقائياً."""
    deleted = delete_document_by_id(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="المستند غير موجود — ربما حُذف مسبقاً.")
    storage.prune(referenced_stored_names())
    return {"deleted": deleted, "id": doc_id}

@app.post("/documents/delete")
async def delete_documents_bulk(ids: Annotated[list[int], Body(embed=True)]):
    """الحذف الجماعي للملفات المحددة في مدير الملفات."""
    deleted = delete_documents_by_ids(ids)
    storage.prune(referenced_stored_names())
    return {"deleted": deleted}

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
    صفحة/صورة مكتملة فعلياً. يعمل داخل منفّذ المهام (خيط واحد) فلا يجمّد الخادم.
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
            page_map = None

            if kind == "pdf":
                def _page_progress(done, total, label):
                    if paged:
                        jobs.add_progress(job_id, done=done, total=total, current=f"{name} — {label}")
                    else:
                        jobs.add_progress(job_id, current=f"{name} — {label}")
                pdf_kwargs = {
                    "force_ocr": item["force_ocr"],
                    "pages": item.get("pages"),
                    "progress": _page_progress,
                    "is_cancelled": lambda: jobs.is_cancelled(job_id),
                }
                if "max_ocr_pages" in item:
                    pdf_kwargs["max_ocr_pages"] = item["max_ocr_pages"]
                extracted_text, page_map = process_hybrid_pdf(
                    item["bytes"], ocr_engine.run_ocr_boxes, **pdf_kwargs,
                )
            elif kind == "docx":
                def _media_progress(done, total, label):
                    jobs.add_progress(job_id, current=f"{name} — {label}")
                extracted_text, page_map = process_docx(
                    item["bytes"],
                    force_ocr=item["force_ocr"],
                    ocr_fn=ocr_engine.run_ocr_boxes if item["force_ocr"] else None,
                    progress=_media_progress,
                    is_cancelled=lambda: jobs.is_cancelled(job_id),
                )
            elif kind == "txt":
                extracted_text = process_txt(item["bytes"])
            else:
                # الصور تُمرَّر كبايتات مباشرة، والدمج الذكي يبني فقرات مترابطة
                extracted_text = join_ocr(ocr_engine.run_ocr_boxes(item["bytes"]))

            # نحفظ نسخة من الملف الأصلي ليُفتح لاحقاً من الواجهة؛ فشل الحفظ
            # لا يُسقط الفهرسة — يبقى المستند قابلاً للبحث وغير قابل للفتح فقط
            stored_name = None
            try:
                stored_name = storage.save(item["bytes"], item["hash"], name)
            except Exception as e:
                print(f"WARNING: could not store a copy of {name}: {e}")

            insert_document(name, item["stored_type"], extracted_text, item["hash"],
                            workspace=item["workspace"], page_map=page_map,
                            stored_name=stored_name)
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

    workspace = _sanitize_workspace(workspace)

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

        # صمام الامتدادات المزيفة: المحتوى الفعلي يجب أن يطابق النوع المدّعى
        _verify_content_matches(kind, data, f.filename)

        prepared.append({
            "name": f.filename,
            "bytes": data,
            "hash": hashlib.sha256(data).hexdigest(),
            "kind": kind,
            # المتصفح يرسل octet-stream للملفات بلا امتداد؛ نحن كشفنا النوع الحقيقي
            # من المحتوى فنخزّنه بدل الترويسة العامة (يصحّح الوسام ووحدة الترقيم معاً)
            "stored_type": (f.content_type
                            if f.content_type and f.content_type != "application/octet-stream"
                            else _FALLBACK_TYPES[kind]),
            "force_ocr": force_ocr,
            "workspace": workspace,
            "skip": False,
            "overwrite_dup": False,
            "pages": None,
        })

    # 2. قواعد الدفعات — Force OCR يعيد التقييد الصارم لأنه معالجة ثقيلة بطلب صريح
    image_count = sum(1 for p in prepared if p["kind"] == "image")
    if force_ocr:
        if len(prepared) > 1 and not (image_count == len(prepared) and image_count <= _MAX_IMAGES_PER_BATCH):
            raise HTTPException(
                status_code=400,
                detail=f"مع تفعيل Force OCR: ملف واحد فقط، أو حتى {_MAX_IMAGES_PER_BATCH} صور."
            )
    elif image_count > _MAX_IMAGES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"الحد الأقصى {_MAX_IMAGES_PER_BATCH} صور في الدفعة الواحدة (أُرسل {image_count})."
        )

    # 3. الفحص المسبق لملفات PDF (سريع، بلا OCR): كم صفحة مصورة سنعالج فعلياً؟
    pdf_items = [p for p in prepared if p["kind"] == "pdf"]
    for p in pdf_items:
        try:
            p["precheck"] = pdf_precheck(p["bytes"])
        except Exception:
            raise HTTPException(status_code=400, detail=f"ملف PDF تالف أو غير قابل للقراءة: {p['name']}")

    # اختيار صفحات بعينها متاح لرفعة PDF واحدة فقط
    if pages:
        if len(prepared) != 1 or prepared[0]["kind"] != "pdf":
            raise HTTPException(status_code=400, detail="تحديد الصفحات متاح عند رفع ملف PDF واحد فقط.")
        try:
            prepared[0]["pages"] = parse_page_selection(pages, prepared[0]["precheck"]["total_pages"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # 4. صمام أمان المعالج: فوق حد الصفحات المصورة نطلب موافقة صريحة مع تقدير زمني
    total_scanned = 0
    confirm_files = []
    for p in pdf_items:
        selected = set(p["pages"]) if p["pages"] else set(range(1, p["precheck"]["total_pages"] + 1))
        if force_ocr:
            scanned_count = len(selected)
        else:
            scanned_count = len(selected & set(p["precheck"]["scanned_pages"]))
        p["scanned_count"] = scanned_count
        total_scanned += scanned_count
        confirm_files.append({
            "name": p["name"],
            "total_pages": p["precheck"]["total_pages"],
            "scanned_pages": scanned_count,
        })

    if total_scanned > _CONFIRM_SCANNED_PAGES and not confirmed:
        per_page = _EST_SEC_PER_PAGE_GPU if ocr_engine.GPU_AVAILABLE else _EST_SEC_PER_PAGE_CPU
        raise HTTPException(status_code=413, detail={
            "reason": "confirm_ocr",
            "total_scanned_pages": total_scanned,
            "estimate_seconds": round(total_scanned * per_page),
            "device": ocr_engine.OCR_DEVICE,
            "files": confirm_files,
            "page_selection_allowed": len(prepared) == 1 and prepared[0]["kind"] == "pdf",
        })

    # لا رفض بعد اليوم مهما بلغ عدد الصفحات: الحماية هي الموافقة الصريحة أعلاه
    # (مع التقدير الزمني واختيار الصفحات) والطابور الخلفي القابل للإلغاء.

    # 5. فحص التكرار يسبق المعالجة حتى لا ينتظر المستخدم OCR بلا فائدة
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

    # 6. إنشاء المهمة وإرسالها للطابور — الرد فوري ولا ينتظر المعالجة
    paged = len(prepared) == 1 and prepared[0]["kind"] == "pdf" and not prepared[0]["skip"]
    job_id = jobs.create_job(
        label=prepared[0]["name"] if len(prepared) == 1 else f"{len(prepared)} ملفات",
        item_names=[p["name"] for p in prepared],
    )
    jobs.submit(job_id, lambda: _process_upload_job(job_id, prepared, paged))

    return JSONResponse(status_code=202, content={
        "job_id": job_id,
        "queued": [p["name"] for p in prepared],
        "workspace": workspace,
    })

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
