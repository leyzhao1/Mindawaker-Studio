from __future__ import annotations

from pathlib import Path

from media_service.analyzers.providers import BaseContentProvider, QwenVLContentProvider
from media_service.config.settings import content_model_settings, resolve_model_cache_dir, resolve_model_source
from media_service.model.schemas import ContentTag


class ContentAnalyzer:
    def __init__(self, provider: BaseContentProvider | None = None) -> None:
        self.provider = provider or self._build_provider()

    def analyze_image(self, path: Path) -> ContentTag:
        try:
            return self.provider.analyze_image(path)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Content analysis failed for image %s", path)
            return fallback_content(path)

    def analyze_video(self, path: Path) -> ContentTag:
        try:
            return self.provider.analyze_video(path, frame_count=content_model_settings.video_frame_count)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Content analysis failed for video %s", path)
            return fallback_content(path)

    def _build_provider(self) -> BaseContentProvider:
        if content_model_settings.provider == "qwen2_5_vl":
            return QwenVLContentProvider(
                model_name=content_model_settings.model_name,
                model_source=resolve_model_source(),
                cache_dir=resolve_model_cache_dir(),
                device=content_model_settings.device,
                max_new_tokens=content_model_settings.max_new_tokens,
            )
        raise ValueError(f"Unsupported content provider: {content_model_settings.provider}")


def fallback_content(path: Path) -> ContentTag:
    return ContentTag(
        caption=f"unavailable content for {path.stem}",
        objects=[],
        scene_tags=[],
        action_tags=[],
    )
