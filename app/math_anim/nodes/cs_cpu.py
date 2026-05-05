from __future__ import annotations

from manim import *
import numpy as np

from app.math_anim.render_primitives.memory_shapes import build_register_box
from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, TEXT_COLOR, en_subtitle, en_text

from .base import as_list, to_float, to_int, to_str, update_context


def _note_wrap(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)


def _build_instruction_flow_body(params: dict) -> Mobject:
    raw_steps = [to_str(x).strip() for x in as_list(params.get("steps")) if to_str(x).strip()]
    if not raw_steps:
        raw_steps = ["Fetch", "Decode", "Execute", "Memory", "Write Back"]

    base_box_width = max(to_float(params.get("box_width"), 2.1), 1.0)
    base_box_height = max(to_float(params.get("box_height"), 0.9), 0.45)
    box_gap = max(to_float(params.get("box_gap"), 0.42), 0.15)
    flow_color = params.get("flow_color") or BLUE_E

    label_mobs: list[Mobject] = [
        en_subtitle(step, size=20, color=TEXT_COLOR, width=24)
        for step in raw_steps
    ]

    content_width = max((mob.width for mob in label_mobs), default=0.0)
    content_height = max((mob.height for mob in label_mobs), default=0.0)
    box_width = max(base_box_width, content_width + 0.45)
    box_height = max(base_box_height, content_height + 0.24)

    boxes = VGroup()
    for txt in label_mobs:
        rect = RoundedRectangle(corner_radius=0.15, width=box_width, height=box_height, color=flow_color)
        rect.set_fill(flow_color, opacity=0.18)
        txt.move_to(rect.get_center())
        boxes.add(VGroup(rect, txt))

    boxes.arrange(RIGHT, buff=box_gap, aligned_edge=UP)

    arrows = VGroup()
    for idx in range(len(boxes) - 1):
        left = boxes[idx]
        right = boxes[idx + 1]
        arrows.add(
            Arrow(
                start=left.get_right() + RIGHT * 0.04,
                end=right.get_left() + LEFT * 0.04,
                buff=0.05,
                stroke_width=2.4,
                color="#D0D0D0",
            )
        )

    return VGroup(arrows, boxes)



def build_cpu_state_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    raw_registers = p.get("registers")
    if isinstance(raw_registers, dict):
        registers = {to_str(k): to_str(v) for k, v in raw_registers.items()}
    elif isinstance(raw_registers, list):
        registers = {}
        for item in raw_registers:
            if isinstance(item, dict):
                name = to_str(item.get("name") or item.get("register"), "").strip()
                value = to_str(item.get("value"), "").strip()
                if name:
                    registers[name] = value
    else:
        registers = {}

    if not registers:
        registers = {"PC": "0x0040", "IR": "LOAD R1, [A]", "R1": "?"}
    active_units = {to_str(x).strip() for x in as_list(p.get("active_units"))}

    reg_boxes = VGroup()
    for name, value in registers.items():
        box = build_register_box(to_str(name), to_str(value))
        if to_str(name) in active_units:
            box.add(SurroundingRectangle(box, color=YELLOW_D, buff=0.04, stroke_width=2.1))
        reg_boxes.add(box)
    reg_boxes.arrange(DOWN, aligned_edge=LEFT, buff=0.08)

    unit_labels = ["ALU", "Control", "Memory", "Bus"]
    unit_boxes = VGroup()
    for u in unit_labels:
        active = u in active_units
        rect = RoundedRectangle(corner_radius=0.1, width=1.6, height=0.58, color=GOLD_E if active else BLUE_E)
        rect.set_fill((GOLD_E if active else BLUE_E), opacity=0.3 if active else 0.12)
        txt = en_text(u, size=17, color=TEXT_COLOR)
        txt.move_to(rect.get_center())
        unit_boxes.add(VGroup(rect, txt))
    unit_boxes.arrange(DOWN, aligned_edge=LEFT, buff=0.08)

    body = VGroup(reg_boxes, unit_boxes).arrange(RIGHT, buff=0.55, aligned_edge=UP)

    connectors = VGroup()
    reg_count = len(reg_boxes)
    unit_count = len(unit_boxes)
    pair_count = min(reg_count, unit_count)
    if pair_count > 0:
        for idx in range(pair_count):
            reg_right = reg_boxes[idx].get_right()
            unit_left = unit_boxes[idx].get_left()
            mid_y = (reg_boxes[idx].get_center()[1] + unit_boxes[idx].get_center()[1]) / 2
            start = np.array([reg_right[0] + 0.02, mid_y, 0.0])
            end = np.array([unit_left[0] - 0.02, mid_y, 0.0])
            line = DashedLine(start, end, stroke_width=1.4, color="#8899AA", dash_length=0.08)
            connectors.add(line)

    rendered_body = VGroup(connectors, body)
    title = en_text(to_str(p.get("title"), "CPU State"), size=24, color=HIGHLIGHT_COLOR)
    rendered: Mobject = VGroup(title, rendered_body).arrange(DOWN, aligned_edge=LEFT, buff=0.14)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)


def build_instruction_cycle_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    steps = [to_str(x).strip() for x in as_list(p.get("steps")) if to_str(x).strip()]
    if not steps:
        steps = ["Fetch", "Decode", "Execute", "Memory", "Write Back"]

    active = to_int(p.get("active_step"), -1)
    flow_body = _build_instruction_flow_body(
        {
            "steps": steps,
            "box_width": to_float(p.get("box_width"), 2.1),
            "box_height": to_float(p.get("box_height"), 0.9),
            "box_gap": to_float(p.get("box_gap"), 0.42),
            "flow_color": p.get("flow_color") or BLUE_E,
        }
    )

    if isinstance(flow_body, VGroup) and len(flow_body) >= 2:
        boxes = flow_body[1]
        if isinstance(boxes, VGroup) and 0 <= active < len(boxes):
            flow_body.add(SurroundingRectangle(boxes[active], color=YELLOW_D, buff=0.05, stroke_width=2.3))

    title = en_text(to_str(p.get("title"), "Instruction Cycle"), size=24, color=HIGHLIGHT_COLOR)
    rendered: Mobject = VGroup(title, flow_body).arrange(DOWN, aligned_edge=LEFT, buff=0.12)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)
