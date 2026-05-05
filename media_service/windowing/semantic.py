from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List

import cv2

from media_service.analyzers.content import ContentAnalyzer
from media_service.model.schemas import ContentTag
from media_service.windowing.features import build_window_sample_timestamps
from media_service.windowing.schema import WindowSemanticTag


class WindowSemanticExtractor:
    def __init__(self) -> None:
        analyzer = ContentAnalyzer()
        self.provider = analyzer.provider

    def empty(self) -> WindowSemanticTag:
        return WindowSemanticTag()

    def extract(self, video_info: Dict[str, Any], window_info: Dict[str, Any], sample_fps: float = 1.0, max_frames_per_window: int = 8) -> WindowSemanticTag:
        source_path = Path(str(video_info.get("source_path", ""))).resolve()
        if not source_path.exists():
            return WindowSemanticTag()
        timestamps = build_window_sample_timestamps(window_info, sample_fps=sample_fps, max_frames_per_window=max_frames_per_window)
        if not timestamps:
            return WindowSemanticTag()
        frame_paths = self._extract_frames_for_timestamps(source_path, timestamps)
        if not frame_paths:
            return WindowSemanticTag()
        try:
            frame_results: List[ContentTag] = []
            for frame_path in frame_paths:
                frame_results.append(self.provider.analyze_image(frame_path))
            merged = self.provider.summarize_frames(frame_results)
            return WindowSemanticTag(
                caption=merged.caption,
                objects=merged.objects,
                scene_tags=merged.scene_tags,
                action_tags=merged.action_tags,
            )
        except Exception:
            return WindowSemanticTag()
        finally:
            for frame_path in frame_paths:
                frame_path.unlink(missing_ok=True)

    def _extract_frames_for_timestamps(self, video_path: Path, timestamps: List[float]) -> List[Path]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []
        output_paths: List[Path] = []
        try:
            for ts in timestamps:
                cap.set(cv2.CAP_PROP_POS_MSEC, float(ts) * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    temp_path = Path(tmp.name)
                cv2.imwrite(str(temp_path), frame)
                output_paths.append(temp_path)
        finally:
            cap.release()
        return output_paths
