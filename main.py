from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

app = FastAPI(title="WaraqVault API")

# 1. ربط مجلد الواجهة الذي صممه Tiger
app.mount("/static", StaticFiles(directory="ui"), name="static")

# 2. عرض الصفحة الرئيسية
@app.get("/")
async def serve_ui():
    return FileResponse("ui/index.html")

# 3. مسار وهمي للبحث (إلى أن يتم ربطه بمحرك Tiger)
@app.get("/search")
async def search_documents(q: str):
    # لاحقاً سيتم استدعاء دوال Tiger هنا
    return {"query": q, "results": [f"نتيجة وهمية لـ: {q}", "نتيجة أخرى"]}

# 4. مسار وهمي للرفع (هنا سيعمل الفيل على دمج EasyOCR لاحقاً)
@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    # لاحقاً سيتم استدعاء دالة extract(image_path) هنا
    return {"status": "success", "filename": file.filename, "message": "تم استلام الملف، بانتظار الـ OCR"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)