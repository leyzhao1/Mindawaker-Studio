"""
角色一致性系统 - 保持多视角下角色外观一致

支持方案：
1. Fixed Seed: 固定随机种子（简单但不完美）
2. IP-Adapter: 使用参考图像引导生成（推荐）
3. Reference Only: 使用Reference-only ControlNet
"""
import json
import copy
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ConsistencyMethod(Enum):
    """一致性方法枚举"""
    FIXED_SEED = "fixed_seed"
    IP_ADAPTER = "ip_adapter"
    REFERENCE_ONLY = "reference_only"


@dataclass
class CharacterIdentity:
    """角色身份定义"""
    character_id: str  # 角色唯一标识
    description: str  # 角色描述（如"一个5岁男孩，穿红色T恤"）
    reference_images: List[str] = field(default_factory=list)  # 参考图像路径列表
    seed: Optional[int] = None  # 固定种子（如果使用fixed_seed方法）
    # 新增字段用于角色库
    name: Optional[str] = None  # 角色名称（如"Lucy"）
    key_features: List[str] = field(default_factory=list)  # 关键特征列表（如["golden hair", "blue eyes"]）
    is_main_character: bool = True  # 是否为主要角色（主要角色生成参考图，路人角色不生成）
    object_type: Optional[str] = None  # 对象类型（如"child", "adult"）


