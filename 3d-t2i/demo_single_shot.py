#!/usr/bin/env python3
"""
MindAwaker - Single Shot Demo Script

从一句文本快速生成完整的生成管线输出：
文本 → shot.json → scene.json → workflow.json

Usage:
    python demo_single_shot.py "室内，一个孩子站在桌边，桌上有花盆，侧面视角"
    python demo_single_shot.py --text "城市街道，日落时分" --output ./my_output
    python demo_single_shot.py --shot ./data/json/example_shot.json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.llm.shot_parser import ShotParser
from app.llm.prompt_builder import PromptBuilder
from app.scene.scene_builder import SceneBuilder
from app.comfy.workflow_loader import create_workflow


def main():
    parser = argparse.ArgumentParser(
        description="MindAwaker - Generate shot/scene/workflow from text"
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Input text description (e.g., '室内，孩子站在桌边')"
    )
    parser.add_argument(
        "--shot", "-s",
        help="Path to existing Shot JSON file (alternative to text)"
    )
    parser.add_argument(
        "--output", "-o",
        default="./data/outputs",
        help="Output directory (default: ./data/outputs)"
    )
    parser.add_argument(
        "--provider", "-p",
        default="rule",
        choices=["rule", "openai", "anthropic"],
        help="Parser provider (default: rule)"
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip Pydantic validation"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    # 确定输入
    if args.shot:
        # 从文件加载
        shot_path = Path(args.shot)
        if not shot_path.exists():
            print(f"Error: Shot file not found: {shot_path}")
            sys.exit(1)

        with open(shot_path, 'r', encoding='utf-8') as f:
            shot_json = json.load(f)
        print(f"Loaded Shot JSON from: {shot_path}")

    elif args.text:
        # 解析文本
        print(f"\n{'='*60}")
        print("Step 1: Parsing text to Shot JSON...")
        print(f"{'='*60}")
        print(f"Input: {args.text}")

        parser = ShotParser(provider=args.provider)
        shot_json = parser.parse(args.text, validate=not args.no_validate)

        if args.verbose:
            print(f"\nParsed Shot JSON:")
            print(json.dumps(shot_json, indent=2, ensure_ascii=False))

    else:
        # 使用默认示例
        default_text = "室内，一个孩子站在桌边，桌上有花盆，侧面视角，温暖灯光"
        print(f"No input provided. Using default: {default_text}")
        print(f"\nTip: Run with --help to see usage options\n")

        parser = ShotParser(provider="rule")
        shot_json = parser.parse(default_text, validate=not args.no_validate)

    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成时间戳
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ========== Step 1: Save Shot JSON ==========
    print(f"\n{'='*60}")
    print("Step 2: Building 3D scene...")
    print(f"{'='*60}")

    shot_output = output_dir / f"shot_{timestamp}.json"
    with open(shot_output, 'w', encoding='utf-8') as f:
        json.dump(shot_json, f, indent=2, ensure_ascii=False)
    print(f"Saved: {shot_output}")

    # ========== Step 2: Build Scene ==========
    try:
        builder = SceneBuilder(shot_json)
        scene_data = builder.export_to_threejs()

        scene_output = output_dir / f"scene_{timestamp}.json"
        with open(scene_output, 'w', encoding='utf-8') as f:
            json.dump(scene_data, f, indent=2, ensure_ascii=False)
        print(f"Saved: {scene_output}")

        if args.verbose:
            print(f"\nScene info:")
            print(f"  Objects: {len(scene_data['objects'])}")
            print(f"  Camera: {scene_data['camera']['position']}")

    except Exception as e:
        print(f"Error building scene: {e}")
        sys.exit(1)

    # ========== Step 3: Build Prompts ==========
    print(f"\n{'='*60}")
    print("Step 3: Building prompts...")
    print(f"{'='*60}")

    try:
        prompt_builder = PromptBuilder(shot_json)
        prompts = prompt_builder.export_prompts()

        print(f"Positive: {prompts['positive'][:100]}...")
        print(f"Negative: {prompts['negative'][:80]}...")

    except Exception as e:
        print(f"Error building prompts: {e}")
        sys.exit(1)

    # ========== Step 4: Build Workflow ==========
    print(f"\n{'='*60}")
    print("Step 4: Building ComfyUI workflow...")
    print(f"{'='*60}")

    try:
        workflow = create_workflow(
            positive_prompt=prompts["positive"],
            negative_prompt=prompts["negative"],
            depth_image_path="depth_map.png"
        )

        workflow_output = output_dir / f"workflow_{timestamp}.json"
        with open(workflow_output, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
        print(f"Saved: {workflow_output}")

    except Exception as e:
        print(f"Error building workflow: {e}")
        sys.exit(1)

    # ========== Summary ==========
    print(f"\n{'='*60}")
    print("Demo completed successfully!")
    print(f"{'='*60}")
    print(f"\nOutput files:")
    print(f"  Shot JSON:   {shot_output}")
    print(f"  Scene JSON:  {scene_output}")
    print(f"  Workflow:    {workflow_output}")
    print(f"\nNext steps:")
    print(f"  1. Open web/threejs_depth_renderer/index.html")
    print(f"  2. Load {scene_output.name} to render depth map")
    print(f"  3. Copy depth map to ./data/depth/depth_map.png")
    print(f"  4. Run ComfyUI with {workflow_output.name}")
    print(f"\nOr use the pipeline script:")
    print(f"  python app/pipeline/run_single_shot.py --shot {shot_output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
