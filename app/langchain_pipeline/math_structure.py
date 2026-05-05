from __future__ import annotations

from enum import Enum
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.langchain_pipeline.base_text import BaseTextGenerator


# ---------- Enums ----------
class PersonaPos(str, Enum):
    center = "center"
    left_bottom = "left_bottom"


class MathPlan(str, Enum):
    write_then_hold = "write_then_hold"
    sequential_reveal = "sequential_reveal"
    stepwise_reveal_and_highlight = "stepwise_reveal_and_highlight"
    transform_and_highlight = "transform_and_highlight"
    substitute_and_emphasize = "substitute_and_emphasize"
    final_reveal_and_hold = "final_reveal_and_hold"


class TextPos(str, Enum):
    top_center = "top_center"
    bottom_center = "bottom_center"
    center = "center"
    left = "left"
    right = "right"


class TextAnim(str, Enum):
    fade_in_hold_fade_out = "fade_in_hold_fade_out"
    typewriter = "typewriter"
    pop = "pop"
    highlight = "highlight"


class TextStyle(str, Enum):
    title = "title"
    subtitle = "subtitle"
    body = "body"
    label = "label"


class TextOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    pos: TextPos = TextPos.top_center
    style: TextStyle = TextStyle.body
    anim: TextAnim = TextAnim.fade_in_hold_fade_out


# ---------- Leaf models ----------
class BgPrompt(BaseModel):
    """
    Correct spelling: bg_prompt
    Old spelling alias: bg_promt
    """
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    type: Literal["image"] = "image"
    prompt: str


class Formula(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    latex: str


class Persona(BaseModel):
    """
    Correct spelling: persona
    Old spelling alias: pensena (typo) is handled in Shot via alias on the field.
    """
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    image_prompt: str
    pos: PersonaPos = PersonaPos.left_bottom
    scale: float = 0.22

    @field_validator("scale")
    @classmethod
    def validate_scale(cls, v: float) -> float:
        # 经验范围：0.1 ~ 0.6
        if not (0.1 <= v <= 0.6):
            raise ValueError("persona.scale must be between 0.1 and 0.6")
        return v


class Math(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    formulas: List[Formula] = Field(default_factory=list)
    plan: Optional[MathPlan] = None


class Shot(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    shot_id: str

    # Correct: persona
    # Accept old typo key: "pensena" in input JSON
    # persona: Persona = Field(validation_alias="pensena")

    narration: str
    math: Math = Field(default_factory=Math)
    text_overlays: List[TextOverlay] = Field(default_factory=list)

    @field_validator("shot_id")
    @classmethod
    def validate_shot_id(cls, v: str) -> str:
        # 要求格式 s1, s2, s10...
        if not v.startswith("s") or not v[1:].isdigit():
            raise ValueError("shot_id must look like 's1', 's2', ...")
        return v


class Scene(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    scene_id: str
    setup_text: str

    # Correct: bg_prompt
    # Accept old typo key: "bg_promt"
    bg_prompt: BgPrompt = Field(validation_alias="bg_promt")

    shots: List[Shot] = Field(default_factory=list)

    @field_validator("shots")
    @classmethod
    def validate_unique_shot_ids(cls, shots: List[Shot]) -> List[Shot]:
        ids = [s.shot_id for s in shots]
        if len(ids) != len(set(ids)):
            raise ValueError("shot_id must be unique within a scene")
        return shots


class Storyboard(BaseModel):
    """
    A whole article output: multiple scenes.
    """
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    scenes: List[Scene] = Field(default_factory=list)

    @field_validator("scenes")
    @classmethod
    def validate_unique_scene_ids(cls, scenes: List[Scene]) -> List[Scene]:
        ids = [s.scene_id for s in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene_id must be unique across storyboard")
        return scenes


# ========= LLM 封装 =========


class MathSturctureChainGenerator(BaseTextGenerator):
    """数学结构生成器 - 固定使用 DeepSeek 模型"""

    def generate(self, prompt: str) -> str:
        """生成数学结构"""
        response = self._invoke_model(prompt)
        return response["content"].strip()
