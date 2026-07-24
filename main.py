from fastapi import FastAPI, APIRouter, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from engine.ocr_engine import reader, extract_text_from_image
import uvicorn
import os
import uuid
from engine.pdf_engine import process_hybrid_pdf

app = FastAPI(title="WaraqVault API")

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
        "search_engine": "Offline - Awaiting Tiger to implement SQLite FTS5.",
        "feedback": "OCR extracts RTL Arabic text in reverse order. DO NOT FIX IT. The keywords (tokens) are present and valid for Full-Text Search indexing."
    }

# 3. مسار وهمي للبحث (إلى أن يتم ربطه بمحرك Tiger)
@app.get("/search")
async def search_documents(q: str):
    # لاحقاً سيتم استدعاء دوال Tiger هنا
    return {"query": q, "results": [f"نتيجة وهمية لـ: {q}", "نتيجة أخرى"]}

# 4. مسار وهمي للرفع (هنا سيعمل الفيل على دمج EasyOCR لاحقاً)
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
            # إرسال الصورة لمحرك OCR في خيط منفصل
            extracted_text = await run_in_threadpool(extract_text_from_image, temp_file_path)

        return {"filename": file.filename, "extracted_text": extracted_text}

    except Exception as e:
        # التقاط أي انهيار وإعادته كرسالة واضحة
        raise HTTPException(status_code=500, detail=f"حدث خطأ أثناء المعالجة: {str(e)}")

    finally:
        # 3. التنظيف الصارم: حذف الملف المؤقت للصورة إذا تم إنشاؤه
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)