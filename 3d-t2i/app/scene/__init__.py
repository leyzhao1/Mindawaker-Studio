"""
Scene module - 3D scene generation from structured JSON
"""

# 旧版场景构建器
from .scene_builder import SceneBuilder, build_scene_from_json

# 新版分层架构构建器
from .instance_builder import (
    InstanceBuilder,
    InstanceCache,
    build_instance_from_shot_json
)

from .templates import (
    get_template, list_templates, get_template_info,
    register_template, unregister_template, create_and_register_template
)
from .object_library import get_object_def, list_object_types
from .depth_renderer_headless import (
    DepthRendererHeadless,
    SimpleDepthRenderer,
    render_depth_headless
)

__all__ = [
    # 旧版
    'SceneBuilder',
    'build_scene_from_json',
    # 新版分层架构
    'InstanceBuilder',
    'InstanceCache',
    'build_instance_from_shot_json',
    # 模板和对象库
    'get_template',
    'list_templates',
    'get_template_info',
    'get_object_def',
    'list_object_types',
    'register_template',
    'unregister_template',
    'create_and_register_template',
    # 渲染
    'DepthRendererHeadless',
    'SimpleDepthRenderer',
    'render_depth_headless'
]
