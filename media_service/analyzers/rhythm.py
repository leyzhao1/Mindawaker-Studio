from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector

from media_service.model.schemas import RhythmTag


def _detect_scenes(path: Path, threshold: float = 27.0) -> List[Tuple[float, float]]:
    video = open_video(str(path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()
    return [(float(start.get_seconds()), float(end.get_seconds())) for start, end in scene_list]


def _compute_video_duration(cap: cv2.VideoCapture) -> Tuple[Optional[float], int, Optional[float]]:
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        return None, frame_count, None
    return frame_count / fps, frame_count, fps


def _compute_motion_intensity(cap: cv2.VideoCapture, max_samples: int = 120) -> float:
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if frame_count <= 1:
        return 0.0
    sample_indices = np.linspace(0, max(frame_count - 2, 0), num=min(max_samples, frame_count - 1), dtype=int)
    motion_values: List[float] = []
    previous_gray = None
    for index in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)
        if previous_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(previous_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
            motion_values.append(float(np.mean(magnitude)))
        previous_gray = gray
    if not motion_values:
        return 0.0
    raw = float(np.mean(motion_values))
    return round(min(raw / 8.0, 1.0) * 100.0, 4)


def _infer_pace(avg_shot_length: Optional[float], motion_intensity: Optional[float]) -> str:
    if avg_shot_length is None or motion_intensity is None:
        return "unknown"
    if avg_shot_length < 2.5 or motion_intensity >= 70:
        return "fast"
    if avg_shot_length < 5.5 or motion_intensity >= 40:
        return "medium"
    return "slow"


class RhythmAnalyzer:
    def analyze_video(self, path: Path) -> RhythmTag:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {path}")
        try:
            duration, _, _ = _compute_video_duration(cap)
            motion_intensity = _compute_motion_intensity(cap)
            try:
                scenes = _detect_scenes(path)
            except Exception:
                scenes = []
            if scenes:
                scene_count = len(scenes)
                shot_lengths = [max(end - start, 0.0) for start, end in scenes]
                avg_shot_length = float(sum(shot_lengths) / len(shot_lengths)) if shot_lengths else None
            else:
                scene_count = 1 if duration is not None else None
                avg_shot_length = duration
            pace = _infer_pace(avg_shot_length, motion_intensity)
            return RhythmTag(
                duration=round(duration, 4) if duration is not None else None,
                scene_count=scene_count,
                avg_shot_length=round(avg_shot_length, 4) if avg_shot_length is not None else None,
                motion_intensity=round(motion_intensity, 4),
                pace=pace,
            )
        finally:
            cap.release()

    def empty_for_image(self) -> RhythmTag:
        return RhythmTag(duration=None, scene_count=None, avg_shot_length=None, motion_intensity=None, pace="unknown")
