from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MEDIA_LIBRARY_ROOT = os.getenv("MEDIA_SERVICE_DEFAULT_MEDIA_LIBRARY_ROOT", "E:/root/media_service_test_assets")
DEFAULT_ANNOTATION_ROOT = os.getenv("MEDIA_SERVICE_DEFAULT_ANNOTATION_ROOT", "E:/root/media_service_test_assets/scan_out")
DEFAULT_WINDOW_ANNOTATION_ROOT = os.getenv("MEDIA_SERVICE_DEFAULT_WINDOW_ANNOTATION_ROOT", "E:/root/media_service_test_assets/window_scan_out")
DEFAULT_MODEL_ROOT = os.getenv("MEDIA_SERVICE_CONTENT_MODEL_ROOT", "/root/autodl-tmp/models")
DEFAULT_MODEL_NAME = os.getenv("MEDIA_SERVICE_CONTENT_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
DEFAULT_MODEL_PATH = os.getenv("MEDIA_SERVICE_CONTENT_MODEL_PATH", f"{DEFAULT_MODEL_ROOT}/models--Qwen--Qwen2.5-VL-7B-Instruct/snapshots/cc594898137f460bfe9f0759e9844b3ce807cfb5/")


@dataclass(frozen=True)
class ContentModelSettings:
    provider: str = os.getenv("MEDIA_SERVICE_CONTENT_PROVIDER", "qwen2_5_vl")
    model_name: str = DEFAULT_MODEL_NAME
    model_root: str = DEFAULT_MODEL_ROOT
    model_path: str = DEFAULT_MODEL_PATH
    device: str = os.getenv("MEDIA_SERVICE_CONTENT_DEVICE", "auto")
    max_new_tokens: int = int(os.getenv("MEDIA_SERVICE_CONTENT_MAX_NEW_TOKENS", "256"))
    video_frame_count: int = int(os.getenv("MEDIA_SERVICE_CONTENT_VIDEO_FRAME_COUNT", "6"))

    @property
    def resolved_model_source(self) -> str:
        model_path = Path(self.model_path)
        return str(model_path) if model_path.exists() else self.model_name


@dataclass(frozen=True)
class MediaLibrarySettings:
    media_library_root: str = DEFAULT_MEDIA_LIBRARY_ROOT
    annotation_root: str = DEFAULT_ANNOTATION_ROOT
    window_annotation_root: str = DEFAULT_WINDOW_ANNOTATION_ROOT


content_model_settings = ContentModelSettings()
media_library_settings = MediaLibrarySettings()


def default_media_library_root() -> Path:
    return Path(media_library_settings.media_library_root).resolve()


def default_annotation_root() -> Path:
    return Path(media_library_settings.annotation_root).resolve()


def default_window_annotation_root() -> Path:
    return Path(media_library_settings.window_annotation_root).resolve()


def resolve_media_library_root(value: str | None) -> Path:
    return Path(value).resolve() if value else default_media_library_root()


def resolve_annotation_root(value: str | None) -> Path:
    return Path(value).resolve() if value else default_annotation_root()


def resolve_window_annotation_root(value: str | None) -> Path:
    return Path(value).resolve() if value else default_window_annotation_root()


def resolve_output_dir(value: str | None) -> Path:
    return Path(value).resolve() if value else default_annotation_root()


def resolve_model_source() -> str:
    return content_model_settings.resolved_model_source


def resolve_model_cache_dir() -> str:
    return str(Path(content_model_settings.model_root).resolve())


def settings_summary() -> dict:
    return {
        "content_provider": content_model_settings.provider,
        "content_model_name": content_model_settings.model_name,
        "content_model_root": content_model_settings.model_root,
        "content_model_path": content_model_settings.model_path,
        "content_model_source": resolve_model_source(),
        "default_media_library_root": str(default_media_library_root()),
        "default_annotation_root": str(default_annotation_root()),
        "default_window_annotation_root": str(default_window_annotation_root()),
    }


__all__ = [
    "content_model_settings",
    "media_library_settings",
    "resolve_media_library_root",
    "resolve_annotation_root",
    "resolve_window_annotation_root",
    "resolve_output_dir",
    "resolve_model_source",
    "resolve_model_cache_dir",
    "settings_summary",
]


