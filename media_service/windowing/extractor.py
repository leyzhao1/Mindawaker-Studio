from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

import cv2

from media_service.utils.io import safe_relative_path
from media_service.windowing.features import count_window_samples, extract_window_features
from media_service.windowing.schema import VideoWindowAnnotation, VideoWindowIndex, WindowBuildConfig, WindowKey, WindowValue
from media_service.windowing.semantic import WindowSemanticExtractor


class WindowExtractor:
    def __init__(self) -> None:
        self.semantic_extractor = WindowSemanticExtractor()

    def extract_video_windows(self, video_path: Path, input_root: Path, config: WindowBuildConfig, enable_semantic_caption: bool = False) -> VideoWindowIndex:
        source_path = video_path.resolve()
        metadata = self._video_metadata(source_path)
        relative_path = safe_relative_path(source_path, input_root)
        windows: List[VideoWindowAnnotation] = []
        duration_sec = metadata["duration_sec"]

        for window_size_sec in config.window_sizes_sec:
            if window_size_sec <= 0:
                continue
            stride_sec = max(window_size_sec * config.stride_ratio, 0.1)
            for start_sec, end_sec in self._iter_window_ranges(duration_sec, window_size_sec, stride_sec, config.min_window_coverage_ratio):
                level = float(window_size_sec)
                window_info = {
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "window_size_sec": float(window_size_sec),
                    "stride_sec": float(stride_sec),
                    "level": level,
                }
                video_info = {
                    "source_path": str(source_path),
                    "duration_sec": duration_sec,
                    "fps": metadata["fps"],
                    "width": metadata["width"],
                    "height": metadata["height"],
                    "relative_path": relative_path,
                }
                features = extract_window_features(
                    video_info=video_info,
                    window_info=window_info,
                    sample_fps=config.sample_fps,
                    max_frames_per_window=config.max_frames_per_window,
                )
                #临时添加
                print("before use semantic extractor")
                semantic = (
                    self.semantic_extractor.extract(
                        video_info=video_info,
                        window_info=window_info,
                        sample_fps=config.sample_fps,
                        max_frames_per_window=config.max_frames_per_window,
                    )
                    if enable_semantic_caption
                    else self.semantic_extractor.empty()
                )
                sample_count = count_window_samples(window_info, sample_fps=config.sample_fps, max_frames_per_window=config.max_frames_per_window)
                duration = max(end_sec - start_sec, 0.0)
                key = self._build_window_key(features=features, semantic=semantic)
                value = WindowValue(
                    representative_frame_ts=round((start_sec + end_sec) / 2.0, 4),
                    subclip_start_sec=round(start_sec, 4),
                    subclip_end_sec=round(end_sec, 4),
                    frame_count_sampled=sample_count,
                )
                window_id = self._build_window_id(relative_path, level, start_sec, end_sec)
                windows.append(
                    VideoWindowAnnotation(
                        window_id=window_id,
                        source_path=str(source_path),
                        relative_path=relative_path,
                        level=level,
                        window_size_sec=float(window_size_sec),
                        stride_sec=float(stride_sec),
                        start_sec=round(start_sec, 4),
                        end_sec=round(end_sec, 4),
                        duration_sec=round(duration, 4),
                        sample_count=sample_count,
                        sample_fps=config.sample_fps,
                        features=features,
                        semantic=semantic,
                        key=key,
                        value=value,
                    )
                )

        return VideoWindowIndex(
            source_path=str(source_path),
            relative_path=relative_path,
            file_name=source_path.name,
            duration_sec=metadata["duration_sec"],
            fps=metadata["fps"],
            width=metadata["width"],
            height=metadata["height"],
            build_config=config,
            windows=windows,
        )

    def _video_metadata(self, video_path: Path) -> Dict[str, float | int]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {"duration_sec": 0.0, "fps": 0.0, "width": 0, "height": 0}
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration_sec = float(frame_count / fps) if fps > 0 else 0.0
            return {
                "duration_sec": round(max(duration_sec, 0.0), 4),
                "fps": round(max(fps, 0.0), 4),
                "width": width,
                "height": height,
            }
        finally:
            cap.release()

    def _iter_window_ranges(self, duration_sec: float, window_size_sec: float, stride_sec: float, min_coverage_ratio: float):
        if duration_sec <= 0:
            return
        cursor = 0.0
        seen = set()
        while cursor < duration_sec + 1e-8:
            end_sec = min(cursor + window_size_sec, duration_sec)
            actual_duration = max(end_sec - cursor, 0.0)
            coverage = actual_duration / window_size_sec if window_size_sec > 0 else 0.0
            key = (round(cursor, 4), round(end_sec, 4))
            if coverage >= min_coverage_ratio and key not in seen:
                seen.add(key)
                yield round(cursor, 4), round(end_sec, 4)
            if end_sec >= duration_sec:
                break
            cursor += stride_sec
        if duration_sec < window_size_sec:
            key = (0.0, round(duration_sec, 4))
            coverage = duration_sec / window_size_sec
            if coverage >= min_coverage_ratio and key not in seen:
                yield 0.0, round(duration_sec, 4)

    def _bucket_brightness(self, value: float) -> str:
        if value >= 65:
            return "bright"
        if value <= 35:
            return "dark"
        return "normal"

    def _bucket_motion(self, value: float) -> str:
        if value >= 65:
            return "high"
        if value >= 35:
            return "medium"
        return "low"

    def _bucket_emotion(self, semantic) -> str:
        text = " ".join([semantic.caption or "", *semantic.action_tags, *semantic.scene_tags]).lower()
        if any(token in text for token in ["happy", "joy", "开心", "快乐"]):
            return "joyful"
        if any(token in text for token in ["sad", "悲伤", "忧郁"]):
            return "melancholic"
        if any(token in text for token in ["tense", "紧张", "悬疑"]):
            return "tense"
        return "unknown"

    def _bucket_pace(self, features) -> str:
        if features.motion_mean >= 65:
            return "fast"
        if features.motion_mean >= 35:
            return "medium"
        return "slow"

    def _infer_role_hint(self, semantic) -> str:
        text = " ".join([semantic.caption or "", *semantic.scene_tags, *semantic.action_tags]).lower()
        if any(token in text for token in ["transition", "过渡", "转场"]):
            return "transition"
        if any(token in text for token in ["action", "fight", "run", "运动", "追逐"]):
            return "action"
        return "background"

    def _build_window_key(self, features, semantic) -> WindowKey:
        semantic_keywords = []
        for value in [semantic.caption, *semantic.objects, *semantic.scene_tags, *semantic.action_tags]:
            if value:
                semantic_keywords.append(str(value).strip().lower())
        semantic_keywords = list(dict.fromkeys([item for item in semantic_keywords if item]))[:32]
        return WindowKey(
            semantic_keywords=semantic_keywords,
            preferred_role_hint=self._infer_role_hint(semantic),
            pace_bucket=self._bucket_pace(features),
            emotion_bucket=self._bucket_emotion(semantic),
            brightness_bucket=self._bucket_brightness(features.brightness_mean),
            motion_bucket=self._bucket_motion(features.motion_mean),
        )

    def _build_window_id(self, relative_path: str, level: float, start_sec: float, end_sec: float) -> str:
        start_ms = int(round(start_sec * 1000.0))
        end_ms = int(round(end_sec * 1000.0))
        raw = f"{relative_path}|{level}|{start_ms}|{end_ms}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
