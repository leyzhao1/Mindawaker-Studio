#!/usr/bin/env python3
"""
Test depth map generation with fixed SimpleDepthRenderer
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.scene.scene_builder import build_scene_from_json
from app.scene.depth_renderer_headless import render_depth_headless, SimpleDepthRenderer

print("Testing depth map generation with different views")

views = ["front", "side", "top", "three_quarter"]
depth_files = []

for view in views:
    print(f"\n--- View: {view} ---")

    # Create simple scene
    reference_shot = {
        "template": "white_background",
        "objects": [{"id": "child1", "type": "child", "position": "center"}],
        "camera": {"view": view},
        "style_prompt": "test",
        "lighting": {"type": "studio"}
    }

    # Build scene
    scene_data = build_scene_from_json(reference_shot)
    print(f"Camera position: {scene_data['camera']['position']}")
    print(f"Camera target: {scene_data['camera']['target']}")

    # Render depth map using simple renderer directly
    output_path = f"./data/test_depth_{view}.png"
    renderer = SimpleDepthRenderer(width=1024, height=1024)

    success = renderer.render(scene_data, output_path)
    print(f"Render success: {success}")

    if Path(output_path).exists():
        depth_files.append(output_path)

print(f"\nGenerated {len(depth_files)} depth files")

# Check if files are different
import hashlib
hashes = []
for file in depth_files:
    with open(file, 'rb') as f:
        md5 = hashlib.md5(f.read()).hexdigest()
        hashes.append(md5)
        print(f"{Path(file).name}: MD5 {md5[:8]}")

if len(set(hashes)) == len(hashes):
    print("All depth files are different - GOOD!")
else:
    print("Some depth files are identical - BAD!")