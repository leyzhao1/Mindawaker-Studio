from __future__ import annotations

from manim import *
import numpy as np

from app.math_anim.render_primitives.common_shapes import (
    build_callout,
    build_highlight_frame,
    build_labeled_box,
    build_labeled_circle,
    build_timeline_cell,
)
from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, TEXT_COLOR, en_subtitle, en_text

from .base import as_list, normalize_numeric_values, to_bool, to_float, to_int, to_str, update_context


def _string_color(raw: str | None, fallback):
    value = to_str(raw, "").strip()
    if not value:
        return fallback
    try:
        return ManimColor(value)
    except Exception:
        return fallback


def _add_note(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)


def _add_note_center(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, buff=0.2)


def build_timeline_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    steps = [to_str(x).strip() for x in as_list(p.get("steps")) if to_str(x).strip()]
    if not steps:
        steps = ["Start", "Middle", "End"]
    active_idx = to_int(p.get("active_index"), -1)

    cells = VGroup(*[build_timeline_cell(step, active=idx == active_idx) for idx, step in enumerate(steps)])
    cells.arrange(RIGHT, buff=0.35, aligned_edge=UP)

    arrows = VGroup()
    for idx in range(len(cells) - 1):
        arrows.add(
            Arrow(
                start=cells[idx].get_right() + RIGHT * 0.03,
                end=cells[idx + 1].get_left() + LEFT * 0.03,
                buff=0.04,
                stroke_width=2.2,
                color="#D0D0D0",
            )
        )

    rendered = VGroup(arrows, cells)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_state_machine_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    states = [to_str(x).strip() for x in as_list(p.get("states")) if to_str(x).strip()]
    if not states:
        states = ["Idle", "Running", "Done"]
    active_state = to_str(p.get("active_state"), "")
    radius = max(to_float(p.get("radius"), 1.9), 1.0)

    circles: dict[str, VGroup] = {}
    ring = VGroup()
    for idx, label in enumerate(states):
        angle = TAU * idx / max(len(states), 1)
        is_active = label == active_state or (not active_state and idx == 0)
        c = build_labeled_circle(
            label,
            radius=0.34,
            color=GOLD_E if is_active else BLUE_D,
            fill_color="#7D5B00" if is_active else "#123B7A",
            text_size=18,
        )
        c.move_to(np.array([radius * np.cos(angle), radius * np.sin(angle), 0.0]))
        circles[label] = c
        ring.add(c)

    edges = VGroup()
    transitions = as_list(p.get("transitions"))
    if not transitions and len(states) >= 2:
        transitions = [[states[i], states[i + 1]] for i in range(len(states) - 1)]

    for item in transitions:
        if isinstance(item, dict):
            source = to_str(item.get("from") or item.get("source"), "")
            target = to_str(item.get("to") or item.get("target"), "")
            label = to_str(item.get("label"), "")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            source = to_str(item[0], "")
            target = to_str(item[1], "")
            label = to_str(item[2], "") if len(item) >= 3 else ""
        else:
            continue
        if source not in circles or target not in circles:
            continue

        arrow = Arrow(
            start=circles[source].get_center(),
            end=circles[target].get_center(),
            buff=0.42,
            stroke_width=2.3,
            color="#D0D0D0",
        )
        edges.add(arrow)
        if label:
            txt = en_text(label, size=16, color=GRAY_A)
            txt.move_to((arrow.get_start() + arrow.get_end()) / 2 + UP * 0.14)
            edges.add(txt)

    rendered = VGroup(edges, ring)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_layer_stack_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    layers = [to_str(x).strip() for x in as_list(p.get("layers")) if to_str(x).strip()]
    if not layers:
        layers = ["Application", "Runtime", "OS", "Hardware"]

    highlight = to_str(p.get("highlight_layer"), "")
    boxes = VGroup()
    for idx, layer in enumerate(layers):
        active = highlight == layer or (not highlight and idx == 0)
        boxes.add(
            build_labeled_box(
                layer,
                width=max(to_float(p.get("layer_width"), 5.1), 1.2),
                height=max(to_float(p.get("layer_height"), 0.72), 0.4),
                color=GOLD_E if active else BLUE_E,
                fill_opacity=0.3 if active else 0.16,
                text_size=20,
            )
        )
    boxes.arrange(DOWN, buff=max(to_float(p.get("layer_gap"), 0.14), 0.05), aligned_edge=LEFT)

    rendered = boxes
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note_center(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_table_grid_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    headers = [to_str(x) for x in as_list(p.get("headers"))]
    rows = [as_list(r) for r in as_list(p.get("rows"))]
    if not headers and rows:
        headers = [f"c{i + 1}" for i in range(len(rows[0]))]
    if not headers:
        headers = ["Item", "Value"]
        rows = [["A", "1"], ["B", "2"]]

    col_count = len(headers)
    for row in rows:
        while len(row) < col_count:
            row.append("")

    highlight_cells = {(int(r), int(c)) for r, c in [tuple(x) for x in as_list(p.get("highlight_cells")) if isinstance(x, (list, tuple)) and len(x) >= 2]}
    text_size = to_float(p.get("text_size"), 18)
    min_cell_w = max(to_float(p.get("cell_width"), 1.8), 0.6)
    min_cell_h = max(to_float(p.get("cell_height"), 0.62), 0.35)
    h_pad = max(to_float(p.get("cell_h_padding"), 0.36), 0.12)
    v_pad = max(to_float(p.get("cell_v_padding"), 0.2), 0.08)
    gap = max(to_float(p.get("cell_gap"), 0.06), 0.02)

    # Pre-measure text dimensions
    all_texts = [[to_str(t) for t in headers]]
    for row in rows:
        all_texts.append([to_str(row[c]) for c in range(col_count)])

    text_mobs: list[list[Mobject]] = []
    for r_idx in range(len(all_texts)):
        row_mobs: list[Mobject] = []
        for c_idx in range(col_count):
            txt = en_subtitle(all_texts[r_idx][c_idx], size=text_size, color=TEXT_COLOR, width=32)
            row_mobs.append(txt)
        text_mobs.append(row_mobs)

    # Compute per-column width and per-row height
    col_widths = [min_cell_w] * col_count
    for c_idx in range(col_count):
        max_w = min_cell_w
        for r_idx in range(len(text_mobs)):
            max_w = max(max_w, text_mobs[r_idx][c_idx].width + h_pad)
        col_widths[c_idx] = max_w

    row_heights = [min_cell_h] * len(text_mobs)
    for r_idx in range(len(text_mobs)):
        max_h = min_cell_h
        for c_idx in range(col_count):
            max_h = max(max_h, text_mobs[r_idx][c_idx].height + v_pad)
        row_heights[r_idx] = max_h

    table_rows = VGroup()
    for r_idx in range(len(text_mobs)):
        row_group = VGroup()
        for c_idx in range(col_count):
            is_header = r_idx == 0
            is_highlight = (r_idx - 1, c_idx) in highlight_cells
            active = is_highlight if not is_header else False

            rect = RoundedRectangle(
                corner_radius=0.12,
                width=col_widths[c_idx],
                height=row_heights[r_idx],
                color=BLUE_D if is_header else (GOLD_E if active else BLUE_E),
            )
            fill_op = 0.28 if (is_header or active) else 0.1
            rect.set_fill(rect.get_color(), opacity=fill_op)

            txt = text_mobs[r_idx][c_idx]
            txt.move_to(rect.get_center())
            cell = VGroup(rect, txt)
            row_group.add(cell)
        row_group.arrange(RIGHT, buff=gap)
        table_rows.add(row_group)

    table_rows.arrange(DOWN, buff=gap, aligned_edge=LEFT)
    rendered = table_rows
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_code_panel_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    from app.math_anim.render_primitives.code_shapes import build_code_panel

    p = node.params
    title = to_str(p.get("title"), "").strip() or None
    lines = as_list(p.get("lines"))
    rendered = build_code_panel(title, lines, width=max(to_float(p.get("width"), 6.2), 2.0))

    line_idx = to_int(p.get("highlight_line"), -1)
    if line_idx >= 0 and len(rendered.submobjects) > 0:
        panel_body = rendered[-1] if title else rendered
        if isinstance(panel_body, VGroup) and len(panel_body) >= 2:
            lines_group = panel_body[1]
            if isinstance(lines_group, VGroup) and 0 <= line_idx < len(lines_group):
                rendered.add(build_highlight_frame(lines_group[line_idx], color=YELLOW_D, buff=0.06, stroke_width=2.2))

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_callout_panel_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    text = to_str(p.get("text"), "").strip()
    if not text:
        return None
    rendered = build_callout(
        text,
        title=to_str(p.get("title"), "").strip() or None,
        width=max(to_float(p.get("width"), 4.8), 1.2),
        color=p.get("color") or YELLOW_D,
    )
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_concept_map_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    raw_concepts = as_list(p.get("concepts") or p.get("nodes"))

    # Normalize concepts: dicts -> use "id" as key and "label" for display, strings -> use as both
    concept_labels: list[str] = []
    concept_keys: list[str] = []
    concept_colors: dict[str, str] = {}
    for item in raw_concepts:
        if isinstance(item, dict):
            cid = to_str(item.get("id"), "").strip()
            c_label = to_str(item.get("label"), "").strip() or cid or f"c{len(concept_labels)}"
            if not cid:
                cid = c_label
            concept_keys.append(cid)
            concept_labels.append(c_label)
            raw_color = item.get("color")
            if raw_color:
                concept_colors[cid] = str(raw_color)
        else:
            text = to_str(item).strip()
            if text:
                concept_keys.append(text)
                concept_labels.append(text)

    if not concept_labels:
        concept_keys = ["Input", "Model", "Output"]
        concept_labels = ["Input", "Model", "Output"]

    relations = as_list(p.get("relations"))
    radius = max(to_float(p.get("radius"), 1.8), 1.0)
    highlights = {to_str(x).strip() for x in as_list(p.get("highlight_nodes"))}

    nodes: dict[str, VGroup] = {}
    ring = VGroup()
    for idx in range(len(concept_labels)):
        cid = concept_keys[idx]
        label = concept_labels[idx]
        angle = TAU * idx / max(len(concept_labels), 1)
        active = cid in highlights or label in highlights
        custom_color = concept_colors.get(cid)
        circle_color = custom_color if custom_color else (GOLD_E if active else TEAL_E)
        fill_color = "#7D5B00" if active else "#0E3A35"
        c = build_labeled_circle(
            label,
            radius=0.33,
            color=circle_color,
            fill_color=fill_color,
            text_size=18,
        )
        c.move_to(np.array([radius * np.cos(angle), radius * np.sin(angle), 0.0]))
        nodes[cid] = c
        ring.add(c)

    edge_color = p.get("edge_color") or "#C8D8E8"
    edges = VGroup()
    if not relations and len(concept_keys) >= 2:
        relations = [[concept_keys[i], concept_keys[i + 1]] for i in range(len(concept_keys) - 1)]

    for rel in relations:
        if isinstance(rel, dict):
            source = to_str(rel.get("from") or rel.get("source"), "")
            target = to_str(rel.get("to") or rel.get("target"), "")
            rel_label = to_str(rel.get("label"), "").strip()
        elif isinstance(rel, (list, tuple)) and len(rel) >= 2:
            source = to_str(rel[0], "")
            target = to_str(rel[1], "")
            rel_label = to_str(rel[2], "").strip() if len(rel) >= 3 else ""
        else:
            continue
        if source not in nodes or target not in nodes:
            continue
        arrow = Arrow(
            start=nodes[source].get_center(),
            end=nodes[target].get_center(),
            buff=0.41,
            stroke_width=2.4,
            color=edge_color,
        )
        if rel_label:
            lbl = en_text(rel_label, size=14, color="#D0D8E0")
            lbl.move_to((arrow.get_start() + arrow.get_end()) / 2 + UP * 0.16)
            edges.add(VGroup(arrow, lbl))
        else:
            edges.add(arrow)

    rendered = VGroup(edges, ring)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)




