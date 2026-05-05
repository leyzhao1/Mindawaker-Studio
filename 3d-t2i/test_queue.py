#!/usr/bin/env python3
"""
测试 ComfyUI 队列请求
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.comfy.workflow_loader import create_workflow
from app.comfy.client import ComfyUIClient


def main():
    print("="*70)
    print("Testing ComfyUI Queue Prompt")
    print("="*70)

    # 创建工作流
    print("\n[1] Creating workflow...")
    workflow = create_workflow(
        positive_prompt="a wooden table in the center, warm indoor lighting",
        negative_prompt="blur, low quality",
        depth_image_path="depth_map.png",
        width=1024,
        height=1024,
        seed=42
    )
    print(f"  - {len(workflow)} nodes created")

    # 保存工作流到文件以供检查
    workflow_file = Path("./data/outputs/test_workflow_for_queue.json")
    workflow_file.parent.mkdir(parents=True, exist_ok=True)
    with open(workflow_file, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    print(f"  - Saved to: {workflow_file}")

    # 创建客户端
    print("\n[2] Creating ComfyUI client...")
    client = ComfyUIClient()

    # 检查服务
    print("\n[3] Checking ComfyUI server...")
    ok, msg = client.check_server()
    if ok:
        print(f"  [OK] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        return

    # 尝试发送请求
    print("\n[4] Sending queue_prompt request...")
    print("-"*70)

    # 准备请求数据
    prompt_data = {
        "prompt": workflow,
        "client_id": client.client_id
    }
    data = json.dumps(prompt_data).encode('utf-8')

    print(f"Request size: {len(data)} bytes")
    print(f"Request preview (first 500 chars):")
    print(data[:500].decode('utf-8'))
    print("...")
    print("-"*70)

    try:
        response = client.queue_prompt(workflow)
        print(f"[OK] Request successful!")
        print(f"Response: {json.dumps(response, indent=2)}")
    except Exception as e:
        print(f"[FAIL] Request failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check if the JSON format is valid")
        print("2. Check ComfyUI server logs for more details")
        print("3. Try loading the workflow manually in ComfyUI web UI:")
        print(f"   - Load {workflow_file} into ComfyUI")
        print(f"   - Check if it shows any errors")


if __name__ == "__main__":
    main()
