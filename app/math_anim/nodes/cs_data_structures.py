from __future__ import annotations

from collections import deque

from manim import *
import numpy as np

from app.math_anim.render_primitives.graph_shapes import build_linked_list_node as build_linked_list_shape, build_tree_node
from app.storyboard.schema import NodeSpec
from app.utils.render_primitives import HIGHLIGHT_COLOR, TEXT_COLOR, en_subtitle, en_text

from .base import as_list, normalize_numeric_values, to_bool, to_float, to_int, to_str, update_context


def _note_wrap(content: Mobject, note_text: str) -> Mobject:
    note = en_subtitle(note_text, size=20, color=TEXT_COLOR, width=80)
    return VGroup(content, note).arrange(DOWN, aligned_edge=LEFT, buff=0.2)


def build_array_cells_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    values = [to_str(x).strip() for x in as_list(p.get("values"))]
    if not values:
        values = ["2", "5", "8", "12", "16", "23"]

    highlight = {int(x) for x in normalize_numeric_values(p.get("highlight_indices"))}
    show_indices = to_bool(p.get("indices"), True)

    cells = VGroup()
    for idx, value in enumerate(values):
        rect = Rectangle(width=max(to_float(p.get("cell_width"), 1.1), 0.4), height=max(to_float(p.get("cell_height"), 0.75), 0.3), color=GOLD_E if idx in highlight else BLUE_E)
        rect.set_fill((GOLD_E if idx in highlight else BLUE_E), opacity=0.3 if idx in highlight else 0.12)
        txt = en_text(value, size=20, color=TEXT_COLOR)
        txt.move_to(rect.get_center())
        cell = VGroup(rect, txt)
        if show_indices:
            idx_text = en_text(str(idx), size=15, color=GRAY_B)
            idx_text.next_to(rect, DOWN, buff=0.06)
            cell.add(idx_text)
        cells.add(cell)
    cells.arrange(RIGHT, buff=0.12, aligned_edge=UP)

    ptr_group = VGroup()
    for ptr in as_list(p.get("pointers")):
        if not isinstance(ptr, dict):
            continue
        label = to_str(ptr.get("label"), "ptr").strip() or "ptr"
        idx = to_int(ptr.get("index"), -1)
        if idx < 0 or idx >= len(cells):
            continue
        arrow = Arrow(
            start=cells[idx].get_top() + UP * 0.42,
            end=cells[idx].get_top() + UP * 0.03,
            buff=0.0,
            stroke_width=2.0,
            color=YELLOW_D,
        )
        text = en_text(label, size=16, color=YELLOW_D)
        text.next_to(arrow, UP, buff=0.04)
        ptr_group.add(arrow, text)

    rendered = VGroup(cells, ptr_group)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)
    scene.add(rendered)
    return update_context(context, node, rendered)


def build_linked_list_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    labels = [to_str(x).strip() for x in as_list(p.get("nodes")) if to_str(x).strip()]
    if not labels:
        labels = ["A", "B", "C"]

    highlight = {int(x) for x in normalize_numeric_values(p.get("highlight_nodes"))}

    nodes = VGroup(*[build_linked_list_shape(label, active=(idx in highlight)) for idx, label in enumerate(labels)])
    nodes.arrange(RIGHT, buff=0.55, aligned_edge=UP)

    edges = VGroup()
    links = as_list(p.get("links"))
    if not links:
        links = [[i, i + 1] for i in range(len(labels) - 1)]

    for item in links:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        src = to_int(item[0], -1)
        dst = to_int(item[1], -1)
        if src < 0 or dst < 0 or src >= len(nodes) or dst >= len(nodes):
            continue
        edges.add(
            Arrow(
                start=nodes[src].get_right() + RIGHT * 0.03,
                end=nodes[dst].get_left() + LEFT * 0.03,
                buff=0.02,
                stroke_width=2.2,
                color="#D0D0D0",
            )
        )

    rendered: Mobject = VGroup(edges, nodes)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    scene.add(rendered)
    return update_context(context, node, rendered)


