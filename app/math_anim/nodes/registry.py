from __future__ import annotations

from app.math_anim.math_nodes import (
    ROLE_PRIORITY,
    RenderContext,
    build_axes_curve_node,
    build_comparison_boxes_node,
    build_formula_focus_node,
    build_group_node,
    build_number_sequence_node,
    build_process_flow_node,
    build_relation_map_node,
    build_rich_text_label_node,
    build_stat_bar_grid_node,
    build_summary_block_node,
    build_text_label_node,
    build_title_card_node,
    build_transition_note_node,
)
from app.math_anim.nodes.common import (
    build_before_after_panel_node,
    build_callout_panel_node,
    build_code_panel_node,
    build_concept_map_node,
    build_layer_stack_node,
    build_pipeline_chain_node,
    build_space_bridge_node,
    build_state_machine_node,
    build_table_grid_node,
    build_terminal_output_node,
    build_timeline_node,
)
from app.math_anim.nodes.cs_cpu import build_cpu_state_node, build_instruction_cycle_node
from app.math_anim.nodes.cs_data_structures import build_array_cells_node, build_linked_list_node, build_tree_diagram_node
from app.math_anim.nodes.cs_memory import build_address_space_node, build_memory_grid_node, build_stack_frame_trace_node


NODE_BUILDERS = {
    "title_card": build_title_card_node,
    "transition_note": build_transition_note_node,
    "formula_focus": build_formula_focus_node,
    "axes_curve": build_axes_curve_node,
    "number_sequence": build_number_sequence_node,
    "comparison_boxes": build_comparison_boxes_node,
    "summary_block": build_summary_block_node,
    "text_label": build_text_label_node,
    "rich_text_label": build_rich_text_label_node,
    "relation_map": build_relation_map_node,
    "stat_bar_grid": build_stat_bar_grid_node,
    "process_flow": build_process_flow_node,
    "group": build_group_node,
    "timeline": build_timeline_node,
    "state_machine": build_state_machine_node,
    "layer_stack": build_layer_stack_node,
    "table_grid": build_table_grid_node,
    "code_panel": build_code_panel_node,
    "callout_panel": build_callout_panel_node,
    "concept_map": build_concept_map_node,
    "before_after_panel": build_before_after_panel_node,
    "pipeline_chain": build_pipeline_chain_node,
    "terminal_output": build_terminal_output_node,
    "space_bridge": build_space_bridge_node,
    "memory_grid": build_memory_grid_node,
    "address_space": build_address_space_node,
    "stack_frame_trace": build_stack_frame_trace_node,
    "cpu_state": build_cpu_state_node,
    "instruction_cycle": build_instruction_cycle_node,
    "array_cells": build_array_cells_node,
    "linked_list": build_linked_list_node,
    "tree_diagram": build_tree_diagram_node,
}


def register_node_builder(node_type: str, builder):
    NODE_BUILDERS[node_type] = builder


def get_node_builder(node_type: str):
    try:
        return NODE_BUILDERS[node_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported node type: {node_type}") from exc
