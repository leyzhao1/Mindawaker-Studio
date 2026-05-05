from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field


class VideoRetrievalRequest(BaseModel):
    theme: str = Field(..., description="视频主题或关键词")
    style: Optional[str] = Field(None, description="可选文案风格")
    text_model_name: str = Field(..., description="文本模型名称")
    text_api_key: str = Field(..., description="文本模型 API Key")
    audio_model_name: str = Field(..., description="音频模型名称")
    audio_api_key: str = Field(..., description="音频模型 API Key")
    voice: Optional[str] = Field("alloy", description="音色")
    language: Optional[Literal["zh", "en"]] = Field(None, description="内容语言")
    with_media_prompts: bool = Field(True, description="是否生成 media prompt")
    media_prompt_style: Optional[str] = Field(None, description="media prompt 风格")
    annotation_root: str = Field(..., description="media_service 检索使用的 annotation 目录")
    media_service_base_url: str = Field("http://127.0.0.1:6000", description="media_service 基础地址")
    media_service_timeout_sec: float = Field(180.0, description="media_service 请求超时时间（秒）")
    top_k_per_line: int = Field(3, description="每句文本返回的候选素材数量")
    prefer_media_type: str = Field("auto", description="偏好媒体类型")
    search_mode: Literal["file_level", "window_level"] = Field("window_level", description="检索模式")
    ranking_strategy: Literal["single_stage", "cascade_v1", "cascade_sequence_v1"] = Field("cascade_sequence_v1", description="窗口检索重排策略")
    window_annotation_root: Optional[str] = Field(None, description="窗口索引目录，默认与 annotation_root 相同")
    window_level_preferred: bool = Field(True, description="非窗口模式下是否偏好窗口检索")
    coarse_top_n: int = Field(50, description="窗口检索粗排候选数")
    fine_top_k: int = Field(10, description="窗口检索精排候选数")
    math_background_enabled: bool = Field(True, description="是否允许作为 math 背景资源")


class RetrievalBackgroundAsset(BaseModel):
    index: int
    text: str
    source_path: str
    media_type: str
    color: str = ""
    annotation_path: str = ""
    score: float = 0.0
    audio_path: str = ""
    audio_duration: float = 0.0
    clip_path: str = ""
    retrieval_result: Dict[str, Any] = Field(default_factory=dict)


class RetrievalClip(BaseModel):
    index: int
    clip_path: str = ""
    image_path: str = ""
    audio_path: str = ""
    duration: float = 0.0
    text: str = ""
    dirty: bool = False
    source_path: str = ""
    media_type: str = ""
    color: str = ""
    annotation_path: str = ""
    score: float = 0.0


class VideoRetrievalTaskResponse(BaseModel):
    task_id: str
    project_id: str
    status: str
    message: str


class VideoRetrievalResult(BaseModel):
    success: bool = True
    error: Optional[str] = None
    project_id: str = ""
    video_path: str = ""
    text: str = ""
    lines: List[str] = Field(default_factory=list)
    shot_texts: List[str] = Field(default_factory=list)
    retrieval_texts: List[str] = Field(default_factory=list)
    audios: List[str] = Field(default_factory=list)
    durations: List[float] = Field(default_factory=list)
    scene_segment_files: List[str] = Field(default_factory=list)
    clips: List[RetrievalClip] = Field(default_factory=list)
    video_segments: List[str] = Field(default_factory=list)
    background_assets: List[RetrievalBackgroundAsset] = Field(default_factory=list)
    missing_head_keywords: List[Dict[str, Any]] = Field(default_factory=list)
