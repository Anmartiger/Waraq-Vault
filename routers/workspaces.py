from fastapi import APIRouter, HTTPException

from engine import storage
from engine.database import list_workspaces, delete_workspace, referenced_stored_names

router = APIRouter()


@router.get("/workspaces")
async def workspaces():
    """مساحات العمل (المجموعات) وعدد مستندات كل واحدة."""
    spaces = list_workspaces()
    return {"count": len(spaces), "workspaces": spaces}


@router.delete("/workspaces/{name}")
async def remove_workspace(name: str):
    """حذف مجموعة كاملة بضربة واحدة — بديل المجلدات المتداخلة بلا تعقيد شجري."""
    deleted = delete_workspace(name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="لا توجد مجموعة بهذا الاسم.")
    storage.prune(referenced_stored_names())
    return {"deleted": deleted, "workspace": name}
