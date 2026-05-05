#!/usr/bin/env python3
"""
测试多视角角色参考图生成
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.schema.scene_hierarchy import SceneBlueprint, BlueprintObject
from app.pipeline.hierarchical_pipeline import HierarchicalPipeline

print("=" * 70)
print("测试多视角角色参考图生成")
print("=" * 70)

# 创建测试Pipeline
print("\n1. 创建HierarchicalPipeline...")
pipeline = HierarchicalPipeline(
    output_dir="./data/test_outputs",
    generate_character_references=True
)

# 创建测试Blueprint（包含一个孩子）
print("\n2. 创建测试Blueprint...")
blueprint = SceneBlueprint(
    template="indoor_room",
    objects=[
        BlueprintObject(id="child1", type="child", description="一个金色长发孩子")
    ]
)

# 手动测试多视角参考图生成
print("\n3. 手动测试多视角参考图生成...")
try:
    from app.scene.scene_builder import build_scene_from_json
    from app.scene.depth_renderer_headless import render_depth_headless

    # 测试视图列表
    test_views = ["front", "side", "three_quarter", "top"]
    print(f"   测试视图: {test_views}")

    # 测试生成多视角参考图
    ref_paths = pipeline._generate_character_reference(
        blueprint=blueprint,
        object_id="child1",
        char_id="test_char_001",
        views=test_views
    )

    print(f"\n4. 生成结果:")
    print(f"   生成参考图数量: {len(ref_paths)}")
    for i, path in enumerate(ref_paths):
        print(f"     {i+1}. {Path(path).name}")

        # 检查文件名是否包含视角
        filename = Path(path).name
        for view in test_views:
            if view in filename:
                print(f"       包含视角: {view}")
                break
        else:
            print(f"       警告: 文件名不包含任何测试视角!")

except Exception as e:
    print(f"   错误: {e}")
    import traceback
    traceback.print_exc()

# 检查缓存中的角色信息
print("\n5. 检查缓存中的角色信息...")
char = pipeline.character_manager.get_character("test_char_001")
if char:
    print(f"   角色ID: {char.character_id}")
    print(f"   参考图数量: {len(char.reference_images)}")
    for i, img_path in enumerate(char.reference_images):
        print(f"     {i+1}. {Path(img_path).name}")
else:
    print("   角色未找到")

print("\n" + "=" * 70)
print("测试完成")