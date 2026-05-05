from manim import *
from typing import Callable, Iterable, Optional, Sequence
import math
import numbers

from .render_primitives import (
    en_text,
    en_subtitle,
    sanitize_latex_text,
    strip_inline_formula_markers,
    TITLE_COLOR,
    SUB_COLOR,
    TEXT_COLOR,
    HIGHLIGHT_COLOR,
)


def _sanitize_latex_text(value: str) -> str:
    return sanitize_latex_text(value)


def _boost_foreground_contrast(mob: Mobject) -> Mobject:
    if hasattr(mob, "set_stroke"):
        mob.set_stroke(BLACK, width=4, background=True)
    return mob


def _fit_within_frame(
    mob: Mobject,
    *,
    side_margin: float = 0.8,
    top_margin: float = 0.35,
    bottom_margin: float = 0.35,
) -> Mobject:
    max_width = max(config.frame_width - side_margin, 0.1)
    max_height = max(config.frame_height - top_margin - bottom_margin, 0.1)

    if mob.width > max_width:
        mob.scale_to_fit_width(max_width)
    if mob.height > max_height:
        mob.scale_to_fit_height(max_height)

    half_limit = max_width / 2
    if mob.get_left()[0] < -half_limit:
        mob.shift(RIGHT * (-half_limit - mob.get_left()[0]))
    if mob.get_right()[0] > half_limit:
        mob.shift(LEFT * (mob.get_right()[0] - half_limit))

    top_limit = config.frame_height / 2 - top_margin
    if mob.get_top()[1] > top_limit:
        mob.shift(DOWN * (mob.get_top()[1] - top_limit))

    bottom_limit = -config.frame_height / 2 + bottom_margin
    if mob.get_bottom()[1] < bottom_limit:
        mob.shift(UP * (bottom_limit - mob.get_bottom()[1]))

    return mob


def _fit_within_frame_width(mob: Mobject, margin: float = 0.8) -> Mobject:
    return _fit_within_frame(mob, side_margin=margin)


def _place_below_within_frame(
    mob: Mobject,
    anchor: Mobject,
    buff: float = 0.3,
    bottom_margin: float = 0.35,
    side_margin: float = 0.8,
) -> Mobject:
    _fit_within_frame(mob, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)
    mob.next_to(anchor, DOWN, buff=buff)

    bottom_limit = -config.frame_height / 2 + bottom_margin
    if mob.get_bottom()[1] < bottom_limit:
        available_top = anchor.get_bottom()[1] - buff
        available_height = max(available_top - bottom_limit, 0.12)
        if mob.height > available_height:
            mob.scale_to_fit_height(available_height)
            _fit_within_frame(mob, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)
            mob.next_to(anchor, DOWN, buff=buff)

    if mob.get_bottom()[1] < bottom_limit:
        mob.shift(UP * (bottom_limit - mob.get_bottom()[1]))

    return _fit_within_frame(mob, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)


def _apply_animation_instant(scene: Scene, animation) -> None:
    nested = getattr(animation, "animations", None)
    if nested:
        for child in nested:
            _apply_animation_instant(scene, child)
        return

    try:
        animation.begin()
        animation.interpolate(1.0)
        animation.finish()
        animation.clean_up_from_scene(scene)

        mob = getattr(animation, "mobject", None)
        if mob is not None and not getattr(animation, "remover", False):
            scene.add(mob)
        return
    except Exception:
        pass

    mob = getattr(animation, "mobject", None)
    if isinstance(animation, FadeOut):
        if mob is not None:
            scene.remove(mob)
        return
    if mob is not None:
        scene.add(mob)


def _scene_play(scene: Scene, *animations, run_time: float = 0.0, instant: bool = False) -> None:
    if instant:
        for animation in animations:
            _apply_animation_instant(scene, animation)
        return
    scene.play(*animations, run_time=run_time)


def _scene_wait(scene: Scene, duration: float, instant: bool = False) -> None:
    if instant:
        return
    scene.wait(duration)


def safe_mathtex(tex: str, **kwargs):
    clean_tex = strip_inline_formula_markers(tex)
    return _fit_within_frame_width(_boost_foreground_contrast(MathTex(_sanitize_latex_text(clean_tex), **kwargs)))


