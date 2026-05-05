from __future__ import annotations

import json
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any

from manim import DOWN, LEFT, RIGHT, UP, Arrow, FadeIn, FadeOut, Mobject, Restore, Scene, VGroup, config
import numpy as np

from app.math_anim.math_nodes import RenderContext, reveal_node
from app.storyboard.layout_engine import apply_group_layout, clamp_mobject_within_frame, compose_scene_layout, sort_scene_nodes
from app.storyboard.node_registry import build_node
from app.storyboard.schema import InterArrowSpec, NodeSpec, Storyboard, ensure_storyboard
from app.utils.render_primitives import en_subtitle, en_text, strip_inline_formula_markers


@dataclass
class RenderedScene:
    header: Mobject | None = None
    narration: Mobject | None = None
    nodes: list[Mobject] = field(default_factory=list)
    persistent: list[Mobject] = field(default_factory=list)

    @property
    def all_mobjects(self) -> list[Mobject]:
        items: list[Mobject] = []
        if self.header is not None:
            items.append(self.header)
        if self.narration is not None:
            items.append(self.narration)
        items.extend(self.nodes)
        items.extend(self.persistent)
        return items


def _build_node_recursive(
    *,
    scene: Scene,
    node,
    context: RenderContext,
) -> Mobject | None:
    return build_node(
        scene=scene,
        node=node,
        context=context,
        build_child=_build_node_recursive,
        group_layout=apply_group_layout,
    )


def _resolve_exit_kind(scene_spec) -> str:
    transitions = scene_spec.transitions
    if transitions is None:
        return "fade_out"
    if transitions.exit_kind is not None:
        return transitions.exit_kind
    if transitions.kind is not None:
        return transitions.kind
    return "fade_out"


def _resolve_exit_run_time(scene_spec, default: float = 0.8) -> float:
    transitions = scene_spec.transitions
    if transitions is not None and transitions.run_time is not None:
        return float(transitions.run_time)
    return default


