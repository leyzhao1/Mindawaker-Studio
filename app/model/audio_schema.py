"""
app/model/audio_schema.py
==========================
定义音频生成的输入与输出结构。
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal


class AudioRequest(BaseModel):
    # pid:str=Field(...,description="项目ID")
    text: str = Field(..., description="要转换为语音的文本内容")
    audio_api_key: str = Field(..., description="用于 TTS 模型的 API Key")
    voice: Optional[str] = Field("alloy", description="语音类型（如 alloy, verse, nova）")
    audio_model_name: str = Field("openai", description="使用的引擎，可选：openai / auralis")
    language: Optional[Literal["zh", "en"]] = Field(None, description="文本语言")

class AudioResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    audio_path: str = Field("", description="生成的音频文件路径")
    duration: float = Field(0, description="音频时长（秒）")
