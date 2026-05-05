from manim import *
import re
import textwrap
from typing import Any, Optional


INLINE_LATEX_MARKER_PATTERN = re.compile(r"\$([^$]+)\$|\\\((.*?)\\\)")


def strip_inline_formula_markers(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    cleaned = INLINE_LATEX_MARKER_PATTERN.sub(
        lambda m: (m.group(1) or m.group(2) or "").strip(),
        raw,
    )
    cleaned = cleaned.replace("$", "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


BG_COLOR = "#000000"
TITLE_COLOR = "#7FDBFF"
SUB_COLOR = "#F2F2F2"
TEXT_COLOR = "#F5F5F5"
FORMULA_COLOR = WHITE
HIGHLIGHT_COLOR = "#FFD54F"


def sanitize_latex_text(value: str) -> str:
    cleaned = (value or "")
    cleaned = cleaned.replace("\f" + "rac", r"\frac")
    cleaned = cleaned.replace("\t" + "heta", r"\theta")
    cleaned = cleaned.replace("\r" + "ight", r"\right")
    cleaned = cleaned.replace("\a" + "pprox", r"\approx")
    cleaned = cleaned.replace("\t" + "o", r"\to")
    unicode_to_latex = {
        "θ": r"\theta",
        "π": r"\pi",
        "α": r"\alpha",
        "β": r"\beta",
        "γ": r"\gamma",
        "λ": r"\lambda",
        "μ": r"\mu",
        "σ": r"\sigma",
        "Δ": r"\Delta",
        "∞": r"\infty",
        "≈": r"\approx",
        "≤": r"\le",
        "≥": r"\ge",
    }
    for ch, latex_cmd in unicode_to_latex.items():
        cleaned = cleaned.replace(ch, latex_cmd)
    return cleaned


def _split_inline_formula_segments(text: str) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    cursor = 0

    for match in INLINE_LATEX_MARKER_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            segments.append(("text", text[cursor:start]))

        latex = (match.group(1) or match.group(2) or "").strip()
        if latex:
            segments.append(("latex", latex))
        cursor = end

    if cursor < len(text):
        segments.append(("text", text[cursor:]))

    if not segments:
        segments.append(("text", text))
    return segments


def _has_inline_formula_markers(text: str) -> bool:
    return bool(INLINE_LATEX_MARKER_PATTERN.search(text or ""))


def _build_mixed_inline_text(
    text: str,
    *,
    size: float,
    color,
    font: str,
    text_kwargs: dict[str, Any],
) -> Mobject:
    segments = _split_inline_formula_segments(text)
    has_latex = any(kind == "latex" for kind, _ in segments)
    if not has_latex:
        clean_txt = strip_inline_formula_markers(text)
        return Text(clean_txt, font=font, font_size=size, color=color, **text_kwargs)

    parts: list[Mobject] = []
    for kind, value in segments:
        if kind == "latex":
            try:
                formula = MathTex(sanitize_latex_text(value), color=color)
                formula.scale(max(float(size), 1.0) / 30.0)
                parts.append(formula)
                continue
            except Exception:
                value = strip_inline_formula_markers(value)

        clean_value = strip_inline_formula_markers(value)
        if clean_value:
            parts.append(Text(clean_value, font=font, font_size=size, color=color, **text_kwargs))

    if not parts:
        return Text("", font=font, font_size=size, color=color, **text_kwargs)

    if len(parts) == 1:
        return parts[0]

    return VGroup(*parts).arrange(RIGHT, buff=0.1, aligned_edge=DOWN)


def en_text(txt: str, size: float = 30, color=TEXT_COLOR, font: str = "Arial", **kwargs) -> Mobject:
    raw_txt = str(txt or "")
    if not _has_inline_formula_markers(raw_txt):
        clean_txt = strip_inline_formula_markers(raw_txt)
        return Text(clean_txt, font=font, font_size=size, color=color, **kwargs)

    return _build_mixed_inline_text(
        raw_txt,
        size=size,
        color=color,
        font=font,
        text_kwargs=kwargs,
    )


def en_subtitle(
    txt: str,
    size: float = 30,
    color=TEXT_COLOR,
    width: int = 80,
    center: bool = True,
    line_buff: float = 0.12,
    bottom_margin: float = 0.35,
    font: str = "Arial",
    **kwargs,
) -> VGroup:
    raw_txt = str(txt or "")
    source_lines = raw_txt.splitlines() or [""]
    rendered_lines: list[Mobject] = []

    for source_line in source_lines:
        if _has_inline_formula_markers(source_line):
            rendered_lines.append(
                _build_mixed_inline_text(
                    source_line,
                    size=size,
                    color=color,
                    font=font,
                    text_kwargs=kwargs,
                )
            )
            continue

        clean_line = strip_inline_formula_markers(source_line)
        wrapped = textwrap.wrap(clean_line, max(int(width), 1)) if clean_line else [""]
        rendered_lines.extend(
            [
                Text(line, font=font, font_size=size, color=color, **kwargs)
                for line in wrapped
            ]
        )

    lines = VGroup(*rendered_lines)
    if len(lines) > 1:
        lines.arrange(DOWN, aligned_edge=ORIGIN, buff=line_buff)
    if center:
        lines.center()

    bottom_limit = -config.frame_height / 2 + float(bottom_margin)
    lines.shift(UP * (bottom_limit - lines.get_bottom()[1]))
    return lines


def fade_out_all(scene: Scene, run_time: float = 0.8) -> None:
    if scene.mobjects:
        scene.play(*[FadeOut(m) for m in list(scene.mobjects)], run_time=run_time)


def switch_header(
    scene: Scene,
    old_header: Optional[Mobject],
    text: str,
    size: float = 30,
    color=TITLE_COLOR,
    run_time: float = 0.6,
) -> Text:
    new_header = en_text(text, size=size, color=color).to_edge(UP)
    if old_header is None:
        scene.play(FadeIn(new_header), run_time=run_time)
    else:
        scene.play(FadeOut(old_header), FadeIn(new_header), run_time=run_time)
    return new_header
