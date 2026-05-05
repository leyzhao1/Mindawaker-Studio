"""
无头浏览器深度图渲染器
使用 Playwright 在后台自动渲染 Three.js 场景并导出深度图
"""
import json
import asyncio
import tempfile
import http.server
import socketserver
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional

# 可选依赖，如果没有安装会给出提示
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class DepthRendererHeadless:
    """无头深度图渲染器"""

    def __init__(
        self,
        width: int = 1024,
        height: int = 1024,
        output_path: str = "./data/depth/depth_map.png"
    ):
        self.width = width
        self.height = height
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def _start_temp_server(self, scene_data: Dict[str, Any], port: int = 8765) -> threading.Thread:
        """启动临时 HTTP 服务器提供场景数据"""

        # 创建临时目录存放 scene.json
        self.temp_dir = Path(tempfile.mkdtemp())
        scene_file = self.temp_dir / "scene.json"
        with open(scene_file, 'w', encoding='utf-8') as f:
            json.dump(scene_data, f, ensure_ascii=False)

        # 复制前端文件到临时目录
        web_dir = Path(__file__).parent.parent.parent / "web" / "threejs_depth_renderer"
        if web_dir.exists():
            import shutil
            for file in ["index.html", "main.js"]:
                src = web_dir / file
                if src.exists():
                    shutil.copy(src, self.temp_dir / file)

        # 创建简单的 HTTP 服务器
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(scene_file.parent), **kwargs)

            def log_message(self, format, *args):
                pass  # 禁用日志

        self.httpd = socketserver.TCPServer(("", port), Handler)
        server_thread = threading.Thread(target=self.httpd.serve_forever)
        server_thread.daemon = True
        server_thread.start()

        return server_thread

    async def _render_with_playwright(
        self,
        scene_data: Dict[str, Any],
        port: int = 8765
    ) -> bool:
        """使用 Playwright 进行无头渲染"""

        if not PLAYWRIGHT_AVAILABLE:
            print("Error: Playwright not installed.")
            print("Install with: pip install playwright && playwright install chromium")
            return False

        # 启动临时服务器
        server_thread = self._start_temp_server(scene_data, port)

        try:
            async with async_playwright() as p:
                # 启动无头浏览器
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_viewport_size({"width": self.width + 100, "height": self.height + 100})

                # 加载页面
                url = f"http://localhost:{port}/index.html?scene=scene.json"
                print(f"Loading {url}...")
                await page.goto(url, wait_until="networkidle")

                # 等待场景加载完成
                print("Waiting for scene to load...")
                await asyncio.sleep(2)  # 给足够时间加载和渲染

                # 等待状态变为加载完成
                for _ in range(10):
                    status = await page.eval_on_selector("#status", "el => el.textContent")
                    if "loaded" in status.lower() or "objects" in status.lower():
                        break
                    await asyncio.sleep(0.5)

                # 截取 depth canvas
                print("Capturing depth map...")
                depth_canvas = await page.query_selector("#depth-canvas")
                if depth_canvas:
                    await depth_canvas.screenshot(path=str(self.output_path))
                    print(f"Depth map saved to: {self.output_path}")
                    success = True
                else:
                    print("Error: Depth canvas not found")
                    success = False

                await browser.close()
                return success

        except Exception as e:
            print(f"Rendering error: {e}")
            return False

        finally:
            # 关闭临时服务器
            self.httpd.shutdown()
            self.httpd.server_close()

            # 清理临时文件
            if hasattr(self, 'temp_dir') and self.temp_dir.exists():
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def render(
        self,
        scene_data: Dict[str, Any],
        output_path: Optional[str] = None
    ) -> bool:
        """
        渲染深度图（同步接口）

        Args:
            scene_data: 场景数据（Scene JSON）
            output_path: 输出路径（可选，覆盖默认路径）

        Returns:
            是否成功
        """
        if output_path:
            self.output_path = Path(output_path)
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

        if not PLAYWRIGHT_AVAILABLE:
            print("\n" + "="*60)
            print("Headless rendering not available")
            print("="*60)
            print("\nTo enable automatic depth rendering:")
            print("  1. pip install playwright")
            print("  2. playwright install chromium")
            print("\nFalling back to manual web renderer...")
            print("  1. Open web/threejs_depth_renderer/index.html")
            print("  2. Load your scene.json")
            print("  3. Click 'Export Depth Map'")
            print("="*60 + "\n")
            return False

        try:
            return asyncio.run(self._render_with_playwright(scene_data))
        except Exception as e:
            print(f"Failed to render: {e}")
            return False


