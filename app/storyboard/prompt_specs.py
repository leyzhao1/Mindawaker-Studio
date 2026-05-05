from __future__ import annotations

GENERATION_PROMPT = """You are generating a storyboard JSON for a Manim math-story renderer.

Rules:
1. Return JSON only.
2. Do not output Python code.
3. Do not output any raw layout geometry such as next_to, shift, move_to, to_edge, VGroup, arrange.
4. Use only the allowed scene layout modes and node types.
5. Use semantic structure only: type, params, children, role, layout_hint.
6. Prefer helper-compatible node types:
   - title_card
   - transition_note
   - formula_focus
   - axes_curve
   - number_sequence
   - comparison_boxes
   - summary_block
   - text_label
   - rich_text_label
   - relation_map
   - stat_bar_grid
   - process_flow
   - group
   - timeline
   - state_machine
   - layer_stack
   - table_grid
   - code_panel
   - callout_panel
   - concept_map
   - before_after_panel
   - pipeline_chain
   - terminal_output
   - space_bridge
   - memory_grid
   - address_space
   - stack_frame_trace
   - cpu_state
   - instruction_cycle
   - array_cells
   - linked_list
   - tree_diagram
7. If a scene needs nested content, use group with children.
8. For plots, use plot_kind + expression or preset; never return Python lambda.
9. If narration exists, include narration_chunks with chunk_id/text/start/end.
10. Every leaf node must include timing.start_s, timing.end_s, timing.align_chunk_id.
11. Keep leaf timing within scene timing.duration_hint when provided.
12. For all textual fields, wrap inline math formulas with delimiters like $...$ or \\(...\\). This includes header.text, narration.text, narration_chunks[].text, text_label/rich_text_label params.text, note, remark, summary_lines, comparison box title/body, title/subtitle/footer_text, etc.
13. Do NOT wrap formula_tex with $...$ or \\(...\\); keep formula_tex as raw LaTeX content.
14. For relation_map/stat_bar_grid/process_flow, category_label is optional; if omitted, renderer defaults are used.
15. When nodes in a scene have semantic connections (data flow, dependency, cause-effect, pipeline stages, call chains), describe them with an "inter_arrows" array on the scene. Each entry:
    - source: node key (e.g. "n1"), or "parent.child" dot-path for children inside groups
    - target: node key or dot-path
    - label (optional): short annotation text on the arrow
    - color (optional): hex color, default "#FFD700"
    - stroke_width (optional): default 2.4
    - style: "straight" (default) or "curved"
    - source_anchor / target_anchor (optional): {"side": "top"|"bottom"|"left"|"right", "offset_ratio": 0.5}
    Use inter_arrows sparingly — only when arrows convey essential meaning beyond what layout alone shows. Never add arrows between unrelated nodes.
16. For system-layer instructional scenes, prefer these semantic nodes:
    - pipeline_chain: stage-by-stage flows (e.g., source→compile→link→load→run)
    - space_bridge: cross-boundary transitions (e.g., user space ↔ kernel space)
    - terminal_output: command/result reveal in terminal-like panels
17. Parameter contract reminders for new nodes:
    - pipeline_chain params: steps (array of labels, required), active_index (optional), title/note (optional)
    - space_bridge params: left_title/right_title, left_items/right_items (arrays), bridge_label (optional)
    - terminal_output params: command (required), output_lines (array, required), cursor/title optional
18. Keep output valid JSON.
"""

REPAIR_PROMPT = """Your previous output was invalid.

Fix the output so that:
- it is valid JSON
- it matches schema version mw_storyboard_v1
- it contains no Python code
- it contains no layout geometry commands
- it uses only allowed node types and layout modes
- narration chunks include chunk_id when narration exists
- each leaf node includes timing.start_s, timing.end_s, timing.align_chunk_id
- inline formulas in all textual fields are wrapped with delimiters ($...$ or \\(...\\))
- formula_tex values remain raw LaTeX and are not wrapped with delimiters

Return corrected JSON only.
"""