def build_before_after_panel_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    before = to_str(p.get("before"), "").strip()
    after = to_str(p.get("after"), "").strip()
    if not before and not after:
        return None

    before_title = to_str(p.get("before_title"), "Before").strip() or "Before"
    after_title = to_str(p.get("after_title"), "After").strip() or "After"

    before_box = build_labeled_box(before or "-", width=3.0, height=1.5, color=BLUE_E, fill_opacity=0.14, text_size=18)
    before_header = en_text(before_title, size=20, color=BLUE_A)
    before_group = VGroup(before_header, before_box).arrange(DOWN, aligned_edge=LEFT, buff=0.08)

    after_box = build_labeled_box(after or "-", width=3.0, height=1.5, color=GREEN_E, fill_opacity=0.14, text_size=18)
    after_header = en_text(after_title, size=20, color=GREEN_B)
    after_group = VGroup(after_header, after_box).arrange(DOWN, aligned_edge=LEFT, buff=0.08)

    arrow = Arrow(LEFT * 0.3, RIGHT * 0.3, stroke_width=2.6, color=HIGHLIGHT_COLOR)
    body = VGroup(before_group, arrow, after_group).arrange(RIGHT, buff=0.28, aligned_edge=UP)

    highlight_side = to_str(p.get("highlight_side"), "").lower()
    if highlight_side == "before":
        body.add(build_highlight_frame(before_box, color=YELLOW_D))
    elif highlight_side == "after":
        body.add(build_highlight_frame(after_box, color=YELLOW_D))

    note = to_str(p.get("note"), "").strip()
    rendered = _add_note(body, note) if note else body
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_pipeline_chain_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    steps = [to_str(x).strip() for x in as_list(p.get("steps")) if to_str(x).strip()]
    if not steps:
        steps = ["Source", "Compile", "Link", "Load", "Run"]

    active_idx = to_int(p.get("active_index"), -1)
    box_gap = max(to_float(p.get("box_gap"), 0.46), 0.14)
    min_box_width = max(to_float(p.get("box_width"), 2.05), 1.0)
    min_box_height = max(to_float(p.get("box_height"), 0.9), 0.5)
    text_size = max(to_float(p.get("text_size"), 20), 12)

    node_color = _string_color(p.get("node_color"), BLUE_E)
    active_color = _string_color(p.get("active_color"), GOLD_E)
    arrow_color = _string_color(p.get("arrow_color"), "#D0D0D0")

    boxes = VGroup()
    for idx, step in enumerate(steps):
        active = idx == active_idx or (active_idx < 0 and idx == 0)
        txt = en_subtitle(step, size=text_size, color=TEXT_COLOR, width=max(to_int(p.get("text_wrap_width"), 24), 10))
        width = max(min_box_width, txt.width + 0.42)
        height = max(min_box_height, txt.height + 0.26)

        rect = RoundedRectangle(corner_radius=0.15, width=width, height=height, color=active_color if active else node_color)
        rect.set_fill(active_color if active else node_color, opacity=0.34 if active else 0.15)
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
                stroke_width=max(to_float(p.get("arrow_width"), 2.4), 1.2),
                color=arrow_color,
            )
        )

    body = VGroup(arrows, boxes)
    title = to_str(p.get("title"), "").strip()
    rendered: Mobject = body
    if title:
        rendered = VGroup(en_text(title, size=24, color=HIGHLIGHT_COLOR), body).arrange(DOWN, aligned_edge=LEFT, buff=0.14)

    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _add_note(rendered, note)

    setattr(rendered, "_mw_pipeline_boxes", boxes)
    setattr(rendered, "_mw_pipeline_arrows", arrows)

    scene.add(rendered)
    return update_context(context, node, rendered)


