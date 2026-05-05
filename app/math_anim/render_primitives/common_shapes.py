from __future__ import annotations

from manim import *

from app.utils.render_primitives import TEXT_COLOR, en_subtitle, en_text


def build_labeled_box(
    label: str,
    *,
    width: float = 2.2,
    height: float = 0.9,
    color=BLUE_E,
    fill_opacity: float = 0.2,
    text_size: float = 22,
    text_color=TEXT_COLOR,
) -> VGroup:
    rect = RoundedRectangle(corner_radius=0.12, width=width, height=height, color=color)
    rect.set_fill(color, opacity=fill_opacity)
    txt = en_subtitle(label, size=text_size, color=text_color, width=30)
    txt.move_to(rect.get_center())
    return VGroup(rect, txt)


def build_labeled_circle(
    label: str,
    *,
    radius: float = 0.36,
    color=BLUE_D,
    fill_color="#123B7A",
    text_size: float = 20,
    text_color=WHITE,
) -> VGroup:
    txt = en_text(label, size=text_size, color=text_color)
    needed_radius = max(txt.width / 1.64, txt.height / 1.44, radius)
    circle = Circle(radius=needed_radius, color=color)
    circle.set_fill(fill_color, opacity=0.85)
    txt.move_to(circle.get_center())
    return VGroup(circle, txt)


def build_timeline_cell(
    label: str,
    *,
    active: bool = False,
    width: float = 1.7,
    height: float = 0.75,
) -> VGroup:
    color = GOLD_E if active else BLUE_E
    opacity = 0.35 if active else 0.16
    return build_labeled_box(label, width=width, height=height, color=color, fill_opacity=opacity, text_size=18)


def build_callout(
    text: str,
    *,
    title: str | None = None,
    width: float = 4.8,
    color=YELLOW_D,
) -> VGroup:
    body = RoundedRectangle(corner_radius=0.15, width=width, height=1.5, color=color)
    body.set_fill(color, opacity=0.08)
    txt = en_subtitle(text, size=20, color=TEXT_COLOR, width=58)
    txt.move_to(body.get_center())
    content = VGroup(body, txt)
    if not title:
        return content
    t = en_text(title, size=20, color=color)
    t.next_to(body, UP, buff=0.12)
    return VGroup(t, content)


def build_highlight_frame(target: Mobject, *, color=YELLOW, buff: float = 0.08, stroke_width: float = 2.8) -> SurroundingRectangle:
    return SurroundingRectangle(target, color=color, buff=buff, stroke_width=stroke_width)
