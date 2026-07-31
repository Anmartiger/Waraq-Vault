from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from engine.database import init_db
from engine.paths import app_dir
from engine.ocr_engine import start_background_load
from routers import documents, jobs, pages, search, system, upload, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    # تهيئة قاعدة البيانات وبناء جداول FTS5 فور إقلاع الخادم
    init_db()
    # يبدأ تنزيل/تحميل نماذج OCR في الخلفية فور الإقلاع بدل انتظار أول رفعة —
    # لا يحجب استعداد الخادم (انظر engine/ocr_engine.py لتفاصيل السبب)
    start_background_load()
    yield

app = FastAPI(title="WaraqVault API", lifespan=lifespan)

# ربط مجلد الواجهة الذي صممه Tiger
app.mount("/static", StaticFiles(directory=str(app_dir() / "ui")), name="static")

for _router_module in (pages, system, search, documents, workspaces, jobs, upload):
    app.include_router(_router_module.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