def build_terminal_output_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    title = to_str(p.get("title"), "Terminal").strip() or "Terminal"
    command = to_str(p.get("command"), "$ ./run").strip() or "$ ./run"
    output_lines = [to_str(x).strip() for x in as_list(p.get("output_lines")) if to_str(x).strip()]
    if not output_lines:
        output_lines = ["Hello, world!"]

    panel_width = max(to_float(p.get("panel_width"), 5.8), 2.4)
    panel_height = max(to_float(p.get("panel_height"), 3.0), 1.2)

    panel = RoundedRectangle(corner_radius=0.16, width=panel_width, height=panel_height, color=BLUE_E)
    panel.set_fill(_string_color(p.get("panel_fill"), "#0f172a"), opacity=0.9)

    header = en_text(title, size=22, color=HIGHLIGHT_COLOR)
    header.next_to(panel.get_top(), DOWN, buff=0.14).align_to(panel.get_left(), LEFT).shift(RIGHT * 0.28)

    cmd = Text(command, font="Consolas", font_size=28, color=_string_color(p.get("command_color"), GREEN_B))
    cmd.next_to(header, DOWN, aligned_edge=LEFT, buff=0.18)

    line_mobs = VGroup()
    for text in output_lines:
        line = Text(text, font="Consolas", font_size=30, color=_string_color(p.get("output_color"), TEXT_COLOR))
        line_mobs.add(line)
    line_mobs.arrange(DOWN, aligned_edge=LEFT, buff=0.2)
    line_mobs.next_to(cmd, DOWN, aligned_edge=LEFT, buff=0.24)

    cursor_text = to_str(p.get("cursor"), "_")
    cursor = Text(cursor_text, font="Consolas", font_size=32, color=_string_color(p.get("cursor_color"), HIGHLIGHT_COLOR))
    cursor.next_to(cmd, RIGHT, buff=0.12)

    body = VGroup(panel, header, cmd, line_mobs, cursor)
    body.move_to(ORIGIN)

    note = to_str(p.get("note"), "").strip()
    rendered: Mobject = _add_note(body, note) if note else body

    setattr(rendered, "_mw_terminal_command", cmd)
    setattr(rendered, "_mw_terminal_output_lines", line_mobs)
    setattr(rendered, "_mw_terminal_cursor", cursor)

    scene.add(rendered)
    return update_context(context, node, rendered)


