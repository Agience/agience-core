from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, status

from services import types_service

router = APIRouter(prefix="/types", tags=["Types"])


@router.get("/index", status_code=status.HTTP_200_OK)
def list_types() -> Dict[str, List[str]]:
    content_types = types_service.list_available_content_types()
    return {"content_types": content_types}


@router.get("/resolve", status_code=status.HTTP_200_OK)
def resolve_type(content_type: str) -> Dict[str, Any]:
    res = types_service.resolve_type_definition(content_type)
    if res is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Type not found")
    return {
        "content_type": res.content_type,
        "definition": res.definition,
        "sources": res.sources,
        "validation_errors": res.validation_errors,
    }