def _update_or_create_header(
    scene: Scene,
    header_text: str,
    header: Optional[Mobject] = None,
    size: float = 30,
    color=TITLE_COLOR,
    run_time: float = 0.6,
    instant: bool = False,
) -> Mobject:
    new_header = _fit_within_frame_width(_boost_foreground_contrast(en_text(header_text, size, color))).to_edge(UP)
    if header is None:
        _scene_play(scene, FadeIn(new_header), run_time=run_time, instant=instant)
        return new_header

    current_text = getattr(header, "text", None)
    new_text = getattr(new_header, "text", None)
    if isinstance(current_text, str) and isinstance(new_text, str) and current_text == new_text:
        return header

    _scene_play(scene, Transform(header, new_header), run_time=run_time, instant=instant)
    return header


def play_title_card(
    scene: Scene,
    title: str,
    subtitle: Optional[str] = None,
    title_size: float = 38,
    subtitle_size: float = 24,
    title_color=TITLE_COLOR,
    subtitle_color=SUB_COLOR,
    hold_time: float = 1.5,
    shift=UP,
) -> VGroup:
    title_mob = _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(title, size=title_size, color=title_color)))
    if subtitle:
        subtitle_mob = _fit_within_frame_width(_boost_foreground_contrast(en_text(subtitle, size=subtitle_size, color=subtitle_color)))
        subtitle_mob.next_to(title_mob, DOWN, buff=0.3)

        bottom_limit = -config.frame_height / 2 + 0.35
        if subtitle_mob.get_bottom()[1] <= bottom_limit + 1e-3:
            subtitle_mob.next_to(title_mob, DOWN, buff=0.3)

        card = _fit_within_frame(VGroup(title_mob, subtitle_mob), side_margin=0.8, top_margin=0.35, bottom_margin=0.35)
    else:
        card = _fit_within_frame(VGroup(title_mob), side_margin=0.8, top_margin=0.35, bottom_margin=0.35)

    card.move_to(ORIGIN)
    card = _fit_within_frame(card, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)

    scene.play(*[FadeIn(m, shift=shift) for m in card], run_time=1.2)
    scene.wait(hold_time)
    scene.play(*[FadeOut(m) for m in card], run_time=0.8)
    return card


def play_transition_scene(
    scene: Scene,
    text: Optional[str] = None,
    pause_time: float = 1.0,
    size: float = 28,
    color=HIGHLIGHT_COLOR,
) -> Optional[Mobject]:
    if not text:
        scene.wait(pause_time)
        return None
    mob = _fit_within_frame(_boost_foreground_contrast(en_subtitle(text, size=size, color=color)), side_margin=0.8, top_margin=0.35, bottom_margin=0.35).to_edge(DOWN)
    mob = _fit_within_frame(mob, side_margin=0.8, top_margin=0.35, bottom_margin=0.35)
    scene.play(FadeIn(mob), run_time=0.6)
    scene.wait(pause_time)
    scene.play(FadeOut(mob), run_time=0.6)
    return mob


def play_formula_focus(
    scene: Scene,
    header_text: str,
    formula_tex: str,
    explanation_items: Optional[Sequence[tuple[str, str]]] = None,
    intro_note: Optional[str] = None,
    remark: Optional[str] = None,
    header: Optional[Mobject] = None,
    header_color=TITLE_COLOR,
    formula_color=WHITE,
    instant: bool = False,
) -> tuple[Mobject, VGroup]:
    header = _update_or_create_header(scene, header_text, header=header, color=header_color, instant=instant)

    rendered = VGroup()
    intro = None
    if intro_note:
        intro = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(intro_note, 24, TEXT_COLOR, width=85))),
            header,
            buff=0.25,
        )
        _scene_play(scene, FadeIn(intro), run_time=0.8, instant=instant)
        rendered.add(intro)

    formula_anchor = intro if intro is not None else header
    formula = _place_below_within_frame(
        _fit_within_frame_width(safe_mathtex(formula_tex, color=formula_color).scale(1.2)),
        formula_anchor,
        buff=0.35,
    )
    _scene_play(scene, Write(formula), run_time=1.2, instant=instant)
    rendered.add(formula)

    explains = None
    if explanation_items:
        rows = []
        for sym, desc in explanation_items:
            sym_m = safe_mathtex(sym, color=YELLOW).scale(1.0)
            desc_m = _fit_within_frame_width(_boost_foreground_contrast(en_text(desc, 24, TEXT_COLOR)))
            row = _fit_within_frame_width(VGroup(sym_m, desc_m).arrange(RIGHT, buff=0.15))
            rows.append(row)
        explains = _place_below_within_frame(
            _fit_within_frame_width(VGroup(*rows).arrange(DOWN, aligned_edge=LEFT, buff=0.25)),
            formula,
            buff=0.3,
        )
        _scene_play(scene, FadeIn(explains), run_time=0.8, instant=instant)
        rendered.add(explains)

    if remark:
        remark_anchor = explains if explains is not None else formula
        remark_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(remark, 24, HIGHLIGHT_COLOR, width=90))),
            remark_anchor,
            buff=0.3,
        )
        _scene_play(scene, FadeIn(remark_m), run_time=0.7, instant=instant)
        rendered.add(remark_m)

    return header, rendered


