"""
一致性Pipeline - 整合场景缓存和角色一致性

使用示例：
    # 方式1: 简单使用（自动缓存）
    pipeline = ConsistentPipeline()

    # 生成第一个视角（会自动缓存场景和角色）
    result1 = pipeline.run_from_text(
        "一个小孩站在桌子旁边，桌子上有个花盆，侧面角度"
    )

    # 生成第二个视角（复用缓存的场景和角色）
    result2 = pipeline.run_from_text(
        "一个小孩站在桌子旁边，桌子上有个花盆，俯视角度"
    )

    # 方式2: 显式多视角生成
    results = pipeline.generate_multiple_views(
        base_description="一个小孩站在桌子旁边，桌子上有个花盆",
        views=["side", "top", "front"],
        consistency_method="ip_adapter"
    )
"""
import json
import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# 导入现有组件
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.llm.shot_parser import ShotParser
from app.llm.prompt_builder import PromptBuilder
from app.scene.scene_builder import SceneBuilder
from app.scene.depth_renderer_headless import render_depth_headless
from app.comfy.workflow_loader import create_workflow
from app.comfy.client import ComfyUIClient

# 导入新增组件
from .scene_cache import SceneCache
from .character_consistency import (
    CharacterConsistencyManager,
    ConsistencyMethod,
    add_character_consistency_to_prompt
)


