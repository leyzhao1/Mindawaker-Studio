from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from manim import *

from app.math_anim.math_renderer import compile_plot_function
from app.math_anim.nodes.common import (
    build_before_after_panel_node,
    build_callout_panel_node,
    build_code_panel_node,
    build_concept_map_node,
    build_layer_stack_node,
    build_pipeline_chain_node,
    build_space_bridge_node,
    build_state_machine_node,
    build_table_grid_node,
    build_terminal_output_node,
    build_timeline_node,
)
from app.math_anim.nodes.cs_cpu import build_cpu_state_node, build_instruction_cycle_node
from app.math_anim.nodes.cs_data_structures import build_array_cells_node, build_linked_list_node, build_tree_diagram_node
from app.math_anim.nodes.cs_memory import build_address_space_node, build_memory_grid_node, build_stack_frame_trace_node
from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, TEXT_COLOR, en_subtitle, en_text
from app.utils.story_blocks import (
    play_axes_curve_scene,
    play_comparison_boxes,
    play_formula_focus,
    play_number_sequence,
    play_summary_scene,
    play_title_card,
)


logger = logging.getLogger(__name__)

ROLE_PRIORITY = {
    "caption": 0,
    "primary": 1,
    "secondary": 2,
    "note": 3,
    "remark": 4,
    "overlay": 5,
}


@dataclass
class RenderContext:
    current_header: Mobject | None = None
    last_rendered: Mobject | None = None
    rendered_nodes: dict[str, Mobject] = field(default_factory=dict)
    scene_header_text: str | None = None
    defer_text_label_reveal: bool = False
    pending_text_label_reveals: list[tuple[Mobject, float]] = field(default_factory=list)
    in_group_build: bool = False


def _update_context(context: RenderContext, node: NodeSpec, rendered: Mobject | None) -> Mobject | None:
    if rendered is not None:
        context.last_rendered = rendered
        context.rendered_nodes[node.key] = rendered
    return rendered


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
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


