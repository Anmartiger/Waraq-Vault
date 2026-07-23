from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from fastapi.templating import Jinja2Templates
from engine.ocr_engine import extract_text_from_image
import uvicorn
import os
import uuid

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
    # 1. التحقق الصارم من نوع الملف (Fail Fast)
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="الملف المرفوع ليس صورة. يدعم النظام الصور فقط حالياً.")

    # 2. حماية الخادم بتوليد اسم عشوائي آمن (UUID) وتجاهل اسم المستخدم
    safe_filename = f"temp_{uuid.uuid4().hex}.img"
    
    try:
        # 3. حفظ الملف
        with open(safe_filename, "wb") as buffer:
            buffer.write(await file.read())
        
        # 4. تشغيل الـ OCR في Thread منفصل لمنع تجميد الخادم!
        extracted_text = await run_in_threadpool(extract_text_from_image, safe_filename)
        
        return {
            "status": "success",
            "filename": file.filename, 
            "extracted_text": extracted_text
        }
        
    except ValueError as ve:
        # التقاط الخطأ القادم من محرك الـ OCR
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        # التقاط أي خطأ آخر
        raise HTTPException(status_code=500, detail=f"حدث خطأ غير متوقع: {str(e)}")
        
    finally:
        # 5. تنظيف إجباري (يُنفذ دائماً سواء نجحت العملية أو فشلت)
        if os.path.exists(safe_filename):
            os.remove(safe_filename)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)