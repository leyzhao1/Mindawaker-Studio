from __future__ import annotations

from fastapi import APIRouter

from media_service.config.settings import settings_summary

router = APIRouter()


@router.get("/")
def root() -> dict:
    return {
        "success": True,
        "service": "media_service",
        "version": "0.1.0",
        "status": "healthy",
    }


@router.get("/health")
def health() -> dict:
    return {
        "success": True,
        "status": "ok",
        "service": "media_service",
    }


@router.get("/settings")
def settings() -> dict:
    return {
        "success": True,
        **settings_summary(),
    }
