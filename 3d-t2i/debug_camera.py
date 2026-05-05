#!/usr/bin/env python3
"""
调试相机配置
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.scene.scene_builder import SceneBuilder

# 测试不同视角的相机配置
views = ["front", "side", "top", "three_quarter"]

for view in views:
    print(f"\n{'='*40}")
    print(f"View: {view}")

    # 创建简单的shot JSON
    shot_json = {
        "template": "white_background",
        "objects": [
            {"id": "child1", "type": "child", "position": "center"}
        ],
        "camera": {"view": view},
        "style_prompt": "test"
    }

    builder = SceneBuilder(shot_json)

    # 检查模板
    print(f"Template: {builder.template.name}")
    print(f"Template default camera: {builder.template.default_camera}")

    # 构建场景数据
    scene_data = builder.export_to_threejs()

    print(f"Camera position: {scene_data['camera']['position']}")
    print(f"Camera target: {scene_data['camera']['target']}")
    print(f"Camera fov: {scene_data['camera']['fov']}")