#!/usr/bin/env python3
"""
命令行图像生成工具

使用示例:
    # 生成单张图片
    python generate.py "室内，一个小孩站在桌边，桌上有花盆，侧面角度"

    # 生成多视角
    python generate.py "室内，一个小孩站在桌边，桌上有花盆" --views 侧面 俯视 正面

    # 指定输出目录
    python generate.py "..." --output ./my_outputs

    # 使用特定一致性方法
    python generate.py "..." --views 侧面 俯视 --method ip_adapter

    # 指定样式
    python generate.py "..." --style storybook_warm
"""
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.pipeline import HierarchicalPipeline, ConsistentPipeline


def main():
    parser = argparse.ArgumentParser(
        description="3D-Guided Text-to-Image Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "室内，一个小孩站在桌边，桌上有花盆，侧面角度"
  %(prog)s "一个小孩站在桌子旁边" --views 侧面 俯视 正面
  %(prog)s "..." --output ./outputs --method ip_adapter
        """
    )

    # 主要参数
    parser.add_argument(
        "description",
        help="场景描述文本"
    )

    # 可选参数
    parser.add_argument(
        "--views",
        nargs="+",
        default=None,
        help="视角列表，如: 侧面 俯视 正面"
    )

    parser.add_argument(
        "--output", "-o",
        default="./data/outputs",
        help="输出目录 (默认: ./data/outputs)"
    )

    parser.add_argument(
        "--style", "-s",
        default="default",
        help="样式标识 (默认: default)"
    )

    parser.add_argument(
        "--method", "-m",
        choices=["fixed_seed", "ip_adapter", "reference_only"],
        default="fixed_seed",
        help="角色一致性方法 (默认: fixed_seed)"
    )

    parser.add_argument(
        "--pipeline", "-p",
        choices=["hierarchical", "consistent"],
        default="hierarchical",
        help="使用的Pipeline类型 (默认: hierarchical)"
    )

    parser.add_argument(
        "--comfy-url",
        default="http://127.0.0.1:8188",
        help="ComfyUI服务器地址 (默认: http://127.0.0.1:8188)"
    )

    parser.add_argument(
        "--gen-ref",
        action="store_true",
        help="自动生成角色参考图（白底干净背景）"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示处理信息，不实际生成"
    )

    args = parser.parse_args()

    # 显示配置信息
    print("=" * 70)
    print("3D-Guided Text-to-Image Generator")
    print("=" * 70)
    print(f"描述: {args.description}")
    print(f"视角: {args.views or '自动检测'}")
    print(f"输出: {args.output}")
    print(f"样式: {args.style}")
    print(f"方法: {args.method}")
    print(f"Pipeline: {args.pipeline}")
    print("=" * 70)

    # 自动增强描述，防止无关物体
    description = args.description
    # 如果描述中没有明确排除交通工具，添加限制
    if not any(word in description for word in ["飞机", "车", "汽车", "vehicle", "airplane"]):
        # 在描述末尾添加场景限制（如果不是已存在）
        if "没有" not in description and "no " not in description.lower():
            description += ", no vehicles, no airplanes, clean indoor scene"
            print(f"[自动增强] 描述已添加场景限制")
            print(f"增强后: {description}")

    if args.dry_run:
        print("\n[DRY RUN] 不执行实际生成")
        return

    # 创建Pipeline
    if args.pipeline == "hierarchical":
        pipeline = HierarchicalPipeline(
            comfy_url=args.comfy_url,
            output_dir=args.output,
            consistency_method=args.method,
            generate_character_references=args.gen_ref
        )

        # 生成多视角或单视角
        if args.views:
            print(f"\n生成 {len(args.views)} 个视角...")
            shots = pipeline.create_multi_view_shots(
                description=args.description,
                views=args.views,
                style_id=args.style
            )
            results = pipeline.render_shots(shots)
        else:
            print("\n生成单张图片...")
            # 自动检测视角
            view_keywords = {
                "侧面": "侧面", "side": "侧面",
                "俯视": "俯视", "top": "俯视", "鸟瞰": "俯视",
                "正面": "正面", "front": "正面",
            }
            view = "侧面"  # 默认
            for keyword, v in view_keywords.items():
                if keyword in args.description.lower():
                    view = v
                    break

            shot = pipeline.create_shot(args.description, view, args.style)
            result = pipeline.render_shot(shot)
            results = [result]

        # 显示结果
        print("\n" + "=" * 70)
        print("生成完成!")
        print("=" * 70)
        for i, result in enumerate(results):
            print(f"\n图片 {i+1}:")
            print(f"  文件: {result.get('output_image', 'N/A')}")
            print(f"  Scene ID: {result.get('scene_id', 'N/A')}")
            if 'cache_hit' in result:
                print(f"  缓存: {'HIT' if result['cache_hit'] else 'MISS'}")

    else:  # consistent pipeline
        pipeline = ConsistentPipeline(
            comfy_url=args.comfy_url,
            output_dir=args.output,
            consistency_method=args.method
        )

        if args.views:
            print(f"\n生成 {len(args.views)} 个视角...")
            results = pipeline.generate_multiple_views(
                base_description=args.description,
                views=args.views,
                consistency_method=args.method
            )

            print("\n" + "=" * 70)
            print("生成完成!")
            print("=" * 70)
            print(f"\nScene IDs: {set(results.get('scene_ids', []))}")
            for view, result in results["views"].items():
                print(f"\n视角 {view}:")
                print(f"  文件: {result.get('output_image', 'N/A')}")
                print(f"  Scene ID: {result.get('scene_id', 'N/A')}")
        else:
            print("\n生成单张图片...")
            result = pipeline.run_from_text(args.description)

            print("\n" + "=" * 70)
            print("生成完成!")
            print("=" * 70)
            print(f"\n文件: {result.get('output_image', 'N/A')}")
            print(f"Scene ID: {result.get('scene_id', 'N/A')}")
            print(f"缓存: {'HIT' if result.get('cache_hit') else 'MISS'}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