def _available_vertical_space_below(anchor: Mobject, *, bottom_margin: float = 0.35, buff: float = 0.3) -> float:
    bottom_limit = -config.frame_height / 2 + bottom_margin
    available_top = anchor.get_bottom()[1] - buff
    return max(available_top - bottom_limit, 0.12)


def _place_formula_with_side_fallback(
    formula: Mobject,
    anchor: Mobject,
    *,
    buff: float = 0.3,
    side_margin: float = 0.8,
    bottom_margin: float = 0.35,
) -> Mobject:
    _fit_within_frame(formula, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)

    available_below = _available_vertical_space_below(anchor, bottom_margin=bottom_margin, buff=buff)
    if formula.height <= available_below + 1e-3:
        return _place_below_within_frame(
            formula,
            anchor,
            buff=buff,
            bottom_margin=bottom_margin,
            side_margin=side_margin,
        )

    max_width = max(config.frame_width - side_margin, 0.1)
    half_limit = max_width / 2

    for direction in (RIGHT, LEFT):
        candidate = formula.copy()
        _fit_within_frame(candidate, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)
        candidate.next_to(anchor, direction, buff=buff)

        top_limit = config.frame_height / 2 - 0.35
        bottom_limit = -config.frame_height / 2 + bottom_margin
        if candidate.get_top()[1] > top_limit:
            candidate.shift(DOWN * (candidate.get_top()[1] - top_limit))
        if candidate.get_bottom()[1] < bottom_limit:
            candidate.shift(UP * (bottom_limit - candidate.get_bottom()[1]))

        if candidate.get_left()[0] >= -half_limit and candidate.get_right()[0] <= half_limit:
            formula.move_to(candidate.get_center())
            return _fit_within_frame(formula, side_margin=side_margin, top_margin=0.35, bottom_margin=bottom_margin)

    return _place_below_within_frame(
        formula,
        anchor,
        buff=buff,
        bottom_margin=bottom_margin,
        side_margin=side_margin,
    )


def _nice_tick_step(span: float, target_ticks: int = 6) -> float:
    safe_span = max(float(span), 1e-6)
    raw_step = safe_span / max(int(target_ticks), 1)
    magnitude = 10 ** math.floor(math.log10(raw_step))
    for factor in (1.0, 2.0, 2.5, 5.0, 10.0):
        step = magnitude * factor
        if step >= raw_step:
            return step
    return magnitude * 10.0


def _resolve_scalar_plot_bounds(
    plot_func: Callable[[float], float | Sequence[float]],
    x_min: float,
    x_max: float,
    *,
    samples: int = 160,
) -> tuple[float, float] | None:
    if x_max <= x_min:
        return None

    y_values: list[float] = []
    for x in np.linspace(x_min, x_max, max(samples, 16)):
        try:
            value = plot_func(float(x))
        except Exception:
            continue
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            continue
        if not isinstance(value, numbers.Real):
            continue
        y = float(value)
        if not math.isfinite(y):
            continue
        y_values.append(y)

    if not y_values:
        return None

    return min(y_values), max(y_values)