def _to_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _normalize_explanation_items(value: Any, formula_tex: str) -> list[tuple[str, str]] | None:
    normalized: list[tuple[str, str]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            sym = _to_str(item.get("symbol") or item.get("sym") or item.get("key") or formula_tex).strip()
            desc = _to_str(item.get("description") or item.get("desc") or item.get("text") or item.get("value")).strip()
            if sym and desc:
                normalized.append((sym, desc))
            continue

        if isinstance(item, (list, tuple)):
            if len(item) >= 2:
                sym = _to_str(item[0]).strip() or formula_tex
                desc = _to_str(item[1]).strip()
                if sym and desc:
                    normalized.append((sym, desc))
            elif len(item) == 1:
                desc = _to_str(item[0]).strip()
                if formula_tex and desc:
                    normalized.append((formula_tex, desc))
            continue

        desc = _to_str(item).strip()
        if formula_tex and desc:
            normalized.append((formula_tex, desc))

    return normalized or None


def _normalize_comparison_items(value: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            title = _to_str(item.get("title") or item.get("label")).strip()
            body = _to_str(item.get("body") or item.get("description") or item.get("desc") or item.get("text")).strip()
            normalized.append(
                {
                    "title": title,
                    "body": body,
                    "color": item.get("color"),
                    "width": item.get("width"),
                    "box_width": item.get("box_width"),
                    "box_height": item.get("box_height"),
                    "title_size": item.get("title_size"),
                    "body_size": item.get("body_size"),
                }
            )
        else:
            normalized.append({"title": _to_str(item).strip(), "body": ""})
    return normalized


def _normalize_summary_lines(params: dict[str, Any]) -> list[str]:
    candidate = params.get("summary_lines")
    if candidate is None:
        candidate = params.get("points")
    lines = [_to_str(x).strip() for x in _as_list(candidate)]
    return [x for x in lines if x]


def _normalize_numeric_sequence(value: Any) -> list[Any]:
    return _as_list(value)


def _normalize_numeric_values(value: Any) -> list[float]:
    numbers: list[float] = []
    for item in _as_list(value):
        try:
            numbers.append(float(item))
        except Exception:
            continue
    return numbers


def _normalize_axis_range(value: Any, default_range: list[float]) -> list[float]:
    values = _normalize_numeric_values(value)
    if len(values) >= 2:
        if len(values) == 2:
            return [values[0], values[1], default_range[2]]
        return values[:3]
    return default_range


def _with_category_label(
    *,
    body: Mobject,
    category_label: str,
    category_color=HIGHLIGHT_COLOR,
    size: float = 20,
) -> VGroup:
    label = en_text(category_label, size=size, color=category_color)
    group = VGroup(label, body).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
    return group


def _build_relation_map_body(params: dict[str, Any]) -> Mobject:
    raw_nodes = _as_list(params.get("nodes"))
    node_labels: list[str] = []
    node_keys: list[str] = []
    for item in raw_nodes:
        if isinstance(item, dict):
            cid = _to_str(item.get("id"), "").strip()
            c_label = _to_str(item.get("label") or item.get("name"), "").strip() or cid or f"n{len(node_labels)}"
            if not cid:
                cid = c_label
            node_keys.append(cid)
            node_labels.append(c_label)
        else:
            text = _to_str(item).strip()
            if text:
                node_keys.append(text)
                node_labels.append(text)

    if not node_labels:
        node_keys = ["A", "B", "C"]
        node_labels = ["A", "B", "C"]

    relation_pairs = []
    for item in _as_list(params.get("relations")):
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            relation_pairs.append((_to_str(item[0]).strip(), _to_str(item[1]).strip()))
        elif isinstance(item, dict):
            source = _to_str(item.get("from") or item.get("source")).strip()
            target = _to_str(item.get("to") or item.get("target")).strip()
            if source and target:
                relation_pairs.append((source, target))

    ring_radius = max(_to_float(params.get("radius"), 1.6), 0.8)
    ring_radius = min(ring_radius, 2.15)
    label_size = _to_float(params.get("label_size"), 24)
    if label_size <= 2.0:
        label_size *= 30.0
    label_size = max(min(label_size, 30.0), 18.0)
    circle_radius = _to_float(params.get("node_radius"), 0.28)
    circle_radius = min(max(circle_radius, 0.2), 0.36)

    node_color = params.get("node_color") or BLUE_D
    node_fill = params.get("node_fill") or "#123B7A"
    text_color = params.get("text_color") or WHITE
    edge_color = params.get("edge_color") or "#C0D0E0"

    circles: dict[str, Mobject] = {}
    nodes = VGroup()
    count = len(node_keys)
    for idx in range(count):
        cid = node_keys[idx]
        label = node_labels[idx]
        theta = TAU * idx / max(count, 1)
        pos = np.array([ring_radius * np.cos(theta), ring_radius * np.sin(theta), 0.0])

        t = en_text(label, size=label_size, color=text_color)
        needed_radius = max(t.width / 1.64, t.height / 1.44, circle_radius)
        c = Circle(radius=needed_radius, color=node_color)
        c.set_fill(node_fill, opacity=0.85)
        c.move_to(pos)
        t.move_to(c.get_center())

        circles[cid] = c
        nodes.add(c, t)

    edges = VGroup()
    for source, target in relation_pairs:
        if source not in circles or target not in circles or source == target:
            continue
        edge = Arrow(
            start=circles[source].get_center(),
            end=circles[target].get_center(),
            buff=circle_radius + 0.03,
            stroke_width=3.0,
            color=edge_color,
        )
        edges.add(edge)

    if len(edges) == 0 and len(node_labels) >= 2:
        first = node_labels[0]
        second = node_labels[1]
        edge = Arrow(
            start=circles[first].get_center(),
            end=circles[second].get_center(),
            buff=circle_radius + 0.03,
            stroke_width=3.0,
            color=edge_color,
        )
        edges.add(edge)

    graph = VGroup(edges, nodes)
    max_graph_width = max(config.frame_width - 1.6, 0.1)
    max_graph_height = max(config.frame_height - 3.0, 0.1)
    if graph.width > max_graph_width:
        graph.scale_to_fit_width(max_graph_width)
    if graph.height > max_graph_height:
        graph.scale_to_fit_height(max_graph_height)

    note_text = _to_str(params.get("note"), "").strip()
    if note_text:
        note = en_subtitle(note_text, size=20, color=text_color, width=80)
        content = VGroup(graph, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    else:
        content = graph

    return content


def _build_stat_bar_grid_body(params: dict[str, Any]) -> Mobject:
    raw_values = _as_list(params.get("values"))
    numeric = _normalize_numeric_values(raw_values)
    if not numeric:
        numeric = [2.0, 4.0, 3.0, 5.0]

    labels = [_to_str(x).strip() for x in _as_list(params.get("labels"))]
    while len(labels) < len(numeric):
        labels.append(f"v{len(labels) + 1}")

    max_value = max(max(numeric), 1e-6)
    chart_width = max(_to_float(params.get("chart_width"), 5.2), 1.2)
    chart_height = max(_to_float(params.get("chart_height"), 2.6), 0.8)
    gap = max(_to_float(params.get("bar_gap"), 0.22), 0.05)
    bar_color = params.get("bar_color") or GREEN_E

    bar_count = len(numeric)
    total_gap = gap * (bar_count - 1)
    bar_width = max((chart_width - total_gap) / max(bar_count, 1), 0.15)

    bars = VGroup()
    for idx, value in enumerate(numeric):
        h = max((value / max_value) * chart_height, 0.08)
        bar = Rectangle(width=bar_width, height=h, color=bar_color)
        bar.set_fill(bar_color, opacity=0.55)

        value_text = en_text(f"{value:g}", size=18, color=TEXT_COLOR)
        value_text.next_to(bar, UP, buff=0.08)

        label_text = en_text(labels[idx], size=18, color=TEXT_COLOR)
        label_text.next_to(bar, DOWN, buff=0.08)

        cell = VGroup(bar, value_text, label_text)
        bars.add(cell)

    bars.arrange(RIGHT, buff=gap, aligned_edge=DOWN)

    baseline = Line(
        start=bars.get_left() + np.array([0.0, -0.02, 0.0]),
        end=bars.get_right() + np.array([0.0, -0.02, 0.0]),
        stroke_width=2.5,
        color="#B0B0B0",
    )

    note_text = _to_str(params.get("note"), "").strip()
    chart = VGroup(baseline, bars)
    if note_text:
        note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
        return VGroup(chart, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    return chart


def _build_process_flow_body(params: dict[str, Any]) -> Mobject:
    raw_steps = [_to_str(x).strip() for x in _as_list(params.get("steps")) if _to_str(x).strip()]
    if not raw_steps:
        raw_steps = ["Input", "Transform", "Output"]

    min_box_width = max(_to_float(params.get("box_width"), 2.25), 1.0)
    max_box_width = max(_to_float(params.get("box_max_width"), min_box_width * 1.8), min_box_width)
    min_box_height = max(_to_float(params.get("box_height"), 0.95), 0.45)
    box_gap = max(_to_float(params.get("box_gap"), 0.45), 0.15)
    text_size = _to_float(params.get("text_size"), 20)
    wrap_width = max(_to_int(params.get("text_wrap_width"), 22), 8)
    horizontal_padding = max(_to_float(params.get("box_horizontal_padding"), 0.28), 0.08)
    vertical_padding = max(_to_float(params.get("box_vertical_padding"), 0.2), 0.08)
    flow_color = params.get("flow_color") or BLUE_E

    boxes = VGroup()
    for step in raw_steps:
        txt = en_subtitle(step, size=text_size, color=TEXT_COLOR, width=wrap_width)

        adaptive_width = min(max(min_box_width, txt.width + horizontal_padding * 2), max_box_width)
        adaptive_height = max(min_box_height, txt.height + vertical_padding * 2)

        rect = RoundedRectangle(corner_radius=0.15, width=adaptive_width, height=adaptive_height, color=flow_color)
        rect.set_fill(flow_color, opacity=0.18)
        txt.move_to(rect.get_center())
        boxes.add(VGroup(rect, txt))

    boxes.arrange(RIGHT, buff=box_gap, aligned_edge=UP)

    arrows = VGroup()
    for idx in range(len(boxes) - 1):
        left = boxes[idx]
        right = boxes[idx + 1]
        arrow = Arrow(
            start=left.get_right() + RIGHT * 0.04,
            end=right.get_left() + LEFT * 0.04,
            buff=0.05,
            stroke_width=2.4,
            color="#D0D0D0",
        )
        arrows.add(arrow)

    content = VGroup(arrows, boxes)
    max_content_width = max(config.frame_width - 1.6, 0.1)
    max_content_height = max(config.frame_height - 3.2, 0.1)
    if content.width > max_content_width:
        content.scale_to_fit_width(max_content_width)
    if content.height > max_content_height:
        content.scale_to_fit_height(max_content_height)

    note_text = _to_str(params.get("note"), "").strip()
    if note_text:
        note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
        return VGroup(content, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    return content


def build_title_card_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    hold_time = _to_float(p.get("hold_time"), 1.5)
    if node.timing is not None and node.timing.start_s is not None and node.timing.end_s is not None:
        timing_duration = _to_float(node.timing.end_s, 0.0) - _to_float(node.timing.start_s, 0.0)
        if timing_duration > 0:
            hold_time = max(timing_duration - 2.0, 0.0)
    rendered = play_title_card(
        scene=scene,
        title=_to_str(p.get("title"), ""),
        subtitle=p.get("subtitle"),
        title_size=_to_float(p.get("title_size"), 38),
        subtitle_size=_to_float(p.get("subtitle_size"), 24),
        hold_time=hold_time,
    )
    return _update_context(context, node, rendered)


def build_transition_note_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    text = _to_str(p.get("text"), "")
    if not text:
        return None

    size = _to_float(p.get("size"), 28)
    color = p.get("color") or HIGHLIGHT_COLOR
    rendered = en_text(text, size=size, color=color)
    for item in rendered.get_family():
        if hasattr(item, "set_stroke"):
            item.set_stroke(BLACK, width=4, background=True)
        try:
            item.set_z_index(100)
        except Exception:
            pass
    rendered.move_to(ORIGIN)
    scene.add(rendered)
    rendered.save_state()
    _hide_for_reveal(rendered)
    return _update_context(context, node, rendered)


def _resolve_node_header_text(params: dict[str, Any], context: RenderContext) -> str:
    if context.scene_header_text:
        return _to_str(context.scene_header_text, "")
    return _to_str(params.get("header_text") or params.get("title"), "")


def build_formula_focus_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    header_text = _resolve_node_header_text(p, context)
    formula_tex = _to_str(p.get("formula_tex") or p.get("latex"), "")
    explanation_items = _normalize_explanation_items(p.get("explanation_items"), formula_tex)
    context.current_header, rendered = play_formula_focus(
        scene=scene,
        header_text=header_text,
        formula_tex=formula_tex,
        explanation_items=explanation_items,
        intro_note=_to_str(p.get("intro_note") or p.get("note"), "") or None,
        remark=_to_str(p.get("remark"), "") or None,
        header=context.current_header,
        instant=True,
    )
    return _update_context(context, node, rendered)


def _wrap_logistic_to_axis_range(plot_func, y_range: list[float]):
    if len(y_range) < 2:
        return plot_func

    y0 = float(y_range[0])
    y1 = float(y_range[1])
    low = min(y0, y1)
    high = max(y0, y1)
    span = max(high - low, 1e-6)

    def _scaled(x: float):
        try:
            base = float(plot_func(x))
        except Exception:
            base = 0.0
        if not math.isfinite(base):
            base = 0.0
        return low + base * span

    return _scaled


def build_axes_curve_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params

    plot_kind = _to_str(p.get("plot_kind"), "expression").lower()
    expression = _to_str(p.get("expression"), "")
    preset = _to_str(p.get("preset") or p.get("preset_name"), "")
    try:
        plot_func = compile_plot_function(
            plot_kind=plot_kind,
            expression=expression,
            preset=preset,
        )
    except Exception as exc:
        logger.warning("axes_curve compile failed for node=%s: %s", node.key, exc)
        plot_func = compile_plot_function(plot_kind="preset", preset="linear")

    point_x_values = _normalize_numeric_values(p.get("point_x_values"))

    plot_x_range = p.get("plot_x_range")
    if plot_x_range is None and plot_kind == "preset" and preset == "unit_circle":
        plot_x_range = [0.0, TAU]

    y_range = _normalize_axis_range(p.get("y_range"), [0, 10, 1])
    effective_plot_func = plot_func
    if plot_kind == "preset" and preset == "logistic_basic":
        effective_plot_func = _wrap_logistic_to_axis_range(plot_func, y_range)

    header_text = _resolve_node_header_text(p, context)
    context.current_header, rendered = play_axes_curve_scene(
        scene=scene,
        header_text=header_text,
        x_range=_normalize_axis_range(p.get("x_range"), [0, 10, 1]),
        y_range=y_range,
        plot_func=effective_plot_func,
        plot_x_range=plot_x_range,
        header=context.current_header,
        note=_to_str(p.get("note"), "") or None,
        x_label_text=_to_str(p.get("x_label_text"), "Time"),
        y_label_text=_to_str(p.get("y_label_text"), "Quantity"),
        formula_tex=_to_str(p.get("formula_tex"), "") or None,
        remark=_to_str(p.get("remark"), "") or None,
        point_x_values=point_x_values,
        point_y_func=effective_plot_func if point_x_values else None,
        instant=True,
    )
    return _update_context(context, node, rendered)


def build_number_sequence_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    header_text = _resolve_node_header_text(p, context)
    context.current_header, rendered = play_number_sequence(
        scene=scene,
        header_text=header_text,
        values=_normalize_numeric_sequence(p.get("values")),
        header=context.current_header,
        note=_to_str(p.get("note"), "") or None,
        show_arrows=_to_bool(p.get("show_arrows"), False),
        formula_tex=_to_str(p.get("formula_tex"), "") or None,
        remark=_to_str(p.get("remark"), "") or None,
        instant=True,
    )
    return _update_context(context, node, rendered)


def build_comparison_boxes_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    header_text = _resolve_node_header_text(p, context)
    context.current_header, rendered = play_comparison_boxes(
        scene=scene,
        header_text=header_text,
        items=_normalize_comparison_items(p.get("items")),
        header=context.current_header,
        note=_to_str(p.get("note"), "") or None,
        remark=_to_str(p.get("remark"), "") or None,
        instant=True,
    )
    return _update_context(context, node, rendered)


def build_summary_block_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    _, rendered = play_summary_scene(
        scene=scene,
        summary_lines=_normalize_summary_lines(p),
        formula_tex=_to_str(p.get("formula_tex"), "") or None,
        footer_text=_to_str(p.get("footer_text") or p.get("title"), "") or None,
        highlight_last=_to_bool(p.get("highlight_last"), False),
        footer_as_subtitle=_to_bool(p.get("footer_as_subtitle"), False),
        wait_time=_to_float(p.get("wait_time"), 2.2),
        instant=True,
    )
    return _update_context(context, node, rendered)


def build_text_label_node(
    scene: Scene,
    node: NodeSpec,
    context: RenderContext,
    anchor: Mobject | None = None,
    **_: Any,
) -> Mobject | None:
    p = node.params
    text = _to_str(p.get("text"), "")
    style = _to_str(p.get("style"), "body")
    size = _to_float(p.get("size"), 24)

    if style in {"subtitle", "panel_body", "formula_text", "highlight_formula_text", "final_formula_text"}:
        mob = en_subtitle(text, size=size, color=p.get("color", TEXT_COLOR), width=_to_int(p.get("width"), 90))
    else:
        mob = en_text(text, size=size, color=p.get("color", TEXT_COLOR))

    target_anchor = anchor if anchor is not None else (context.last_rendered if context.last_rendered is not None else context.current_header)
    buff = _to_float(p.get("buff"), 0.25)
    if target_anchor is not None:
        mob.next_to(target_anchor, DOWN, buff=buff)

    setattr(mob, "_mw_anchor", target_anchor)
    setattr(mob, "_mw_anchor_buff", buff)

    if context.defer_text_label_reveal:
        scene.add(mob)
        mob.set_opacity(0)
    else:
        scene.play(FadeIn(mob), run_time=_to_float(p.get("run_time"), 0.6))
    return _update_context(context, node, mob)


def build_rich_text_label_node(
    scene: Scene,
    node: NodeSpec,
    context: RenderContext,
    anchor: Mobject | None = None,
    **kwargs: Any,
) -> Mobject | None:
    return build_text_label_node(scene=scene, node=node, context=context, anchor=anchor, **kwargs)


def build_relation_map_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    body = _build_relation_map_body(p)
    labeled = _with_category_label(
        body=body,
        category_label=_to_str(p.get("category_label"), "关系类"),
        category_color=p.get("category_color", HIGHLIGHT_COLOR),
        size=_to_float(p.get("category_size"), 20),
    )
    return _update_context(context, node, labeled)


def build_stat_bar_grid_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    body = _build_stat_bar_grid_body(p)
    labeled = _with_category_label(
        body=body,
        category_label=_to_str(p.get("category_label"), "统计类"),
        category_color=p.get("category_color", HIGHLIGHT_COLOR),
        size=_to_float(p.get("category_size"), 20),
    )
    return _update_context(context, node, labeled)


def build_process_flow_node(scene: Scene, node: NodeSpec, context: RenderContext, **_: Any) -> Mobject | None:
    p = node.params
    body = _build_process_flow_body(p)
    labeled = _with_category_label(
        body=body,
        category_label=_to_str(p.get("category_label"), "过程类"),
        category_color=p.get("category_color", HIGHLIGHT_COLOR),
        size=_to_float(p.get("category_size"), 20),
    )
    return _update_context(context, node, labeled)


def _sort_children(nodes: list[NodeSpec]) -> list[NodeSpec]:
    return sorted(nodes, key=lambda n: (ROLE_PRIORITY.get(n.role, 99), n.key))


def build_group_node(scene: Scene, node: NodeSpec, context: RenderContext, build_child, group_layout, **kwargs: Any) -> Mobject | None:
    children = _sort_children(node.children)
    rendered_children: list[Mobject] = []
    child_map: dict[str, Mobject] = {}
    previous_group_build = context.in_group_build
    context.in_group_build = True
    try:
        for child in children:
            try:
                rendered = build_child(scene=scene, node=child, context=context, **kwargs)
            except Exception as exc:
                logger.warning("group child render failed node=%s child=%s: %s", node.key, child.key, exc)
                continue
            if rendered is not None:
                rendered_children.append(rendered)
                child_map[child.key] = rendered
    finally:
        context.in_group_build = previous_group_build
    if not rendered_children:
        return None
    arranged = group_layout(node=node, children=rendered_children, context=context)
    setattr(arranged, "_mw_child_map", child_map)
    return _update_context(context, node, arranged)


def _hide_for_reveal(mob: Mobject) -> None:
    for item in mob.get_family():
        try:
            item.set_opacity(0)
        except Exception:
            pass
        if hasattr(item, "set_stroke"):
            try:
                item.set_stroke(opacity=0)
            except Exception:
                pass
        if hasattr(item, "set_fill"):
            try:
                item.set_fill(opacity=0)
            except Exception:
                pass


def _clone_for_reveal(mob: Mobject) -> Mobject:
    clone = mob.copy()
    clone.set_opacity(1)
    if hasattr(clone, "set_stroke"):
        try:
            clone.set_stroke(opacity=1)
        except Exception:
            pass
    if hasattr(clone, "set_fill"):
        try:
            clone.set_fill(opacity=0)
        except Exception:
            pass
    return clone


def _reveal_axes_curve_node(scene: Scene, rendered: Mobject, run_time: float) -> bool:
    if not isinstance(rendered, VGroup):
        return False

    items = list(rendered.submobjects)
    axes_group_idx = None
    for idx, item in enumerate(items):
        if isinstance(item, VGroup) and len(item.submobjects) >= 4 and isinstance(item.submobjects[0], Axes):
            axes_group_idx = idx
            break

    if axes_group_idx is None:
        return False

    animated_clones: list[Mobject] = []

    def _animate_clone(mob: Mobject, animation_factory, duration: float) -> None:
        clone = _clone_for_reveal(mob)
        animated_clones.append(clone)
        scene.add(clone)
        scene.play(animation_factory(clone), run_time=max(duration, 0.05))

    prefix_items = items[:axes_group_idx]
    axes_group = items[axes_group_idx]
    suffix_items = items[axes_group_idx + 1 :]

    budget = max(float(run_time), 0.2)

    axes = axes_group.submobjects[0]
    x_label = axes_group.submobjects[1]
    y_label = axes_group.submobjects[2]
    curve = axes_group.submobjects[3]

    scene.remove(*rendered.get_family())

    axes_clone = _clone_for_reveal(axes)
    x_label_clone = _clone_for_reveal(x_label)
    y_label_clone = _clone_for_reveal(y_label)
    curve_clone = _clone_for_reveal(curve)
    animated_clones.extend([axes_clone, x_label_clone, y_label_clone, curve_clone])

    scene.add(axes_clone, x_label_clone, y_label_clone, curve_clone)

    for mob in prefix_items:
        _animate_clone(mob, lambda m: FadeIn(m), duration=max(budget * 0.08, 0.06))

    scene.play(
        Create(axes_clone),
        FadeIn(x_label_clone),
        FadeIn(y_label_clone),
        run_time=max(budget * 0.32, 0.12),
    )
    scene.play(Create(curve_clone), run_time=max(budget * 0.56, 0.12))

    for mob in suffix_items:
        _animate_clone(mob, lambda m: FadeIn(m), duration=max(budget * 0.08, 0.06))

    for clone in animated_clones:
        scene.remove(clone)

    for item in rendered.get_family():
        try:
            item.set_opacity(1)
        except Exception:
            pass
        if hasattr(item, "set_stroke"):
            try:
                item.set_stroke(opacity=1)
            except Exception:
                pass
        if hasattr(item, "set_fill"):
            try:
                item.set_fill(opacity=0)
            except Exception:
                pass

    scene.add(*rendered.get_family())
    return True


def _reveal_tree_diagram_node(
    scene: Scene,
    node: NodeSpec,
    rendered: Mobject,
    run_time: float,
    scene_narration_chunks: list[dict[str, Any]] | None = None,
) -> bool:
    traversal_mode = getattr(rendered, "_mw_tree_traversal_mode", None)
    traversal_order = getattr(rendered, "_mw_tree_traversal_order", None)
    node_map = getattr(rendered, "_mw_tree_node_map", None)
    label_map = getattr(rendered, "_mw_tree_label_map", None)
    edge_map = getattr(rendered, "_mw_tree_edge_map", None)
    step_edges = getattr(rendered, "_mw_tree_traversal_step_edges", None)

    if not traversal_mode or not isinstance(traversal_order, list) or not isinstance(node_map, dict):
        return False

    sequence_keys: list[str] = []
    sequence_nodes: list[Mobject] = []
    for key in traversal_order:
        key_str = str(key)
        mob = node_map.get(key_str)
        if isinstance(mob, Mobject):
            sequence_keys.append(key_str)
            sequence_nodes.append(mob)

    if not sequence_nodes:
        return False

    def _extract_circle_and_label(mob: Mobject) -> tuple[Mobject | None, Mobject | None]:
        if isinstance(mob, VGroup) and len(mob.submobjects) >= 2:
            return mob.submobjects[0], mob.submobjects[1]
        return None, None

    reveal_time = max(min(run_time * 0.2, 0.7), 0.12)
    scene.play(Restore(rendered), run_time=reveal_time)

    remain = max(run_time - reveal_time, 0.06)

    highlight_color = getattr(rendered, "_mw_tree_highlight_color", HIGHLIGHT_COLOR)
    highlight_scale = float(getattr(rendered, "_mw_tree_highlight_scale", 1.08) or 1.08)
    visited_fill_color = node.params.get("visited_fill_color") or "#2563eb"
    default_edge_color = node.params.get("edge_color") or GRAY_B

    edge_sequences: list[list[Line]] = []
    if isinstance(step_edges, list) and isinstance(edge_map, dict):
        for route in step_edges:
            route_edges: list[Line] = []
            if isinstance(route, list):
                for pair in route:
                    if not isinstance(pair, tuple) or len(pair) != 2:
                        continue
                    edge = edge_map.get((str(pair[0]), str(pair[1])))
                    if isinstance(edge, Line):
                        route_edges.append(edge)
            edge_sequences.append(route_edges)

    timing_mode_raw = _to_str(node.params.get("traversal_timing_mode"), "node").strip().lower()
    timing_mode = "chunk" if timing_mode_raw == "chunk" else "node"

    step_durations: list[float]
    if timing_mode == "chunk" and scene_narration_chunks:
        chunk_durations = []
        for chunk in scene_narration_chunks:
            if not isinstance(chunk, dict):
                continue
            start = _to_float(chunk.get("start"), 0.0)
            end = _to_float(chunk.get("end"), start)
            if end > start:
                chunk_durations.append(end - start)

        if chunk_durations and len(sequence_nodes) > 0:
            total_chunk = sum(chunk_durations)
            if total_chunk <= 0:
                total_chunk = remain
            scale = remain / max(total_chunk, 1e-6)

            step_durations = []
            chunk_count = len(chunk_durations)
            base_step_count = len(sequence_nodes) // chunk_count
            remainder = len(sequence_nodes) % chunk_count
            assigned = 0
            for idx, chunk_duration in enumerate(chunk_durations):
                steps_in_chunk = base_step_count + (1 if idx < remainder else 0)
                if steps_in_chunk <= 0:
                    continue
                per_step = max((chunk_duration * scale) / steps_in_chunk, 0.04)
                for _ in range(steps_in_chunk):
                    step_durations.append(per_step)
                    assigned += 1
            while assigned < len(sequence_nodes):
                step_durations.append(max(remain / max(len(sequence_nodes), 1), 0.04))
                assigned += 1
        else:
            step_durations = [max(remain / max(len(sequence_nodes), 1), 0.06)] * len(sequence_nodes)
    else:
        step_durations = [max(remain / max(len(sequence_nodes), 1), 0.06)] * len(sequence_nodes)

    trace_label = en_text("Visited:", size=20, color=TEXT_COLOR)
    trace_label.next_to(rendered, DOWN, buff=0.22)
    left_limit = -config.frame_width / 2 + 0.8
    right_limit = config.frame_width / 2 - 0.8
    if trace_label.get_left()[0] < left_limit:
        trace_label.shift(RIGHT * (left_limit - trace_label.get_left()[0]))
    if trace_label.get_right()[0] > right_limit:
        trace_label.shift(LEFT * (trace_label.get_right()[0] - right_limit))
    bottom_limit = -config.frame_height / 2 + 0.5
    if trace_label.get_bottom()[1] < bottom_limit:
        trace_label.shift(UP * (bottom_limit - trace_label.get_bottom()[1]))
    scene.play(FadeIn(trace_label), run_time=min(0.25, max(remain * 0.1, 0.1)))

    visited_labels: list[str] = []

    for idx, target in enumerate(sequence_nodes):
        circle, label = _extract_circle_and_label(target)
        current_edges = edge_sequences[idx] if idx < len(edge_sequences) else []
        step_time = step_durations[idx] if idx < len(step_durations) else max(remain / max(len(sequence_nodes), 1), 0.06)
        pulse_time = max(step_time * 0.58, 0.04)
        settle_time = max(step_time - pulse_time, 0.02)

        ring = Circle(radius=max(target.width * 0.6, 0.2), color=highlight_color, stroke_width=4)
        ring.move_to(target.get_center())

        pulse_anims: list[Animation] = [Create(ring, run_time=pulse_time)]
        if circle is not None:
            pulse_anims.append(circle.animate.set_fill(highlight_color, opacity=1.0))
        if label is not None:
            pulse_anims.append(label.animate.set_color(BLACK))
        for edge in current_edges:
            pulse_anims.append(edge.animate.set_color(highlight_color).set_stroke(width=3.4))
        scene.play(*pulse_anims, run_time=pulse_time)

        visited_key = sequence_keys[idx] if idx < len(sequence_keys) else ""
        visited_text = str(label_map.get(visited_key) if isinstance(label_map, dict) else "") or visited_key
        visited_labels.append(visited_text)
        next_trace = en_text(f"Visited: {'  '.join(visited_labels)}", size=20, color=TEXT_COLOR)
        next_trace.move_to(trace_label.get_center())
        if next_trace.width > max(config.frame_width - 1.6, 0.6):
            next_trace.scale_to_fit_width(max(config.frame_width - 1.6, 0.6))
            next_trace.move_to(trace_label.get_center())

        settle_anims: list[Animation] = [FadeOut(ring)]
        if circle is not None:
            settle_anims.append(circle.animate.set_fill(visited_fill_color, opacity=1.0))
        if label is not None:
            settle_anims.append(label.animate.set_color(WHITE))
        for edge in current_edges:
            settle_anims.append(edge.animate.set_color(default_edge_color).set_stroke(width=2.2))
        settle_anims.append(Transform(trace_label, next_trace))
        scene.play(*settle_anims, run_time=settle_time)

    tail_hold = max(min(remain * 0.08, 0.25), 0.06)
    scene.wait(tail_hold)
    scene.play(FadeOut(trace_label), run_time=min(0.25, tail_hold + 0.04))

    return True



def _reveal_pipeline_chain_node(scene: Scene, rendered: Mobject, run_time: float) -> bool:
    boxes = getattr(rendered, "_mw_pipeline_boxes", None)
    arrows = getattr(rendered, "_mw_pipeline_arrows", None)
    if not isinstance(boxes, VGroup):
        return False

    steps = len(boxes)
    if steps <= 0:
        return False

    scene.remove(*rendered.get_family())
    budget = max(float(run_time), 0.25)

    if isinstance(arrows, VGroup) and len(arrows) > 0:
        arrow_time = max(budget * 0.35 / len(arrows), 0.06)
    else:
        arrow_time = 0.0
    box_time = max(budget * 0.65 / steps, 0.07)

    for idx in range(steps):
        scene.play(FadeIn(boxes[idx]), run_time=box_time)
        if isinstance(arrows, VGroup) and idx < len(arrows):
            scene.play(GrowArrow(arrows[idx]), run_time=arrow_time)

    for item in rendered.get_family():
        try:
            item.set_opacity(1)
        except Exception:
            pass
        if hasattr(item, "set_stroke"):
            try:
                item.set_stroke(opacity=1)
            except Exception:
                pass
        if hasattr(item, "set_fill"):
            try:
                item.set_fill(opacity=getattr(item, "fill_opacity", 1.0))
            except Exception:
                pass

    scene.add(*rendered.get_family())
    return True


def _reveal_terminal_output_node(scene: Scene, rendered: Mobject, run_time: float) -> bool:
    command = getattr(rendered, "_mw_terminal_command", None)
    lines = getattr(rendered, "_mw_terminal_output_lines", None)
    cursor = getattr(rendered, "_mw_terminal_cursor", None)
    if command is None or not isinstance(lines, VGroup):
        return False

    scene.remove(*rendered.get_family())
    budget = max(float(run_time), 0.25)

    line_count = max(len(lines), 1)
    cmd_time = max(budget * 0.35, 0.08)
    lines_time = max(budget * 0.5 / line_count, 0.06)
    cursor_time = max(budget * 0.15, 0.06)

    scene.play(FadeIn(command), run_time=cmd_time)
    for line in lines:
        scene.play(FadeIn(line), run_time=lines_time)

    if cursor is not None:
        scene.play(FadeIn(cursor), run_time=cursor_time)
        scene.play(Indicate(cursor, scale_factor=1.06), run_time=min(cursor_time, 0.2))

    for item in rendered.get_family():
        try:
            item.set_opacity(1)
        except Exception:
            pass
        if hasattr(item, "set_stroke"):
            try:
                item.set_stroke(opacity=1)
            except Exception:
                pass
        if hasattr(item, "set_fill"):
            try:
                item.set_fill(opacity=getattr(item, "fill_opacity", 1.0))
            except Exception:
                pass

    scene.add(*rendered.get_family())
    return True


def _reveal_space_bridge_node(scene: Scene, rendered: Mobject, run_time: float) -> bool:
    left_group = getattr(rendered, "_mw_space_left", None)
    right_group = getattr(rendered, "_mw_space_right", None)
    boundary_group = getattr(rendered, "_mw_space_boundary", None)
    bridge_group = getattr(rendered, "_mw_space_bridge", None)
    if not isinstance(left_group, VGroup) or not isinstance(right_group, VGroup):
        return False

    scene.remove(*rendered.get_family())
    budget = max(float(run_time), 0.25)

    side_time = max(budget * 0.34, 0.08)
    boundary_time = max(budget * 0.22, 0.06)
    bridge_time = max(budget * 0.44, 0.08)

    scene.play(FadeIn(left_group), run_time=side_time)
    scene.play(FadeIn(right_group), run_time=side_time)

    if isinstance(boundary_group, VGroup):
        boundary_parts = list(boundary_group)
        if boundary_parts:
            scene.play(*[FadeIn(x) for x in boundary_parts], run_time=boundary_time)

    if isinstance(bridge_group, VGroup) and len(bridge_group) > 0:
        first = bridge_group[0]
        rest = [x for x in bridge_group[1:]]
        if isinstance(first, Arrow):
            if rest:
                scene.play(GrowArrow(first), *[FadeIn(x) for x in rest], run_time=bridge_time)
            else:
                scene.play(GrowArrow(first), run_time=bridge_time)
        else:
            scene.play(*[FadeIn(x) for x in bridge_group], run_time=bridge_time)

    scene.add(*rendered.get_family())
    return True


def reveal_node(
    scene: Scene,
    node: NodeSpec,
    rendered: Mobject,
    context: RenderContext,
    run_time_override: float | None = None,
    scene_narration_chunks: list[dict[str, Any]] | None = None,
) -> None:
    run_time = _to_float(run_time_override, _to_float(node.params.get("run_time"), 0.8))

    if node.type == "title_card":
        return

    if node.type == "transition_note":
        fade_time = max(min(run_time * 0.18, 0.7), 0.12)
        scene.play(Restore(rendered), run_time=fade_time)
        if run_time > fade_time:
            scene.wait(run_time - fade_time)
        return

    if node.type in {"text_label", "rich_text_label"}:
        fade_time = max(min(run_time * 0.2, 0.7), 0.12)
        scene.play(FadeIn(rendered), run_time=fade_time)
        if run_time > fade_time:
            scene.wait(run_time - fade_time)
        return

    if node.type == "tree_diagram" and _reveal_tree_diagram_node(
        scene,
        node,
        rendered,
        run_time,
        scene_narration_chunks=scene_narration_chunks,
    ):
        return

    if node.type == "axes_curve" and _reveal_axes_curve_node(scene, rendered, run_time):
        return

    if node.type == "pipeline_chain" and _reveal_pipeline_chain_node(scene, rendered, run_time):
        return

    if node.type == "terminal_output" and _reveal_terminal_output_node(scene, rendered, run_time):
        return

    if node.type == "space_bridge" and _reveal_space_bridge_node(scene, rendered, run_time):
        return

    scene.play(Restore(rendered), run_time=run_time)


__all__ = [
    "ROLE_PRIORITY",
    "RenderContext",
    "build_title_card_node",
    "build_transition_note_node",
    "build_formula_focus_node",
    "build_axes_curve_node",
    "build_number_sequence_node",
    "build_comparison_boxes_node",
    "build_summary_block_node",
    "build_text_label_node",
    "build_rich_text_label_node",
    "build_relation_map_node",
    "build_stat_bar_grid_node",
    "build_process_flow_node",
    "build_group_node",
    "build_timeline_node",
    "build_state_machine_node",
    "build_layer_stack_node",
    "build_table_grid_node",
    "build_code_panel_node",
    "build_callout_panel_node",
    "build_concept_map_node",
    "build_before_after_panel_node",
    "build_pipeline_chain_node",
    "build_terminal_output_node",
    "build_space_bridge_node",
    "build_memory_grid_node",
    "build_address_space_node",
    "build_stack_frame_trace_node",
    "build_cpu_state_node",
    "build_instruction_cycle_node",
    "build_array_cells_node",
    "build_linked_list_node",
    "build_tree_diagram_node",
    "reveal_node",
]
