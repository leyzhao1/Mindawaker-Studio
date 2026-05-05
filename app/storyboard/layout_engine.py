from __future__ import annotations

from typing import Callable

from manim import *

from app.math_anim.math_nodes import ROLE_PRIORITY, RenderContext
from app.storyboard.schema import NodeSpec, SceneSpec


SceneLayoutHandler = Callable[..., list[Mobject]]
GroupLayoutHandler = Callable[..., Mobject | None]


def _sort_by_role(nodes: list[NodeSpec]) -> list[NodeSpec]:
    return sorted(nodes, key=lambda n: (ROLE_PRIORITY.get(n.role, 99), n.key))


def _safe_to_vgroup(children: list[Mobject]) -> VGroup:
    return VGroup(*children) if children else VGroup()


def _apply_group_vertical(node: NodeSpec, children: list[Mobject], **_) -> Mobject | None:
    if not children:
        return None
    group = _safe_to_vgroup(children)
    return group.arrange(DOWN, aligned_edge=LEFT, buff=float(node.params.get("group_buff", 0.3)))


def _apply_group_horizontal(node: NodeSpec, children: list[Mobject], **_) -> Mobject | None:
    if not children:
        return None
    group = _safe_to_vgroup(children)
    return group.arrange(RIGHT, aligned_edge=UP, buff=float(node.params.get("group_buff", 0.35)))


def _apply_group_overlay(node: NodeSpec, children: list[Mobject], **_) -> Mobject | None:
    if not children:
        return None
    anchor = children[0]
    for child in children[1:]:
        child.move_to(anchor.get_center())
    return _safe_to_vgroup(children)


def _apply_group_anchor_relative(node: NodeSpec, children: list[Mobject], **_) -> Mobject | None:
    if not children:
        return None
    anchor = children[0]
    slot = str(node.params.get("slot", "right"))
    buff = float(node.params.get("group_buff", 0.25))
    for child in children[1:]:
        if slot == "left":
            child.next_to(anchor, LEFT, buff=buff)
        elif slot == "below":
            child.next_to(anchor, DOWN, buff=buff)
        elif slot == "upper_right":
            child.next_to(anchor, UR, buff=buff)
        else:
            child.next_to(anchor, RIGHT, buff=buff)
    return _safe_to_vgroup(children)


def _apply_group_auto_grid(node: NodeSpec, children: list[Mobject], **_) -> Mobject | None:
    if not children:
        return None
    limited = children[:4]
    if len(limited) == 1:
        return limited[0]
    cols = 2
    rows = (len(limited) + 1) // 2
    grid = VGroup(*limited).arrange_in_grid(
        rows=rows,
        cols=cols,
        buff=(float(node.params.get("grid_row_buff", 0.35)), float(node.params.get("grid_col_buff", 0.4))),
    )
    return grid


GROUP_LAYOUT_REGISTRY: dict[str, GroupLayoutHandler] = {
    "vertical": _apply_group_vertical,
    "horizontal": _apply_group_horizontal,
    "overlay": _apply_group_overlay,
    "anchor_relative": _apply_group_anchor_relative,
    "auto_grid": _apply_group_auto_grid,
}


def register_group_layout(name: str, handler: GroupLayoutHandler) -> None:
    GROUP_LAYOUT_REGISTRY[name] = handler


def apply_group_layout(node: NodeSpec, children: list[Mobject], context: RenderContext) -> Mobject | None:
    hint = node.layout_hint or "vertical"
    handler = GROUP_LAYOUT_REGISTRY.get(hint, _apply_group_vertical)
    arranged = handler(node=node, children=children, context=context)
    if arranged is None:
        return None
    return _scale_within_frame_bounds(arranged)


def _fit_within_frame_width(mob: Mobject, side_margin: float = 0.8) -> Mobject:
    max_width = max(config.frame_width - side_margin, 0.1)
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    half_limit = max_width / 2
    if mob.get_left()[0] < -half_limit:
        mob.shift(RIGHT * (-half_limit - mob.get_left()[0]))
    if mob.get_right()[0] > half_limit:
        mob.shift(LEFT * (mob.get_right()[0] - half_limit))
    return mob