def _adaptive_y_range(
    y_range: Sequence[float],
    plot_func: Callable[[float], float | Sequence[float]],
    *,
    x_min: float,
    x_max: float,
) -> list[float]:
    base = list(y_range)
    if len(base) < 2:
        return [0.0, 10.0, 1.0]

    y_start = float(base[0])
    y_end = float(base[1])
    if y_end < y_start:
        y_start, y_end = y_end, y_start

    bounds = _resolve_scalar_plot_bounds(plot_func, x_min, x_max)
    if bounds is None:
        step = float(base[2]) if len(base) >= 3 and float(base[2]) > 0 else max((y_end - y_start) / 6.0, 1.0)
        return [y_start, y_end, step]

    data_min, data_max = bounds
    lower = min(y_start, data_min)
    upper = max(y_end, data_max)

    if data_min >= y_start and data_max <= y_end:
        step = float(base[2]) if len(base) >= 3 and float(base[2]) > 0 else max((y_end - y_start) / 6.0, 1.0)
        return [y_start, y_end, step]

    if y_start >= 0 and lower >= 0:
        lower = 0.0

    span = max(upper - lower, 1.0)
    requested_step = float(base[2]) if len(base) >= 3 and float(base[2]) > 0 else None
    step = requested_step if requested_step is not None and span / requested_step <= 10 else _nice_tick_step(span)

    snapped_lower = math.floor(lower / step) * step
    snapped_upper = math.ceil(upper / step) * step
    if snapped_upper <= snapped_lower:
        snapped_upper = snapped_lower + step

    return [float(snapped_lower), float(snapped_upper), float(step)]


def _axes_point_from_y_value(axes: Axes, x_value: float, y_value):
    if isinstance(y_value, numbers.Real):
        return axes.c2p(x_value, float(y_value))
    if isinstance(y_value, Iterable) and not isinstance(y_value, (str, bytes)):
        coords = [float(v) for v in y_value]
        if len(coords) >= 3:
            return axes.c2p(coords[0], coords[1], coords[2])
        if len(coords) == 2:
            return axes.c2p(coords[0], coords[1])
    return axes.c2p(x_value, 0.0)


