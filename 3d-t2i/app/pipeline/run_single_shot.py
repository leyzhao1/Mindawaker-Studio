"""
单镜头流水线 - 端到端的生成流程
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.llm.shot_parser import ShotParser
from app.llm.prompt_builder import PromptBuilder
from app.scene.scene_builder import SceneBuilder
from app.scene.depth_renderer_headless import render_depth_headless
from app.comfy.workflow_loader import create_workflow
from app.comfy.client import ComfyUIClient


class SingleShotPipeline:
    """单镜头生成流水线"""

    def __init__(
        self,
        comfy_url: str = "http://127.0.0.1:8188",
        llm_provider: str = "openai",
        output_dir: str = "./data/outputs"
    ):
        self.comfy_url = comfy_url
        self.llm_provider = llm_provider
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.shot_parser = ShotParser(provider=llm_provider)
        self.comfy_client = ComfyUIClient(server_url=comfy_url)

    def run_from_text(
        self,
        text: str,
        save_intermediate: bool = True
    ) -> Dict[str, Any]:
        """
        从文本描述开始完整流程

        Args:
            text: 自然语言描述
            save_intermediate: 是否保存中间文件

        Returns:
            包含所有中间产物的结果字典
        """
        print(f"\n{'='*60}")
        print("Step 1: Parsing text to Shot JSON...")
        print(f"{'='*60}")

        shot_json = self.shot_parser.parse(text)
        print(f"Shot JSON:\n{json.dumps(shot_json, indent=2, ensure_ascii=False)}")

        if save_intermediate:
            shot_path = self.output_dir / "shot.json"
            with open(shot_path, 'w', encoding='utf-8') as f:
                json.dump(shot_json, f, indent=2, ensure_ascii=False)
            print(f"Saved to: {shot_path}")

        return self.run_from_shot(shot_json, save_intermediate)

    def run_from_shot(
        self,
        shot_json: Dict[str, Any],
        save_intermediate: bool = True
    ) -> Dict[str, Any]:
        """
        从 Shot JSON 开始完整流程

        Args:
            shot_json: Shot JSON 字典
            save_intermediate: 是否保存中间文件

        Returns:
            包含所有中间产物的结果字典
        """
        results = {
            "shot_json": shot_json,
            "scene_data": None,
            "prompts": None,
            "depth_map_path": None,
            "output_image": None,
            "workflow": None,
        }

        # Step 2: 构建场景
        print(f"\n{'='*60}")
        print("Step 2: Building 3D scene...")
        print(f"{'='*60}")

        builder = SceneBuilder(shot_json)
        scene_data = builder.export_to_threejs()
        results["scene_data"] = scene_data

        # 计算场景内容哈希作为Scene ID（用于验证场景复用）
        import hashlib
        scene_content = json.dumps({
            "template": scene_data.get("template"),
            "objects": [{"id": obj.get("id"), "type": obj.get("type")}
                       for obj in scene_data.get("objects", [])]
        }, sort_keys=True)
        scene_id = hashlib.md5(scene_content.encode()).hexdigest()[:12]
        scene_data["scene_id"] = scene_id

        print(f"[Scene] ID: {scene_id}")
        print(f"[Scene] Objects: {len(scene_data['objects'])}")
        print(f"[Scene] Camera: {scene_data['camera']}")

        if save_intermediate:
            scene_path = self.output_dir / "scene.json"
            with open(scene_path, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)
            print(f"Saved to: {scene_path}")

        # Step 3: 构建提示词
        print(f"\n{'='*60}")
        print("Step 3: Building prompts...")
        print(f"{'='*60}")

        prompt_builder = PromptBuilder(shot_json)
        prompts = prompt_builder.export_prompts()
        results["prompts"] = prompts

        print(f"Positive: {prompts['positive'][:100]}...")
        print(f"Negative: {prompts['negative'][:80]}...")

        # Step 4: 渲染深度图（尝试无头渲染，失败则提示手动）
        print(f"\n{'='*60}")
        print("Step 4: Rendering depth map...")
        print(f"{'='*60}")

        depth_map_path = self.output_dir.parent / "depth" / "depth_map.png"
        results["depth_map_path"] = str(depth_map_path)

        # 尝试无头渲染
        auto_render_success = False
        try:
            auto_render_success = render_depth_headless(
                scene_data,
                output_path=str(depth_map_path),
                method="auto"  # 自动选择可用方法
            )
        except Exception as e:
            print(f"Auto rendering failed: {e}")

        if not auto_render_success:
            print("\nAutomatic rendering not available.")
            print("Please render depth map manually using the web renderer:")
            print(f"  1. Open web/threejs_depth_renderer/index.html in browser")
            print(f"  2. Load the scene.json file")
            print(f"  3. Click 'Export Depth Map'")
            print(f"  4. Save depth map to: {depth_map_path}")
            print("\nTo enable automatic rendering:")
            print("  pip install playwright && playwright install chromium")

        # Step 5: 构建 ComfyUI 工作流
        print(f"\n{'='*60}")
        print("Step 5: Building ComfyUI workflow...")
        print(f"{'='*60}")

        # 使用相对于 ComfyUI input 目录的路径，或绝对路径
        # ComfyUI 通常从 input/ 目录加载图像
        depth_filename = depth_map_path.name if auto_render_success else "depth_map.png"

        workflow = create_workflow(
            positive_prompt=prompts["positive"],
            negative_prompt=prompts["negative"],
            depth_image_path=depth_filename,
            width=1024,
            height=1024,
            seed=42
        )
        results["workflow"] = workflow

        if save_intermediate:
            workflow_path = self.output_dir / "workflow.json"
            with open(workflow_path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            print(f"Saved to: {workflow_path}")

        print(f"\n{'='*60}")
        print("Pipeline completed!")
        print(f"{'='*60}")

        if auto_render_success:
            print("\n[OK] Depth map auto-rendered successfully!")
            print("Next steps:")
            print(f"  1. Ensure ComfyUI is running at {self.comfy_url}")
            print("  2. Run generate() to create the final image")
        else:
            print("\nNext steps:")
            print("  1. Render depth map using the web renderer")
            print("  2. Ensure ComfyUI is running at", self.comfy_url)
            print("  3. Run generate() to create the final image")

        results["depth_rendered"] = auto_render_success
        return results

    def generate(
        self,
        workflow: Optional[Dict[str, Any]] = None,
        output_name: Optional[str] = None,
        timeout: int = 300
    ) -> Optional[str]:
        """
        调用 ComfyUI 生成最终图像

        Args:
            workflow: ComfyUI 工作流（如果为 None，尝试从文件加载）
            output_name: 输出文件名（默认为时间戳命名）
            timeout: 超时时间

        Returns:
            生成的图像路径
        """
        # 默认使用时间戳命名
        if output_name is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_name = f"output_{timestamp}.png"
        if workflow is None:
            workflow_path = self.output_dir / "workflow.json"
            if workflow_path.exists():
                with open(workflow_path, 'r', encoding='utf-8') as f:
                    workflow = json.load(f)
            else:
                print("No workflow found!")
                return None

        print(f"\n{'='*60}")
        print("Generating image with ComfyUI...")
        print(f"{'='*60}")

        def progress_callback(status, progress):
            print(f"[{status}] {progress}%")

        filename = self.comfy_client.generate(
            workflow,
            timeout=timeout,
            progress_callback=progress_callback
        )

        if filename:
            output_path = self.output_dir / output_name
            if self.comfy_client.save_image(str(filename), str(output_path)):
                print(f"\nImage saved to: {output_path}")
                return str(output_path)

        return None


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="MindAwaker 3D-Guided T2I Pipeline")
    parser.add_argument("--text", "-t", help="Input text description")
    parser.add_argument("--shot", "-s", help="Path to Shot JSON file")
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188", help="ComfyUI server URL")
    parser.add_argument("--output", "-o", default="./data/outputs", help="Output directory")
    parser.add_argument("--generate", "-g", action="store_true", help="Also run generation")

    args = parser.parse_args()

    pipeline = SingleShotPipeline(
        comfy_url=args.comfy_url,
        output_dir=args.output
    )

    if args.shot:
        with open(args.shot, 'r', encoding='utf-8') as f:
            shot_json = json.load(f)
        results = pipeline.run_from_shot(shot_json)
    elif args.text:
        results = pipeline.run_from_text(args.text)
    else:
        # 默认测试
        test_text = "室内，一个孩子站在桌边，桌上有花盆，侧面视角，温暖灯光"
        print(f"Using test text: {test_text}")
        results = pipeline.run_from_text(test_text)

    if args.generate and results.get("workflow"):
        pipeline.generate(results["workflow"])


if __name__ == "__main__":
    main()
