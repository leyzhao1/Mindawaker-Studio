"""
Shot JSON 的 Pydantic 数据模型
提供类型安全的数据验证和序列化
"""
from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field, validator


class CameraConfig(BaseModel):
    """相机配置"""
    view: Literal["front", "side", "top", "three_quarter", "low_angle", "high_angle"] = "side"
    shot: Literal["extreme_closeup", "closeup", "medium", "full", "wide", "establishing"] = "medium"
    position: Optional[dict] = None  # {x, y, z}
    target: Optional[dict] = None    # {x, y, z}
    fov: Optional[float] = None


class Object3D(BaseModel):
    """3D 物体定义"""
    id: str = Field(..., description="物体唯一标识")
    type: Literal[
        "child", "adult", "table", "chair", "flowerpot", "book", "lamp",
        "building", "tree", "car", "bridge", "river"
    ] = Field(..., description="物体类型")
    position: Optional[Literal["left", "center", "right", "front", "back"]] = "center"
    coordinates: Optional[dict] = None  # 精确坐标 {x, y, z}
    scale: Optional[dict] = None        # {x, y, z}
    rotation: Optional[dict] = None     # {x, y, z}
    relation: Optional[str] = None      # "on_top_of:id" | "beside:id" | "behind:id" | "in_front_of:id"

    @validator('relation')
    def validate_relation(cls, v):
        """验证 relation 格式"""
        if v is None:
            return v
        valid_prefixes = ['on_top_of:', 'beside:', 'behind:', 'in_front_of:', 'inside:']
        if not any(v.startswith(prefix) for prefix in valid_prefixes):
            raise ValueError(f'relation must start with one of {valid_prefixes}')
        return v


class LightingConfig(BaseModel):
    """光照配置"""
    type: Literal["day", "night", "sunset", "indoor_warm", "indoor_cool"] = "indoor_warm"
    direction: Optional[dict] = None    # {x, y, z}


class ShotJSON(BaseModel):
    """
    Shot JSON 数据模型 - 系统的核心中间表示
    """
    template: Literal["indoor_room", "street", "bridge_river"] = Field(
        ...,
        description="场景模板类型"
    )
    camera: CameraConfig = Field(default_factory=CameraConfig)
    objects: List[Object3D] = Field(default_factory=list)
    lighting: LightingConfig = Field(default_factory=LightingConfig)
    style_prompt: str = Field(default="", description="生成图像的风格提示词")

    class Config:
        """Pydantic 配置"""
        extra = "forbid"  # 禁止额外字段，确保数据严格符合 schema
        json_schema_extra = {
            "example": {
                "template": "indoor_room",
                "camera": {"view": "side", "shot": "medium"},
                "objects": [
                    {"id": "child1", "type": "child", "position": "left"},
                    {"id": "table1", "type": "table", "position": "center"},
                    {"id": "flowerpot1", "type": "flowerpot", "relation": "on_top_of:table1"}
                ],
                "lighting": {"type": "indoor_warm"},
                "style_prompt": "warm indoor lighting, storybook illustration"
            }
        }

    def to_dict(self) -> dict:
        """转换为字典（过滤 None 值）"""
        return self.model_dump(exclude_none=True)

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON 字符串"""
        return self.model_dump_json(indent=indent, exclude_none=True)


def validate_shot_json(data: dict) -> ShotJSON:
    """
    验证并解析 Shot JSON 数据

    Args:
        data: 原始字典数据

    Returns:
        验证后的 ShotJSON 对象

    Raises:
        ValidationError: 数据验证失败
    """
    return ShotJSON(**data)


def safe_validate_shot_json(data: dict) -> tuple[bool, Union[ShotJSON, str]]:
    """
    安全地验证 Shot JSON 数据

    Returns:
        (是否成功, ShotJSON对象或错误信息)
    """
    try:
        return True, ShotJSON(**data)
    except Exception as e:
        return False, str(e)
