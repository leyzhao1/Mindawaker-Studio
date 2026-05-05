#!/usr/bin/env python3
"""
调试工作流脚本 - 帮助诊断 ComfyUI 工作流问题
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.comfy.workflow_loader import create_workflow
from app.comfy.workflow_validator import WorkflowValidator
from app.comfy.client import ComfyUIClient


def main():
    print("="*70)
    print("MindAwaker - Workflow Debugger")
    print("="*70)

    # 1. 创建测试工作流
    print("\n[1] Creating test workflow...")
    workflow = create_workflow(
        positive_prompt="a young child on the left, a wooden table in the center, warm indoor lighting",
        negative_prompt="blur, low quality",
        depth_image_path="depth_map.png",
        width=1024,
        height=1024,
        seed=42
    )
    print(f"  - Created workflow with {len(workflow)} nodes")

    # 2. 验证工作流
    print("\n[2] Validating workflow...")
    validator = WorkflowValidator()
    valid, errors = validator.validate(workflow)

    if valid:
        print("  [OK] Workflow structure is valid")
    else:
        print("  [FAIL] Workflow has errors:")
        for error in errors:
            print(f"    - {error}")

    # 3. 检查深度图文件
    print("\n[3] Checking depth map file...")
    depth_ok, depth_path = validator.check_depth_file(workflow)
    if depth_ok:
        print(f"  [OK] Depth file found: {depth_path}")
    else:
        print(f"  [FAIL] Depth file not found: {depth_path}")
        print("\n  Suggestions:")
        print("    - Run: python demo_single_shot.py to generate scene and depth map")
        print("    - Or manually create: data/depth/depth_map.png")
        print("    - Or copy your depth map to ComfyUI/input/depth_map.png")

    # 4. 检查 ComfyUI 服务
    print("\n[4] Checking ComfyUI server...")
    client = ComfyUIClient()
    server_ok, server_msg = client.check_server()
    if server_ok:
        print(f"  [OK] {server_msg}")
    else:
        print(f"  [FAIL] {server_msg}")
        print("\n  Make sure ComfyUI is running:")
        print("    cd ComfyUI && python main.py")

    # 5. 检查模型
    if server_ok:
        print("\n[5] Checking available models...")
        models = client.get_available_models()
        controlnets = client.get_available_controlnets()

        print(f"  - Checkpoints: {len(models)} found")
        if models:
            print(f"    First few: {', '.join(models[:3])}")

        print(f"  - ControlNets: {len(controlnets)} found")
        if controlnets:
            print(f"    First few: {', '.join(controlnets[:3])}")

        # 检查工作流中的模型是否存在
        workflow_model = workflow.get("1", {}).get("inputs", {}).get("ckpt_name", "")
        workflow_cn = workflow.get("6", {}).get("inputs", {}).get("control_net_name", "")

        if workflow_model in models:
            print(f"  [OK] Checkpoint '{workflow_model}' found")
        else:
            print(f"  [FAIL] Checkpoint '{workflow_model}' NOT found")
            print(f"    Download and place in ComfyUI/models/checkpoints/")

        if workflow_cn in controlnets:
            print(f"  [OK] ControlNet '{workflow_cn}' found")
        else:
            print(f"  [FAIL] ControlNet '{workflow_cn}' NOT found")
            print(f"    Download and place in ComfyUI/models/controlnet/")

    # 6. 保存测试工作流
    print("\n[6] Saving test workflow...")
    output_path = Path("./data/outputs/debug_workflow.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    print(f"  Saved to: {output_path}")

    # 7. 打印工作流摘要
    print("\n[7] Workflow Summary:")
    print(f"  - Nodes: {len(workflow)}")
    for node_id in sorted(workflow.keys(), key=int):
        node = workflow[node_id]
        class_type = node.get("class_type", "unknown")
        inputs = list(node.get("inputs", {}).keys())
        print(f"    {node_id}: {class_type} (inputs: {', '.join(inputs)})")

    # 总结
    print("\n" + "="*70)
    if valid and depth_ok and server_ok:
        print("[OK] All checks passed! Workflow should work.")
    else:
        print("[FAIL] Some checks failed. Please fix the issues above.")
    print("="*70)


if __name__ == "__main__":
    main()
