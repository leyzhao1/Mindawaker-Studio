from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import cv2
import numpy as np

from media_service.model.schemas import StyleTag


def _clamp_0_100(value: float) -> float:
    return float(max(0.0, min(100.0, value)))


def _bgr_to_hex(color_bgr: Sequence[float]) -> str:
    b, g, r = [int(max(0, min(255, round(c)))) for c in color_bgr]
    return f"#{r:02X}{g:02X}{b:02X}"


def _resize_for_analysis(image: np.ndarray, max_side: int = 512) -> np.ndarray:
    h, w = image.shape[:2]
    if max(h, w) <= max_side:
        return image
    if h >= w:
        new_h = max_side
        new_w = int(w * (max_side / h))
    else:
        new_w = max_side
        new_h = int(h * (max_side / w))
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _extract_dominant_colors(image_bgr: np.ndarray, k: int = 5) -> List[str]:
    small = _resize_for_analysis(image_bgr, max_side=256)
    pixels = small.reshape((-1, 3)).astype(np.float32)
    if len(pixels) == 0:
        return ["unknown"]
    sample_size = min(len(pixels), 5000)
    if len(pixels) > sample_size:
        indices = np.random.choice(len(pixels), sample_size, replace=False)
        pixels = pixels[indices]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=len(centers))
    sorted_indices = np.argsort(counts)[::-1]
    return [_bgr_to_hex(centers[idx]) for idx in sorted_indices]


def _compute_brightness(image_bgr: np.ndarray) -> float:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    return _clamp_0_100(float(np.mean(hsv[:, :, 2]) / 255.0 * 100.0))


def _compute_contrast(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return _clamp_0_100(float(np.std(gray)) / 127.5 * 100.0)


def _compute_saturation(image_bgr: np.ndarray) -> float:
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    return _clamp_0_100(float(np.mean(hsv[:, :, 1]) / 255.0 * 100.0))


def _compute_color_temperature(image_bgr: np.ndarray) -> str:
    mean_b = float(np.mean(image_bgr[:, :, 0]))
    mean_r = float(np.mean(image_bgr[:, :, 2]))
    delta = mean_r - mean_b
    if delta > 15:
        return "warm"
    if delta < -15:
        return "cool"
    return "neutral"


def _compute_texture_density(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return _clamp_0_100(min(lap_var / 1500.0, 1.0) * 100.0)


def compute_style_metrics(image_bgr: np.ndarray) -> StyleTag:
    image_bgr = _resize_for_analysis(image_bgr)
    return StyleTag(
        dominant_colors=_extract_dominant_colors(image_bgr),
        brightness=_compute_brightness(image_bgr),
        contrast=_compute_contrast(image_bgr),
        saturation=_compute_saturation(image_bgr),
        color_temperature=_compute_color_temperature(image_bgr),
        texture_density=_compute_texture_density(image_bgr),
        aesthetic_score=None,
    )


class StyleAnalyzer:
    def analyze_image(self, path: Path) -> StyleTag:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to read image: {path}")
        return compute_style_metrics(image)

    def analyze_video(self, path: Path, max_frames: int = 8) -> StyleTag:
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {path}")
        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if frame_count <= 0:
                raise ValueError(f"Video has no frames: {path}")
            sample_indices = np.linspace(0, max(frame_count - 1, 0), num=min(max_frames, frame_count), dtype=int)
            collected: List[StyleTag] = []
            for frame_index in sample_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                collected.append(compute_style_metrics(frame))
            if not collected:
                raise ValueError(f"Failed to sample frames from video: {path}")
            all_colors: List[str] = []
            for style in collected:
                all_colors.extend(style.dominant_colors[:3])
            dominant_colors = list(dict.fromkeys(all_colors))[:5]
            temperatures = [style.color_temperature for style in collected]
            color_temperature = max(set(temperatures), key=temperatures.count)
            return StyleTag(
                dominant_colors=dominant_colors,
                brightness=float(np.mean([style.brightness for style in collected])),
                contrast=float(np.mean([style.contrast for style in collected])),
                saturation=float(np.mean([style.saturation for style in collected])),
                color_temperature=color_temperature,
                texture_density=float(np.mean([style.texture_density for style in collected])),
                aesthetic_score=None,
            )
        finally:
            cap.release()