def build_space_bridge_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    left_title = to_str(p.get("left_title"), "User Space").strip() or "User Space"
    right_title = to_str(p.get("right_title"), "Kernel Space").strip() or "Kernel Space"

    left_items = [to_str(x).strip() for x in as_list(p.get("left_items")) if to_str(x).strip()]
    right_items = [to_str(x).strip() for x in as_list(p.get("right_items")) if to_str(x).strip()]
    if not left_items:
        left_items = ["printf()", "libc buffer", "write(fd=1, buf, len)"]
    if not right_items:
        right_items = ["sys_write handler", "fd lookup", "terminal driver"]

    panel_width = max(to_float(p.get("panel_width"), 5.3), 2.2)
    panel_height = max(to_float(p.get("panel_height"), 4.9), 1.4)
    box_width = max(to_float(p.get("item_width"), 3.2), 1.1)
    box_height = max(to_float(p.get("item_height"), 0.8), 0.38)

    left_panel = RoundedRectangle(corner_radius=0.14, width=panel_width, height=panel_height, color=BLUE_E)
    left_panel.set_fill(_string_color(p.get("left_fill"), "#0E223A"), opacity=0.4)
    right_panel = RoundedRectangle(corner_radius=0.14, width=panel_width, height=panel_height, color=BLUE_E)
    right_panel.set_fill(_string_color(p.get("right_fill"), "#2A1A0E"), opacity=0.35)

    left_panel_group = VGroup(left_panel)
    right_panel_group = VGroup(right_panel)
    container = VGroup(left_panel_group, right_panel_group).arrange(RIGHT, buff=max(to_float(p.get("panel_gap"), 0.8), 0.25), aligned_edge=UP)

    left_header = en_text(left_title, size=21, color=HIGHLIGHT_COLOR)
    right_header = en_text(right_title, size=21, color=HIGHLIGHT_COLOR)
    left_header.next_to(left_panel.get_top(), DOWN, buff=0.12)
    right_header.next_to(right_panel.get_top(), DOWN, buff=0.12)

    def _build_side_items(items: list[str], active_index: int, base_color) -> VGroup:
        groups = VGroup()
        for idx, text in enumerate(items):
            active = idx == active_index
            rect = RoundedRectangle(corner_radius=0.12, width=box_width, height=box_height, color=GOLD_E if active else base_color)
            rect.set_fill(GOLD_E if active else base_color, opacity=0.32 if active else 0.16)
            label = en_subtitle(text, size=19, color=TEXT_COLOR, width=max(to_int(p.get("item_text_wrap"), 26), 10))
            label.move_to(rect.get_center())
            groups.add(VGroup(rect, label))
        groups.arrange(DOWN, buff=max(to_float(p.get("item_gap"), 0.34), 0.08))
        return groups

    left_active = to_int(p.get("left_active_index"), -1)
    right_active = to_int(p.get("right_active_index"), -1)

    left_group = _build_side_items(left_items, left_active, BLUE_D)
    right_group = _build_side_items(right_items, right_active, ORANGE)

    left_group.move_to(left_panel.get_center()).shift(DOWN * 0.25)
    right_group.move_to(right_panel.get_center()).shift(DOWN * 0.25)

    boundary = DashedLine(start=UP * (panel_height * 0.52), end=DOWN * (panel_height * 0.56), color=_string_color(p.get("boundary_color"), RED_E), dash_length=0.1)
    boundary.move_to((left_panel.get_right() + right_panel.get_left()) / 2)

    mode_label = en_text(to_str(p.get("mode_label"), "CPU mode switch"), size=18, color=_string_color(p.get("boundary_color"), RED_E))
    mode_label.next_to(boundary, UP, buff=0.14)

    src_idx = to_int(p.get("bridge_from_index"), len(left_group) - 1)
    dst_idx = to_int(p.get("bridge_to_index"), 0)
    src_idx = min(max(src_idx, 0), max(len(left_group) - 1, 0))
    dst_idx = min(max(dst_idx, 0), max(len(right_group) - 1, 0))
    bridge_arrow = Arrow(
        start=left_group[src_idx].get_right() + RIGHT * 0.03,
        end=right_group[dst_idx].get_left() + LEFT * 0.03,
        buff=0.03,
        stroke_width=max(to_float(p.get("bridge_width"), 2.8), 1.2),
        color=_string_color(p.get("bridge_color"), HIGHLIGHT_COLOR),
    )

    bridge_label_text = to_str(p.get("bridge_label"), "")
    bridge_label = None
    if bridge_label_text:
        bridge_label = en_subtitle(bridge_label_text, size=17, color=_string_color(p.get("bridge_color"), HIGHLIGHT_COLOR), width=32)
        bridge_label.move_to((bridge_arrow.get_start() + bridge_arrow.get_end()) / 2 + UP * 0.18)

    body_items = [left_panel, right_panel, left_header, right_header, left_group, right_group, boundary, mode_label, bridge_arrow]
    if bridge_label is not None:
        body_items.append(bridge_label)
    body = VGroup(*body_items)

    note = to_str(p.get("note"), "").strip()
    rendered: Mobject = _add_note(body, note) if note else body

    setattr(rendered, "_mw_space_left", VGroup(left_panel, left_header, left_group))
    setattr(rendered, "_mw_space_right", VGroup(right_panel, right_header, right_group))
    setattr(rendered, "_mw_space_boundary", VGroup(boundary, mode_label))
    bridge_parts = VGroup(bridge_arrow)
    if bridge_label is not None:
        bridge_parts.add(bridge_label)
    setattr(rendered, "_mw_space_bridge", bridge_parts)

    scene.add(rendered)
    return update_context(context, node, rendered)