def _iter_tree_children(root: dict) -> list[dict]:
    children: list[dict] = []
    seen: set[int] = set()

    def push(candidate) -> None:
        if not isinstance(candidate, dict):
            return
        marker = id(candidate)
        if marker in seen:
            return
        seen.add(marker)
        children.append(candidate)

    push(root.get("left"))

    raw_children = root.get("children")
    if isinstance(raw_children, list):
        for child in raw_children:
            push(child)

    push(root.get("right"))

    return children


def _collect_tree_nodes(
    root: dict,
    *,
    depth: int = 0,
    x: float = 0.0,
    spread: float = 2.2,
    node_key: str = "0",
    parent_key: str | None = None,
):
    label = to_str(root.get("value"), "").strip() or "?"
    pos = np.array([x, -depth * 1.05, 0.0])
    nodes = [(node_key, label, pos)]
    edges: list[tuple[str, str]] = []
    if parent_key is not None:
        edges.append((parent_key, node_key))

    children = _iter_tree_children(root)
    child_count = len(children)
    if child_count == 1:
        child_offsets = [0.0]
    elif child_count > 1:
        child_offsets = np.linspace(-spread / 2.0, spread / 2.0, child_count).tolist()
    else:
        child_offsets = []

    next_spread = max(spread * 0.78, 1.1)
    for index, (child, offset) in enumerate(zip(children, child_offsets)):
        child_key = f"{node_key}.{index}"
        n, e = _collect_tree_nodes(
            child,
            depth=depth + 1,
            x=x + float(offset),
            spread=next_spread,
            node_key=child_key,
            parent_key=node_key,
        )
        nodes.extend(n)
        edges.extend(e)

    return nodes, edges


def _normalize_tree_traversal_mode(value: str) -> str | None:
    raw = to_str(value, "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "pre": "preorder",
        "pre_order": "preorder",
        "in": "inorder",
        "in_order": "inorder",
        "post": "postorder",
        "post_order": "postorder",
        "level": "levelorder",
        "level_order": "levelorder",
        "bfs": "levelorder",
    }
    normalized = aliases.get(raw, raw)
    if normalized in {"preorder", "inorder", "postorder", "levelorder"}:
        return normalized
    return None


def _traverse_tree_keys(root: dict, mode: str, *, node_key: str = "0") -> list[str]:
    children = _iter_tree_children(root)

    if mode == "levelorder":
        order: list[str] = []
        queue: deque[tuple[str, dict]] = deque([(node_key, root)])
        while queue:
            current_key, current_node = queue.popleft()
            order.append(current_key)
            for idx, child in enumerate(_iter_tree_children(current_node)):
                queue.append((f"{current_key}.{idx}", child))
        return order

    if mode == "preorder":
        order = [node_key]
        for idx, child in enumerate(children):
            order.extend(_traverse_tree_keys(child, mode, node_key=f"{node_key}.{idx}"))
        return order

    if mode == "postorder":
        order: list[str] = []
        for idx, child in enumerate(children):
            order.extend(_traverse_tree_keys(child, mode, node_key=f"{node_key}.{idx}"))
        order.append(node_key)
        return order

    if mode == "inorder":
        if not children:
            return [node_key]
        if len(children) == 1:
            return _traverse_tree_keys(children[0], mode, node_key=f"{node_key}.0") + [node_key]

        left = _traverse_tree_keys(children[0], mode, node_key=f"{node_key}.0")
        right: list[str] = []
        for idx in range(1, len(children)):
            right.extend(_traverse_tree_keys(children[idx], mode, node_key=f"{node_key}.{idx}"))
        return left + [node_key] + right

    return []


def _key_parts(value: str) -> list[str]:
    raw = to_str(value, "").strip()
    if not raw:
        return []
    return raw.split(".")


def _join_key(parts: list[str]) -> str:
    return ".".join(parts)


