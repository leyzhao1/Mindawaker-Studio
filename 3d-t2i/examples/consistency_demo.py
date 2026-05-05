"""
多视角一致性生成演示

演示如何使用ConsistentPipeline生成多视角图像并保持角色一致
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.pipeline.consistent_pipeline import ConsistentPipeline


def demo_fixed_seed():
    """演示使用固定种子的一致性方法"""
    print("=" * 70)
    print("演示: 使用 Fixed Seed 方法生成多视角")
    print("=" * 70)

    pipeline = ConsistentPipeline(
        consistency_method="fixed_seed",
        output_dir="./data/outputs/fixed_seed_demo"
    )

    base_desc = "室内，一个小孩站在桌边，桌上有花盆"
    views = ["侧面", "俯视", "正面"]
    view_codes = ["side", "top", "front"]

    results = pipeline.generate_multiple_views(
        base_description=base_desc,
        views=view_codes,
        consistency_method="fixed_seed"
    )

    print("\n生成完成!")
    print(f"参考图像: {results.get('references', [])}")
    for view, result in results["views"].items():
        cache_status = "(缓存命中)" if result.get("cache_hit") else "(新建)"
        print(f"  {view}视角: {result.get('output_image')} {cache_status}")


def demo_ip_adapter():
    """演示使用IP-Adapter的一致性方法"""
    print("\n" + "=" * 70)
    print("演示: 使用 IP-Adapter 方法生成多视角")
    print("=" * 70)
    print("注意: 需要安装ComfyUI_IPAdapter_plus节点包")
    print("=" * 70)

    pipeline = ConsistentPipeline(
        consistency_method="ip_adapter",
        output_dir="./data/outputs/ipadapter_demo"
    )

    # 生成两个不同视角
    descriptions = [
        "室内，一个小孩站在桌边，桌上有花盆，侧面角度",
        "室内，一个小孩站在桌边，桌上有花盆，俯视角度",
    ]

    for i, desc in enumerate(descriptions, 1):
        print(f"\n[{i}/{len(descriptions)}] 生成: {desc}")
        result = pipeline.run_from_text(desc)

        print(f"  输出: {result.get('output_image')}")
        print(f"  角色ID: {result.get('character_id')}")
        print(f"  使用参考: {result.get('reference_used')}")


def demo_manual_cache():
    """演示手动控制缓存"""
    print("\n" + "=" * 70)
    print("演示: 手动控制场景缓存")
    print("=" * 70)

    pipeline = ConsistentPipeline(
        consistency_method="fixed_seed",
        output_dir="./data/outputs/cache_demo"
    )

    # 第一次生成 - 应该没有缓存
    print("\n第一次生成 (预期缓存未命中)...")
    result1 = pipeline.run_from_text(
        "一个小孩站在桌子旁边，桌子上有个花盆，侧面角度"
    )
    print(f"缓存命中: {result1.get('cache_hit')}")  # False

    # 第二次生成 - 应该命中缓存
    print("\n第二次生成 (预期缓存命中)...")
    result2 = pipeline.run_from_text(
        "一个小孩站在桌子旁边，桌子上有个花盆，俯视角度"
    )
    print(f"缓存命中: {result2.get('cache_hit')}")  # True

    # 第三次生成 - 强制不使用缓存
    print("\n第三次生成 (强制新建)...")
    result3 = pipeline.run_from_text(
        "一个小孩站在桌子旁边，桌子上有个花盆，正面角度",
        force_new_scene=True
    )
    print(f"缓存命中: {result3.get('cache_hit')}")  # False


def demo_different_scenes():
    """演示不同场景使用不同缓存"""
    print("\n" + "=" * 70)
    print("演示: 不同场景的独立缓存")
    print("=" * 70)

    pipeline = ConsistentPipeline(
        consistency_method="fixed_seed",
        output_dir="./data/outputs/multi_scene_demo"
    )

    # 场景1: 室内
    print("\n场景1: 室内")
    r1 = pipeline.run_from_text("室内，一个小孩站在桌边，侧面角度")
    print(f"缓存命中: {r1.get('cache_hit')}")

    # 场景2: 相同室内，不同视角
    print("\n场景2: 相同室内，不同视角")
    r2 = pipeline.run_from_text("室内，一个小孩站在桌边，俯视角度")
    print(f"缓存命中: {r2.get('cache_hit')}")

    # 场景3: 不同内容（街上）
    print("\n场景3: 街上（不同场景）")
    r3 = pipeline.run_from_text("街上，一个小孩站在汽车旁边，侧面角度")
    print(f"缓存命中: {r3.get('cache_hit')}")

    # 场景4: 回到室内
    print("\n场景4: 回到室内")
    r4 = pipeline.run_from_text("室内，一个小孩站在桌边，正面角度")
    print(f"缓存命中: {r4.get('cache_hit')}")


def compare_methods():
    """对比不同一致性方法的效果"""
    print("\n" + "=" * 70)
    print("对比: 不同一致性方法")
    print("=" * 70)

    base_desc = "一个小孩站在桌子旁边，桌子上有个花盆"
    views = ["side", "top"]

    for method in ["fixed_seed", "ip_adapter"]:
        print(f"\n方法: {method}")
        print("-" * 40)

        try:
            pipeline = ConsistentPipeline(
                consistency_method=method,
                output_dir=f"./data/outputs/compare_{method}"
            )

            results = pipeline.generate_multiple_views(
                base_description=base_desc,
                views=views,
                consistency_method=method
            )

            print(f"成功生成 {len(results['views'])} 个视角")

        except Exception as e:
            print(f"失败: {e}")
            print("提示: IP-Adapter需要预先安装节点包")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="一致性生成演示")
    parser.add_argument(
        "demo",
        nargs="?",
        default="all",
        choices=["all", "fixed_seed", "ip_adapter", "cache", "scenes", "compare"],
        help="选择要运行的演示"
    )

    args = parser.parse_args()

    demos = {
        "fixed_seed": demo_fixed_seed,
        "ip_adapter": demo_ip_adapter,
        "cache": demo_manual_cache,
        "scenes": demo_different_scenes,
        "compare": compare_methods,
    }

    if args.demo == "all":
        print("运行所有演示...")
        print("注意: 部分演示需要ComfyUI正在运行")

        for name, demo_func in demos.items():
            try:
                demo_func()
            except Exception as e:
                print(f"\n演示 '{name}' 出错: {e}")
                print("请确保ComfyUI在 http://127.0.0.1:8188 运行")
                break

    else:
        demos[args.demo]()

    print("\n" + "=" * 70)
    print("演示完成!")
    print("=" * 70)
