from typing import Annotated

from fastapi import APIRouter, Query

from engine.database import search_documents

router = APIRouter()


@router.get("/search")
async def search(q: str, doc_id: Annotated[list[int] | None, Query()] = None,
                 workspace: str | None = None):
    if not q or len(q) < 2:
        return {"results": []}
    results = search_documents(q, doc_ids=doc_id, workspace=workspace)
    return {"query": q, "count": len(results), "results": results,
            "scope": doc_id or [], "workspace": workspace}