def _build_route_edges(prev_key: str, next_key: str) -> list[tuple[str, str]]:
    prev_parts = _key_parts(prev_key)
    next_parts = _key_parts(next_key)
    if not prev_parts or not next_parts:
        return []

    common_len = 0
    max_common = min(len(prev_parts), len(next_parts))
    while common_len < max_common and prev_parts[common_len] == next_parts[common_len]:
        common_len += 1

    edges: list[tuple[str, str]] = []

    # Move upward: child -> parent, but edge key remains (parent, child)
    curr_parts = prev_parts[:]
    while len(curr_parts) > common_len:
        child_key = _join_key(curr_parts)
        parent_parts = curr_parts[:-1]
        if not parent_parts:
            break
        parent_key = _join_key(parent_parts)
        edges.append((parent_key, child_key))
        curr_parts = parent_parts

    # Move downward from LCA to next
    curr_parts = next_parts[:common_len]
    for idx in range(common_len, len(next_parts)):
        parent_key = _join_key(curr_parts)
        curr_parts.append(next_parts[idx])
        child_key = _join_key(curr_parts)
        if parent_key and child_key:
            edges.append((parent_key, child_key))

    return edges


def _build_tree_step_edges(order: list[str]) -> list[list[tuple[str, str]]]:
    steps: list[list[tuple[str, str]]] = []
    prev: str | None = None
    for key in order:
        if prev is None:
            steps.append([])
        else:
            steps.append(_build_route_edges(prev, key))
        prev = key
    return steps



def build_tree_diagram_node(scene: Scene, node: NodeSpec, context, **_) -> Mobject | None:
    p = node.params
    root = p.get("root") if isinstance(p.get("root"), dict) else {"value": "8", "left": {"value": "3"}, "right": {"value": "10"}}

    highlight_labels = {to_str(x).strip() for x in as_list(p.get("highlight_path")) if to_str(x).strip()}
    highlight_keys = {to_str(x).strip() for x in as_list(p.get("highlight_keys")) if to_str(x).strip()}
    node_data, edge_data = _collect_tree_nodes(root)

    circle_nodes: dict[str, VGroup] = {}
    node_labels: dict[str, str] = {}
    circles = VGroup()
    positions_by_key: dict[str, np.ndarray] = {}

    for node_key, label, pos in node_data:
        active = node_key in highlight_keys or label in highlight_labels
        circle = build_tree_node(label, active=active)
        circle.move_to(pos)
        circles.add(circle)
        circle_nodes[node_key] = circle
        node_labels[node_key] = label
        positions_by_key[node_key] = pos

    line_edges = VGroup()
    edge_lines: dict[tuple[str, str], Line] = {}
    for src_key, dst_key in edge_data:
        src_pos = positions_by_key.get(src_key)
        dst_pos = positions_by_key.get(dst_key)
        if src_pos is None or dst_pos is None:
            continue
        edge = Line(src_pos, dst_pos, stroke_width=2.2, color="#D0D0D0")
        line_edges.add(edge)
        edge_lines[(src_key, dst_key)] = edge

    traversal_mode = _normalize_tree_traversal_mode(p.get("traversal_mode"))
    traversal_order = _traverse_tree_keys(root, traversal_mode, node_key="0") if traversal_mode else []
    traversal_step_edges = _build_tree_step_edges(traversal_order)

    rendered: Mobject = VGroup(line_edges, circles)
    note = to_str(p.get("note"), "").strip()
    if note:
        rendered = _note_wrap(rendered, note)

    setattr(rendered, "_mw_tree_node_map", circle_nodes)
    setattr(rendered, "_mw_tree_label_map", node_labels)
    setattr(rendered, "_mw_tree_edge_map", edge_lines)
    setattr(rendered, "_mw_tree_traversal_mode", traversal_mode)
    setattr(rendered, "_mw_tree_traversal_order", traversal_order)
    setattr(rendered, "_mw_tree_traversal_step_edges", traversal_step_edges)
    setattr(rendered, "_mw_tree_highlight_color", p.get("traversal_highlight_color") or HIGHLIGHT_COLOR)
    setattr(rendered, "_mw_tree_highlight_scale", max(to_float(p.get("traversal_highlight_scale"), 1.08), 1.0))

    scene.add(rendered)
    return update_context(context, node, rendered)


