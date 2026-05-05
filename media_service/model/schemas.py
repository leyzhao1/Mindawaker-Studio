from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


MediaType = Literal["image", "video"]
PreferMediaType = Literal["image", "video", "mixed", "auto"]
SearchStrategy = Literal["independent", "sequential_coherence"]
WindowSearchMode = Literal["file_level", "window_level"]
RankingStrategy = Literal["single_stage", "cascade_v1", "cascade_sequence_v1"]


class ContentTag(BaseModel):
    caption: str = "unknown"
    objects: List[str] = Field(default_factory=list)
    scene_tags: List[str] = Field(default_factory=list)
    action_tags: List[str] = Field(default_factory=list)


class StyleTag(BaseModel):
    dominant_colors: List[str] = Field(default_factory=list)
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    color_temperature: str = "unknown"
    texture_density: float = 0.0
    aesthetic_score: Optional[float] = None


class CinemaTag(BaseModel):
    framing: str = "unknown"
    camera_angle: str = "unknown"
    lens_feel: str = "unknown"
    movement: str = "unknown"


class EmotionTag(BaseModel):
    primary: str = "unknown"
    secondary: str = "unknown"
    confidence: float = 0.0


class RhythmTag(BaseModel):
    duration: Optional[float] = None
    scene_count: Optional[int] = None
    avg_shot_length: Optional[float] = None
    motion_intensity: Optional[float] = None
    pace: str = "unknown"


class RetrievalHints(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    media_role: str = "unknown"
    duration_bucket: str = "unknown"
    pace_bucket: str = "unknown"
    emotion_bucket: str = "unknown"


class MediaAnnotation(BaseModel):
    source_path: str
    relative_path: str
    file_name: str
    extension: str
    media_type: MediaType
    status: str = "ok"
    error: Optional[str] = None
    content: ContentTag = Field(default_factory=ContentTag)
    style: StyleTag = Field(default_factory=StyleTag)
    cinema: CinemaTag = Field(default_factory=CinemaTag)
    emotion: EmotionTag = Field(default_factory=EmotionTag)
    rhythm: RhythmTag = Field(default_factory=RhythmTag)
    retrieval_hints: RetrievalHints = Field(default_factory=RetrievalHints)


class QueryIntent(BaseModel):
    keywords: List[str] = Field(default_factory=list)
    prefer_media_type: PreferMediaType = "auto"
    preferred_pace: str = "unknown"
    preferred_emotion: str = "unknown"
    preferred_temperature: str = "unknown"
    preferred_brightness: str = "unknown"
    preferred_saturation: str = "unknown"
    preferred_role: str = "unknown"
    estimated_duration: float = 0.0


class ScoreBreakdown(BaseModel):
    keyword_score: float = 0.0
    style_score: float = 0.0
    emotion_score: float = 0.0
    rhythm_score: float = 0.0
    duration_fit_score: float = 0.0
    coherence_score: float = 0.0
    total: float = 0.0


class RetrievalResult(BaseModel):
    source_path: str
    relative_path: str
    media_type: MediaType
    annotation_path: str
    score: ScoreBreakdown
    matched_terms: List[str] = Field(default_factory=list)
    estimated_text_duration: float = 0.0
    media_duration: Optional[float] = None
    duration_fit_score: float = 0.0
    continuity_notes: List[str] = Field(default_factory=list)
    annotation: Optional[Dict[str, Any]] = None
    window_id: Optional[str] = None
    window_level: Optional[float] = None
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    source_scope: str = "file"


class TagScanRequest(BaseModel):
    input_dir: Optional[str] = None
    output_dir: Optional[str] = None
    overwrite: bool = True
    recursive: bool = True


class WindowBuildRequest(BaseModel):
    input_dir: Optional[str] = None
    output_dir: Optional[str] = None
    overwrite: bool = True
    recursive: bool = True
    window_sizes_sec: List[float] = Field(default_factory=lambda: [2.0, 5.0, 10.0])
    stride_ratio: float = 0.5
    sample_fps: float = 1.0
    max_frames_per_window: int = 8
    min_window_coverage_ratio: float = 0.5
    enable_semantic_caption: bool = False


class WindowBuildFileRequest(BaseModel):
    file_path: str
    input_root: Optional[str] = None
    output_dir: Optional[str] = None
    window_sizes_sec: List[float] = Field(default_factory=lambda: [2.0, 5.0, 10.0])
    stride_ratio: float = 0.5
    sample_fps: float = 1.0
    max_frames_per_window: int = 8
    min_window_coverage_ratio: float = 0.5
    enable_semantic_caption: bool = False


class TagFileRequest(BaseModel):
    file_path: str
    input_root: Optional[str] = None
    output_dir: Optional[str] = None
    overwrite: bool = True


class IndexBuildRequest(BaseModel):
    annotation_root: Optional[str] = None


class SearchRequest(BaseModel):
    text: str
    texts: Optional[str | List[str]] = None
    index: Optional[int] = None
    duration: Optional[float] = None
    duration_text: Optional[str] = None
    annotation_root: Optional[str] = None
    top_k: int = 5
    prefer_media_type: PreferMediaType = "auto"
    explain: bool = False
    search_mode: WindowSearchMode = "file_level"
    ranking_strategy: RankingStrategy = "single_stage"
    window_annotation_root: Optional[str] = None
    window_level_preferred: bool = False
    coarse_top_n: int = 50
    fine_top_k: int = 10


class BatchSearchRequest(BaseModel):
    texts: str | List[str]
    duration_texts: Optional[str | List[str]] = None
    durations: Optional[List[float]] = None
    duration: Optional[float] = None
    annotation_root: Optional[str] = None
    top_k_per_line: int = 3
    prefer_media_type: PreferMediaType = "auto"
    strategy: SearchStrategy = "sequential_coherence"
    search_mode: WindowSearchMode = "file_level"
    ranking_strategy: RankingStrategy = "single_stage"
    window_annotation_root: Optional[str] = None
    window_level_preferred: bool = False
    coarse_top_n: int = 50
    fine_top_k: int = 10


class DirectoryListRequest(BaseModel):
    """目录浏览请求"""
    directory: str
    recursive: bool = False


class FileUploadRequest(BaseModel):
    """文件上传请求"""
    directory: str
    overwrite: bool = True


class ExplainRequest(BaseModel):
    text: str
    texts: Optional[str | List[str]] = None
    index: Optional[int] = None
    annotation_path: str
    prefer_media_type: PreferMediaType = "auto"
