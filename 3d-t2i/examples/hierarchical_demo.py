"""
分层架构演示 - Scene/Shot分离的一致性生成

演示新的三层架构：
1. Blueprint -> 语义场景定义
2. Instance -> 实际3D场景（可复用）
3. Shot -> 镜头（只包含相机）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipeline.hierarchical_pipeline import HierarchicalPipeline, quick_generate_views
from app.schema.scene_hierarchy import SceneBlueprint, BlueprintObject


def demo_basic_flow():
    """演示基本流程"""
    print("=" * 70)
    print("演示: 基本流程 - 从文本生成多视角")
    print("=" * 70)

    # 创建pipeline
    pipeline = HierarchicalPipeline(
        output_dir="./data/outputs/hierarchical_demo"
    )

    # 描述场景（不含视角）
    description = "室内，一个小孩站在桌边，桌上有花盆"

    # 创建多个视角的shots
    print("\n1. 创建多视角Shots...")
    shots = pipeline.create_multi_view_shots(
        description=description,
        views=["侧面", "俯视", "正面"]
    )

    print(f"   创建了 {len(shots)} 个shots")
    print(f"   它们都引用同一个Scene Instance: {shots[0].scene_id}")

    # 渲染shots
    print("\n2. 渲染Shots...")
    for i, shot in enumerate(shots, 1):
        print(f"\n   [{i}/{len(shots)}] 渲染视角: {shot.camera.view}")
        result = pipeline.render_shot(shot)
        print(f"       输出: {result.get('output_image')}")


def demo_cache_reuse():
    """演示缓存复用机制"""
    print("\n" + "=" * 70)
    print("演示: Scene Instance缓存复用")
    print("=" * 70)

    pipeline = HierarchicalPipeline(
        output_dir="./data/outputs/cache_reuse_demo"
    )

    description = "一个小孩站在桌子旁边，桌子上有个花盆"

    # 第一次生成
    print("\n1. 第一次生成（应该创建新的Instance）...")
    shot1 = pipeline.create_shot(description, "侧面")
    print(f"   Instance ID: {shot1.scene_id}")

    # 第二次生成 - 相同场景，不同视角
    print("\n2. 第二次生成 - 相同场景，不同视角...")
    shot2 = pipeline.create_shot(description, "俯视")
    print(f"   Instance ID: {shot2.scene_id}")
    print(f"   复用Instance: {shot1.scene_id == shot2.scene_id}")

    # 第三次生成 - 不同场景
    print("\n3. 第三次生成 - 不同场景（小孩和椅子）...")
    shot3 = pipeline.create_shot("一个小孩坐在椅子上", "侧面")
    print(f"   Instance ID: {shot3.scene_id}")
    print(f"   新Instance: {shot3.scene_id != shot1.scene_id}")


def demo_manual_blueprint():
    """演示手动创建Blueprint"""
    print("\n" + "=" * 70)
    print("演示: 手动创建Blueprint")
    print("=" * 70)

    from app.scene.instance_builder import InstanceBuilder, InstanceCache

    # 手动创建Blueprint
    blueprint = SceneBlueprint(
        template="indoor_room",
        objects=[
            BlueprintObject(id="child_1", type="child"),
            BlueprintObject(id="table_1", type="table"),
            BlueprintObject(id="flowerpot_1", type="flowerpot", relation="on_top_of:table_1"),
        ],
        metadata={"style_prompt": "storybook illustration"}
    )

    print(f"\nBlueprint ID: {blueprint.blueprint_id}")
    print(f"Objects: {[obj.id for obj in blueprint.objects]}")

    # 构建Instance
    print("\n构建Instance...")
    cache = InstanceCache()
    instance = cache.get_or_build_instance(
        blueprint,
        style_id="storybook_warm",
        character_bindings={"child_1": "char_child_001"}
    )

    print(f"Instance ID: {instance.instance_id}")
    print(f"Objects位置:")
    for obj in instance.objects:
        print(f"  {obj.id}: pos={obj.position}, scale={obj.scale}")

    # 创建不同视角的Shots
    print("\n创建Shots...")
    from app.schema.scene_hierarchy import create_shot_from_text

    for view in ["侧面", "俯视"]:
        shot = create_shot_from_text(instance, view)
        print(f"  {view}: camera pos={shot.camera.compute_position_from_angles()}")


def demo_quick_function():
    """演示便捷函数"""
    print("\n" + "=" * 70)
    print("演示: 便捷函数 quick_generate_views")
    print("=" * 70)

    print("\n快速生成多视角...")
    results = quick_generate_views(
        description="一个小孩站在桌子旁边，花盆在桌子上",
        views=["侧面", "俯视"],
        output_dir="./data/outputs/quick_demo"
    )

    print("\n生成结果:")
    for view, path in results.items():
        print(f"  {view}: {path}")


def compare_with_legacy():
    """对比新旧架构"""
    print("\n" + "=" * 70)
    print("对比: 新旧架构")
    print("=" * 70)

    description = "室内，一个小孩站在桌边，桌上有花盆"

    # 旧架构
    print("\n[旧架构] ConsistentPipeline:")
    print("  - 每次调用独立生成")
    print("  - 缓存基于场景内容哈希")
    print("  - 代码: pipeline.run_from_text('...侧面...')")
    print("          pipeline.run_from_text('...俯视...')")

    # 新架构
    print("\n[新架构] HierarchicalPipeline:")
    print("  - Scene/Shot分离")
    print("  - Instance显式复用")
    print("  - 代码: shots = pipeline.create_multi_view_shots('...', ['侧面', '俯视'])")
    print("          results = pipeline.render_shots(shots)")

    print("\n关键区别:")
    print("  旧: 自动缓存，隐式复用")
    print("  新: 显式Instance管理，更可控")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="分层架构演示")
    parser.add_argument(
        "demo",
        nargs="?",
        default="all",
        choices=["all", "basic", "cache", "blueprint", "quick", "compare"],
        help="选择要运行的演示"
    )

    args = parser.parse_args()

    demos = {
        "basic": demo_basic_flow,
        "cache": demo_cache_reuse,
        "blueprint": demo_manual_blueprint,
        "quick": demo_quick_function,
        "compare": compare_with_legacy,
    }

    if args.demo == "all":
        for name, demo_func in demos.items():
            try:
                demo_func()
            except Exception as e:
                print(f"\n演示 '{name}' 出错: {e}")
                import traceback
                traceback.print_exc()
    else:
        demos[args.demo]()

    print("\n" + "=" * 70)
    print("演示完成!")
    print("=" * 70)