def _normalize_narration_text(text: str) -> str:
    normalized = strip_inline_formula_markers(text)
    replacements = {
        r"\pi": "π",
        r"\theta": "θ",
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\sigma": "σ",
        r"\\pi": "π",
        r"\\theta": "θ",
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\lambda": "λ",
        r"\\mu": "μ",
        r"\\sigma": "σ",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("\\", "")
    normalized = normalized.replace("{", "").replace("}", "")
    return normalized


def _build_narration_group(text: str, size: float, color: str, width: int) -> Mobject:
    lines = str(text).splitlines() or [""]
    rendered_lines: list[Mobject] = []

    for raw_line in lines:
        line = _normalize_narration_text(raw_line).strip()
        if not line:
            rendered_lines.append(en_subtitle("", size=size, color=color, width=width, center=False))
            continue
        rendered_lines.append(en_subtitle(line, size=size, color=color, width=width, center=False))

    if len(rendered_lines) == 1:
        return rendered_lines[0]

    return VGroup(*rendered_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.12)


def _build_narration_with_wrap_fallback(text: str, size: float, color: str) -> Mobject:
    side_margin = 0.8
    max_width = max(config.frame_width - side_margin, 0.1)

    for wrap_width in (90, 84, 78, 72, 66, 60, 54, 48, 42, 36):
        narration = _build_narration_group(text, size=size, color=color, width=wrap_width)
        if narration.width <= max_width + 1e-3:
            return narration

    fallback = _build_narration_group(text, size=size, color=color, width=30)
    return fallback


def _build_header(scene: Scene, scene_spec) -> Mobject | None:
    if scene_spec.header is None:
        return None
    header = en_text(
        scene_spec.header.text,
        size=float(scene_spec.header.size or 34),
        color=scene_spec.header.color or "#58C4DD",
    ).to_edge(UP)
    clamp_mobject_within_frame(header, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)
    scene.add(header)
    return header


def _build_narration(scene: Scene, scene_spec, header: Mobject | None) -> Mobject | None:
    if scene_spec.narration is None:
        return None
    narration = _build_narration_with_wrap_fallback(
        scene_spec.narration.text,
        size=22,
        color="#DCDCDC",
    )
    narration.to_edge(DOWN, buff=0.35)
    bottom_margin = 0.35
    clamp_mobject_within_frame(narration, side_margin=0.8, top_margin=0.35, bottom_margin=bottom_margin)

    if header is not None and narration.get_top()[1] > header.get_bottom()[1] - 0.3:
        top_limit = header.get_bottom()[1] - 0.3
        narration.shift(DOWN * (narration.get_top()[1] - top_limit))
        clamp_mobject_within_frame(narration, side_margin=0.8, top_margin=0.35, bottom_margin=bottom_margin)

    scene.add(narration)
    return narration


def _resolve_mobject_by_path(key_path: str, context: RenderContext) -> Mobject | None:
    parts = key_path.split(".")
    parent_mob = context.rendered_nodes.get(parts[0])
    if parent_mob is None:
        return None
    if len(parts) == 1:
        return parent_mob
    child_map = getattr(parent_mob, "_mw_child_map", None)
    if not isinstance(child_map, dict):
        return None
    return child_map.get(parts[1])


def _arrow_anchor_point(mob: Mobject, side: str | None, offset_ratio: float) -> np.ndarray:
    if side is None:
        return mob.get_center()
    ratio = max(0.0, min(1.0, offset_ratio))
    ul = mob.get_corner(UP + LEFT)
    ur = mob.get_corner(UP + RIGHT)
    dl = mob.get_corner(DOWN + LEFT)
    dr = mob.get_corner(DOWN + RIGHT)
    if side == "top":
        return ul + (ur - ul) * ratio
    if side == "bottom":
        return dl + (dr - dl) * ratio
    if side == "left":
        return ul + (dl - ul) * ratio
    if side == "right":
        return ur + (dr - ur) * ratio
    return mob.get_center()


def _auto_anchor_side(source_pos: np.ndarray, target_pos: np.ndarray) -> tuple[str, str]:
    """Pick the nearest-facing sides for source→target arrow."""
    delta = target_pos - source_pos
    dx, dy = float(delta[0]), float(delta[1])
    if abs(dx) > abs(dy):
        return ("right", "left") if dx > 0 else ("left", "right")
    else:
        return ("top", "bottom") if dy > 0 else ("bottom", "top")


def _draw_inter_arrows(
    scene: Scene,
    inter_arrows: list[InterArrowSpec],
    context: RenderContext,
) -> list[Mobject]:
    drawn: list[Mobject] = []
    default_color = "#FFD700"

    for spec in inter_arrows:
        source_mob = _resolve_mobject_by_path(spec.source, context)
        target_mob = _resolve_mobject_by_path(spec.target, context)
        if source_mob is None or target_mob is None:
            continue

        source_pos = source_mob.get_center()
        target_pos = target_mob.get_center()

        if spec.source_anchor:
            src_pt = _arrow_anchor_point(source_mob, spec.source_anchor.side, spec.source_anchor.offset_ratio)
        else:
            auto_src_side, _ = _auto_anchor_side(source_pos, target_pos)
            src_pt = _arrow_anchor_point(source_mob, auto_src_side, 0.5)

        if spec.target_anchor:
            dst_pt = _arrow_anchor_point(target_mob, spec.target_anchor.side, spec.target_anchor.offset_ratio)
        else:
            _, auto_dst_side = _auto_anchor_side(source_pos, target_pos)
            dst_pt = _arrow_anchor_point(target_mob, auto_dst_side, 0.5)

        color = spec.color or default_color
        if spec.style == "curved":
            arrow = Arrow(
                start=src_pt,
                end=dst_pt,
                stroke_width=spec.stroke_width,
                color=color,
            )
            drawn.append(arrow)
        else:
            arrow = Arrow(
                start=src_pt,
                end=dst_pt,
                stroke_width=spec.stroke_width,
                color=color,
            )
            drawn.append(arrow)

        scene.add(arrow)

        if spec.label:
            lbl = en_subtitle(spec.label, size=18, color=color, width=50)
            lbl.move_to((src_pt + dst_pt) / 2 + UP * 0.16)
            drawn.append(lbl)
            scene.add(lbl)

    return drawn


def _hide_mobject_for_reveal(mob: Mobject) -> None:
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


def _play_pending_text_label_reveals(scene: Scene, context: RenderContext) -> None:
    if not context.pending_text_label_reveals:
        return
    for mob, run_time in context.pending_text_label_reveals:
        scene.play(FadeIn(mob), run_time=run_time)
    context.pending_text_label_reveals.clear()


def _collect_leaf_keys(nodes: list[NodeSpec]) -> set[str]:
    keys: set[str] = set()

    def _walk(items: list[NodeSpec]) -> None:
        for item in items:
            if item.children:
                _walk(item.children)
            else:
                keys.add(item.key)

    _walk(nodes)
    return keys


def _resolve_scene_duration(scene_spec) -> float:
    if scene_spec.timing and scene_spec.timing.duration_hint is not None:
        duration = float(scene_spec.timing.duration_hint)
        if duration > 0:
            return duration

    max_end = 0.0

    def _walk(items: list[NodeSpec]) -> None:
        nonlocal max_end
        for item in items:
            if item.children:
                _walk(item.children)
                continue
            if item.timing and item.timing.end_s is not None:
                max_end = max(max_end, float(item.timing.end_s))

    _walk(scene_spec.nodes)
    return max_end


def _estimate_non_timeline_elapsed(
    reveal_candidates: list[tuple[NodeSpec, Mobject]],
) -> float:
    special_elapsed = 0.0
    reveal_elapsed = 0.0

    for node_spec, _ in reveal_candidates:
        if node_spec.type in {"title_card", "transition_note"}:
            if node_spec.timing and node_spec.timing.start_s is not None and node_spec.timing.end_s is not None:
                duration = float(node_spec.timing.end_s) - float(node_spec.timing.start_s)
                if duration > 0:
                    special_elapsed += duration
                    continue

            run_time = float(node_spec.params.get("run_time", 0.8) or 0.8)
            if node_spec.type == "title_card":
                hold_time = float(node_spec.params.get("hold_time", 1.5) or 1.5)
                special_elapsed += max(run_time, 0.05) + hold_time + 0.8
            else:
                pause_time = float(node_spec.params.get("pause_time", 1.0) or 1.0)
                special_elapsed += max(run_time, 0.05) + pause_time + 0.6
            continue

        reveal_run_time = float(node_spec.params.get("run_time", 0.8) or 0.8)
        reveal_elapsed += max(reveal_run_time, 0.05)

    return special_elapsed + reveal_elapsed


def _play_timeline_reveals(
    *,
    scene: Scene,
    scene_spec,
    reveal_candidates: list[tuple[NodeSpec, Mobject]],
    context: RenderContext,
) -> bool:
    leaf_keys = _collect_leaf_keys(scene_spec.nodes)
    timeline_events: list[tuple[float, float, int, NodeSpec, Mobject]] = []

    for idx, (node_spec, node_mobject) in enumerate(reveal_candidates):
        if node_spec.key not in leaf_keys:
            continue
        if node_spec.timing is None:
            continue
        if node_spec.timing.start_s is None or node_spec.timing.end_s is None:
            continue

        start_s = float(node_spec.timing.start_s)
        end_s = float(node_spec.timing.end_s)
        if end_s <= start_s:
            continue
        timeline_events.append((start_s, end_s, idx, node_spec, node_mobject))

    if not timeline_events:
        return False

    timeline_events.sort(key=lambda item: (item[0], item[2]))
    scene_duration = _resolve_scene_duration(scene_spec)

    cursor = 0.0
    for start_s, end_s, _, node_spec, node_mobject in timeline_events:
        start = max(start_s, 0.0)
        if scene_duration > 0:
            start = min(start, scene_duration)
        if start > cursor:
            scene.wait(start - cursor)
            cursor = start

        run_time = max(end_s - start_s, 0.05)
        reveal_node(
            scene=scene,
            node=node_spec,
            rendered=node_mobject,
            context=context,
            run_time_override=run_time,
            scene_narration_chunks=scene_spec.narration_chunks,
        )
        cursor = max(cursor, end_s)

    if scene_duration > cursor:
        scene.wait(scene_duration - cursor)

    return True


def clear_rendered_scene(
    scene: Scene,
    rendered: RenderedScene,
    policy: str = "clear_all",
    run_time: float = 0.8,
    exit_kind: str = "fade_out",
) -> None:
    if policy == "manual":
        return

    if exit_kind == "none":
        return

    if exit_kind != "fade_out":
        return

    if policy == "clear_all":
        targets = rendered.all_mobjects
    elif policy == "keep_header":
        targets = [m for m in rendered.all_mobjects if rendered.header is None or m is not rendered.header]
    elif policy == "keep_nodes":
        targets = [m for m in rendered.all_mobjects if m is rendered.narration]
    else:
        targets = rendered.all_mobjects

    unique_targets: list[Mobject] = []
    seen: set[int] = set()
    for mob in targets:
        key = id(mob)
        if key in seen:
            continue
        seen.add(key)
        unique_targets.append(mob)

    if unique_targets:
        scene.play(*[FadeOut(m) for m in unique_targets], run_time=run_time)


def render_storyboard(scene: Scene, storyboard: Storyboard | dict[str, Any] | str) -> Storyboard:
    sb = ensure_storyboard(storyboard)
    context = RenderContext()

    for scene_spec in sb.scenes:
        context.scene_header_text = scene_spec.header.text if scene_spec.header else None
        context.defer_text_label_reveal = True
        context.pending_text_label_reveals.clear()
        rendered = RenderedScene()

        rendered.header = _build_header(scene, scene_spec)
        if rendered.header is not None:
            rendered.persistent.append(rendered.header)
            context.current_header = rendered.header
        else:
            context.current_header = None

        rendered.narration = _build_narration(scene, scene_spec, rendered.header)

        reveal_candidates: list[tuple[Any, Mobject]] = []
        hidden_candidates: list[Mobject] = []
        layout_candidates: list[Mobject] = []
        for node in sort_scene_nodes(scene_spec):
            node_mobject = _build_node_recursive(scene=scene, node=node, context=context)
            if node_mobject is None:
                continue

            if node.type != "title_card":
                rendered.nodes.append(node_mobject)

            if node.type not in {"title_card", "transition_note"}:
                hidden_candidates.append(node_mobject)
                layout_candidates.append(node_mobject)

            reveal_candidates.append((node, node_mobject))

        if layout_candidates:
            compose_scene_layout(
                scene=scene,
                scene_spec=scene_spec,
                rendered_nodes=layout_candidates,
                header=rendered.header,
                narration=rendered.narration,
            )

        for node_spec, node_mobject in reveal_candidates:
            if node_spec.type not in {"text_label", "rich_text_label"}:
                continue
            clamp_mobject_within_frame(node_mobject, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)

        inter_arrow_mobjects: list[Mobject] = []
        if scene_spec.inter_arrows:
            inter_arrow_mobjects = _draw_inter_arrows(scene, scene_spec.inter_arrows, context)
            for mob in inter_arrow_mobjects:
                mob.save_state()
                _hide_mobject_for_reveal(mob)

        for mob in hidden_candidates:
            mob.save_state()
            _hide_mobject_for_reveal(mob)

        if inter_arrow_mobjects:
            for mob in inter_arrow_mobjects:
                scene.play(Restore(mob), run_time=0.4)

        used_timeline = _play_timeline_reveals(
            scene=scene,
            scene_spec=scene_spec,
            reveal_candidates=reveal_candidates,
            context=context,
        )

        if not used_timeline:
            for node_spec, node_mobject in reveal_candidates:
                reveal_node(
                    scene=scene,
                    node=node_spec,
                    rendered=node_mobject,
                    context=context,
                    scene_narration_chunks=scene_spec.narration_chunks,
                )

            scene_duration = _resolve_scene_duration(scene_spec)
            if scene_duration > 0:
                non_timeline_elapsed = _estimate_non_timeline_elapsed(reveal_candidates)
                if scene_duration > non_timeline_elapsed:
                    scene.wait(scene_duration - non_timeline_elapsed)

        _play_pending_text_label_reveals(scene, context)
        context.defer_text_label_reveal = False

        hold_after = None
        if scene_spec.timing and scene_spec.timing.hold_after is not None:
            hold_after = float(scene_spec.timing.hold_after)
        hold_after = max(hold_after, 2.0) if hold_after else 2.5
        if hold_after > 0:
            scene.wait(hold_after)

        clear_rendered_scene(
            scene=scene,
            rendered=rendered,
            policy=scene_spec.clear_policy,
            run_time=_resolve_exit_run_time(scene_spec),
            exit_kind=_resolve_exit_kind(scene_spec),
        )

        if scene_spec.clear_policy == "clear_all":
            context.current_header = None

    return sb


def emit_python_script(storyboard: Storyboard | dict[str, Any] | str) -> str:
    sb = ensure_storyboard(storyboard)
    payload = sb.model_dump(mode="json")
    payload_json = json.dumps(payload, ensure_ascii=False)
    payload_literal = repr(payload_json)

    return dedent(
        f'''
        from manim import *
        import json
        from app.storyboard.renderer import render_storyboard


        STORYBOARD_DATA = json.loads({payload_literal})


        class StoryboardScene(Scene):
            def construct(self):
                self.camera.background_color = "#00000000"
                render_storyboard(self, STORYBOARD_DATA)
        '''
    ).strip() + "\n"