class ConsistentPipeline:
    """
    一致性Pipeline

    特性：
    1. 场景结构缓存 - 相同内容不同视角复用3D结构
    2. 角色一致性 - 支持多种方法保持角色外观一致
    3. 参考图像传播 - 第一视角的生成结果作为后续视角的参考
    """

    def __init__(
        self,
        comfy_url: str = "http://127.0.0.1:8188",
        llm_provider: str = "openai",
        output_dir: str = "./data/outputs",
        cache_dir: str = "./data/cache",
        consistency_method: str = "fixed_seed"
    ):
        self.comfy_url = comfy_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.shot_parser = ShotParser(provider=llm_provider)
        self.comfy_client = ComfyUIClient(server_url=comfy_url)

        # 初始化缓存
        self.scene_cache = SceneCache(cache_dir=cache_dir + "/scenes")
        self.character_manager = CharacterConsistencyManager(
            storage_dir=cache_dir + "/characters"
        )

        # 一致性设置
        self.consistency_method = ConsistencyMethod(consistency_method)
        self._last_reference_image: Optional[str] = None
        self._scene_objects_cache: Optional[List[Dict]] = None

    def run_from_text(
        self,
        text: str,
        save_intermediate: bool = True,
        force_new_scene: bool = False,
        custom_seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从文本描述生成图像（支持缓存）

        Args:
            text: 自然语言描述
            save_intermediate: 是否保存中间文件
            force_new_scene: 是否强制重新生成场景（不使用缓存）
            custom_seed: 自定义种子（覆盖默认设置）

        Returns:
            包含生成结果和缓存信息的字典
        """
        # Step 1: 解析文本
        print(f"\n{'='*60}")
        print("Step 1: Parsing text...")
        print(f"{'='*60}")

        shot_json = self.shot_parser.parse(text)
        print(f"Parsed: {json.dumps(shot_json, indent=2, ensure_ascii=False)}")

        return self.run_from_shot(
            shot_json,
            save_intermediate=save_intermediate,
            force_new_scene=force_new_scene,
            custom_seed=custom_seed
        )

    def run_from_shot(
        self,
        shot_json: Dict[str, Any],
        save_intermediate: bool = True,
        force_new_scene: bool = False,
        custom_seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从Shot JSON生成图像（支持缓存）
        """
        results = {
            "shot_json": shot_json,
            "cache_hit": False,
            "character_id": None,
            "reference_used": None,
        }

        # Step 2: 构建场景（使用缓存）
        print(f"\n{'='*60}")
        print("Step 2: Building scene...")
        print(f"{'='*60}")

        if force_new_scene:
            scene_data = self._build_new_scene(shot_json)
        else:
            scene_data, cache_hit = self._build_scene_with_cache(shot_json)
            results["cache_hit"] = cache_hit

        # 计算场景内容哈希作为Scene ID
        scene_content = json.dumps({
            "template": scene_data.get("template"),
            "objects": [{"id": obj.get("id"), "type": obj.get("type")}
                       for obj in scene_data.get("objects", [])]
        }, sort_keys=True)
        scene_id = hashlib.md5(scene_content.encode()).hexdigest()[:12]
        scene_data["scene_id"] = scene_id
        results["scene_id"] = scene_id

        print(f"[Scene] ID: {scene_id}")
        print(f"[Scene] Cache hit: {results['cache_hit']}")
        print(f"[Scene] Objects: {len(scene_data.get('objects', []))}")
        print(f"[Scene] Camera: {scene_data.get('camera', {})}")

        # Step 3: 处理角色一致性
        print(f"\n{'='*60}")
        print("Step 3: Character consistency...")
        print(f"{'='*60}")

        char_id = self._ensure_character(shot_json)
        results["character_id"] = char_id

        if char_id:
            print(f"Character ID: {char_id}")
            char = self.character_manager.get_character(char_id)
            if char and char.reference_images:
                print(f"Using reference: {char.reference_images[0]}")
                results["reference_used"] = char.reference_images[0]

        # Step 4: 构建提示词
        print(f"\n{'='*60}")
        print("Step 4: Building prompts...")
        print(f"{'='*60}")

        prompt_builder = PromptBuilder(shot_json)
        prompts = prompt_builder.export_prompts()

        # 增强提示词以保持一致性
        if char_id:
            char = self.character_manager.get_character(char_id)
            if char:
                prompts["positive"] = add_character_consistency_to_prompt(
                    prompts["positive"],
                    char.description
                )

        print(f"Positive: {prompts['positive'][:100]}...")

        # Step 5: 渲染深度图
        print(f"\n{'='*60}")
        print("Step 5: Rendering depth map...")
        print(f"{'='*60}")

        depth_map_path = self.output_dir / f"depth_{char_id or 'temp'}.png"
        render_success = self._render_depth(scene_data, str(depth_map_path))

        # Step 6: 构建并修改工作流
        print(f"\n{'='*60}")
        print("Step 6: Building workflow...")
        print(f"{'='*60}")

        seed = custom_seed if custom_seed is not None else 42

        workflow = create_workflow(
            positive_prompt=prompts["positive"],
            negative_prompt=prompts["negative"],
            depth_image_path=str(depth_map_path.name) if render_success else "depth_map.png",
            seed=seed
        )

        # 应用一致性控制
        if char_id:
            workflow = self.character_manager.apply_consistency_to_workflow(
                workflow,
                char_id,
                method=self.consistency_method
            )

        results["workflow"] = workflow

        # Step 7: 生成图像
        print(f"\n{'='*60}")
        print("Step 7: Generating image...")
        print(f"{'='*60}")
        print(f"[Scene] ID: {results.get('scene_id', 'N/A')}")
        print(f"[Scene] Cache: {'HIT' if results.get('cache_hit') else 'MISS'}")

        output_path = self._generate_image(workflow)
        results["output_image"] = output_path
        if output_path:
            print(f"[Output] Image saved: {output_path}")

        # 注意：不再自动把场景图设为角色参考图
        # 参考图应该是干净背景的角色图，需要单独生成或外部传入
        # if output_path and char_id:
        #     self._update_reference_image(char_id, output_path, is_clean_reference=True)

        return results

    def generate_multiple_views(
        self,
        base_description: str,
        views: List[str],
        consistency_method: str = "fixed_seed",
        save_references: bool = True
    ) -> Dict[str, Any]:
        """
        为同一场景生成多个视角

        Args:
            base_description: 基础场景描述（不含视角）
            views: 视角列表，如["side", "top", "front"]
            consistency_method: 一致性方法 (fixed_seed/ip_adapter/reference_only)
            save_references: 是否保存中间参考图

        Returns:
            多视角生成结果
        """
        print(f"\n{'='*60}")
        print(f"Generating {len(views)} views: {views}")
        print(f"Consistency method: {consistency_method}")
        print(f"{'='*60}")

        method = ConsistencyMethod(consistency_method)
        results = {"views": {}, "scene_outputs": [], "scene_ids": []}

        # 生成第一个视角（基础视角）
        first_view = views[0]
        first_text = f"{base_description}，{self._view_to_chinese(first_view)}角度"

        print(f"\n[1/{len(views)}] Generating base view: {first_view}")
        first_result = self.run_from_text(
            first_text,
            custom_seed=42  # 固定种子
        )
        results["views"][first_view] = first_result
        results["scene_ids"].append(first_result.get("scene_id", "N/A"))

        # 注意：不再自动把场景图设为参考图
        # 参考图应该是干净背景的角色图，需要单独生成或外部传入
        if first_result.get("output_image"):
            # 只记录为输出，不作为角色参考
            results["scene_outputs"].append(first_result["output_image"])

        # 生成其他视角
        for i, view in enumerate(views[1:], 2):
            view_text = f"{base_description}，{self._view_to_chinese(view)}角度"

            print(f"\n[{i}/{len(views)}] Generating view: {view}")

            # 临时切换一致性方法
            original_method = self.consistency_method
            self.consistency_method = method

            view_result = self.run_from_text(view_text)
            results["views"][view] = view_result
            results["scene_ids"].append(view_result.get("scene_id", "N/A"))

            # 恢复方法
            self.consistency_method = original_method

        # 验证场景一致性
        print(f"\n{'='*60}")
        print("Scene Consistency Check:")
        unique_scenes = set(results["scene_ids"])
        print(f"  Total views: {len(views)}")
        print(f"  Unique Scene IDs: {len(unique_scenes)}")
        for scene_id in unique_scenes:
            count = results["scene_ids"].count(scene_id)
            print(f"    - {scene_id}: {count} view(s)")
        if len(unique_scenes) == 1:
            print("  [OK] All views use the same scene!")
        else:
            print("  [WARNING] Views use different scenes!")
        print(f"{'='*60}")

        return results

    def _build_scene_with_cache(
        self,
        shot_json: Dict[str, Any]
    ) -> tuple[Dict[str, Any], bool]:
        """
        使用缓存构建场景

        Returns:
            (scene_data, cache_hit)
        """
        # 尝试获取缓存
        cached = self.scene_cache.get_cached_scene(shot_json)

        if cached is not None:
            print("Scene cache HIT")
            # 应用当前视角到缓存的场景
            scene_data = self.scene_cache.apply_view_to_scene(cached, shot_json)
            return scene_data, True

        print("Scene cache MISS - building new scene")
        # 构建新场景
        scene_data = self._build_new_scene(shot_json)

        # 保存到缓存（使用默认视角的基础版本）
        base_scene = copy.deepcopy(scene_data)
        base_scene["camera"] = {"position": [12, 3, 0], "target": [0, 1, 0], "fov": 50}
        self.scene_cache.save_scene(shot_json, base_scene)

        return scene_data, False

    def _build_new_scene(self, shot_json: Dict[str, Any]) -> Dict[str, Any]:
        """构建新场景"""
        builder = SceneBuilder(shot_json)
        return builder.export_to_threejs()

    def _ensure_character(self, shot_json: Dict[str, Any]) -> Optional[str]:
        """确保角色存在"""
        char_id = self.character_manager.extract_character_from_shot(shot_json)

        if char_id:
            char = self.character_manager.get_character(char_id)
            if not char:
                # 自动注册
                description = self._extract_character_description(shot_json)
                self.character_manager.register_character(
                    character_id=char_id,
                    description=description,
                    seed=42,
                    object_type=None  # 暂时为None，后续从shot_json中提取
                )
            return char_id

        return None

    def _extract_character_description(self, shot_json: Dict[str, Any]) -> str:
        """从shot中提取角色描述"""
        objects = shot_json.get("objects", [])
        character_types = {
            "child": "a young child",
            "adult": "an adult person",
            "boy": "a young boy",
            "girl": "a young girl",
            "man": "a man",
            "woman": "a woman"
        }

        for obj in objects:
            obj_type = obj.get("type", "").lower()
            if obj_type in character_types:
                return character_types[obj_type]

        return "consistent character"

    def _render_depth(self, scene_data: Dict[str, Any], output_path: str) -> bool:
        """渲染深度图"""
        try:
            return render_depth_headless(
                scene_data,
                output_path=output_path,
                method="auto"
            )
        except Exception as e:
            print(f"Depth rendering failed: {e}")
            return False

    def _generate_image(self, workflow: Dict[str, Any], output_name: Optional[str] = None) -> Optional[str]:
        """生成图像"""
        try:
            filename = self.comfy_client.generate(workflow, timeout=300)
            if filename:
                # 默认使用时间戳命名
                if output_name is None:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_name = f"output_{timestamp}.png"
                output_path = self.output_dir / output_name
                if self.comfy_client.save_image(str(filename), str(output_path)):
                    print(f"Image saved: {output_path}")
                    return str(output_path)
        except Exception as e:
            print(f"Image generation failed: {e}")

        return None

    def _update_reference_image(self, char_id: str, image_path: str, is_clean_reference: bool = False):
        """
        更新角色的参考图像

        Args:
            char_id: 角色ID
            image_path: 图像路径
            is_clean_reference: 是否为干净背景的角色参考图（白底/透明背景）
                只有干净背景的参考图才适合保存为 reference_images
                场景图不应保存为 reference_images
        """
        if not is_clean_reference:
            # 不保存场景图作为参考图
            return

        char = self.character_manager.get_character(char_id)
        if char:
            if not char.reference_images:
                char.reference_images = []
            char.reference_images.insert(0, image_path)
            # 只保留最近的3张
            char.reference_images = char.reference_images[:3]
            self.character_manager._save_character(char)
            print(f"  Saved clean reference image: {image_path}")

    def _view_to_chinese(self, view: str) -> str:
        """视角英文转中文"""
        mapping = {
            "front": "正面",
            "side": "侧面",
            "top": "俯视",
            "three_quarter": "四分之三",
            "low_angle": "低角度",
            "high_angle": "高角度"
        }
        return mapping.get(view, view)

    def clear_cache(self):
        """清空所有缓存"""
        self.scene_cache.clear_cache()
        print("Scene cache cleared")


def demo():
    """演示用法"""
    pipeline = ConsistentPipeline(
        consistency_method="fixed_seed"  # 或 "ip_adapter"
    )

    # 示例1: 连续生成不同视角
    print("=" * 60)
    print("示例1: 连续生成不同视角")
    print("=" * 60)

    descriptions = [
        "一个小孩站在桌子旁边，桌子上有个花盆，侧面角度",
        "一个小孩站在桌子旁边，桌子上有个花盆，俯视角度",
        "一个小孩站在桌子旁边，桌子上有个花盆，正面角度",
    ]

    for desc in descriptions:
        result = pipeline.run_from_text(desc)
        print(f"\n生成结果:")
        print(f"  缓存命中: {result.get('cache_hit')}")
        print(f"  角色ID: {result.get('character_id')}")
        print(f"  输出图像: {result.get('output_image')}")

    # 示例2: 批量生成多视角
    print("\n" + "=" * 60)
    print("示例2: 批量生成多视角")
    print("=" * 60)

    results = pipeline.generate_multiple_views(
        base_description="一个小孩站在桌子旁边，桌子上有个花盆",
        views=["side", "top", "front"],
        consistency_method="fixed_seed"
    )

    print(f"\n生成完成:")
    for view, result in results["views"].items():
        print(f"  {view}: {result.get('output_image')}")


if __name__ == "__main__":
    demo()
