from __future__ import annotations

from manim import *

from app.utils.render_primitives import TEXT_COLOR, en_subtitle, en_text


TOKEN_COLORS = {
    "keyword": YELLOW_E,
    "identifier": BLUE_B,
    "string": GREEN_E,
    "number": ORANGE,
    "comment": GRAY_B,
    "plain": TEXT_COLOR,
}


def build_code_token(text: str, *, kind: str = "plain", size: float = 18) -> Mobject:
    color = TOKEN_COLORS.get(kind, TEXT_COLOR)
    return en_text(text, size=size, color=color)


def build_code_line(tokens: list[dict[str, str]] | list[str] | str, *, size: float = 18) -> Mobject:
    if isinstance(tokens, str):
        return en_subtitle(tokens, size=size, color=TEXT_COLOR, width=72)

    parts = VGroup()
    for item in tokens:
        if isinstance(item, dict):
            parts.add(build_code_token(str(item.get("text", "")), kind=str(item.get("kind", "plain")), size=size))
        else:
            parts.add(build_code_token(str(item), kind="plain", size=size))

    if len(parts) == 0:
        return en_text("", size=size, color=TEXT_COLOR)
    if len(parts) == 1:
        return parts[0]
    return parts.arrange(RIGHT, aligned_edge=DOWN, buff=0.05)


def build_code_panel(title: str | None, lines: list[dict] | list[str], *, width: float = 6.2) -> VGroup:
    body = RoundedRectangle(corner_radius=0.12, width=width, height=2.8, color=BLUE_E)
    body.set_fill("#0D1B2A", opacity=0.7)

    rendered_lines = VGroup()
    for line in lines:
        rendered_lines.add(build_code_line(line, size=17))
    if len(rendered_lines) == 0:
        rendered_lines.add(en_text("", size=17, color=TEXT_COLOR))
    rendered_lines.arrange(DOWN, aligned_edge=LEFT, buff=0.11)

    if rendered_lines.width > body.width * 0.9:
        rendered_lines.scale_to_fit_width(body.width * 0.9)
    if rendered_lines.height > body.height * 0.78:
        rendered_lines.scale_to_fit_height(body.height * 0.78)
    rendered_lines.move_to(body.get_center())

    panel = VGroup(body, rendered_lines)
    if not title:
        return panel
    t = en_text(title, size=20, color=BLUE_A)
    t.next_to(body, UP, buff=0.1)
    return VGroup(t, panel)