class CharacterConsistencyManager:
    """
    角色一致性管理器

    核心功能：
    1. 为角色创建统一的身份标识
    2. 管理参考图像
    3. 生成带有一致性控制的ComfyUI工作流
    """

    def __init__(self, storage_dir: str = "./data/character_cache"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._characters: Dict[str, CharacterIdentity] = {}
        self._load_characters()

    def _get_character_path(self, char_id: str) -> Path:
        """获取角色存储路径"""
        return self.storage_dir / f"{char_id}.json"

    def _load_characters(self):
        """加载已保存的角色"""
        for char_file in self.storage_dir.glob("*.json"):
            try:
                with open(char_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    char = CharacterIdentity(
                        character_id=data["character_id"],
                        description=data.get("description", ""),
                        reference_images=data.get("reference_images", []),
                        seed=data.get("seed"),
                        name=data.get("name"),
                        key_features=data.get("key_features", []),
                        is_main_character=data.get("is_main_character", True),
                        object_type=data.get("object_type")
                    )
                    self._characters[char.character_id] = char
            except Exception as e:
                print(f"Failed to load character {char_file}: {e}")

    def _save_character(self, char: CharacterIdentity):
        """保存角色"""
        char_path = self._get_character_path(char.character_id)
        with open(char_path, 'w', encoding='utf-8') as f:
            json.dump({
                "character_id": char.character_id,
                "description": char.description,
                "reference_images": char.reference_images,
                "seed": char.seed,
                "name": char.name,
                "key_features": char.key_features,
                "is_main_character": char.is_main_character,
                "object_type": char.object_type
            }, f, indent=2, ensure_ascii=False)

    def register_character(
        self,
        character_id: str,
        description: str,
        reference_images: List[str] = None,
        seed: Optional[int] = None,
        name: Optional[str] = None,
        key_features: List[str] = None,
        is_main_character: bool = True,
        object_type: Optional[str] = None
    ) -> CharacterIdentity:
        """
        注册角色

        Args:
            character_id: 角色唯一标识
            description: 角色描述（用于增强prompt）
            reference_images: 参考图像路径列表
            seed: 固定种子（可选）
            name: 角色名称（如"Lucy"）
            key_features: 关键特征列表
            is_main_character: 是否为主要角色
            object_type: 对象类型（如"child", "adult"）
        """
        char = CharacterIdentity(
            character_id=character_id,
            description=description,
            reference_images=reference_images or [],
            seed=seed,
            name=name,
            key_features=key_features or [],
            is_main_character=is_main_character,
            object_type=object_type
        )
        self._characters[character_id] = char
        self._save_character(char)
        return char

    def get_character(self, character_id: str) -> Optional[CharacterIdentity]:
        """获取角色"""
        return self._characters.get(character_id)

    def extract_character_from_shot(self, shot_json: Dict[str, Any]) -> Optional[str]:
        """
        从shot中识别角色

        简单的启发式方法：找到人物类型对象并生成ID
        """
        character_types = ["child", "adult", "boy", "girl", "man", "woman"]
        objects = shot_json.get("objects", [])

        for obj in objects:
            obj_type = obj.get("type", "").lower()
            if obj_type in character_types:
                # 基于场景内容生成角色ID
                # 这样同一描述的不同视角会识别为同一角色
                content = json.dumps({
                    "template": shot_json.get("template"),
                    "obj_type": obj_type,
                    "style": shot_json.get("style_prompt", "")
                }, sort_keys=True)
                char_id = hashlib.md5(content.encode()).hexdigest()[:12]
                return char_id

        return None

    def enhance_prompt_with_character(
        self,
        base_prompt: str,
        character_id: str
    ) -> str:
        """
        使用角色描述增强提示词

        将角色特征描述插入到prompt中，增加一致性
        """
        char = self._characters.get(character_id)
        if not char or not char.description:
            return base_prompt

        # 在prompt中加入角色描述
        # 策略：在主体描述后添加详细特征
        enhanced = f"{base_prompt}, {char.description}, same character, consistent appearance"
        return enhanced

    def create_ipadapter_workflow(
        self,
        base_workflow: Dict[str, Any],
        character_id: str,
        ipadapter_strength: float = 0.6,
        attention_mask_path: Optional[str] = None,
        node_offset: int = 100,
    ) -> Optional[Dict[str, Any]]:
        """
        创建带有IP-Adapter的工作流（支持注意力mask）

        注意：需要在ComfyUI中安装ComfyUI_IPAdapter_plus节点包

        Args:
            base_workflow: 基础工作流
            character_id: 角色ID
            ipadapter_strength: IP-Adapter强度（0-1）
            attention_mask_path: 注意力mask图像路径（可选，用于空间约束）
            node_offset: 节点ID起始偏移量

        Returns:
            (修改后的工作流, 下一个可用节点ID) 元组，如果无法创建则返回None
        """
        char = self._characters.get(character_id)
        if not char or not char.reference_images:
            return None

        workflow = copy.deepcopy(base_workflow)
        ref_image = char.reference_images[0]

        loader_id = str(node_offset)
        mask_id = str(node_offset + 1)
        ipadapter_id = str(node_offset + 2)

        has_mask = attention_mask_path is not None

        workflow[loader_id] = {
            "inputs": {"image": ref_image},
            "class_type": "LoadImage",
        }

        if has_mask:
            workflow[mask_id] = {
                "inputs": {"image": attention_mask_path},
                "class_type": "LoadImage",
            }

        workflow[ipadapter_id] = {
            "inputs": {
                "weight": ipadapter_strength,
                "noise": 0.0,
                "weight_type": "original",
                "start_at": 0.0,
                "end_at": 1.0,
                "unfold_batch": False,
                "model": ["1", 0],
                "ipadapter": ["101", 0],
                "image": [loader_id, 0],
            },
            "class_type": "IPAdapter",
        }

        if has_mask:
            workflow[ipadapter_id]["inputs"]["attn_mask"] = [mask_id, 0]

        # 修改KSampler使用IP-Adapter处理后的模型
        if "8" in workflow:
            workflow["8"]["inputs"]["model"] = [ipadapter_id, 0]

        return workflow

    def create_multi_character_ipadapter_workflow(
        self,
        base_workflow: Dict[str, Any],
        character_masks: Dict[str, Dict[str, Any]],
        ipadapter_strength: float = 0.6,
    ) -> Optional[Dict[str, Any]]:
        """
        创建多角色 IP-Adapter 工作流（每个角色可带注意力mask）

        多个IPAdapter节点串联：Model → IPAdapter1 → IPAdapter2 → ... → KSampler

        Args:
            base_workflow: 基础工作流
            character_masks: {
                character_id: {
                    "mask_path": "/path/to/mask.png",  # 可选
                    "strength": 0.6,  # 可选，覆盖全局strength
                }
            }
            ipadapter_strength: 默认 IP-Adapter 强度

        Returns:
            修改后的工作流
        """
        workflow = copy.deepcopy(base_workflow)

        ipadapter_loader_id = "101"
        workflow[ipadapter_loader_id] = {
            "inputs": {"ipadapter_file": "ip-adapter_sd15.bin"},
            "class_type": "IPAdapterModelLoader",
        }

        prev_model_ref = ["1", 0]  # 从CheckpointLoader开始
        node_id = 200

        for character_id, config in character_masks.items():
            char = self._characters.get(character_id)
            if not char or not char.reference_images:
                continue

            ref_image = char.reference_images[0]
            mask_path = config.get("mask_path")
            strength = config.get("strength", ipadapter_strength)

            loader_id = str(node_id)
            mask_id = str(node_id + 1)
            ipadapter_id = str(node_id + 2)
            node_id += 3

            workflow[loader_id] = {
                "inputs": {"image": ref_image},
                "class_type": "LoadImage",
            }

            ipadapter_inputs = {
                "weight": strength,
                "noise": 0.0,
                "weight_type": "original",
                "start_at": 0.0,
                "end_at": 1.0,
                "unfold_batch": False,
                "model": prev_model_ref,
                "ipadapter": [ipadapter_loader_id, 0],
                "image": [loader_id, 0],
            }

            if mask_path:
                workflow[mask_id] = {
                    "inputs": {"image": mask_path},
                    "class_type": "LoadImage",
                }
                ipadapter_inputs["attn_mask"] = [mask_id, 0]

            workflow[ipadapter_id] = {
                "inputs": ipadapter_inputs,
                "class_type": "IPAdapter",
            }

            prev_model_ref = [ipadapter_id, 0]

        # 最后一个IPAdapter输出 → KSampler
        if "8" in workflow:
            workflow["8"]["inputs"]["model"] = prev_model_ref

        return workflow

    def create_reference_only_workflow(
        self,
        base_workflow: Dict[str, Any],
        character_id: str,
        reference_strength: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """
        创建带有Reference-only ControlNet的工作流

        使用ControlNet的reference-only模式来保持风格/角色一致
        不需要额外模型，但效果可能不如IP-Adapter

        Args:
            base_workflow: 基础工作流
            character_id: 角色ID
            reference_strength: 参考强度

        Returns:
            修改后的工作流
        """
        char = self._characters.get(character_id)
        if not char or not char.reference_images:
            return None

        workflow = copy.deepcopy(base_workflow)
        ref_image = char.reference_images[0]

        # Reference-only作为额外的ControlNet
        ref_nodes = {
            "110": {
                "inputs": {"image": ref_image},
                "class_type": "LoadImage"
            },
            "111": {
                "inputs": {
                    "control_net_name": "control_v11p_sd15_inpaint.pth"  # 使用inpaint模型作为reference
                },
                "class_type": "ControlNetLoader"
            },
            "112": {
                "inputs": {
                    "strength": reference_strength,
                    "conditioning": ["2", 0],  # 正向提示词
                    "control_net": ["111", 0],
                    "image": ["110", 0]
                },
                "class_type": "ControlNetApply"
            }
        }

        workflow.update(ref_nodes)

        # 更新后续节点使用reference conditioning
        # 如果有depth ControlNet，需要链式连接
        if "7" in workflow:  # depth controlnet apply
            workflow["7"]["inputs"]["conditioning"] = ["112", 0]
        else:
            workflow["8"]["inputs"]["positive"] = ["112", 0]

        return workflow

    def apply_consistency_to_workflow(
        self,
        workflow: Dict[str, Any],
        character_id: str,
        method: ConsistencyMethod = ConsistencyMethod.FIXED_SEED,
        **kwargs
    ) -> Dict[str, Any]:
        """
        应用一致性控制到工作流

        Args:
            workflow: 基础工作流
            character_id: 角色ID
            method: 一致性方法
            **kwargs: 方法特定参数

        Returns:
            修改后的工作流
        """
        char = self._characters.get(character_id)
        if not char:
            return workflow

        result = copy.deepcopy(workflow)

        if method == ConsistencyMethod.FIXED_SEED:
            # 使用固定种子
            seed = char.seed if char.seed is not None else 42
            if "8" in result:  # KSampler
                result["8"]["inputs"]["seed"] = seed

        elif method == ConsistencyMethod.IP_ADAPTER:
            ip_workflow = self.create_ipadapter_workflow(
                result, character_id,
                ipadapter_strength=kwargs.get("ipadapter_strength", 0.6),
                attention_mask_path=kwargs.get("attention_mask_path"),
            )
            if ip_workflow:
                result = ip_workflow

        elif method == ConsistencyMethod.REFERENCE_ONLY:
            ref_workflow = self.create_reference_only_workflow(
                result, character_id,
                kwargs.get("reference_strength", 1.0)
            )
            if ref_workflow:
                result = ref_workflow

        return result


class MultiViewGenerator:
    """
    多视角生成器

    专门用于从同一场景生成多个视角的图像，同时保持结构和角色一致
    """

    def __init__(
        self,
        scene_cache: Any,
        character_manager: CharacterConsistencyManager,
        comfy_client: Any,
        output_dir: str = "./data/outputs"
    ):
        self.scene_cache = scene_cache
        self.character_manager = character_manager
        self.comfy_client = comfy_client
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_views(
        self,
        base_shot: Dict[str, Any],
        views: List[str],
        consistency_method: ConsistencyMethod = ConsistencyMethod.FIXED_SEED,
        output_prefix: str = "view",
        character_reference_image: Optional[str] = None,
        generate_reference: bool = True
    ) -> Dict[str, Any]:
        """
        为同一场景生成多个视角，保持角色一致性

        Args:
            base_shot: 基础shot定义（包含默认视角）
            views: 视角列表，如["side", "top", "front"]
            consistency_method: 一致性方法
            output_prefix: 输出文件名前缀
            character_reference_image: 外部传入的角色参考图路径（干净背景下的角色）
            generate_reference: 是否自动生成角色参考图（当未提供外部参考图时）

        Returns:
            生成结果字典
        """
        results = {
            "views": {},
            "reference_image": None,  # 干净背景的角色参考图
            "character_id": None
        }

        # 识别/注册角色
        char_id = self.character_manager.extract_character_from_shot(base_shot)
        if char_id:
            results["character_id"] = char_id
            char = self.character_manager.get_character(char_id)
            if not char:
                # 自动注册新角色
                self.character_manager.register_character(
                    character_id=char_id,
                    description=self._generate_character_description(base_shot),
                    seed=42
                )

        # 确定角色参考图
        reference_image = character_reference_image

        # 如果没有外部参考图且需要自动生成
        if not reference_image and generate_reference and char_id:
            print("Generating character reference image (clean background)...")
            reference_image = self._generate_character_reference(
                char_id, base_shot, consistency_method, output_prefix
            )

        if reference_image:
            results["reference_image"] = reference_image

            # 如果使用IP-Adapter，设置参考图
            if consistency_method == ConsistencyMethod.IP_ADAPTER and char_id:
                char = self.character_manager.get_character(char_id)
                if char:
                    char.reference_images = [reference_image]
                    self.character_manager._save_character(char)

        # 生成所有场景视角（使用角色参考图保持一致性）
        for view in views:
            print(f"Generating scene view: {view}")
            view_shot = copy.deepcopy(base_shot)
            view_shot["camera"] = {"view": view}

            result = self._generate_single_view(
                view_shot, consistency_method, char_id,
                f"{output_prefix}_{view}.png",
                character_reference=reference_image
            )
            results["views"][view] = result

        return results

    def _generate_character_reference(
        self,
        character_id: str,
        base_shot: Dict[str, Any],
        consistency_method: ConsistencyMethod,
        output_prefix: str
    ) -> Optional[str]:
        """
        生成干净背景下的角色参考图

        创建一个白底的shot，只包含角色，用于后续场景生成的一致性控制
        """
        # 创建干净背景的shot（只有角色，无其他物体）
        reference_shot = copy.deepcopy(base_shot)

        # 只保留角色类型的对象
        character_types = ["child", "adult", "boy", "girl", "man", "woman"]
        character_objects = [
            obj for obj in reference_shot.get("objects", [])
            if obj.get("type", "").lower() in character_types
        ]

        if not character_objects:
            print("Warning: No character found in shot, cannot generate reference")
            return None

        # 简化为单个人物，白底场景
        reference_shot["objects"] = character_objects
        reference_shot["template"] = "white_background"  # 假设有白底模板
        reference_shot["lighting"] = {
            "type": "studio",
            "background": "#FFFFFF"
        }

        # 使用正面视角
        reference_shot["camera"] = {"view": "front"}

        # 生成参考图
        result = self._generate_single_view(
            reference_shot,
            consistency_method,
            character_id,
            f"{output_prefix}_character_reference.png",
            is_reference=True
        )

        return result.get("image_path") if result else None

    def _generate_single_view(
        self,
        shot: Dict[str, Any],
        method: ConsistencyMethod,
        character_id: Optional[str],
        output_name: str,
        character_reference: Optional[str] = None,
        is_reference: bool = False
    ) -> Dict[str, Any]:
        """
        生成单个视角的图像

        Args:
            shot: shot定义（包含template, objects, camera等）
            method: 一致性方法
            character_id: 角色ID
            output_name: 输出文件名
            character_reference: 角色参考图路径（用于IP-Adapter等）
            is_reference: 是否正在生成参考图

        Returns:
            包含生成结果的字典
        """
        result = {
            "shot": shot,
            "output_name": output_name,
            "image_path": None,
            "is_reference": is_reference
        }

        try:
            # 1. 构建场景
            from ..scene.scene_builder import build_scene_from_json

            # 生成场景数据
            scene_data = build_scene_from_json(shot)

            # 2. 加载工作流
            workflow_loader = self._get_workflow_loader()
            workflow = workflow_loader.load_for_scene(scene_data)

            if not workflow:
                print(f"  Failed to load workflow for {output_name}")
                return result

            # 3. 应用角色一致性
            if character_id and character_reference:
                # 应用IP-Adapter或Reference-only
                workflow = self.character_manager.apply_consistency_to_workflow(
                    workflow,
                    character_id,
                    method=method,
                    ipadapter_strength=0.6 if method == ConsistencyMethod.IP_ADAPTER else None
                )

            # 4. 生成图像
            output_path = self.output_dir / output_name

            if self.comfy_client:
                filename = self.comfy_client.generate(workflow, timeout=300)
                if filename:
                    if self.comfy_client.save_image(str(filename), str(output_path)):
                        result["image_path"] = str(output_path)
                        print(f"  Generated: {output_path}")
                    else:
                        print(f"  Failed to save image: {output_name}")
                else:
                    print(f"  Generation failed for: {output_name}")
            else:
                # 无comfy_client时的mock实现（用于测试）
                print(f"  [Mock] Would generate: {output_name}")
                result["image_path"] = str(output_path)

        except Exception as e:
            print(f"  Error generating {output_name}: {e}")
            import traceback
            traceback.print_exc()

        return result

    def _get_workflow_loader(self):
        """获取工作流加载器"""
        from ..comfy.workflow_loader import WorkflowLoader
        return WorkflowLoader()

    def _generate_character_description(self, shot: Dict[str, Any]) -> str:
        """从shot生成角色描述"""
        objects = shot.get("objects", [])
        for obj in objects:
            obj_type = obj.get("type", "").lower()
            if obj_type in ["child", "adult", "boy", "girl"]:
                # 可以在这里添加更多特征提取逻辑
                return f"{obj_type}, consistent appearance"
        return "consistent character appearance"


def add_character_consistency_to_prompt(
    prompt: str,
    character_description: str
) -> str:
    """
    简单工具函数：在prompt中添加角色一致性描述

    如果无法使用IP-Adapter等高级功能，可以用这个方法增强prompt
    """
    consistency_tags = [
        character_description,
        "same character",
        "consistent facial features",
        "consistent clothing",
        "consistent hairstyle"
    ]

    # 检查是否已经在prompt中
    existing_lower = prompt.lower()
    new_tags = [tag for tag in consistency_tags if tag.lower() not in existing_lower]

    if new_tags:
        prompt = prompt.rstrip(", ") + ", " + ", ".join(new_tags)

    return prompt