def play_axes_curve_scene(
    scene: Scene,
    header_text: str,
    x_range: Sequence[float],
    y_range: Sequence[float],
    plot_func: Callable[[float], float | Sequence[float]],
    plot_x_range: Optional[Sequence[float]] = None,
    header: Optional[Mobject] = None,
    note: Optional[str] = None,
    x_label_text: str = "Time",
    y_label_text: str = "Quantity",
    label_color=TEXT_COLOR,
    formula_tex: Optional[str] = None,
    remark: Optional[str] = None,
    curve_color=GREEN,
    header_color=TITLE_COLOR,
    x_length: float = 8,
    y_length: float = 4.5,
    axes_shift=DOWN * 0.4,
    point_x_values: Optional[Sequence[float]] = None,
    point_y_func: Optional[Callable[[float], float]] = None,
    point_color=ORANGE,
    point_radius: float = 0.06,
    instant: bool = False,
) -> tuple[Mobject, VGroup]:

    header = _update_or_create_header(scene, header_text, header=header, color=header_color, instant=instant)

    rendered = VGroup()

    note_m = None
    if note:
        note_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(note, 22, TEXT_COLOR, width=90))),
            header,
            buff=0.25,
        )
        _scene_play(scene, FadeIn(note_m), run_time=0.6, instant=instant)
        rendered.add(note_m)

    x_values = list(x_range)
    if len(x_values) < 2:
        x_values = [0.0, 10.0, 1.0]
    elif len(x_values) < 3:
        x_step = max((float(x_values[1]) - float(x_values[0])) / 6.0, 0.1)
        x_values = [float(x_values[0]), float(x_values[1]), x_step]

    x_min = float(plot_x_range[0]) if plot_x_range else float(x_values[0])
    x_max = float(plot_x_range[1]) if plot_x_range else float(x_values[1])
    if x_max < x_min:
        x_min, x_max = x_max, x_min

    sample_value = None
    try:
        sample_value = plot_func(x_min)
    except Exception:
        sample_value = None

    y_values = list(y_range)
    if len(y_values) < 2:
        y_values = [0.0, 10.0, 1.0]
    elif len(y_values) < 3:
        y_step = max((float(y_values[1]) - float(y_values[0])) / 6.0, 0.1)
        y_values = [float(y_values[0]), float(y_values[1]), y_step]

    if not (isinstance(sample_value, Iterable) and not isinstance(sample_value, (str, bytes))):
        y_values = _adaptive_y_range(y_values, plot_func, x_min=x_min, x_max=x_max)

    axes = Axes(
        x_range=x_values,
        y_range=y_values,
        x_length=x_length,
        y_length=y_length,
        axis_config={"color": GRAY_A},
        tips=False,
    ).shift(axes_shift)

    x_label = _fit_within_frame_width(_boost_foreground_contrast(en_text(x_label_text, 22, label_color)).next_to(axes.x_axis, RIGHT, buff=0.2))
    y_label = _fit_within_frame_width(_boost_foreground_contrast(en_text(y_label_text, 22, label_color)).next_to(axes.y_axis, UP, buff=0.2))

    if isinstance(sample_value, Iterable) and not isinstance(sample_value, (str, bytes)):
        curve = ParametricFunction(
            lambda t: axes.c2p(*plot_func(t)),
            t_range=[x_min, x_max],
            color=curve_color,
        )
    else:
        curve = axes.plot(plot_func, x_range=[x_min, x_max], color=curve_color)

    rendered_group = _fit_within_frame_width(VGroup(axes, x_label, y_label, curve))
    rendered_group = _place_below_within_frame(
        rendered_group,
        note_m if note_m else header,
        buff=0.3,
    )

    _scene_play(scene, Create(axes), FadeIn(x_label), FadeIn(y_label), run_time=1.0, instant=instant)
    _scene_play(scene, Create(curve), run_time=1.6, instant=instant)
    rendered.add(rendered_group)

    points = None
    if point_x_values and point_y_func:
        points = VGroup(*[
            Dot(_axes_point_from_y_value(axes, x, point_y_func(x)), color=point_color, radius=point_radius)
            for x in point_x_values
        ])
        _scene_play(
            scene,
            LaggedStart(*[FadeIn(p, scale=0.6) for p in points], lag_ratio=0.15),
            run_time=1.0,
            instant=instant,
        )
        rendered.add(_fit_within_frame_width(points))

    formula_m = None
    if formula_tex:
        formula_m = _place_formula_with_side_fallback(
            _fit_within_frame_width(safe_mathtex(formula_tex, color=HIGHLIGHT_COLOR).scale(1.0)),
            rendered_group,
            buff=0.3,
        )
        _scene_play(scene, Write(formula_m), run_time=0.8, instant=instant)
        rendered.add(formula_m)

    if remark:
        remark_anchor = formula_m if formula_m is not None else rendered_group
        remark_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_text(remark, 24, HIGHLIGHT_COLOR))),
            remark_anchor,
            buff=0.3,
        )
        _scene_play(scene, FadeIn(remark_m), run_time=0.7, instant=instant)
        rendered.add(remark_m)

    return header, rendered


def play_number_sequence(
    scene: Scene,
    header_text: str,
    values: Sequence,
    header: Optional[Mobject] = None,
    note: Optional[str] = None,
    number_size: float = 28,
    color=TEXT_COLOR,
    header_color=TITLE_COLOR,
    show_arrows: bool = False,
    arrow_color=GRAY_B,
    formula_tex: Optional[str] = None,
    remark: Optional[str] = None,
    instant: bool = False,
) -> tuple[Mobject, VGroup]:
    header = _update_or_create_header(scene, header_text, header=header, color=header_color, instant=instant)

    rendered = VGroup()

    note_m = None
    if note:
        note_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(note, 22, TEXT_COLOR, width=90))),
            header,
            buff=0.25,
        )
        _scene_play(scene, FadeIn(note_m), run_time=0.6, instant=instant)
        rendered.add(note_m)

    num_anchor = note_m if note_m is not None else header
    num_mobs = _place_below_within_frame(
        _fit_within_frame_width(VGroup(*[en_text(str(v), number_size, color) for v in values]).arrange(RIGHT, buff=0.4)),
        num_anchor,
        buff=0.3,
    )
    _scene_play(
        scene,
        LaggedStart(*[FadeIn(n, shift=UP * 0.12) for n in num_mobs], lag_ratio=0.12),
        run_time=1.3,
        instant=instant,
    )
    rendered.add(num_mobs)

    if show_arrows and len(num_mobs) > 1:
        arrows = VGroup(*[
            Arrow(
                start=num_mobs[i].get_right() + RIGHT * 0.08,
                end=num_mobs[i + 1].get_left() + LEFT * 0.08,
                buff=0.05,
                stroke_width=2.5,
                color=arrow_color,
            )
            for i in range(len(num_mobs) - 1)
        ])
        _scene_play(
            scene,
            LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.1),
            run_time=1.0,
            instant=instant,
        )
        rendered.add(_fit_within_frame_width(arrows))

    f = None
    if formula_tex:
        f = _place_below_within_frame(
            _fit_within_frame_width(safe_mathtex(formula_tex, color=HIGHLIGHT_COLOR).scale(1.0)),
            num_mobs,
            buff=0.45,
        )
        _scene_play(scene, Write(f), run_time=0.9, instant=instant)
        rendered.add(f)

    if remark:
        remark_anchor = f if f is not None else num_mobs
        r = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(remark, 24, HIGHLIGHT_COLOR, width=90))),
            remark_anchor,
            buff=0.3,
        )
        _scene_play(scene, FadeIn(r), run_time=0.7, instant=instant)
        rendered.add(r)

    return header, rendered



