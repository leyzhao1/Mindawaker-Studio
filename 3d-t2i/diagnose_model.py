#!/usr/bin/env python3
"""
诊断模型文件是否正确加载
"""
import json
import sys
import urllib.request
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"


def test_simplest_workflow():
    """测试最简单的可能工作流 - 只包含 Checkpoint 和 CLIP"""

    # 最简单的工作流：Checkpoint -> CLIP Text Encode
    workflow = {
        "1": {
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": "test", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        }
    }

    print("Testing simplest workflow (Checkpoint -> CLIP)...")
    print("=" * 60)

    prompt_data = {
        "prompt": workflow,
        "client_id": "diagnose_001"
    }

    data = json.dumps(prompt_data).encode('utf-8')

    try:
        req = urllib.request.Request(
            f"{COMFY_URL}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("✓ Request queued successfully!")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"✗ HTTP {e.code} Error:")
        try:
            error_json = json.loads(error_body)
            print(json.dumps(error_json, indent=2))
        except:
            print(error_body)
        return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def check_model_info():
    """检查模型信息"""
    print("\nChecking model list...")
    print("=" * 60)

    try:
        # 获取可用模型
        with urllib.request.urlopen(f"{COMFY_URL}/object_info/CheckpointLoaderSimple", timeout=10) as response:
            info = json.loads(response.read().decode('utf-8'))

            inputs = info.get("CheckpointLoaderSimple", {}).get("input", {})
            required = inputs.get("required", {})
            ckpt_name = required.get("ckpt_name", [[]])

            if ckpt_name and isinstance(ckpt_name[0], list):
                models = ckpt_name[0]
                print(f"Found {len(models)} checkpoints:")
                for m in models[:5]:  # 只显示前5个
                    print(f"  - {m}")

                if "sd_xl_base_1.0.safetensors" in models:
                    print("\n✓ sd_xl_base_1.0.safetensors is available")
                else:
                    print("\n✗ sd_xl_base_1.0.safetensors NOT found!")
                    print(f"  Available models: {models}")

    except Exception as e:
        print(f"Error checking models: {e}")


def test_checkpoint_only():
    """仅测试 Checkpoint 加载，不连接 CLIP"""
    print("\nTesting CheckpointLoaderSimple only...")
    print("=" * 60)

    # 只有 Checkpoint，没有下游连接
    workflow = {
        "1": {
            "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        }
    }

    prompt_data = {
        "prompt": workflow,
        "client_id": "diagnose_002"
    }

    data = json.dumps(prompt_data).encode('utf-8')

    try:
        req = urllib.request.Request(
            f"{COMFY_URL}/prompt",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print("✓ Checkpoint can be loaded")
            print(f"Response: {json.dumps(result, indent=2)}")
            return True

    except Exception as e:
        print(f"✗ Checkpoint loading failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("ComfyUI Model Diagnostics")
    print("=" * 60)

    # 1. 检查模型列表
    check_model_info()

    # 2. 仅测试 Checkpoint 加载
    test_checkpoint_only()

    # 3. 测试最简单工作流
    test_simplest_workflow()
