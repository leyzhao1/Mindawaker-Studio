from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from media_service.config.settings import resolve_annotation_root
from media_service.model.schemas import IndexBuildRequest
from media_service.service.index_service import IndexService

router = APIRouter()
service = IndexService()


@router.post("/build")
def build_index(request: IndexBuildRequest) -> dict:
    return service.build_index(resolve_annotation_root(request.annotation_root))


@router.get("/stats")
def index_stats(annotation_root: str = "") -> dict:
    return service.stats(resolve_annotation_root(annotation_root or None))
