from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from engine.paths import app_dir

router = APIRouter()
templates = Jinja2Templates(directory=str(app_dir() / "ui"))


@router.get("/")
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
