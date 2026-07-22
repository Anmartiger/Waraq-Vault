from fastapi import FastAPI, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from engine.ocr_engine import extract_text_from_image
import uvicorn
import os

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
    # 1. إنشاء مسار مؤقت لحفظ الصورة
    temp_file_path = f"temp_{file.filename}"
    
    # 2. حفظ الملف القادم من المستخدم على القرص
    with open(temp_file_path, "wb") as buffer:
        buffer.write(await file.read())
    
    # 3. تشغيل محرك الفيل
    extracted_text = extract_text_from_image(temp_file_path)
    
    # 4. تنظيف المكان (حذف الملف المؤقت بعد الانتهاء)
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
    
    # 5. إرجاع النتيجة
    return {
        "status": "success",
        "filename": file.filename,
        "extracted_text": extracted_text
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)