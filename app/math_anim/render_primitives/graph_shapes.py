from __future__ import annotations

from manim import *

from app.math_anim.render_primitives.common_shapes import build_labeled_circle


def build_linked_list_node(label: str, *, active: bool = False) -> VGroup:
    color = GOLD_E if active else BLUE_D
    fill = "#7D5B00" if active else "#123B7A"
    return build_labeled_circle(label, radius=0.34, color=color, fill_color=fill, text_size=20)


def build_tree_node(label: str, *, active: bool = False) -> VGroup:
    color = GOLD_E if active else TEAL_E
    fill = "#7D5B00" if active else "#0E3A35"
    return build_labeled_circle(label, radius=0.32, color=color, fill_color=fill, text_size=19)
