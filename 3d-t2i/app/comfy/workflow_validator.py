"""
ComfyUI 工作流验证器
检查工作流配置和依赖是否完整
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


class WorkflowValidator:
    """工作流验证器"""

    def __init__(self, comfyui_path: str = None):
        self.comfyui_path = Path(comfyui_path) if comfyui_path else None

    def validate(self, workflow: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        验证工作流

        Returns:
            (是否有效, 错误列表)
        """
        errors = []

        # 1. 检查基本结构
        if not isinstance(workflow, dict):
            errors.append("Workflow must be a dictionary")
            return False, errors

        # 2. 检查每个节点
        for node_id, node in workflow.items():
            if not isinstance(node, dict):
                errors.append(f"Node {node_id}: must be a dictionary")
                continue

            if "class_type" not in node:
                errors.append(f"Node {node_id}: missing class_type")
                continue

            if "inputs" not in node:
                errors.append(f"Node {node_id}: missing inputs")
                continue

            # 3. 检查节点引用 (ComfyUI API uses string IDs like "1", "2")
            inputs = node.get("inputs", {})
            for input_name, input_value in inputs.items():
                if isinstance(input_value, list) and len(input_value) == 2:
                    ref_node_id, ref_output_index = input_value
                    # ComfyUI uses string references like ["1", 0] or [1, 0]
                    # Check both string and int versions
                    ref_exists = ref_node_id in workflow
                    if not ref_exists and isinstance(ref_node_id, int):
                        ref_exists = str(ref_node_id) in workflow
                    if not ref_exists and isinstance(ref_node_id, str):
                        try:
                            ref_exists = int(ref_node_id) in workflow
                        except ValueError:
                            pass
                    if not ref_exists:
                        errors.append(
                            f"Node {node_id}: references non-existent node {ref_node_id}"
                        )

        # 4. 检查必要节点 (support both int and string keys)
        required_nodes = {
            "1": "CheckpointLoaderSimple",
            "2": "CLIPTextEncode",
            "3": "CLIPTextEncode",
            "4": "EmptyLatentImage",
            "8": "KSampler",
            "9": "VAEDecode",
            "10": "SaveImage"
        }

        for node_id, expected_type in required_nodes.items():
            # Check for string key first, then int key
            if node_id not in workflow and int(node_id) not in workflow:
                errors.append(f"Missing required node: {node_id} ({expected_type})")
            else:
                # Get the node with either string or int key
                node = workflow.get(node_id) or workflow.get(int(node_id))
                if node and node.get("class_type") != expected_type:
                    errors.append(
                        f"Node {node_id}: expected {expected_type}, "
                        f"got {node.get('class_type')}"
                    )

        return len(errors) == 0, errors

    def check_depth_file(self, workflow: Dict[str, Any]) -> Tuple[bool, str]:
        """检查深度图文件是否存在"""
        # Support both string "5" and int 5 keys
        load_image_node = workflow.get("5") or workflow.get(5)
        if not load_image_node:
            return False, "LoadImage node (5) not found"

        image_path = load_image_node.get("inputs", {}).get("image", "")
        if not image_path:
            return False, "No image path specified"

        # 检查多个可能的位置
        possible_paths = [
            Path(image_path),
            Path("./data/depth") / image_path,
            Path("../ComfyUI/input") / image_path,
            Path("./ComfyUI/input") / image_path,
        ]

        for p in possible_paths:
            if p.exists():
                return True, str(p.absolute())

        return False, f"Depth file not found: {image_path}"

    def fix_common_issues(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """
        修复常见问题
        """
        workflow = workflow.copy()

        # ComfyUI API uses string node IDs like "1", "2"
        # Ensure consistent string keys for better compatibility
        try:
            workflow = {str(k) if isinstance(k, int) else k: v for k, v in workflow.items()}
        except (ValueError, TypeError):
            pass  # Keep original if conversion fails

        # 修复节点引用格式 (ensure string IDs in references for API compatibility)
        for node_id, node in workflow.items():
            if "inputs" in node:
                for input_name, input_value in node["inputs"].items():
                    if isinstance(input_value, list) and len(input_value) == 2:
                        ref_id, ref_idx = input_value
                        # Ensure ref_id is string for API
                        try:
                            ref_id = str(ref_id) if isinstance(ref_id, int) else ref_id
                        except (ValueError, TypeError):
                            pass
                        workflow[node_id]["inputs"][input_name] = [ref_id, ref_idx]

        # 确保必要的输入字段存在 (use string IDs)
        node_2 = workflow.get("2") or workflow.get(2)
        if node_2 and "text" not in node_2.get("inputs", {}):
            node_2["inputs"]["text"] = ""

        node_3 = workflow.get("3") or workflow.get(3)
        if node_3 and "text" not in node_3.get("inputs", {}):
            node_3["inputs"]["text"] = ""

        return workflow

    def print_validation_report(self, workflow: Dict[str, Any]):
        """打印验证报告"""
        print("\n" + "="*60)
        print("Workflow Validation Report")
        print("="*60)

        # 结构验证
        valid, errors = self.validate(workflow)
        if valid:
            print("[OK] Workflow structure is valid")
        else:
            print("[FAIL] Workflow structure errors:")
            for error in errors:
                print(f"  - {error}")

        # 深度图检查
        depth_ok, depth_path = self.check_depth_file(workflow)
        if depth_ok:
            print(f"[OK] Depth file found: {depth_path}")
        else:
            print(f"[FAIL] Depth file: {depth_path}")

        # 节点统计
        print(f"\nNode count: {len(workflow)}")
        node_types = [node.get("class_type", "unknown") for node in workflow.values()]
        print(f"Node types: {', '.join(set(node_types))}")

        print("="*60 + "\n")

        return valid and depth_ok


def validate_and_fix_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并修复工作流

    Args:
        workflow: 原始工作流

    Returns:
        修复后的工作流
    """
    validator = WorkflowValidator()

    # 打印原始报告
    print("Original workflow:")
    validator.print_validation_report(workflow)

    # 修复问题
    fixed_workflow = validator.fix_common_issues(workflow)

    # 打印修复后报告
    print("Fixed workflow:")
    is_valid = validator.print_validation_report(fixed_workflow)

    if not is_valid:
        print("Warning: Workflow has issues that cannot be auto-fixed")

    return fixed_workflow


if __name__ == "__main__":
    # 测试验证器
    test_workflow = {
        "1": {
            "inputs": {"ckpt_name": "test.safetensors"},
            "class_type": "CheckpointLoaderSimple"
        },
        "2": {
            "inputs": {"text": "", "clip": ["1", 1]},
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "seed": 42
            },
            "class_type": "KSampler"
        }
    }

    validator = WorkflowValidator()
    valid, errors = validator.validate(test_workflow)
    print(f"Valid: {valid}")
    if errors:
        for e in errors:
            print(f"  - {e}")
