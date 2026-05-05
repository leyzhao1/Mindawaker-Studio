from typing import Any

from .schema import (
    Storyboard,
    SceneSpec,
    NodeSpec,
    HeaderSpec,
    NarrationSpec,
    TimingSpec,
    TransitionSpec,
    AssetRequirement,
    GlobalStyle,
    VideoMetadata,
    validate_storyboard_json,
    StoryboardValidationError,
)


def render_storyboard(*args: Any, **kwargs: Any):
    from .renderer import render_storyboard as _render_storyboard

    return _render_storyboard(*args, **kwargs)


def emit_python_script(*args: Any, **kwargs: Any):
    from .renderer import emit_python_script as _emit_python_script

    return _emit_python_script(*args, **kwargs)


__all__ = [
    "Storyboard",
    "SceneSpec",
    "NodeSpec",
    "HeaderSpec",
    "NarrationSpec",
    "TimingSpec",
    "TransitionSpec",
    "AssetRequirement",
    "GlobalStyle",
    "VideoMetadata",
    "StoryboardValidationError",
    "validate_storyboard_json",
    "render_storyboard",
    "emit_python_script",
]
