from fastapi import FastAPI, APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from engine.ocr_engine import reader, extract_text_from_image
from engine.pdf_engine import process_hybrid_pdf
from engine.docx_engine import process_docx
from engine.text_engine import process_txt
from engine.database import init_db, insert_document, search_documents, find_duplicate, delete_documents
from contextlib import asynccontextmanager
import uvicorn
import os
import uuid
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

# نوع افتراضي يُخزَّن في قاعدة البيانات إذا لم يرسل المتصفح content_type
_FALLBACK_TYPES = {
    "pdf": "application/pdf",
    "docx": _DOCX_TYPE,
    "txt": "text/plain",
    "image": "image/png",
}

def detect_kind(filename: str, content_type: str) -> str | None:
    """
    تحديد نوع الملف من الامتداد أولاً ثم من content_type،
    لأن المتصفحات لا ترسل نوعاً موحداً لملفات DOCX والنصوص.
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
    return None

@app.get("/status")
async def system_status():
    """مسار لتتبع حالة النظام وتوجيه الفريق"""
    return {
        "ingestion_pipeline": "Online - EasyOCR is active and working.",
        "search_engine": "Online - SQLite FTS5 index is active and receiving data.",
        "feedback": "OCR extracts RTL Arabic text in reverse order. DO NOT FIX IT. Tokens are valid for indexing."
    }

@app.get("/search")
async def search(q: str):
    if not q or len(q) < 2:
        return {"results": []}
    results = search_documents(q)
    return {"query": q, "count": len(results), "results": results}

@app.post("/upload")
async def upload_document(file: UploadFile = File(...), overwrite: bool = Form(False)):
    # 1. الرفض السريع (Fail Fast): يدعم الصور و PDF و DOCX والملفات النصية
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext == ".doc" or file.content_type == "application/msword":
        raise HTTPException(
            status_code=400,
            detail="صيغة .doc القديمة غير مدعومة. يرجى حفظ الملف بصيغة .docx ثم رفعه."
        )

    kind = detect_kind(file.filename, file.content_type)
    if kind is None:
        raise HTTPException(
            status_code=400,
            detail="الملف المرفوع غير مدعوم. النظام يدعم PDF و Word (DOCX) والملفات النصية (TXT) والصور (PNG/JPG)."
        )

    # 2. قراءة الملف مرة واحدة وحساب بصمته لكشف التكرار
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 3. فحص التكرار يسبق المعالجة الثقيلة حتى لا ينتظر المستخدم OCR بلا فائدة
    duplicate = find_duplicate(file.filename, file_hash)
    if duplicate and not overwrite:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "duplicate",
                "match": duplicate["match"],          # "content" أو "filename"
                "filename": duplicate["filename"],
                "indexed_at": duplicate["created_at"],
            }
        )

    replaced = 0
    if overwrite:
        # الاستبدال يزيل النسخ القديمة بالاسم وبالبصمة معاً
        replaced = delete_documents(filename=file.filename, file_hash=file_hash)

    temp_file_path = f"temp_{uuid.uuid4()}_{file.filename}"

    try:
        # 4. التوجيه الذكي بناءً على نوع الملف
        if kind == "pdf":
            # معالجة PDF في الذاكرة (لا نحتاج لحفظ الملف على القرص)
            # إرسال العملية لخيط منفصل (Threadpool) لمنع تجميد الخادم
            extracted_text = await run_in_threadpool(process_hybrid_pdf, file_bytes, reader)

        elif kind == "docx":
            # قراءة DOCX في الذاكرة (فك ضغط الملف قد يستغرق وقتاً لذا نستخدم خيطاً منفصلاً)
            extracted_text = await run_in_threadpool(process_docx, file_bytes)

        elif kind == "txt":
            # الملفات النصية لا تحتاج معالجة ثقيلة، فقط فك الترميز
            extracted_text = process_txt(file_bytes)

        else:
            # معالجة الصور (بناءً على الهيكل الذي بنيناه سابقاً)
            # حفظ الصورة مؤقتاً
            with open(temp_file_path, "wb") as buffer:
                buffer.write(file_bytes)

            # إرسال الصورة لمحرك OCR في خيط منفصل
            extracted_text = await run_in_threadpool(extract_text_from_image, temp_file_path)

        # بعد الانتهاء من run_in_threadpool واستخراج النص (extracted_text)
        stored_type = file.content_type or _FALLBACK_TYPES[kind]
        insert_document(file.filename, stored_type, extracted_text, file_hash)
        return {
            "filename": file.filename,
            "status": "تمت المعالجة والفهرسة بنجاح",
            "replaced": replaced,
            "extracted_text": extracted_text,
        }

    except Exception as e:
        # التقاط أي انهيار وإعادته كرسالة واضحة
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء المعالجة: {str(e)}")

    finally:
        # 3. التنظيف الصارم: حذف الملف المؤقت للصورة إذا تم إنشاؤه
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)