def _fit_mobject_within_rect(
    mob: Mobject,
    *,
    max_width: float,
    max_height: float,
) -> Mobject:
    target_w = max(max_width, 0.1)
    target_h = max(max_height, 0.1)
    if mob.width > target_w:
        mob.scale_to_fit_width(target_w)
    if mob.height > target_h:
        mob.scale_to_fit_height(target_h)
    if mob.width > target_w:
        mob.scale_to_fit_width(target_w)
    return mob


def _build_comparison_item_group(
    *,
    item: dict,
    default_box_width: float,
    default_box_height: float,
) -> VGroup:
    color = item.get("color")
    if color is None:
        color = BLUE

    width = item.get("width")
    if width is None:
        width = 22

    item_box_width = item.get("box_width")
    if item_box_width is None:
        item_box_width = default_box_width

    item_box_height = item.get("box_height")
    if item_box_height is None:
        item_box_height = default_box_height

    item_title_size = item.get("title_size")
    if item_title_size is None:
        item_title_size = 24

    item_body_size = item.get("body_size")
    if item_body_size is None:
        item_body_size = 21

    box = RoundedRectangle(corner_radius=0.2, width=float(item_box_width), height=float(item_box_height), color=color)

    side_padding = 0.28
    top_padding = 0.24
    bottom_padding = 0.24
    title_body_gap = 0.22

    max_text_width = max(box.width - side_padding * 2, 0.2)
    max_title_height = max(box.height * 0.24, 0.16)
    max_body_height = max(box.height - top_padding - bottom_padding - max_title_height - title_body_gap, 0.16)

    title = _boost_foreground_contrast(en_text(str(item.get("title", "")), float(item_title_size), color))
    _fit_mobject_within_rect(title, max_width=max_text_width, max_height=max_title_height)

    body = _boost_foreground_contrast(
        en_subtitle(str(item.get("body", "")), float(item_body_size), TEXT_COLOR, width=int(width))
    )
    _fit_mobject_within_rect(body, max_width=max_text_width, max_height=max_body_height)

    title_top_y = box.get_top()[1] - top_padding
    title.shift(UP * (title_top_y - title.get_top()[1]))
    title.shift(RIGHT * (box.get_center()[0] - title.get_center()[0]))

    body_bottom_limit = box.get_bottom()[1] + bottom_padding
    body.shift(UP * (body_bottom_limit - body.get_bottom()[1]))
    body.shift(RIGHT * (box.get_center()[0] - body.get_center()[0]))

    body_top_limit = title.get_bottom()[1] - title_body_gap
    if body.get_top()[1] > body_top_limit:
        body.shift(DOWN * (body.get_top()[1] - body_top_limit))

    if body.get_bottom()[1] < body_bottom_limit:
        body.shift(UP * (body_bottom_limit - body.get_bottom()[1]))

    return VGroup(box, title, body)


