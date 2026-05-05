from __future__ import annotations

from typing import Any, Callable

from manim import Mobject, Scene

from app.math_anim.math_nodes import RenderContext
from app.math_anim.nodes.registry import get_node_builder, register_node_builder
from app.storyboard.schema import NodeSpec


NodeBuilder = Callable[..., Mobject | None]


def build_node(
    *,
    scene: Scene,
    node: NodeSpec,
    context: RenderContext,
    build_child: Callable[..., Mobject | None],
    group_layout: Callable[..., Mobject | None],
    **kwargs: Any,
) -> Mobject | None:
    builder = get_node_builder(node.type)
    return builder(
        scene=scene,
        node=node,
        context=context,
        build_child=build_child,
        group_layout=group_layout,
        **kwargs,
    )
