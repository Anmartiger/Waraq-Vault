from fastapi import FastAPI, APIRouter, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from engine.ocr_engine import reader, extract_text_from_image
from engine.pdf_engine import process_hybrid_pdf
from engine.database import init_db, insert_document, search_documents
from contextlib import asynccontextmanager
import uvicorn
import os
import uuid

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
async def upload_document(file: UploadFile = File(...)):
    # 1. الرفض السريع (Fail Fast): الآن يدعم الصور والـ PDF
    if not (file.content_type.startswith("image/") or file.content_type == "application/pdf"):
        raise HTTPException(
            status_code=400, 
            detail="الملف المرفوع غير مدعوم. النظام يدعم الصور (PNG/JPG) وملفات PDF فقط حالياً."
        )

    temp_file_path = f"temp_{uuid.uuid4()}_{file.filename}"
    
    try:
        # 2. التوجيه الذكي بناءً على نوع الملف
        if file.content_type == "application/pdf":
            # معالجة PDF في الذاكرة (لا نحتاج لحفظ الملف على القرص)
            file_bytes = await file.read()
            # إرسال العملية لخيط منفصل (Threadpool) لمنع تجميد الخادم
            extracted_text = await run_in_threadpool(process_hybrid_pdf, file_bytes, reader)
            
        else:
            # معالجة الصور (بناءً على الهيكل الذي بنيناه سابقاً)
            # حفظ الصورة مؤقتاً
            with open(temp_file_path, "wb") as buffer:
                buffer.write(await file.read())
            
            # إرسال الصورة لمحرك OCR في خيط منفصل
            extracted_text = await run_in_threadpool(extract_text_from_image, temp_file_path)

        # بعد الانتهاء من run_in_threadpool واستخراج النص (extracted_text)
        insert_document(file.filename, file.content_type, extracted_text)
        return {"filename": file.filename, "status": "تمت المعالجة والفهرسة بنجاح","extracted_text": extracted_text}

    except Exception as e:
        # التقاط أي انهيار وإعادته كرسالة واضحة
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء المعالجة: {str(e)}")

    finally:
        # 3. التنظيف الصارم: حذف الملف المؤقت للصورة إذا تم إنشاؤه
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)