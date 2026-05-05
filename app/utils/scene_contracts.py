"""
Prompt-facing helper contract for Manim math-story generation.

All helpers are intended for Python 3.x + Manim Community v0.18.1.
Use these blocks to reduce repeated scene wiring and lower generation error rate.
"""

HELPER_CONTRACT = {
    "imports": [
        "from app.utils.render_primitives import BG_COLOR, TITLE_COLOR, SUB_COLOR, TEXT_COLOR, FORMULA_COLOR, HIGHLIGHT_COLOR, en_text, en_subtitle, fade_out_all, switch_header",
        "from app.utils.story_blocks import play_title_card, play_transition_scene, play_formula_focus, play_axes_curve_scene, play_number_sequence, play_comparison_boxes, play_summary_scene",
    ],
    "render_primitives": {
        "en_text": {
            "signature": "en_text(text, size=30, color=TEXT_COLOR, **kwargs) -> Text",
            "behavior": "Single-line Text with shared default style.",
        },
        "en_subtitle": {
            "signature": "en_subtitle(text, size=30, color=TEXT_COLOR, width=80, center=True, **kwargs) -> VGroup",
            "behavior": "Wrapped multi-line subtitle block.",
        },
        "switch_header": {
            "signature": "switch_header(scene, old_header, text, size=30, color=TITLE_COLOR, run_time=0.6) -> Text",
            "behavior": "Header transition helper with FadeIn/FadeOut.",
        },
        "fade_out_all": {
            "signature": "fade_out_all(scene, run_time=0.8) -> None",
            "behavior": "Fade out all current scene mobjects.",
        },
    },
    "story_blocks": {
        "play_title_card": {
            "signature": "play_title_card(scene, title, subtitle=None, title_size=38, subtitle_size=24, ...) -> VGroup",
            "behavior": "Intro title/subtitle card with hold then fade out.",
        },
        "play_transition_scene": {
            "signature": "play_transition_scene(scene, text=None, pause_time=1.0, size=28, color=HIGHLIGHT_COLOR) -> Optional[Mobject]",
            "behavior": "Lightweight narration bridge; optional text-only transition.",
        },
        "play_formula_focus": {
            "signature": "play_formula_focus(scene, header_text, formula_tex, explanation_items=None, intro_note=None, remark=None, header=None, ...) -> (header, rendered)",
            "behavior": "Section header + optional intro + formula + optional symbol explanations + optional bottom remark.",
        },
        "play_axes_curve_scene": {
            "signature": "play_axes_curve_scene(scene, header_text, x_range, y_range, plot_func, plot_x_range=None, note=None, x_label_text='Time', y_label_text='Quantity', formula_tex=None, remark=None, point_x_values=None, point_y_func=None, ...) -> (header, rendered)",
            "behavior": "Header + optional note + axes + labels + one curve + optional points + optional formula + optional remark.",
        },
        "play_number_sequence": {
            "signature": "play_number_sequence(scene, header_text, values, note=None, show_arrows=False, formula_tex=None, remark=None, ...) -> (header, rendered)",
            "behavior": "Header + optional note + staged number sequence + optional arrows + optional formula/remark.",
        },
        "play_comparison_boxes": {
            "signature": "play_comparison_boxes(scene, header_text, items, note=None, remark=None, ...) -> (header, rendered)",
            "behavior": "Header + optional note + horizontal rounded boxes with title/body + optional remark.",
        },
        "play_summary_scene": {
            "signature": "play_summary_scene(scene, summary_lines, formula_tex=None, footer_text=None, highlight_last=False, footer_as_subtitle=False, ...) -> VGroup",
            "behavior": "Multi-line ending summary with optional formula/footer and last-line highlight.",
        },
    },
    "generation_guidelines": [
        "Prefer scene blocks over ad-hoc FadeIn/Create/Write wiring for common story patterns.",
        "Use core Manim primitives only; avoid plugins, voiceover packages, and experimental APIs.",
        "Keep layout explicit and conservative for cross-version stability.",
    ],
}
