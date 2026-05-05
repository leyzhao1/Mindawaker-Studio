from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WindowFeatures(BaseModel):
    brightness_mean: float = 0.0
    brightness_std: float = 0.0
    contrast: float = 0.0
    saturation_mean: float = 0.0
    edge_density: float = 0.0
    texture_complexity: float = 0.0
    motion_mean: float = 0.0
    motion_std: float = 0.0
    dark_background_score: float = 0.0
    readability_score: float = 0.0


class WindowSemanticTag(BaseModel):
    caption: Optional[str] = None
    objects: List[str] = Field(default_factory=list)
    scene_tags: List[str] = Field(default_factory=list)
    action_tags: List[str] = Field(default_factory=list)


class WindowBuildConfig(BaseModel):
    window_sizes_sec: List[float] = Field(default_factory=list)
    stride_ratio: float = 0.5
    sample_fps: float = 1.0
    max_frames_per_window: int = 8
    min_window_coverage_ratio: float = 0.5


class WindowKey(BaseModel):
    semantic_keywords: List[str] = Field(default_factory=list)
    preferred_role_hint: str = "unknown"
    pace_bucket: str = "unknown"
    emotion_bucket: str = "unknown"
    brightness_bucket: str = "unknown"
    motion_bucket: str = "unknown"


class WindowValue(BaseModel):
    representative_frame_ts: Optional[float] = None
    subclip_start_sec: Optional[float] = None
    subclip_end_sec: Optional[float] = None
    frame_count_sampled: int = 0


class VideoWindowAnnotation(BaseModel):
    window_id: str
    source_path: str
    relative_path: str
    level: float
    window_size_sec: float
    stride_sec: float
    start_sec: float
    end_sec: float
    duration_sec: float
    sample_count: int = 0
    sample_fps: float = 1.0
    features: WindowFeatures = Field(default_factory=WindowFeatures)
    semantic: WindowSemanticTag = Field(default_factory=WindowSemanticTag)
    key: WindowKey = Field(default_factory=WindowKey)
    value: WindowValue = Field(default_factory=WindowValue)
    embeddings: Dict[str, Any] = Field(default_factory=lambda: {"semantic": None, "style": None})


class VideoWindowIndex(BaseModel):
    version: str = "0.1"
    source_path: str
    relative_path: str
    file_name: str
    duration_sec: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    build_config: WindowBuildConfig = Field(default_factory=WindowBuildConfig)
    windows: List[VideoWindowAnnotation] = Field(default_factory=list)
