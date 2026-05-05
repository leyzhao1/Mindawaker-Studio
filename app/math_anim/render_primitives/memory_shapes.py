from __future__ import annotations

from manim import *

from app.utils.render_primitives import TEXT_COLOR, en_subtitle, en_text


def build_memory_cell(
    value: str,
    *,
    address: str | None = None,
    width: float = 1.3,
    height: float = 0.7,
    color=BLUE_E,
    active: bool = False,
    text_size: float = 20,
    min_width: float = 0.6,
    min_height: float = 0.4,
    h_pad: float = 0.3,
    v_pad: float = 0.22,
) -> VGroup:
    value_text = en_text(value, size=text_size, color=TEXT_COLOR)
    cell_w = max(min_width, value_text.width + h_pad, width)
    cell_h = max(min_height, value_text.height + v_pad, height)
    rect = Rectangle(width=cell_w, height=cell_h, color=GOLD_E if active else color)
    rect.set_fill((GOLD_E if active else color), opacity=0.3 if active else 0.14)
    value_text.move_to(rect.get_center())
    cell = VGroup(rect, value_text)
    if not address:
        return cell
    addr = en_text(address, size=15, color=GRAY_B)
    addr.next_to(rect, DOWN, buff=0.08)
    return VGroup(cell, addr)


def build_register_box(name: str, value: str, *, width: float = 2.6, height: float = 0.68) -> VGroup:
    rect = RoundedRectangle(corner_radius=0.1, width=width, height=height, color=TEAL_E)
    rect.set_fill(TEAL_E, opacity=0.12)
    name_text = en_text(name, size=18, color=TEAL_A)
    value_text = en_subtitle(value, size=18, color=TEXT_COLOR, width=26)
    row = VGroup(name_text, value_text).arrange(RIGHT, buff=0.25)
    if row.width > rect.width * 0.9:
        row.scale_to_fit_width(rect.width * 0.9)
    row.move_to(rect.get_center())
    return VGroup(rect, row)


def build_stack_frame(name: str, locals_text: str, *, width: float = 3.8, height: float = 0.95, active: bool = False) -> VGroup:
    color = ORANGE if active else BLUE_E
    rect = RoundedRectangle(corner_radius=0.12, width=width, height=height, color=color)
    rect.set_fill(color, opacity=0.24 if active else 0.12)
    title = en_text(name, size=19, color=TEXT_COLOR)
    subtitle = en_subtitle(locals_text, size=16, color=GRAY_A, width=44)
    stack = VGroup(title, subtitle).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
    if stack.width > rect.width * 0.9:
        stack.scale_to_fit_width(rect.width * 0.9)
    stack.move_to(rect.get_center())
    return VGroup(rect, stack)
