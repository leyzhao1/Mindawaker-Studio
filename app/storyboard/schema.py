from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


SceneType = Literal["title_card", "content", "transition", "summary"]
SceneLayoutMode = Literal[
    "stack_with_footer",
    "two_col",
    "card_row",
    "summary_stack",
    "plot_with_side_annotation",
]
NodeRole = Literal["primary", "secondary", "note", "remark", "overlay", "caption"]
NodeLayoutHint = Literal["vertical", "horizontal", "overlay", "anchor_relative", "auto_grid"]
NodeType = Literal[
    "title_card",
    "transition_note",
    "formula_focus",
    "axes_curve",
    "number_sequence",
    "comparison_boxes",
    "summary_block",
    "text_label",
    "rich_text_label",
    "relation_map",
    "stat_bar_grid",
    "process_flow",
    "group",
    "timeline",
    "state_machine",
    "layer_stack",
    "table_grid",
    "code_panel",
    "callout_panel",
    "concept_map",
    "before_after_panel",
    "pipeline_chain",
    "terminal_output",
    "space_bridge",
    "memory_grid",
    "address_space",
    "stack_frame_trace",
    "cpu_state",
    "instruction_cycle",
    "array_cells",
    "linked_list",
    "tree_diagram",
]


class StoryboardValidationError(ValueError):
    def __init__(self, message: str, *, code: str, details: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or []


class VideoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    subject: str
    target_audience: str
    aspect_ratio: str = "16:9"


class GlobalStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    color_preset: str | None = None
    font_preset: str | None = None
    animation_preset: str | None = None


class HeaderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    color: str | None = None
    size: float | None = None


class NarrationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class NarrationChunkSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    text: str
    start: float
    end: float

    @model_validator(mode="after")
    def validate_range(self):
        if self.start < 0:
            raise ValueError("narration_chunks.start must be >= 0")
        if self.end <= self.start:
            raise ValueError("narration_chunks.end must be greater than narration_chunks.start")
        return self


class TimingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hold_after: float | None = None
    duration_hint: float | None = None


class TransitionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    enter_kind: str | None = None
    exit_kind: str | None = None
    run_time: float | None = None


class ArrowAnchorHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["top", "bottom", "left", "right"] | None = None
    offset_ratio: float = 0.5


class InterArrowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    label: str | None = None
    color: str | None = None
    stroke_width: float = 2.4
    source_anchor: ArrowAnchorHint | None = None
    target_anchor: ArrowAnchorHint | None = None
    style: Literal["straight", "curved"] = "straight"


class AssetRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_type: str
    query: str | None = None
    key: str | None = None


class NodeTimingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_s: float | None = None
    end_s: float | None = None
    align_chunk_id: str | None = None
    offset_s: float | None = None

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_s is not None and self.start_s < 0:
            raise ValueError("timing.start_s must be >= 0")
        if self.end_s is not None and self.end_s < 0:
            raise ValueError("timing.end_s must be >= 0")
        if self.start_s is not None and self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError("timing.end_s must be greater than timing.start_s")
        return self


class NodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    type: NodeType
    role: NodeRole = "primary"
    layout_hint: NodeLayoutHint | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    timing: NodeTimingSpec | None = None
    children: list["NodeSpec"] = Field(default_factory=list)


class SceneSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: str
    scene_type: SceneType
    layout_mode: SceneLayoutMode
    clear_policy: Literal["clear_all", "keep_header", "keep_nodes", "manual"] = "clear_all"
    header: HeaderSpec | None = None
    narration: NarrationSpec | None = None
    narration_chunks: list[NarrationChunkSpec] = Field(default_factory=list)
    nodes: list[NodeSpec] = Field(default_factory=list)
    transitions: TransitionSpec | None = None
    timing: TimingSpec | None = None
    asset_requirements: list[AssetRequirement] = Field(default_factory=list)
    inter_arrows: list[InterArrowSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_node_timing_bounds(self):
        duration_hint = None
        if self.timing is not None and self.timing.duration_hint is not None:
            duration_hint = float(self.timing.duration_hint)
            if duration_hint <= 0:
                duration_hint = None

        if duration_hint is None:
            return self

        def _walk(nodes: list[NodeSpec]):
            for node in nodes:
                yield node
                if node.children:
                    yield from _walk(node.children)

        for node in _walk(self.nodes):
            if node.timing is None:
                continue
            if node.timing.start_s is not None and node.timing.start_s > duration_hint + 1e-6:
                raise ValueError(f"node {node.key} timing.start_s exceeds scene duration_hint")
            if node.timing.end_s is not None and node.timing.end_s > duration_hint + 1e-6:
                raise ValueError(f"node {node.key} timing.end_s exceeds scene duration_hint")

        return self


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["mw_storyboard_v1"]
    video_id: str
    lang: str
    theme: str
    metadata: VideoMetadata
    global_style: GlobalStyle | None = None
    scenes: list[SceneSpec] = Field(default_factory=list)

    @field_validator("scenes")
    @classmethod
    def validate_unique_scene_ids(cls, scenes: list[SceneSpec]) -> list[SceneSpec]:
        ids = [s.scene_id for s in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("scene_id must be unique across storyboard")
        return scenes


NodeSpec.model_rebuild()


def _format_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    details = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []))
        details.append(
            {
                "loc": loc,
                "type": err.get("type", "validation_error"),
                "msg": err.get("msg", "Invalid value"),
                "input": err.get("input"),
            }
        )
    return details


def validate_storyboard_json(raw_text: str) -> Storyboard:
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise StoryboardValidationError(
            "Storyboard input is empty",
            code="empty_input",
            details=[],
        )

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise StoryboardValidationError(
            f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})",
            code="json_parse_error",
            details=[
                {
                    "line": exc.lineno,
                    "column": exc.colno,
                    "msg": exc.msg,
                }
            ],
        ) from exc

    try:
        return Storyboard.model_validate(parsed)
    except ValidationError as exc:
        details = _format_validation_errors(exc)
        raise StoryboardValidationError(
            "Storyboard schema validation failed",
            code="schema_validation_error",
            details=details,
        ) from exc


def ensure_storyboard(value: Storyboard | dict[str, Any] | str) -> Storyboard:
    if isinstance(value, Storyboard):
        return value
    if isinstance(value, str):
        return validate_storyboard_json(value)
    if not isinstance(value, dict):
        raise StoryboardValidationError(
            "Storyboard input must be Storyboard, dict, or JSON string",
            code="invalid_input_type",
            details=[{"input_type": type(value).__name__}],
        )
    try:
        return Storyboard.model_validate(value)
    except ValidationError as exc:
        details = _format_validation_errors(exc)
        raise StoryboardValidationError(
            "Storyboard schema validation failed",
            code="schema_validation_error",
            details=details,
        ) from exc
