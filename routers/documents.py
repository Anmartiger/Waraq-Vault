from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from engine import storage
from engine.database import (
    list_documents, get_document, delete_document_by_id,
    delete_documents_by_ids, referenced_stored_names,
)

router = APIRouter()


@router.get("/documents")
async def documents(workspace: str | None = None):
    """قائمة المستندات المفهرسة — تغذي مدير الملفات في الواجهة."""
    docs = list_documents(workspace=workspace)
    return {"count": len(docs), "documents": docs}


@router.get("/documents/{doc_id}/open")
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


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """حذف مستند واحد. الزناد في قاعدة البيانات يزيله من فهرس البحث تلقائياً."""
    deleted = delete_document_by_id(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="المستند غير موجود — ربما حُذف مسبقاً.")
    storage.prune(referenced_stored_names())
    return {"deleted": deleted, "id": doc_id}


@router.post("/documents/delete")
async def delete_documents_bulk(ids: Annotated[list[int], Body(embed=True)]):
    """الحذف الجماعي للملفات المحددة في مدير الملفات."""
    deleted = delete_documents_by_ids(ids)
    storage.prune(referenced_stored_names())
    return {"deleted": deleted}
