#!/usr/bin/env python3
"""
调试角色参考图生成
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.schema.scene_hierarchy import SceneBlueprint, BlueprintObject
from app.pipeline.hierarchical_pipeline import HierarchicalPipeline
from app.scene.scene_builder import build_scene_from_json
from app.scene.depth_renderer_headless import render_depth_headless
from app.llm.prompt_builder import PromptBuilder
from app.comfy.workflow_loader import create_workflow

print("=" * 70)
print("调试角色参考图生成")
print("=" * 70)

# 创建测试Pipeline
pipeline = HierarchicalPipeline(
    output_dir="./data/debug_outputs",
    generate_character_references=True
)

# 创建测试Blueprint
blueprint = SceneBlueprint(
    template="indoor_room",
    objects=[
        BlueprintObject(id="child1", type="child", description="一个金色长发孩子")
    ]
)

# 测试生成多视角参考图
views = ["front", "side", "top", "three_quarter"]
print(f"\n测试视图: {views}")

for view in views:
    print(f"\n{'='*40}")
    print(f"处理视图: {view}")

    # 创建白底shot
    reference_shot = {
        "template": "white_background",
        "objects": [{"id": "child1", "type": "child", "position": "center"}],
        "camera": {"view": view},
        "style_prompt": "child, full body, clean white background, studio lighting",
        "lighting": {"type": "studio"}
    }

    print(f"1. 构建场景数据...")
    try:
        scene_data = build_scene_from_json(reference_shot)
        print(f"   场景数据构建成功")
        print(f"   相机位置: {scene_data.get('camera', {}).get('position')}")
        print(f"   相机目标: {scene_data.get('camera', {}).get('target')}")
    except Exception as e:
        print(f"   场景构建失败: {e}")
        continue

    # 渲染深度图
    print(f"2. 渲染深度图...")
    depth_path = Path("./data/debug_outputs") / f"depth_{view}.png"
    depth_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        render_success = render_depth_headless(
            scene_data,
            output_path=str(depth_path),
            method="auto"
        )
        print(f"   深度图渲染: {'成功' if render_success else '失败'}")
        if depth_path.exists():
            print(f"   文件大小: {depth_path.stat().st_size} 字节")
        else:
            print(f"   深度图文件不存在")
    except Exception as e:
        print(f"   深度图渲染错误: {e}")
        continue

    # 构建提示词
    print(f"3. 构建提示词...")
    try:
        prompt_builder = PromptBuilder(reference_shot)
        prompts = prompt_builder.export_prompts()
        print(f"   原始正向提示词: {prompts['positive'][:100]}...")
        print(f"   原始负向提示词: {prompts['negative'][:100]}...")

        # 视角映射
        view_prompt_mapping = {
            "front": "frontal view, facing camera directly",
            "side": "profile view, side angle, from the side",
            "top": "overhead view, bird's eye view, from above",
            "three_quarter": "three-quarter view, angled perspective",
        }
        view_prompt = view_prompt_mapping.get(view, f"{view} view")
        enhanced_prompt = f"child, full body, clean white background, studio lighting, high quality, {view_prompt}"
        print(f"   增强提示词: {enhanced_prompt}")
    except Exception as e:
        print(f"   提示词构建失败: {e}")
        continue

    # 构建工作流
    print(f"4. 构建工作流...")
    try:
        workflow = create_workflow(
            positive_prompt=enhanced_prompt,
            negative_prompt=prompts["negative"],
            depth_image_path=depth_path.name,
            seed=42
        )
        print(f"   工作流构建成功")
        print(f"   工作流节点数: {len(workflow)}")
    except Exception as e:
        print(f"   工作流构建失败: {e}")
        continue

    print(f"5. 检查ComfyUI连接...")
    try:
        client = pipeline.comfy_client
        print(f"   ComfyUI服务器: {client.server_url}")
        # 简单的连接测试
        import requests
        response = requests.get(f"{client.server_url}/history", timeout=5)
        print(f"   连接测试: {'成功' if response.status_code == 200 else '失败'}")
    except Exception as e:
        print(f"   ComfyUI连接失败: {e}")
        print(f"   跳过图像生成")
        continue

print("\n" + "=" * 70)
print("调试完成")