from __future__ import annotations

from manim import *

from app.math_anim.render_primitives.memory_shapes import build_memory_cell, build_stack_frame
from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, TEXT_COLOR, en_subtitle, en_text

from .base import as_list, normalize_numeric_values, to_float, to_int, to_str, update_context


def _note_wrap(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)


def _note_wrap_center(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, buff=0.2)


def build_memory_grid_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    raw_cells = as_list(p.get("cells"))

    cells: list[str] = []
    addresses: list[str] = [to_str(x).strip() for x in as_list(p.get("addresses"))]
    for item in raw_cells:
        if isinstance(item, dict):
            cell_value = to_str(item.get("value") or item.get("label"), "").strip()
            cells.append(cell_value)
            if "address" in item:
                addresses.append(to_str(item.get("address"), "").strip())
            else:
                addresses.append("")
        else:
            cells.append(to_str(item).strip())

    cells = [x for x in cells if x]
    if not cells:
        cells = ["3", "7", "9", "12"]

    if len(addresses) > len(cells):
        addresses = addresses[: len(cells)]
    while len(addresses) < len(cells):
        addresses.append("")

    highlight_indices = {int(x) for x in normalize_numeric_values(p.get("highlight_indices"))}
    min_width = max(to_float(p.get("cell_width"), 1.3), 0.5)
    min_height = max(to_float(p.get("cell_height"), 0.7), 0.3)
    text_size = to_float(p.get("text_size"), 20)
    gap = max(to_float(p.get("cell_gap"), 0.2), 0.06)

    # Pre-measure all value texts to compute consistent cell size
    text_mobs = [en_text(v, size=text_size, color=TEXT_COLOR) for v in cells]
    grid_w = max(min_width, max((t.width for t in text_mobs), default=0.0) + 0.3)
    grid_h = max(min_height, max((t.height for t in text_mobs), default=0.0) + 0.22)

    mem = VGroup()
    for idx, value in enumerate(cells):
        mem.add(
            build_memory_cell(
                value,
                address=addresses[idx] or None,
                width=grid_w,
                height=grid_h,
                active=idx in highlight_indices,
                text_size=text_size,
            )
        )
    mem.arrange(RIGHT, buff=gap, aligned_edge=UP)

    title = to_str(p.get("title"), "").strip()
    rendered: Mobject = mem
    if title:
        t = en_text(title, size=24, color=HIGHLIGHT_COLOR)
        rendered = VGroup(t, mem).arrange(DOWN, aligned_edge=LEFT, buff=0.16)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)


def _compute_segment_size(seg: dict, default: float = 1.0) -> float:
    raw_size = seg.get("size")
    if raw_size is not None:
        size = to_float(raw_size, -1.0)
        if size >= 0:
            return size
    start_str = to_str(seg.get("start"), "").strip()
    end_str = to_str(seg.get("end"), "").strip()
    if start_str and end_str:
        try:
            start_val = int(start_str, 16)
            end_val = int(end_str, 16)
            raw_range = abs(start_val - end_val)
            if raw_range > 0:
                return max(raw_range / 0x4000, 0.3)
        except (ValueError, TypeError):
            pass
    return default


def build_address_space_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    segments = as_list(p.get("segments"))
    if not segments:
        segments = [
            {"name": "Stack", "size": 1.2, "note": "function calls"},
            {"name": "Heap", "size": 1.6, "note": "dynamic objects"},
            {"name": "Data", "size": 0.8, "note": "globals"},
            {"name": "Code", "size": 0.8, "note": "instructions"},
        ]

    highlight = to_str(p.get("highlight"), "").strip()
    blocks = VGroup()
    max_width = max(to_float(p.get("width"), 4.2), 1.0)
    size_unit = max(to_float(p.get("size_unit"), 0.62), 0.2)

    for seg in segments:
        if not isinstance(seg, dict):
            continue
        label = to_str(seg.get("label") or seg.get("name"), "").strip() or "Segment"
        size = max(_compute_segment_size(seg), 0.3)
        seg_note = to_str(seg.get("note"), "").strip()
        is_active = label == highlight

        rect = RoundedRectangle(
            corner_radius=0.08,
            width=max_width,
            height=max(size * size_unit, 0.32),
            color=GOLD_E if is_active else BLUE_E,
        )
        rect.set_fill((GOLD_E if is_active else BLUE_E), opacity=0.32 if is_active else 0.12)
        label_text = en_text(label, size=20, color=TEXT_COLOR)
        label_text.move_to(rect.get_center() + LEFT * (rect.width * 0.24))
        seg_group = VGroup(rect, label_text)
        if seg_note:
            note_text = en_text(seg_note, size=16, color=GRAY_B)
            note_text.move_to(rect.get_center() + RIGHT * (rect.width * 0.18))
            seg_group.add(note_text)
        blocks.add(seg_group)

    if len(blocks) == 0:
        return None

    blocks.arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    border = SurroundingRectangle(blocks, buff=0.08, color=GRAY_B, stroke_width=1.8)
    rendered: Mobject = VGroup(border, blocks)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)


def build_stack_frame_trace_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    frames = as_list(p.get("frames"))
    if not frames:
        frames = [
            {"name": "main()", "locals": {"n": "3"}},
            {"name": "factorial(3)", "locals": {"n": "3"}},
            {"name": "factorial(2)", "locals": {"n": "2"}},
            {"name": "factorial(1)", "locals": {"n": "1"}},
        ]

    active_idx = to_int(p.get("highlight_frame"), -1)
    width = max(to_float(p.get("frame_width"), 3.8), 1.0)
    height = max(to_float(p.get("frame_height"), 0.95), 0.45)

    stack = VGroup()
    for idx, frame in enumerate(frames):
        if not isinstance(frame, dict):
            continue
        name = to_str(frame.get("name"), "").strip() or f"frame_{idx}"
        locals_data = frame.get("locals") or frame.get("variables")
        if isinstance(locals_data, dict):
            locals_text = ", ".join(f"{to_str(k)}={to_str(v)}" for k, v in locals_data.items())
        else:
            locals_text = to_str(locals_data, "")
        stack.add(build_stack_frame(name, locals_text, width=width, height=height, active=(idx == active_idx)))

    if len(stack) == 0:
        return None

    stack.arrange(DOWN, aligned_edge=LEFT, buff=0.08)

    title = to_str(p.get("title"), "Call Stack").strip() or "Call Stack"
    title_mob = en_text(title, size=24, color=HIGHLIGHT_COLOR)
    rendered: Mobject = VGroup(title_mob, stack).arrange(DOWN, aligned_edge=LEFT, buff=0.16)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap_center(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)
