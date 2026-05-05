"""
分层架构Pipeline - Scene/Shot分离的一致性生成

核心概念：
1. Blueprint: 场景语义模板（对象类型和关系）
2. Instance: 实际落位的场景（3D坐标 + 样式绑定 + 角色绑定）
3. Shot: 镜头（只包含相机信息，引用Instance）

使用示例：
    # 简单用法
    pipeline = HierarchicalPipeline()

    # 生成第一个视角（自动创建Scene Instance并缓存）
    shot1 = pipeline.create_shot("一个小孩站在桌子旁边，花盆在桌子上", "侧面")
    result1 = pipeline.render_shot(shot1)

    # 生成第二个视角（复用同一个Scene Instance）
    shot2 = pipeline.create_shot("一个小孩站在桌子旁边，花盆在桌子上", "俯视")
    result2 = pipeline.render_shot(shot2)  # 角色和布局完全一致

    # 批量生成多视角
    shots = pipeline.create_multi_view_shots(
        "一个小孩站在桌子旁边，花盆在桌子上",
        views=["侧面", "俯视", "正面"]
    )
    results = pipeline.render_shots(shots)
"""
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from copy import deepcopy

from app.schema.scene_hierarchy import (
    SceneBlueprint, BlueprintObject, SceneInstance,
    Shot, CameraConfig, create_shot_from_text
)
from app.scene.instance_builder import InstanceBuilder, InstanceCache
from app.scene.depth_renderer_headless import render_depth_headless
from app.scene.spatial_projector import (
    SpatialProjector, ProjectedRegion,
    build_projector_from_camera_config, project_instance_objects,
)
from app.llm.shot_parser import ShotParser
from app.llm.prompt_builder import PromptBuilder
from datetime import datetime
from app.comfy.workflow_loader import create_workflow, create_regional_prompt_workflow
from app.comfy.client import ComfyUIClient
from .character_consistency import (
    CharacterConsistencyManager,
    ConsistencyMethod,
    add_character_consistency_to_prompt
)
from .character_library import CharacterLibrary


