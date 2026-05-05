from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from media_service.analyzers.content import ContentAnalyzer
from media_service.analyzers.emotion import EmotionAnalyzer
from media_service.analyzers.rhythm import RhythmAnalyzer
from media_service.analyzers.style import StyleAnalyzer
from media_service.model.schemas import MediaAnnotation, RetrievalHints
from media_service.utils.io import build_output_json_path, is_image_file, is_video_file, safe_relative_path, scan_media_files, write_json

logger = logging.getLogger(__name__)


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


class TaggingService:
    def __init__(self) -> None:
        self.content_analyzer = ContentAnalyzer()
        self.style_analyzer = StyleAnalyzer()
        self.rhythm_analyzer = RhythmAnalyzer()
        self.emotion_analyzer = EmotionAnalyzer()

    def process_directory(self, input_dir: Path, output_dir: Path, overwrite: bool = True, recursive: bool = True) -> Dict[str, Any]:
        logger.info("Start tagging directory: input=%s output=%s overwrite=%s recursive=%s", input_dir, output_dir, overwrite, recursive)
        output_dir.mkdir(parents=True, exist_ok=True)
        media_files = scan_media_files(input_dir, recursive=recursive)
        logger.info("Discovered %s media files under %s", len(media_files), input_dir)
        errors: List[Dict[str, str]] = []
        processed = 0
        failed = 0
        outputs: List[str] = []
        total_files = len(media_files)
        for index, media_path in enumerate(media_files, start=1):
            output_path = build_output_json_path(media_path, input_dir, output_dir)
            logger.info("[%s/%s] Tagging file: %s -> %s", index, total_files, media_path, output_path)
            if output_path.exists() and not overwrite:
                logger.info("[%s/%s] Skip existing annotation for %s", index, total_files, media_path)
                outputs.append(str(output_path))
                continue
            try:
                annotation = self.process_file(media_path=media_path, input_root=input_dir)
                write_json(output_path, annotation.model_dump(mode="json"))
                outputs.append(str(output_path))
                processed += 1
                logger.info("[%s/%s] Tagged successfully: %s", index, total_files, media_path)
            except Exception as exc:
                failed += 1
                logger.exception("[%s/%s] Tagging failed for %s", index, total_files, media_path)
                errors.append({"source_path": str(media_path), "error": str(exc)})
                error_annotation = self._error_annotation(media_path=media_path, input_root=input_dir, error=str(exc))
                write_json(output_path, error_annotation.model_dump(mode="json"))
                outputs.append(str(output_path))
        logger.info("Finished tagging directory: scanned=%s processed=%s failed=%s output_dir=%s", len(media_files), processed, failed, output_dir)
        return {
            "success": True,
            "scanned": len(media_files),
            "processed": processed,
            "failed": failed,
            "errors": errors,
            "outputs": outputs,
        }

    def process_file(self, media_path: Path, input_root: Path) -> MediaAnnotation:
        logger.info("Process file: %s", media_path)
        if is_image_file(media_path):
            logger.info("Detected image file: %s", media_path)
            return self._process_image(media_path, input_root)
        if is_video_file(media_path):
            logger.info("Detected video file: %s", media_path)
            return self._process_video(media_path, input_root)
        raise ValueError(f"Unsupported media file: {media_path}")

    def _process_image(self, media_path: Path, input_root: Path) -> MediaAnnotation:
        logger.info("Analyzing image content/style: %s", media_path)
        content = self.content_analyzer.analyze_image(media_path)
        style = self.style_analyzer.analyze_image(media_path)
        rhythm = self.rhythm_analyzer.empty_for_image()
        emotion = self.emotion_analyzer.analyze(style, rhythm)
        return MediaAnnotation(
            source_path=str(media_path.resolve()),
            relative_path=safe_relative_path(media_path, input_root),
            file_name=media_path.name,
            extension=media_path.suffix.lower(),
            media_type="image",
            content=content,
            style=style,
            emotion=emotion,
            rhythm=rhythm,
            retrieval_hints=self._build_retrieval_hints(content, emotion, rhythm),
        )

    def _process_video(self, media_path: Path, input_root: Path) -> MediaAnnotation:
        logger.info("Analyzing video content/style/rhythm: %s", media_path)
        content = self.content_analyzer.analyze_video(media_path)
        style = self.style_analyzer.analyze_video(media_path)
        rhythm = self.rhythm_analyzer.analyze_video(media_path)
        emotion = self.emotion_analyzer.analyze(style, rhythm)
        movement = "unknown"
        if rhythm.motion_intensity is not None:
            if rhythm.motion_intensity >= 70:
                movement = "high_motion"
            elif rhythm.motion_intensity >= 40:
                movement = "medium_motion"
            else:
                movement = "low_motion"
        annotation = MediaAnnotation(
            source_path=str(media_path.resolve()),
            relative_path=safe_relative_path(media_path, input_root),
            file_name=media_path.name,
            extension=media_path.suffix.lower(),
            media_type="video",
            content=content,
            style=style,
            cinema={"framing": "unknown", "camera_angle": "unknown", "lens_feel": "unknown", "movement": movement},
            emotion=emotion,
            rhythm=rhythm,
            retrieval_hints=self._build_retrieval_hints(content, emotion, rhythm),
        )
        return annotation

    def _build_retrieval_hints(self, content, emotion, rhythm) -> RetrievalHints:
        keywords = []
        for value in [content.caption, *content.objects, *content.scene_tags, *content.action_tags, emotion.primary, emotion.secondary]:
            if value and value != "unknown":
                keywords.append(str(value).lower())
        unique_keywords = list(dict.fromkeys(keywords))[:20]
        duration_bucket = "unknown"
        if rhythm.duration is not None:
            if rhythm.duration < 5:
                duration_bucket = "short"
            elif rhythm.duration < 15:
                duration_bucket = "medium"
            else:
                duration_bucket = "long"
        media_role = "action" if rhythm.motion_intensity and rhythm.motion_intensity >= 50 else "background"
        return RetrievalHints(
            keywords=unique_keywords,
            media_role=media_role,
            duration_bucket=duration_bucket,
            pace_bucket=rhythm.pace,
            emotion_bucket=emotion.primary,
        )

    def _error_annotation(self, media_path: Path, input_root: Path, error: str) -> MediaAnnotation:
        media_type = "video" if is_video_file(media_path) else "image"
        return MediaAnnotation(
            source_path=str(media_path.resolve()),
            relative_path=safe_relative_path(media_path, input_root),
            file_name=media_path.name,
            extension=media_path.suffix.lower(),
            media_type=media_type,
            status="error",
            error=error,
        )
