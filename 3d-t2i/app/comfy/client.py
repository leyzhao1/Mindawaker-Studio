"""
ComfyUI API 客户端
增强版：增加调用前检查功能
"""
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, Optional, Callable, Tuple, List
from pathlib import Path


class ComfyUICheckError(Exception):
    """ComfyUI 检查错误"""
    pass


class ComfyUIClient:
    """ComfyUI API 客户端 - 增强版"""

    def __init__(self, server_url: str = "http://127.0.0.1:8188"):
        self.server_url = server_url.rstrip('/')
        self.client_id = f"mw_client_{int(time.time())}"

    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[bytes] = None, timeout: int = 30) -> Any:
        """发送 HTTP 请求"""
        url = f"{self.server_url}{endpoint}"
        headers = {}

        if data:
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            # 捕获 HTTP 错误并读取响应体
            error_body = e.read().decode('utf-8')
            try:
                error_json = json.loads(error_body)
                error_msg = error_json.get('error', error_body)
            except json.JSONDecodeError:
                error_msg = error_body

            # 添加更详细的诊断信息
            if "tuple index out of range" in str(error_msg):
                error_msg += (
                    "\n\nPossible cause: The checkpoint model may not include a VAE. "
                    "Try using a model that includes VAE, or modify the workflow to use a separate VAELoader node."
                )

            raise ComfyUICheckError(f"HTTP {e.code}: {error_msg}")
        except urllib.error.URLError as e:
            raise ComfyUICheckError(f"Connection failed: {e}")
        except json.JSONDecodeError as e:
            raise ComfyUICheckError(f"Invalid response: {e}")

    # ========== 检查方法 ==========

    def check_server(self) -> Tuple[bool, str]:
        """
        检查 ComfyUI 服务是否运行

        Returns:
            (是否可用, 状态信息)
        """
        try:
            # 尝试获取系统信息
            result = self._make_request("/system_stats", timeout=5)
            return True, f"Server running, system: {result.get('system', 'unknown')}"
        except Exception as e:
            return False, f"Server not available: {e}"

    def get_available_models(self) -> List[str]:
        """
        获取可用的 checkpoint 模型列表

        Returns:
            模型文件名列表
        """
        try:
            result = self._make_request("/object_info/CheckpointLoaderSimple", timeout=10)
            inputs = result.get("CheckpointLoaderSimple", {}).get("input", {})
            required = inputs.get("required", {})
            ckpt_name = required.get("ckpt_name", [[]])
            if ckpt_name and isinstance(ckpt_name[0], list):
                return ckpt_name[0]
            return []
        except Exception as e:
            print(f"Warning: Failed to get model list: {e}")
            return []

    def get_available_controlnets(self) -> List[str]:
        """
        获取可用的 ControlNet 模型列表

        Returns:
            模型文件名列表
        """
        try:
            result = self._make_request("/object_info/ControlNetLoader", timeout=10)
            inputs = result.get("ControlNetLoader", {}).get("input", {})
            required = inputs.get("required", {})
            cn_name = required.get("control_net_name", [[]])
            if cn_name and isinstance(cn_name[0], list):
                return cn_name[0]
            return []
        except Exception as e:
            print(f"Warning: Failed to get ControlNet list: {e}")
            return []

    def check_model_exists(self, model_name: str) -> bool:
        """检查指定模型是否存在"""
        available = self.get_available_models()
        return model_name in available

    def check_controlnet_exists(self, model_name: str) -> bool:
        """检查指定 ControlNet 模型是否存在"""
        available = self.get_available_controlnets()
        return model_name in available

    def check_depth_file(self, depth_path: str) -> Tuple[bool, str]:
        """
        检查深度图文件是否存在

        Args:
            depth_path: 文件路径或相对于 ComfyUI input 目录的路径

        Returns:
            (是否存在, 完整路径)
        """
        # 首先检查相对路径
        path = Path(depth_path)
        if path.exists():
            return True, str(path.absolute())

        # 检查 ComfyUI input 目录（常见位置）
        possible_paths = [
            Path("../ComfyUI/input") / depth_path,
            Path("../../ComfyUI/input") / depth_path,
            Path("./input") / depth_path,
        ]

        for p in possible_paths:
            if p.exists():
                return True, str(p.absolute())

        return False, depth_path

    def full_check(self, workflow: Optional[Dict[str, Any]] = None, depth_path: Optional[str] = None) -> Dict[str, Any]:
        """
        执行完整的生成前检查

        Args:
            workflow: 工作流配置（用于检查模型）
            depth_path: 深度图路径

        Returns:
            检查结果字典
        """
        results = {
            "server": {"ok": False, "message": ""},
            "models": {"ok": True, "missing": []},
            "controlnet": {"ok": True, "missing": []},
            "depth_file": {"ok": True, "path": ""},
            "overall": False
        }

        # 1. 检查服务
        ok, msg = self.check_server()
        results["server"] = {"ok": ok, "message": msg}
        if not ok:
            return results

        # 2. 检查模型（如果提供了 workflow）
        if workflow:
            # 检查 checkpoint
            if "1" in workflow and "ckpt_name" in workflow["1"].get("inputs", {}):
                model_name = workflow["1"]["inputs"]["ckpt_name"]
                if not self.check_model_exists(model_name):
                    results["models"]["ok"] = False
                    results["models"]["missing"].append(model_name)

            # 检查 ControlNet
            if "6" in workflow and "control_net_name" in workflow["6"].get("inputs", {}):
                cn_name = workflow["6"]["inputs"]["control_net_name"]
                if not self.check_controlnet_exists(cn_name):
                    results["controlnet"]["ok"] = False
                    results["controlnet"]["missing"].append(cn_name)

        # 3. 检查深度图文件
        if depth_path:
            exists, full_path = self.check_depth_file(depth_path)
            results["depth_file"] = {"ok": exists, "path": full_path}

        # 总体结果
        results["overall"] = (
            results["server"]["ok"] and
            results["models"]["ok"] and
            results["controlnet"]["ok"] and
            results["depth_file"]["ok"]
        )

        return results

    def print_check_results(self, results: Dict[str, Any]):
        """打印检查结果"""
        print("\n" + "="*60)
        print("ComfyUI Pre-generation Check")
        print("="*60)

        # 服务状态
        status = "[OK]" if results["server"]["ok"] else "[FAIL]"
        print(f"{status} Server: {results['server']['message']}")

        # 模型状态
        if results["models"].get("missing"):
            print(f"[FAIL] Missing models: {', '.join(results['models']['missing'])}")
        else:
            print("[OK] Models: OK")

        # ControlNet 状态
        if results["controlnet"].get("missing"):
            print(f"[FAIL] Missing ControlNets: {', '.join(results['controlnet']['missing'])}")
        else:
            print("[OK] ControlNet: OK")

        # 深度图状态
        if results["depth_file"].get("ok"):
            print(f"[OK] Depth file: {results['depth_file']['path']}")
        else:
            print(f"[FAIL] Depth file not found")

        print("="*60)
        status = "READY" if results["overall"] else "FAILED"
        print(f"Overall: {status}")
        print("="*60 + "\n")

    # ========== API 方法 ==========

    def queue_prompt(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """
        将工作流加入队列

        Args:
            workflow: ComfyUI 工作流配置

        Returns:
            包含 prompt_id 的响应
        """
        prompt_data = {
            "prompt": workflow,
            "client_id": self.client_id
        }

        data = json.dumps(prompt_data).encode('utf-8')
        return self._make_request("/prompt", method="POST", data=data)

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """获取生成历史"""
        return self._make_request(f"/history/{prompt_id}")

    def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        """获取生成的图像"""
        params = urllib.parse.urlencode({
            "filename": filename,
            "subfolder": subfolder,
            "type": folder_type
        })

        url = f"{self.server_url}/view?{params}"

        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read()

    def upload_image(self, image_path: str, name: Optional[str] = None) -> Dict[str, Any]:
        """
        上传图像到 ComfyUI

        Args:
            image_path: 本地图像路径
            name: 上传后的名称

        Returns:
            上传结果
        """
        import mimetypes

        if name is None:
            name = Path(image_path).name

        boundary = f"----WebKitFormBoundary{int(time.time())}"

        # 读取图像数据
        with open(image_path, 'rb') as f:
            image_data = f.read()

        content_type = mimetypes.guess_type(image_path)[0] or 'image/png'

        # 构建 multipart form data
        body = []
        body.append(f'--{boundary}'.encode())
        body.append(f'Content-Disposition: form-data; name="image"; filename="{name}"'.encode())
        body.append(f'Content-Type: {content_type}'.encode())
        body.append(b'')
        body.append(image_data)
        body.append(f'--{boundary}--'.encode())

        data = b'\r\n'.join(body)

        url = f"{self.server_url}/upload/image"
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode('utf-8'))

    def generate(
        self,
        workflow: Dict[str, Any],
        timeout: int = 300,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        check_before: bool = True,
        depth_path: Optional[str] = None,
        validate_workflow: bool = True
    ) -> Optional[str]:
        """
        执行完整的生成流程

        Args:
            workflow: ComfyUI 工作流
            timeout: 超时时间（秒）
            progress_callback: 进度回调函数
            check_before: 生成前是否执行检查
            depth_path: 深度图路径（用于检查）
            validate_workflow: 是否验证工作流结构

        Returns:
            生成的图像文件名，失败返回 None
        """
        # 验证工作流结构
        if validate_workflow:
            try:
                from .workflow_validator import WorkflowValidator
                validator = WorkflowValidator()
                valid, errors = validator.validate(workflow)
                if not valid:
                    print("Workflow validation failed:")
                    for error in errors:
                        print(f"  - {error}")
                    return None

                # 检查深度图文件
                depth_ok, depth_msg = validator.check_depth_file(workflow)
                if not depth_ok:
                    print(f"Warning: {depth_msg}")
                    print("Please ensure depth map exists before running generation.")
                    # 不返回 None，让用户决定是否继续
            except ImportError:
                pass

        # 生成前检查
        if check_before:
            check_results = self.full_check(workflow, depth_path)
            self.print_check_results(check_results)

            if not check_results["overall"]:
                print("Pre-generation check failed. Aborting.")
                return None

        # 加入队列
        if progress_callback:
            progress_callback("queueing", 0)

        try:
            response = self.queue_prompt(workflow)
        except ComfyUICheckError as e:
            print(f"Failed to queue prompt: {e}")
            return None

        prompt_id = response.get("prompt_id")

        if not prompt_id:
            print("Failed to get prompt_id")
            return None

        if progress_callback:
            progress_callback("generating", 10)

        # 等待完成
        start_time = time.time()
        last_status = ""

        while time.time() - start_time < timeout:
            try:
                history = self.get_history(prompt_id)
            except Exception as e:
                print(f"Error getting history: {e}")
                time.sleep(1)
                continue

            if prompt_id in history:
                prompt_data = history[prompt_id]

                # 检查状态
                status = prompt_data.get("status", {})
                status_str = status.get("status_str", "unknown")

                if status_str != last_status:
                    last_status = status_str
                    print(f"Status: {status_str}")

                if status_str == "success":
                    if progress_callback:
                        progress_callback("completed", 100)

                    # 获取输出图像
                    outputs = prompt_data.get("outputs", {})
                    for node_id, node_output in outputs.items():
                        if "images" in node_output:
                            images = node_output["images"]
                            if images:
                                return images[0].get("filename")

                    return None

                elif status_str == "error":
                    print(f"Generation failed: {status}")
                    return None

                # 更新进度
                if progress_callback:
                    progress_data = status.get("messages", [])
                    if progress_data:
                        # 简单进度估计
                        elapsed = time.time() - start_time
                        progress = min(90, int((elapsed / 30) * 50) + 10)
                        progress_callback("generating", progress)

            time.sleep(1)

        print("Generation timeout")
        return None

    def save_image(self, filename: str, output_path: str, subfolder: str = "") -> bool:
        """
        保存生成的图像到本地

        Args:
            filename: ComfyUI 中的文件名
            output_path: 本地保存路径
            subfolder: 子文件夹

        Returns:
            是否成功
        """
        try:
            image_data = self.get_image(filename, subfolder)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'wb') as f:
                f.write(image_data)

            print(f"Image saved to: {output_path}")
            return True

        except Exception as e:
            print(f"Failed to save image: {e}")
            return False


def generate_image(
    workflow: Dict[str, Any],
    server_url: str = "http://127.0.0.1:8188",
    output_path: Optional[str] = None,
    timeout: int = 300,
    check_before: bool = True,
    depth_path: Optional[str] = None
) -> Optional[str]:
    """
    便捷函数：生成图像

    Args:
        workflow: ComfyUI 工作流
        server_url: ComfyUI 服务器地址
        output_path: 保存路径（可选）
        timeout: 超时时间
        check_before: 生成前是否执行检查
        depth_path: 深度图路径（用于检查）

    Returns:
        生成的图像文件名或保存路径
    """
    client = ComfyUIClient(server_url)
    filename = client.generate(
        workflow,
        timeout=timeout,
        check_before=check_before,
        depth_path=depth_path
    )

    if filename and output_path:
        if client.save_image(filename, output_path):
            return output_path
        return None

    return filename