class HierarchicalPipeline:
    """
    分层架构Pipeline

    优势：
    1. Scene Instance复用：多个Shots共享同一个3D场景
    2. 角色一致性：角色绑定在Instance层
    3. 确定性生成：相同Blueprint总是生成相同的Instance布局
    """

    def __init__(
        self,
        comfy_url: str = "http://127.0.0.1:8188",
        llm_provider: str = "openai",
        output_dir: str = "./data/outputs",
        cache_dir: str = "./data/cache",
        consistency_method: str = "fixed_seed",
        generate_character_references: bool = False,
        character_library_path: str = "./data/character_library.json"
    ):
        self.comfy_url = comfy_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generate_character_references = generate_character_references

        # 初始化组件
        self.shot_parser = ShotParser(provider=llm_provider)
        self.comfy_client = ComfyUIClient(server_url=comfy_url)

        # 缓存系统
        self.instance_cache = InstanceCache(cache_dir=f"{cache_dir}/instances")
        self.character_manager = CharacterConsistencyManager(
            storage_dir=f"{cache_dir}/characters"
        )
        # 角色库
        self.character_library = CharacterLibrary(library_path=character_library_path)

        # 一致性设置
        self.consistency_method = ConsistencyMethod(consistency_method)

        # 跟踪当前会话的Scene Instance
        self._current_instance: Optional[SceneInstance] = None

    # ==========================================================================
    # 核心API：Scene/Shot操作
    # ==========================================================================

    def parse_to_blueprint(self, description: str) -> SceneBlueprint:
        """
        将文本描述解析为SceneBlueprint

        Args:
            description: 自然语言描述（如"一个小孩站在桌子旁边，花盆在桌子上"）

        Returns:
            SceneBlueprint对象
        """
        # 使用现有的shot_parser，然后转换为Blueprint
        shot_json = self.shot_parser.parse(description)

        blueprint = SceneBlueprint.from_shot_json(shot_json)
        return blueprint

    def build_instance(
        self,
        blueprint: SceneBlueprint,
        style_id: str = "default",
        force_rebuild: bool = False,
        character_references: Optional[Dict[str, str]] = None
    ) -> SceneInstance:
        """
        将Blueprint构建为SceneInstance

        Args:
            blueprint: 场景蓝图
            style_id: 样式标识（如"storybook_warm"）
            force_rebuild: 是否强制重建（忽略缓存）
            character_references: 角色参考图路径 {object_id: image_path}
                参考图应该是干净背景的角色图（白底/透明）
            注意：自动生成参考图由实例属性 self.generate_character_references 控制

        Returns:
            SceneInstance对象
        """
        # 检查角色绑定（传入外部参考图）
        character_bindings = self._extract_character_bindings(
            blueprint, character_references
        )

        # 如果需要自动生成参考图
        if self.generate_character_references and not character_references:
            print("\n[Character] Auto-generating character references...")
            self._generate_missing_references(blueprint, character_bindings)

        instance = self.instance_cache.get_or_build_instance(
            blueprint,
            style_id=style_id,
            character_bindings=character_bindings,
            force_rebuild=force_rebuild
        )

        self._current_instance = instance
        return instance

    def _generate_missing_references(
        self,
        blueprint: SceneBlueprint,
        character_bindings: Dict[str, str]
    ):
        """为没有参考图的角色生成多视角参考图"""
        for obj_id, char_id in character_bindings.items():
            char = self.character_manager.get_character(char_id)
            if char and not char.reference_images:
                # 找到对应的角色对象
                char_obj = None
                for obj in blueprint.objects:
                    if obj.id == obj_id:
                        char_obj = obj
                        break

                if char_obj:
                    # 生成多视角参考图
                    ref_paths = self._generate_character_reference(
                        blueprint, obj_id, char_id
                    )
                    if ref_paths:
                        char.reference_images = ref_paths
                        self.character_manager._save_character(char)
                        print(f"  Generated and saved {len(ref_paths)} reference images")

    def create_shot(
        self,
        description: str,
        view: str,
        style_id: str = "default",
        reuse_instance: bool = True
    ) -> Shot:
        """
        创建Shot（一站式方法）

        Args:
            description: 场景描述
            view: 视角（如"侧面", "俯视", "正面"）
            style_id: 样式标识
            reuse_instance: 是否尝试复用当前Instance

        Returns:
            Shot对象
        """
        # 解析为Blueprint
        blueprint = self.parse_to_blueprint(description)

        # 检查是否可以复用Instance
        if reuse_instance and self._current_instance:
            if self._current_instance.blueprint_id == blueprint.blueprint_id:
                # Blueprint相同，复用Instance
                instance = self._current_instance
            else:
                # 不同场景，构建新Instance
                instance = self.build_instance(blueprint, style_id)
        else:
            # 获取或构建Instance
            instance = self.build_instance(blueprint, style_id)

        # 创建Shot
        shot = create_shot_from_text(instance, view)
        return shot

    def create_multi_view_shots(
        self,
        description: str,
        views: List[str],
        style_id: str = "default"
    ) -> List[Shot]:
        """
        为同一场景创建多个视角的Shots

        Args:
            description: 场景描述
            views: 视角列表（如["侧面", "俯视", "正面"]）
            style_id: 样式标识

        Returns:
            Shot对象列表
        """
        # 解析一次Blueprint
        blueprint = self.parse_to_blueprint(description)
        print(f"[Scene] Blueprint ID: {blueprint.blueprint_id}")

        # 构建一次Instance
        instance = self.build_instance(blueprint, style_id)
        print(f"[Scene] Instance ID: {instance.instance_id}")
        print(f"[Scene] Style ID: {instance.style_id}")
        print(f"[Scene] Creating {len(views)} shots with same scene...")

        # 为每个视角创建Shot
        shots = []
        for view in views:
            shot = create_shot_from_text(instance, view)
            shots.append(shot)
            print(f"  - Shot: {view} -> scene_id: {shot.scene_id}")

        return shots

    # ==========================================================================
    # 渲染API
    # ==========================================================================

    def render_shot(
        self,
        shot: Shot,
        output_name: Optional[str] = None,
        save_intermediate: bool = True,
        use_spatial_masks: bool = True,
    ) -> Dict[str, Any]:
        """
        渲染单个Shot

        Args:
            shot: Shot对象
            output_name: 输出文件名
            save_intermediate: 是否保存中间文件
            use_spatial_masks: 是否使用空间投影mask进行区域控制

        Returns:
            渲染结果字典
        """
        result = {
            "shot": shot.to_dict(),
            "scene_id": shot.scene_id,
            "output_image": None,
            "depth_map": None,
            "projected_regions": None,
        }

        # 获取SceneInstance
        instance = self.instance_cache.get_instance_by_id(shot.scene_id)

        if not instance:
            raise ValueError(f"Scene instance not found: {shot.scene_id}")

        # Step 1: 准备Three.js场景数据
        print(f"\n[Shot {shot.shot_id}] Preparing scene data...")
        scene_data = instance.to_threejs_scene()
        camera_config = shot.to_camera_config()
        scene_data["camera"] = camera_config

        # Step 1.5: 3D → 2D 投影（空间mask生成）
        projected_regions = None
        mask_dir = self.output_dir / "masks"
        if use_spatial_masks:
            print(f"[Shot {shot.shot_id}] Projecting 3D objects to 2D masks...")
            projected_regions = project_instance_objects(
                instance, camera_config, width=1024, height=1024
            )
            if projected_regions:
                # 为有角色绑定的对象保存mask
                mask_dir.mkdir(parents=True, exist_ok=True)
                from app.scene.spatial_projector import _save_mask_image
                uploaded_masks = {}
                for region in projected_regions:
                    mask_filename = f"mask_{shot.shot_id}_{region.object_id}.png"
                    mask_path = mask_dir / mask_filename
                    _save_mask_image(region.mask, str(mask_path))
                    try:
                        self.comfy_client.upload_image(str(mask_path), name=mask_filename)
                        uploaded_masks[region.object_id] = mask_filename
                        print(f"  [Mask] {region.object_id}: bbox={region.bbox}, uploaded")
                    except Exception as e:
                        print(f"  [Mask] {region.object_id}: upload failed ({e}), falling back to local path")
                        uploaded_masks[region.object_id] = str(mask_path)
                result["uploaded_masks"] = uploaded_masks
                print(f"  [Projection] {len(projected_regions)} objects projected")
            result["projected_regions"] = [
                {
                    "object_id": r.object_id,
                    "object_type": r.object_type,
                    "bbox": list(r.bbox),
                    "mask_path": str(mask_dir / f"mask_{shot.shot_id}_{r.object_id}.png"),
                }
                for r in projected_regions
            ] if projected_regions else []

        # Step 2: 渲染深度图
        print(f"[Shot {shot.shot_id}] Rendering depth map...")
        depth_path = self.output_dir / f"depth_{shot.shot_id}.png"
        render_success = render_depth_headless(
            scene_data,
            output_path=str(depth_path),
            method="auto"
        )
        result["depth_map"] = str(depth_path) if render_success else None

        # 上传深度图到 ComfyUI
        if render_success:
            try:
                self.comfy_client.upload_image(str(depth_path), name=depth_path.name)
                print(f"  [Depth] Uploaded: {depth_path.name}")
            except Exception as e:
                print(f"  [Depth] Upload failed: {e}")

        # Step 3: 构建提示词
        print(f"[Shot {shot.shot_id}] Building prompts...")
        shot_json = self._build_shot_json_for_prompt(instance, shot)
        prompt_builder = PromptBuilder(shot_json)

        # 使用区域提示词集（如果启用空间mask）
        if use_spatial_masks and projected_regions:
            regional_prompts = prompt_builder.build_regional_prompt_set()
            prompts = {
                "positive": regional_prompts["global_positive"],
                "negative": regional_prompts["global_negative"],
                "regions": regional_prompts["regions"],
            }
        else:
            prompts = prompt_builder.export_prompts()
            # 增强提示词以保持一致性
            for binding in instance.character_bindings.values():
                prompts["positive"] = add_character_consistency_to_prompt(
                    prompts["positive"],
                    binding.character_description
                )

        # Step 4: 构建工作流（三级回退：IP-Adapter → 区域提示词 → 全局提示词）
        print(f"[Shot {shot.shot_id}] Building workflow...")
        depth_file = depth_path.name if render_success else "depth_map.png"

        workflow = None
        used_method = "global"

        if use_spatial_masks and projected_regions:
            # 使用已上传到 ComfyUI 的 mask 文件名（优先），回退到本地路径
            uploaded = result.get("uploaded_masks", {})
            region_masks = {}
            for region in projected_regions:
                if region.object_id in uploaded:
                    region_masks[region.object_id] = uploaded[region.object_id]
                else:
                    region_masks[region.object_id] = str(
                        mask_dir / f"mask_{shot.shot_id}_{region.object_id}.png"
                    )

            # 检查哪些角色有 reference image
            character_masks = {}
            has_any_reference = False
            for obj_id, binding in instance.character_bindings.items():
                if obj_id in region_masks:
                    char = self.character_manager._characters.get(binding.character_id)
                    if char and char.reference_images:
                        character_masks[binding.character_id] = {
                            "mask_path": region_masks[obj_id],
                        }
                        has_any_reference = True

            if has_any_reference:
                # 路径 A: 有 reference image → IP-Adapter + mask
                print(f"  [Method] Regional IP-Adapter ({len(character_masks)} chars)")
                base_wf = create_workflow(
                    positive_prompt=prompts["positive"],
                    negative_prompt=prompts["negative"],
                    depth_image_path=depth_file,
                    seed=42,
                )
                workflow = self.character_manager.create_multi_character_ipadapter_workflow(
                    base_wf, character_masks
                )
                used_method = "ip_adapter_mask"

            if workflow is None:
                # 路径 B: 无 reference image → 纯区域提示词（ConditioningSetMask）
                print(f"  [Method] Regional prompt ({len(region_masks)} masks, no reference needed)")
                region_prompts_for_wf = {
                    obj_id: prompts["regions"][obj_id]["positive"]
                    for obj_id in region_masks
                    if obj_id in prompts.get("regions", {})
                }
                workflow = create_regional_prompt_workflow(
                    global_positive=prompts["positive"],
                    global_negative=prompts["negative"],
                    region_prompts=region_prompts_for_wf,
                    region_masks=region_masks,
                    depth_image_path=depth_file,
                    seed=42,
                )
                used_method = "regional_prompt_mask"

        if workflow is None:
            # 路径 C: 普通全图工作流 + 角色一致性
            print(f"  [Method] Global prompt + character consistency")
            workflow = create_workflow(
                positive_prompt=prompts["positive"],
                negative_prompt=prompts["negative"],
                depth_image_path=depth_file,
                seed=42,
            )
            for obj_id, binding in instance.character_bindings.items():
                workflow = self.character_manager.apply_consistency_to_workflow(
                    workflow,
                    binding.character_id,
                    method=self.consistency_method,
                )
            used_method = "global_consistency"

        result["used_method"] = used_method

        # Step 5: 生成图像
        print(f"[Shot {shot.shot_id}] Generating image...")
        print(f"  [Scene] Instance ID: {instance.instance_id}")
        print(f"  [Scene] Blueprint ID: {instance.blueprint_id}")
        print(f"  [Scene] Style ID: {instance.style_id}")
        if output_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            view_tag = shot.camera.view if hasattr(shot.camera, 'view') else 'view'
            output_name = f"output_{timestamp}_{view_tag}.png"
        image_path = self._generate_image(workflow, output_name)
        result["output_image"] = image_path
        if image_path:
            print(f"  [Output] Image saved: {image_path}")

        return result

    def render_shots(
        self,
        shots: List[Shot],
        output_prefix: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        批量渲染多个Shots

        Args:
            shots: Shot对象列表
            output_prefix: 输出文件名前缀（默认为时间戳）

        Returns:
            渲染结果列表
        """
        # 生成统一的时间戳前缀
        if output_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_prefix = f"shot_{timestamp}"

        # 检查所有shots是否使用同一个scene
        scene_ids = set(shot.scene_id for shot in shots)
        print(f"\n{'='*60}")
        print(f"Batch Rendering: {len(shots)} shots")
        print(f"{'='*60}")
        print(f"[Scene] Unique Scene IDs: {len(scene_ids)}")
        for scene_id in scene_ids:
            print(f"  - {scene_id}")
        print(f"{'='*60}")

        results = []
        for i, shot in enumerate(shots):
            print(f"\n{'='*60}")
            print(f"Rendering shot {i+1}/{len(shots)}: {shot.camera.view}")
            print(f"[Scene] ID: {shot.scene_id}")
            print(f"{'='*60}")

            result = self.render_shot(
                shot,
                output_name=f"{output_prefix}_{i:02d}_{shot.camera.view}.png"
            )
            results.append(result)

        return results

    # ==========================================================================
    # 便捷方法：旧版API兼容
    # ==========================================================================

    def run_from_text(
        self,
        text: str,
        save_intermediate: bool = True
    ) -> Dict[str, Any]:
        """
        兼容旧版API：从文本描述生成

        自动解析description和view
        """
        # 尝试从文本中提取视角
        view_keywords = {
            "侧面": "侧面", "side": "侧面",
            "俯视": "俯视", "top": "俯视", "鸟瞰": "俯视",
            "正面": "正面", "front": "正面",
            "四分之三": "四分之三", "three_quarter": "四分之三",
        }

        view = "侧面"  # 默认
        description = text

        for keyword, view_name in view_keywords.items():
            if keyword in text.lower():
                view = view_name
                # 从描述中移除视角关键词（可选）
                break

        # 创建并渲染shot
        shot = self.create_shot(description, view)
        return self.render_shot(shot, save_intermediate=save_intermediate)

    def generate_multiple_views(
        self,
        base_description: str,
        views: List[str],
        consistency_method: str = "fixed_seed"
    ) -> Dict[str, Any]:
        """
        兼容旧版API：批量生成多视角
        """
        original_method = self.consistency_method
        self.consistency_method = ConsistencyMethod(consistency_method)

        try:
            shots = self.create_multi_view_shots(base_description, views)
            results = self.render_shots(shots, output_prefix="view")

            return {
                "views": {
                    shot.camera.view: result
                    for shot, result in zip(shots, results)
                },
                "shots": [s.to_dict() for s in shots]
            }
        finally:
            self.consistency_method = original_method

    # ==========================================================================
    # 内部方法
    # ==========================================================================

    def _extract_character_bindings(
        self,
        blueprint: SceneBlueprint,
        character_references: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        从Blueprint提取角色绑定，优先使用角色库匹配

        Args:
            blueprint: 场景蓝图
            character_references: 外部传入的角色参考图路径 {object_id: image_path}

        Returns:
            角色绑定字典 {object_id: character_id}
        """
        bindings = {}
        character_types = ["child", "adult", "boy", "girl", "man", "woman"]
        character_references = character_references or {}

        for obj in blueprint.objects:
            if obj.type in character_types:
                # 1. 尝试在角色库中匹配角色
                char_def = None
                if self.character_library:
                    # 使用对象类型和描述（如果有）进行匹配
                    description = obj.description or ""
                    char_def = self.character_library.find_matching_character(
                        object_type=obj.type,
                        description=description
                    )

                if char_def:
                    # 使用角色库中的角色
                    char_id = char_def.character_id
                    print(f"  Matched character from library: {char_def.name} ({char_id})")

                    # 确保角色已注册到一致性管理器
                    self.character_library.ensure_character_in_manager(
                        self.character_manager,
                        char_def,
                        generate_references=False  # 参考图生成由外部流程控制
                    )
                else:
                    # 2. 没有匹配，使用默认ID生成
                    char_id = f"char_{obj.type}_{blueprint.blueprint_id[:8]}"
                    print(f"  No library match, using generated ID: {char_id}")

                    # 检查是否已注册
                    existing_char = self.character_manager.get_character(char_id)
                    if not existing_char:
                        # 注册新角色（没有角色库信息）
                        reference_images = []
                        if obj.id in character_references:
                            reference_images = [character_references[obj.id]]

                        self.character_manager.register_character(
                            character_id=char_id,
                            description=f"a {obj.type}, consistent appearance",
                            reference_images=reference_images,
                            seed=42,
                            object_type=obj.type
                        )
                        print(f"    Registered new character: {char_id}")

                bindings[obj.id] = char_id

                # 3. 处理外部参考图（如果有）
                if obj.id in character_references:
                    char = self.character_manager.get_character(char_id)
                    if char:
                        char.reference_images = [character_references[obj.id]]
                        self.character_manager._save_character(char)
                        print(f"    Updated with external reference: {character_references[obj.id]}")

        return bindings

    def _build_shot_json_for_prompt(
        self,
        instance: SceneInstance,
        shot: Shot
    ) -> Dict[str, Any]:
        """构建用于PromptBuilder的shot_json格式"""
        objects = []
        for obj in instance.objects:
            obj_data = {
                "id": obj.id,
                "type": obj.type,
            }
            if obj.parent:
                obj_data["relation"] = f"on_top_of:{obj.parent}"
            objects.append(obj_data)

        return {
            "template": instance.template,
            "objects": objects,
            "camera": shot.to_camera_config(),
            "style_prompt": instance.metadata.get("style_prompt", ""),
            "lighting": instance.metadata.get("lighting", {})
        }

    def _generate_image(
        self,
        workflow: Dict[str, Any],
        output_name: str
    ) -> Optional[str]:
        """生成图像"""
        try:
            filename = self.comfy_client.generate(workflow, timeout=300)
            if filename:
                output_path = self.output_dir / output_name
                if self.comfy_client.save_image(str(filename), str(output_path)):
                    print(f"  Saved: {output_path}")
                    return str(output_path)
        except Exception as e:
            print(f"  Generation failed: {e}")

        return None

    def _update_reference_images(self, instance: SceneInstance, image_path: str, is_clean_reference: bool = False):
        """
        更新Instance中所有角色的参考图像

        Args:
            instance: 场景实例
            image_path: 图像路径
            is_clean_reference: 是否为干净背景的角色参考图
                只有干净背景的角色参考图才保存到 reference_images
                场景图不应保存为 reference_images
        """
        if not is_clean_reference:
            # 不保存场景图作为参考
            return

        for binding in instance.character_bindings.values():
            char = self.character_manager.get_character(binding.character_id)
            if char:
                if not char.reference_images:
                    char.reference_images = []
                char.reference_images.insert(0, image_path)
                char.reference_images = char.reference_images[:3]  # 保留最近3张
                self.character_manager._save_character(char)

    def _ensure_character(self, blueprint: SceneBlueprint, generate_reference: bool = False) -> Optional[str]:
        """
        确保角色存在，可选生成参考图

        Args:
            blueprint: 场景蓝图
            generate_reference: 是否自动生成角色参考图

        Returns:
            角色ID，如果没有角色返回None
        """
        character_types = ["child", "adult", "boy", "girl", "man", "woman"]

        for obj in blueprint.objects:
            if obj.type in character_types:
                char_id = f"char_{obj.type}_{blueprint.blueprint_id[:8]}"
                char = self.character_manager.get_character(char_id)

                if not char:
                    # 注册新角色
                    description = self._extract_character_description(obj.type)
                    self.character_manager.register_character(
                        character_id=char_id,
                        description=description,
                        seed=42,
                        object_type=obj.type
                    )
                    print(f"  Registered character: {char_id}")

                # 如果需要生成参考图且没有参考图
                if generate_reference and not char.reference_images:
                    ref_paths = self._generate_character_reference(blueprint, obj.id, char_id)
                    if ref_paths:
                        char.reference_images = ref_paths
                        self.character_manager._save_character(char)

                return char_id

        return None

    def _extract_character_description(self, obj_type: str) -> str:
        """提取角色描述"""
        descriptions = {
            "child": "a young child",
            "adult": "an adult person",
            "boy": "a young boy",
            "girl": "a young girl",
            "man": "a man",
            "woman": "a woman"
        }
        return descriptions.get(obj_type, "consistent character")

    def _generate_character_reference(
        self,
        blueprint: SceneBlueprint,
        object_id: str,
        char_id: str,
        views: List[str] = None
    ) -> List[str]:
        """
        生成角色多视角参考图（白底干净背景）

        Args:
            blueprint: 场景蓝图
            object_id: 角色对象ID
            char_id: 角色ID
            views: 要生成的视角列表，默认为["front", "side", "three_quarter"]

        Returns:
            生成的参考图路径列表
        """
        from app.scene.scene_builder import build_scene_from_json
        from app.scene.depth_renderer_headless import render_depth_headless

        # 默认视角
        if views is None:
            views = ["front", "side", "three_quarter"]

        # 视角到提示词的映射
        view_prompt_mapping = {
            "front": "frontal view, facing camera directly",
            "side": "profile view, side angle, from the side",
            "top": "overhead view, bird's eye view, from above",
            "three_quarter": "three-quarter view, angled perspective",
            "low_angle": "low angle view, looking up",
            "high_angle": "high angle view, looking down",
        }

        # 找到角色对象
        char_obj = None
        for obj in blueprint.objects:
            if obj.id == object_id:
                char_obj = obj
                break

        if not char_obj:
            return []

        print(f"  Generating {len(views)} reference views for {char_obj.type}...")

        generated_paths = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for view in views:
            print(f"    Generating {view} view...")

            # 创建白底shot
            reference_shot = {
                "template": "white_background",
                "objects": [{"id": char_obj.id, "type": char_obj.type, "position": "center"}],
                "camera": {"view": view},
                "style_prompt": f"{char_obj.type}, full body, clean white background, studio lighting",
                "lighting": {"type": "studio"}
            }

            try:
                # 构建场景和深度图
                scene_data = build_scene_from_json(reference_shot)
                depth_path = self.output_dir / f"ref_{char_obj.type}_{timestamp}_{view}_depth.png"

                render_success = render_depth_headless(
                    scene_data, output_path=str(depth_path), method="auto"
                )

                # 构建提示词和工作流
                prompt_builder = PromptBuilder(reference_shot)
                prompts = prompt_builder.export_prompts()

                # 获取视角描述
                view_prompt = view_prompt_mapping.get(view, f"{view} view")
                prompts["positive"] = f"{char_obj.type}, full body, clean white background, studio lighting, high quality, {view_prompt}"

                workflow = create_workflow(
                    positive_prompt=prompts["positive"],
                    negative_prompt=prompts["negative"],
                    depth_image_path=depth_path.name if render_success else "depth_map.png",
                    seed=42
                )

                # 生成图像
                output_name = f"char_ref_{char_obj.type}_{timestamp}_{view}.png"
                image_path = self._generate_image(workflow, output_name)

                if image_path:
                    generated_paths.append(image_path)
                    print(f"      Generated {view} reference: {image_path}")

            except Exception as e:
                print(f"      Failed to generate {view} reference: {e}")
                continue

        # 保存所有参考图到角色
        if generated_paths:
            char = self.character_manager.get_character(char_id)
            if char:
                char.reference_images = generated_paths
                self.character_manager._save_character(char)
                print(f"  Saved {len(generated_paths)} reference images for character {char_id}")

        return generated_paths


# ==============================================================================
# 便捷函数
# ==============================================================================

def quick_generate_views(
    description: str,
    views: List[str],
    style: str = "default",
    output_dir: str = "./data/outputs"
) -> Dict[str, str]:
    """
    快速生成多视角（一站式函数）

    Returns:
        {view_name: image_path}
    """
    pipeline = HierarchicalPipeline(output_dir=output_dir)
    shots = pipeline.create_multi_view_shots(description, views, style)
    results = pipeline.render_shots(shots)

    return {
        shot.camera.view: result.get("output_image")
        for shot, result in zip(shots, results)
    }