class SimpleDepthRenderer:
    """
    简化的 Python-only 深度图渲染器
    不需要浏览器，但渲染效果较简单
    """

    def __init__(self, width: int = 1024, height: int = 1024):
        self.width = width
        self.height = height

    def render(
        self,
        scene_data: Dict[str, Any],
        output_path: str = "./data/depth/depth_map.png"
    ) -> bool:
        """
        使用简单的 Python 3D 投影渲染深度图
        不需要浏览器，但仅支持基础几何体
        """
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            print("Error: numpy and Pillow required for simple renderer")
            print("Install: pip install numpy Pillow")
            return False

        depth = np.ones((self.height, self.width), dtype=np.float32)

        camera = scene_data.get("camera", {})
        cam_pos = np.array(camera.get("position", [8, 3, 8]), dtype=np.float32)
        cam_target = np.array(camera.get("target", [0, 1, 0]), dtype=np.float32)
        fov = float(camera.get("fov", 50))

        forward = cam_target - cam_pos
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-6:
            forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        else:
            forward = forward / forward_norm

        world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        right = np.cross(forward, world_up)
        right_norm = np.linalg.norm(right)
        if right_norm < 1e-6:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        else:
            right = right / right_norm

        up = np.cross(right, forward)
        up_norm = np.linalg.norm(up)
        if up_norm < 1e-6:
            up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        else:
            up = up / up_norm

        focal = self.width / (2.0 * np.tan(np.radians(fov) / 2.0))
        objects = scene_data.get("objects", [])

        excluded_ids = {
            "floor", "ceiling", "back_wall", "front_wall", "left_wall", "right_wall"
        }

        visible_depths = []
        for obj in objects:
            obj_id = str(obj.get("id", "")).lower()
            if obj_id in excluded_ids:
                continue
            pos = np.array(obj.get("position", [0, 0, 0]), dtype=np.float32)
            rel = pos - cam_pos
            z_cam = float(np.dot(rel, forward))
            if z_cam > 0.01:
                visible_depths.append(z_cam)

        if not visible_depths:
            print("Simple depth renderer: no visible foreground objects in camera frustum")
            return False

        z_near = min(visible_depths)
        z_far = max(visible_depths)
        if z_far - z_near < 1e-6:
            z_far = z_near + 1.0

        for obj in objects:
            obj_id = str(obj.get("id", "")).lower()
            if obj_id in excluded_ids:
                continue

            pos = np.array(obj.get("position", [0, 0, 0]), dtype=np.float32)
            size = obj.get("size", [1, 1, 1])
            radius_world = max(float(v) for v in size) * 0.5

            rel = pos - cam_pos
            x_cam = float(np.dot(rel, right))
            y_cam = float(np.dot(rel, up))
            z_cam = float(np.dot(rel, forward))

            if z_cam <= 0.01:
                continue

            px = int(self.width / 2.0 + focal * x_cam / z_cam)
            py = int(self.height / 2.0 - focal * y_cam / z_cam)
            radius_px = max(2, int(focal * radius_world / z_cam))
            radius_px = min(radius_px, int(min(self.width, self.height) * 0.18))

            if px + radius_px < 0 or px - radius_px >= self.width or py + radius_px < 0 or py - radius_px >= self.height:
                continue

            normalized_depth = (z_cam - z_near) / (z_far - z_near)
            depth_value = min(max(normalized_depth, 0.0), 1.0)

            y_min = max(0, py - radius_px)
            y_max = min(self.height - 1, py + radius_px)
            x_min = max(0, px - radius_px)
            x_max = min(self.width - 1, px + radius_px)

            for iy in range(y_min, y_max + 1):
                dy = iy - py
                for ix in range(x_min, x_max + 1):
                    dx = ix - px
                    if dx * dx + dy * dy <= radius_px * radius_px:
                        depth[iy, ix] = min(depth[iy, ix], depth_value)

        foreground_mask = depth < 1.0
        if np.any(foreground_mask):
            fg = depth[foreground_mask]
            p5 = np.percentile(fg, 5)
            p95 = np.percentile(fg, 95)
            if p95 - p5 > 1e-6:
                depth[foreground_mask] = np.clip((fg - p5) / (p95 - p5), 0.0, 1.0)

        depth_img = ((1.0 - depth) * 255.0).astype(np.uint8)


        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.fromarray(depth_img, mode='L')
        img.save(output_path)

        print(f"Simple depth map saved to: {output_path}")
        return True


def render_depth_headless(
    scene_data: Dict[str, Any],
    output_path: str = "./data/depth/depth_map.png",
    method: str = "auto"
) -> bool:
    """
    便捷函数：无头渲染深度图

    Args:
        scene_data: 场景数据
        output_path: 输出路径
        method: 渲染方法 ("auto", "playwright", "simple")

    Returns:
        是否成功
    """
    if method == "auto":
        # 先尝试 Playwright，失败后自动回退 simple
        if PLAYWRIGHT_AVAILABLE:
            playwright_renderer = DepthRendererHeadless(output_path=output_path)
            if playwright_renderer.render(scene_data):
                return True
            print("Playwright render failed, falling back to simple renderer")

        simple_renderer = SimpleDepthRenderer()
        return simple_renderer.render(scene_data, output_path)

    if method == "playwright":
        renderer = DepthRendererHeadless(output_path=output_path)
        return renderer.render(scene_data)

    if method == "simple":
        renderer = SimpleDepthRenderer()
        return renderer.render(scene_data, output_path)

    raise ValueError(f"Unknown method: {method}")


if __name__ == "__main__":
    # 测试
    test_scene = {
        "template": "indoor_room",
        "objects": [
            {"id": "floor", "type": "plane", "position": [0, 0, 0], "size": [10, 0.1, 10]},
            {"id": "table", "type": "box", "position": [0, 0.4, 0], "size": [1.5, 0.8, 0.8]},
        ],
        "camera": {
            "position": [8, 3, 8],
            "target": [0, 1, 0],
            "fov": 50
        }
    }

    # 尝试使用 simple 渲染器（无需浏览器）
    success = render_depth_headless(test_scene, method="simple")
    print(f"Render {'success' if success else 'failed'}")