def play_comparison_boxes(
    scene: Scene,
    header_text: str,
    items: Sequence[dict],
    header: Optional[Mobject] = None,
    note: Optional[str] = None,
    remark: Optional[str] = None,
    header_color=TITLE_COLOR,
    note_color=TEXT_COLOR,
    remark_color=HIGHLIGHT_COLOR,
    box_width: float = 3.8,
    box_height: float = 2.6,
    box_gap: float = 0.45,
    instant: bool = False,
) -> tuple[Mobject, VGroup]:
    header = _update_or_create_header(scene, header_text, header=header, color=header_color, instant=instant)

    rendered = VGroup()

    note_m = None
    if note:
        note_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(note, 22, note_color, width=90))),
            header,
            buff=0.25,
        )
        _scene_play(scene, FadeIn(note_m), run_time=0.6, instant=instant)
        rendered.add(note_m)

    cards = VGroup(*[
        _build_comparison_item_group(
            item=item,
            default_box_width=box_width,
            default_box_height=box_height,
        )
        for item in items
    ])

    if len(cards) > 0:
        cards.arrange(RIGHT, buff=box_gap, aligned_edge=UP)
        cards = _place_below_within_frame(
            _fit_within_frame_width(cards),
            note_m if note_m is not None else header,
            buff=0.3,
        )
        _scene_play(
            scene,
            LaggedStart(*[FadeIn(card, shift=UP * 0.12) for card in cards], lag_ratio=0.12),
            run_time=1.2,
            instant=instant,
        )
        rendered.add(cards)

    if remark:
        remark_anchor = cards if len(cards) > 0 else (note_m if note_m is not None else header)
        remark_m = _place_below_within_frame(
            _fit_within_frame_width(_boost_foreground_contrast(en_subtitle(remark, 24, remark_color, width=90))),
            remark_anchor,
            buff=0.3,
        )
        _scene_play(scene, FadeIn(remark_m), run_time=0.7, instant=instant)
        rendered.add(remark_m)

    return header, rendered


def play_summary_scene(
    scene: Scene,
    summary_lines: Sequence[str],
    formula_tex: Optional[str] = None,
    footer_text: Optional[str] = None,
    line_size: float = 28,
    line_color=TEXT_COLOR,
    line_buff: float = 0.35,
    highlight_last: bool = False,
    highlight_color=HIGHLIGHT_COLOR,
    formula_color=HIGHLIGHT_COLOR,
    formula_scale: float = 1.0,
    footer_size: float = 22,
    footer_color=HIGHLIGHT_COLOR,
    footer_as_subtitle: bool = False,
    wait_time: float = 2.2,
    instant: bool = False,
) -> tuple[None, VGroup]:
    lines = [str(line) for line in summary_lines] if summary_lines else [""]
    rendered = VGroup()

    mobs = []
    for idx, line in enumerate(lines):
        color = highlight_color if highlight_last and idx == len(lines) - 1 else line_color
        mobs.append(_boost_foreground_contrast(en_text(line, line_size, color)))

    top_anchor = Dot(point=UP * (config.frame_height / 2 - 0.35), radius=0.0)
    summary = _place_below_within_frame(
        _fit_within_frame_width(VGroup(*mobs).arrange(DOWN, aligned_edge=LEFT, buff=line_buff)),
        top_anchor,
        buff=0.15,
    )

    for row in summary:
        _scene_play(scene, FadeIn(row, shift=UP * 0.2), run_time=0.8, instant=instant)
    rendered.add(summary)

    formula = None
    if formula_tex:
        formula = _place_below_within_frame(
            _fit_within_frame_width(safe_mathtex(formula_tex, color=formula_color).scale(formula_scale)),
            summary,
            buff=0.6,
        )
        _scene_play(scene, Write(formula), run_time=1.0, instant=instant)
        rendered.add(formula)

    if footer_text:
        footer_anchor = formula or summary
        if footer_as_subtitle:
            footer_base = _boost_foreground_contrast(en_subtitle(footer_text, size=footer_size, color=footer_color, width=90))
        else:
            footer_base = _boost_foreground_contrast(en_text(footer_text, size=footer_size, color=footer_color))
        footer = _place_below_within_frame(_fit_within_frame_width(footer_base), footer_anchor, buff=0.45)
        _scene_play(scene, FadeIn(footer), run_time=0.8, instant=instant)
        rendered.add(footer)

    _scene_wait(scene, wait_time, instant=instant)
    return None, rendered