def _fit_within_frame_height(
    mob: Mobject,
    *,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    max_height = max(config.frame_height - top_margin - bottom_margin, 0.1)
    if mob.height > max_height:
        mob.scale_to_fit_height(max_height)

    top_limit = config.frame_height / 2 - top_margin
    if mob.get_top()[1] > top_limit:
        mob.shift(DOWN * (mob.get_top()[1] - top_limit))

    bottom_limit = -config.frame_height / 2 + bottom_margin
    if mob.get_bottom()[1] < bottom_limit:
        mob.shift(UP * (bottom_limit - mob.get_bottom()[1]))

    return mob


def _scale_within_frame_bounds(
    mob: Mobject,
    *,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    max_width = max(config.frame_width - side_margin, 0.1)
    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)

    max_height = max(config.frame_height - top_margin - bottom_margin, 0.1)
    if mob.height > max_height:
        mob.scale_to_fit_height(max_height)

    return mob


def _clamp_within_frame(
    mob: Mobject,
    *,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    _fit_within_frame_width(mob, side_margin=side_margin)
    _fit_within_frame_height(mob, top_margin=top_margin, bottom_margin=bottom_margin)
    _fit_within_frame_width(mob, side_margin=side_margin)
    return mob




def _compute_layout_corridor(
    *,
    header: Mobject | None,
    narration: Mobject | None,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
    header_buff: float = 0.3,
    narration_buff: float = 0.22,
) -> tuple[float, float]:
    top_limit = config.frame_height / 2 - top_margin
    if header is not None:
        top_limit = min(top_limit, float(header.get_bottom()[1]) - header_buff)

    bottom_limit = -config.frame_height / 2 + bottom_margin
    if narration is not None:
        bottom_limit = max(bottom_limit, float(narration.get_top()[1]) + narration_buff)

    if top_limit <= bottom_limit:
        center = (top_limit + bottom_limit) / 2
        top_limit = center + 0.06
        bottom_limit = center - 0.06

    return top_limit, bottom_limit



def _available_layout_height(
    *,
    header: Mobject | None,
    narration: Mobject | None,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
    buff: float = 0.3,
) -> float:
    top_limit, bottom_limit = _compute_layout_corridor(
        header=header,
        narration=narration,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
        header_buff=buff,
    )
    return max(top_limit - bottom_limit, 0.12)



def _place_group_in_corridor(
    group: Mobject,
    *,
    header: Mobject | None,
    narration: Mobject | None,
    buff: float = 0.3,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    _scale_within_frame_bounds(
        group,
        side_margin=side_margin,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
    )

    top_limit, bottom_limit = _compute_layout_corridor(
        header=header,
        narration=narration,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
        header_buff=buff,
    )
    corridor_height = max(top_limit - bottom_limit, 0.12)

    if group.height > corridor_height:
        group.scale_to_fit_height(corridor_height)
        _fit_within_frame_width(group, side_margin=side_margin)

    target_center_y = (top_limit + bottom_limit) / 2
    group.shift(UP * (target_center_y - group.get_center()[1]))
    group.shift(RIGHT * (0.0 - group.get_center()[0]))

    if group.get_top()[1] > top_limit:
        group.shift(DOWN * (group.get_top()[1] - top_limit))
    if group.get_bottom()[1] < bottom_limit:
        group.shift(UP * (bottom_limit - group.get_bottom()[1]))

    _fit_within_frame_width(group, side_margin=side_margin)

    if group.get_top()[1] > top_limit:
        group.shift(DOWN * (group.get_top()[1] - top_limit))
    if group.get_bottom()[1] < bottom_limit:
        group.shift(UP * (bottom_limit - group.get_bottom()[1]))

    return group



def _layout_scene_group(
    group: Mobject,
    rendered_nodes: list[Mobject],
    *,
    header: Mobject | None,
    narration: Mobject | None,
    buff: float = 0.3,
) -> list[Mobject]:
    _place_group_in_corridor(group, header=header, narration=narration, buff=buff)
    _clamp_within_frame(group)
    group.shift(RIGHT * (0.0 - group.get_center()[0]))
    _fit_within_frame_width(group, side_margin=0.8)
    return rendered_nodes

def clamp_mobject_within_frame(
    mob: Mobject,
    *,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    return _clamp_within_frame(
        mob,
        side_margin=side_margin,
        top_margin=top_margin,
        bottom_margin=bottom_margin,
    )


def _bbox_overlap_area(a: Mobject, b: Mobject) -> float:
    left = max(float(a.get_left()[0]), float(b.get_left()[0]))
    right = min(float(a.get_right()[0]), float(b.get_right()[0]))
    bottom = max(float(a.get_bottom()[1]), float(b.get_bottom()[1]))
    top = min(float(a.get_top()[1]), float(b.get_top()[1]))

    width = right - left
    height = top - bottom
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def _is_out_of_frame(
    mob: Mobject,
    *,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
    epsilon: float = 1e-4,
) -> bool:
    left_limit = -(config.frame_width - side_margin) / 2
    right_limit = (config.frame_width - side_margin) / 2
    top_limit = config.frame_height / 2 - top_margin
    bottom_limit = -config.frame_height / 2 + bottom_margin

    return (
        float(mob.get_left()[0]) < left_limit - epsilon
        or float(mob.get_right()[0]) > right_limit + epsilon
        or float(mob.get_top()[1]) > top_limit + epsilon
        or float(mob.get_bottom()[1]) < bottom_limit - epsilon
    )


def _has_overlap(nodes: list[Mobject], area_epsilon: float = 1e-3) -> bool:
    filtered = [node for node in nodes if node is not None]
    for idx, current in enumerate(filtered):
        for other in filtered[idx + 1 :]:
            if _bbox_overlap_area(current, other) > area_epsilon:
                return True
    return False


def _overlaps_fixed_elements(
    nodes: list[Mobject],
    *,
    header: Mobject | None,
    narration: Mobject | None,
    area_epsilon: float = 1e-3,
) -> bool:
    anchors = [mob for mob in (header, narration) if mob is not None]
    if not anchors:
        return False

    for node in nodes:
        for anchor in anchors:
            if _bbox_overlap_area(node, anchor) > area_epsilon:
                return True
    return False


def _enforce_scene_safety(
    rendered_nodes: list[Mobject],
    *,
    header: Mobject | None,
    narration: Mobject | None,
    layout_mode: str,
    buff: float = 0.3,
) -> list[Mobject]:
    if not rendered_nodes:
        return rendered_nodes

    if header is not None:
        _clamp_within_frame(header, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)
    if narration is not None:
        _clamp_within_frame(narration, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)
        if header is not None and narration.get_top()[1] > header.get_bottom()[1] - 0.3:
            narration.next_to(header, DOWN, buff=0.3)
            _clamp_within_frame(narration, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)

    for node in rendered_nodes:
        _clamp_within_frame(node)

    needs_fallback = _has_overlap(rendered_nodes)
    if not needs_fallback:
        needs_fallback = _overlaps_fixed_elements(rendered_nodes, header=header, narration=narration)
    if not needs_fallback:
        needs_fallback = any(_is_out_of_frame(node) for node in rendered_nodes)

    if not needs_fallback:
        return rendered_nodes

    fallback_group = VGroup(*rendered_nodes).arrange(DOWN, aligned_edge=ORIGIN, buff=buff)
    _place_group_in_corridor(fallback_group, header=header, narration=narration, buff=buff)
    _clamp_within_frame(fallback_group)

    if (
        _has_overlap(rendered_nodes)
        or _overlaps_fixed_elements(rendered_nodes, header=header, narration=narration)
        or any(_is_out_of_frame(node) for node in rendered_nodes)
    ):
        available_height = _available_layout_height(
            header=header,
            narration=narration,
            bottom_margin=0.35,
            buff=buff,
        )
        if fallback_group.height > available_height:
            fallback_group.scale_to_fit_height(max(available_height, 0.12))
            _fit_within_frame_width(fallback_group, side_margin=0.8)
            _place_group_in_corridor(fallback_group, header=header, narration=narration, buff=buff)
            _clamp_within_frame(fallback_group)

    return rendered_nodes


def _scene_stack_with_footer(
    *,
    scene: Scene,
    rendered_nodes: list[Mobject],
    _scene_spec: SceneSpec,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    if not rendered_nodes:
        return []
    group = VGroup(*rendered_nodes).arrange(DOWN, aligned_edge=ORIGIN, buff=0.3)
    return _layout_scene_group(group, rendered_nodes, header=header, narration=narration)


def _scene_two_col(
    *,
    scene: Scene,
    rendered_nodes: list[Mobject],
    _scene_spec: SceneSpec,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    if not rendered_nodes:
        return []

    left = VGroup()
    right = VGroup()
    for idx, node in enumerate(rendered_nodes):
        (left if idx % 2 == 0 else right).add(node)

    if len(left) > 0:
        left.arrange(DOWN, aligned_edge=LEFT, buff=0.3)
    if len(right) > 0:
        right.arrange(DOWN, aligned_edge=LEFT, buff=0.3)

    if len(left) == 0 or len(right) == 0:
        pair = VGroup(left, right).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
    else:
        horizontal = VGroup(left, right).arrange(RIGHT, buff=0.8, aligned_edge=UP)
        max_width = max(config.frame_width - 0.8, 0.1)
        available_height = _available_layout_height(
            header=header,
            narration=narration,
            buff=0.3,
        )

        width_ratio = (max_width * 0.98) / horizontal.width if horizontal.width > 0 else 1.0
        height_ratio = (available_height * 0.98) / horizontal.height if horizontal.height > 0 else 1.0
        scale_ratio = min(width_ratio, height_ratio, 1.0)
        if scale_ratio < 1.0:
            horizontal.scale(scale_ratio)

        if horizontal.width <= max_width * 0.98 and horizontal.height <= available_height * 0.98:
            pair = horizontal
        else:
            pair = VGroup(left, right).arrange(DOWN, aligned_edge=LEFT, buff=0.35)

    return _layout_scene_group(pair, rendered_nodes, header=header, narration=narration)


def _scene_card_row(
    *,
    scene: Scene,
    rendered_nodes: list[Mobject],
    _scene_spec: SceneSpec,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    if not rendered_nodes:
        return []
    row = VGroup(*rendered_nodes).arrange(RIGHT, buff=0.45)
    return _layout_scene_group(row, rendered_nodes, header=header, narration=narration)


def _scene_summary_stack(
    *,
    scene: Scene,
    rendered_nodes: list[Mobject],
    _scene_spec: SceneSpec,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    if not rendered_nodes:
        return []
    stack = VGroup(*rendered_nodes).arrange(DOWN, aligned_edge=ORIGIN, buff=0.35)
    return _layout_scene_group(stack, rendered_nodes, header=header, narration=narration)


def _scene_plot_with_side_annotation(
    *,
    scene: Scene,
    rendered_nodes: list[Mobject],
    _scene_spec: SceneSpec,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    if not rendered_nodes:
        return []

    if len(rendered_nodes) == 1:
        group = VGroup(rendered_nodes[0])
        return _layout_scene_group(group, rendered_nodes, header=header, narration=narration)

    main = rendered_nodes[0]
    side = VGroup(*rendered_nodes[1:]).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
    horizontal = VGroup(main, side).arrange(RIGHT, buff=0.6, aligned_edge=UP)

    max_width = max(config.frame_width - 0.8, 0.1)
    available_height = _available_layout_height(
        header=header,
        narration=narration,
        buff=0.3,
    )
    if horizontal.width > max_width * 0.98 or side.height > available_height * 0.75:
        layout_group = VGroup(main, side).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
    else:
        layout_group = horizontal

    return _layout_scene_group(layout_group, rendered_nodes, header=header, narration=narration)


SCENE_LAYOUT_REGISTRY: dict[str, SceneLayoutHandler] = {
    "stack_with_footer": _scene_stack_with_footer,
    "two_col": _scene_two_col,
    "card_row": _scene_card_row,
    "summary_stack": _scene_summary_stack,
    "plot_with_side_annotation": _scene_plot_with_side_annotation,
}


def register_scene_layout(name: str, handler: SceneLayoutHandler) -> None:
    SCENE_LAYOUT_REGISTRY[name] = handler


def compose_scene_layout(
    scene: Scene,
    scene_spec: SceneSpec,
    rendered_nodes: list[Mobject],
    *,
    header: Mobject | None = None,
    narration: Mobject | None = None,
) -> list[Mobject]:
    handler = SCENE_LAYOUT_REGISTRY.get(scene_spec.layout_mode)
    if handler is None:
        raise ValueError(f"Unsupported scene layout mode: {scene_spec.layout_mode}")
    laid_out = handler(scene=scene, rendered_nodes=rendered_nodes, _scene_spec=scene_spec, header=header, narration=narration)
    return _enforce_scene_safety(
        laid_out,
        header=header,
        narration=narration,
        layout_mode=scene_spec.layout_mode,
    )


def sort_scene_nodes(scene_spec: SceneSpec) -> list[NodeSpec]:
    return _sort_by_role(scene_spec.nodes)
