from __future__ import annotations

from typing import Any

from manim import *

from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, en_text


def update_context(context: Any, node: NodeSpec, rendered: Mobject | None) -> Mobject | None:
    if rendered is not None:
        context.last_rendered = rendered
        if hasattr(context, "rendered_nodes"):
            context.rendered_nodes[node.key] = rendered
    return rendered


def to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def normalize_numeric_values(value: Any) -> list[float]:
    result: list[float] = []
    for item in as_list(value):
        try:
            result.append(float(item))
        except Exception:
            continue
    return result


def with_category_label(
    *,
    body: Mobject,
    category_label: str,
    category_color=HIGHLIGHT_COLOR,
    size: float = 20,
) -> VGroup:
    label = en_text(category_label, size=size, color=category_color)
    return VGroup(label, body).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
