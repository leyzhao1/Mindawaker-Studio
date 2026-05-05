from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np

from media_service.windowing.schema import WindowFeatures


def build_window_sample_timestamps(window_info: Dict[str, Any], sample_fps: float = 1.0, max_frames_per_window: int = 8) -> List[float]:
    start_sec = float(window_info.get("start_sec", 0.0))
    end_sec = float(window_info.get("end_sec", start_sec))
    if end_sec < start_sec:
        end_sec = start_sec
    duration = end_sec - start_sec
    if duration <= 0:
        return [round(start_sec, 4)]
    safe_fps = max(sample_fps, 0.1)
    step = 1.0 / safe_fps
    count = max(1, int(np.floor(duration * safe_fps)) + 1)
    timestamps = [start_sec + index * step for index in range(count)]
    timestamps = [ts for ts in timestamps if ts <= end_sec + 1e-6]
    if not timestamps:
        timestamps = [start_sec]
    if len(timestamps) > max_frames_per_window > 0:
        sampled = np.linspace(0, len(timestamps) - 1, num=max_frames_per_window, dtype=int)
        timestamps = [timestamps[index] for index in sampled]
    return [round(ts, 4) for ts in timestamps]


def count_window_samples(window_info: Dict[str, Any], sample_fps: float = 1.0, max_frames_per_window: int = 8) -> int:
    return len(build_window_sample_timestamps(window_info, sample_fps=sample_fps, max_frames_per_window=max_frames_per_window))


def extract_window_features(video_info: Dict[str, Any], window_info: Dict[str, Any], sample_fps: float = 1.0, max_frames_per_window: int = 8) -> WindowFeatures:
    source_path = Path(str(video_info.get("source_path", ""))).resolve()
    timestamps = build_window_sample_timestamps(window_info, sample_fps=sample_fps, max_frames_per_window=max_frames_per_window)
    if not source_path.exists() or not timestamps:
        return WindowFeatures()
    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        return WindowFeatures()
    try:
        frames: List[np.ndarray] = []
        for ts in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, float(ts) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames.append(frame)
        if not frames:
            return WindowFeatures()

        brightness_values: List[float] = []
        brightness_std_values: List[float] = []
        contrast_values: List[float] = []
        saturation_values: List[float] = []
        edge_density_values: List[float] = []
        texture_values: List[float] = []
        dark_values: List[float] = []
        readability_values: List[float] = []
        motion_raw_values: List[float] = []
        previous_gray: np.ndarray | None = None

        for frame in frames:
            resized = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

            brightness_mean = float(np.mean(gray) / 255.0 * 100.0)
            brightness_std = float(np.std(gray) / 127.5 * 100.0)
            saturation_mean = float(np.mean(hsv[:, :, 1]) / 255.0 * 100.0)
            contrast = brightness_std

            edges = cv2.Canny(gray, 80, 180)
            edge_density = float(np.mean(edges > 0) * 100.0)
            lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            texture = float(min(lap_var / 1500.0, 1.0) * 100.0)
            dark_ratio = float(np.mean(gray < 40) * 100.0)

            edge_balance = 100.0 - min(abs(edge_density - 15.0) * 4.0, 100.0)
            readability = 0.5 * contrast + 0.3 * edge_balance + 0.2 * (100.0 - dark_ratio)
            readability = float(max(0.0, min(100.0, readability)))

            brightness_values.append(brightness_mean)
            brightness_std_values.append(brightness_std)
            contrast_values.append(contrast)
            saturation_values.append(saturation_mean)
            edge_density_values.append(edge_density)
            texture_values.append(texture)
            dark_values.append(dark_ratio)
            readability_values.append(readability)

            if previous_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(previous_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
                motion_raw_values.append(float(np.mean(magnitude)))
            previous_gray = gray

        if motion_raw_values:
            motion_values = [min(value / 8.0, 1.0) * 100.0 for value in motion_raw_values]
            motion_mean = float(np.mean(motion_values))
            motion_std = float(np.std(motion_values))
        else:
            motion_mean = 0.0
            motion_std = 0.0

        return WindowFeatures(
            brightness_mean=float(np.mean(brightness_values)),
            brightness_std=float(np.mean(brightness_std_values)),
            contrast=float(np.mean(contrast_values)),
            saturation_mean=float(np.mean(saturation_values)),
            edge_density=float(np.mean(edge_density_values)),
            texture_complexity=float(np.mean(texture_values)),
            motion_mean=motion_mean,
            motion_std=motion_std,
            dark_background_score=float(np.mean(dark_values)),
            readability_score=float(np.mean(readability_values)),
        )
    finally:
        cap.release()
