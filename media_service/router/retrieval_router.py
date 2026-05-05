from __future__ import annotations

from fastapi import APIRouter

from media_service.config.settings import resolve_annotation_root, resolve_window_annotation_root
from media_service.model.schemas import BatchSearchRequest, ExplainRequest, SearchRequest
from media_service.service.retrieval_service import RetrievalService

router = APIRouter()
service = RetrievalService()


@router.post("/search")
def search(request: SearchRequest) -> dict:
    request.annotation_root = str(resolve_annotation_root(request.annotation_root))
    request.window_annotation_root = str(resolve_window_annotation_root(request.window_annotation_root))
    return service.search(request)


@router.post("/batch")
def batch_search(request: BatchSearchRequest) -> dict:
    request.annotation_root = str(resolve_annotation_root(request.annotation_root))
    request.window_annotation_root = str(resolve_window_annotation_root(request.window_annotation_root))
    texts = request.texts or []
    durations = request.durations or []
    print(f"[media_service][batch] request_count={len(texts)} durations_count={len(durations)}")
    for idx, text in enumerate(texts):
        duration = durations[idx] if idx < len(durations) else None
        print(f"[media_service][batch] idx={idx} duration={duration} text={text}")
    return service.batch_search(request)


@router.post("/explain")
def explain(request: ExplainRequest) -> dict:
    return service.explain(request)


@router.get("/debug-window")
def debug_window(annotation_root: str | None = None, window_annotation_root: str | None = None) -> dict:
    resolved_annotation_root = str(resolve_annotation_root(annotation_root))
    resolved_window_annotation_root = str(resolve_window_annotation_root(window_annotation_root))
    return service.debug_window_sources(
        annotation_root=resolved_annotation_root,
        window_annotation_root=resolved_window_annotation_root,
    )
