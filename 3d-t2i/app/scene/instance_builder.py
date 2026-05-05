"""
SceneInstanceBuilder - 将SceneBlueprint转换为SceneInstance

核心功能：
1. 解析Blueprint中的关系，计算实际3D位置
2. 确定性构建：相同Blueprint总是生成相同的Instance布局
3. 支持样式绑定和角色绑定

使用示例：
    blueprint = SceneBlueprint(...)
    builder = SceneInstanceBuilder(blueprint)
    instance = builder.build_instance(
        style_id="storybook_warm_v1",
        character_bindings={"child_1": "char_001"}
    )
"""
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

from ..schema.scene_hierarchy import (
    SceneBlueprint, BlueprintObject, SceneInstance,
    InstanceObject, CharacterBinding
)
from .object_library import get_object_def
from .templates import get_template
import math


class InstanceBuilder:
    """
    SceneInstance构建器

    构建流程：
    1. 加载模板（地面、基础环境）
    2. 按依赖顺序解析对象（先独立对象，后关联对象）
    3. 计算每个对象的实际位置（确定性算法）
    4. 应用样式和角色绑定
    """

    def __init__(self, blueprint: SceneBlueprint):
        self.blueprint = blueprint
        self.template = get_template(blueprint.template)

        # 构建过程中的临时存储
        self._built_objects: Dict[str, InstanceObject] = {}
        self._object_positions: Dict[str, Tuple[float, float, float]] = {}

    def build_instance(
        self,
        style_id: str = "default",
        character_bindings: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SceneInstance:
        """
        构建SceneInstance

        Args:
            style_id: 样式标识（如"storybook_warm_v1"）
            character_bindings: 角色绑定 {object_id: character_id}
            metadata: 额外元数据

        Returns:
            构建好的SceneInstance
        """
        # 1. 构建基础元素（地面等）
        self._build_base_elements()

        # 2. 分离独立对象和关联对象
        independent = []
        related = []

        for obj in self.blueprint.objects:
            if obj.relation:
                related.append(obj)
            else:
                independent.append(obj)

        # 3. 构建独立对象
        for obj in independent:
            self._build_independent_object(obj)

        # 4. 按依赖顺序构建关联对象
        self._build_related_objects_in_order(related)

        # 5. 创建Instance
        instance = SceneInstance(
            blueprint_id=self.blueprint.blueprint_id,
            instance_id=f"inst_{self.blueprint.blueprint_id}_{style_id}",
            template=self.blueprint.template,
            objects=list(self._built_objects.values()),
            style_id=style_id,
            metadata=metadata or self.blueprint.metadata
        )

        # 6. 应用角色绑定
        if character_bindings:
            self._apply_character_bindings(instance, character_bindings)

        return instance

    # 模板几何类型到标准几何类型的映射
    GEOMETRY_TYPE_MAP = {
        "floor": "box",
        "ground": "box",
        "water": "box",
        "wall": "box",
        "box": "box",
        "plane": "plane",
        "sphere": "sphere",
        "cylinder": "cylinder",
    }

    def _map_geometry_type(self, template_type: str) -> str:
        """将模板类型映射为标准几何类型"""
        return self.GEOMETRY_TYPE_MAP.get(template_type, "box")

    def _build_base_elements(self):
        """构建模板基础元素"""
        if not self.template:
            return

        for elem in self.template.base_elements:
            # 映射几何类型以确保前端能正确渲染
            geom_type = self._map_geometry_type(elem["type"])

            obj = InstanceObject(
                id=elem["id"],
                type=geom_type,  # 使用映射后的类型
                position=tuple(elem["position"]),
                rotation=(0, 0, 0),
                scale=tuple(elem["size"]),
                color=elem["color"]
            )
            self._built_objects[obj.id] = obj
            self._object_positions[obj.id] = obj.position

    def _build_independent_object(self, blueprint_obj: BlueprintObject):
        """构建独立对象（无relation）"""
        obj_def = get_object_def(blueprint_obj.type)
        if not obj_def:
            print(f"Warning: Unknown object type '{blueprint_obj.type}'")
            return

        # 独立对象放在地面中心或指定位置
        # 使用对象ID哈希来确定位置偏移，确保确定性
        position = self._calculate_independent_position(blueprint_obj)

        # 估算rotation: 基于物体类型和描述
        rotation = self._estimate_rotation(blueprint_obj, obj_def, None)

        obj = InstanceObject(
            id=blueprint_obj.id,
            type=blueprint_obj.type,
            position=position,
            rotation=rotation,
            scale=obj_def.size,
            color=obj_def.color
        )

        self._built_objects[obj.id] = obj
        self._object_positions[obj.id] = position

    def _build_related_objects_in_order(self, related_objects: List[BlueprintObject]):
        """按依赖顺序构建关联对象"""
        remaining = related_objects[:]
        max_iterations = len(related_objects) * 2
        iteration = 0

        while remaining and iteration < max_iterations:
            iteration += 1
            still_remaining = []

            for obj in remaining:
                target_id = self._extract_target_id(obj.relation)

                if target_id and target_id in self._built_objects:
                    self._build_related_object(obj)
                else:
                    still_remaining.append(obj)

            if len(still_remaining) == len(remaining):
                # 无法解析的依赖，强制构建
                print(f"Warning: Could not resolve relations for {[o.id for o in remaining]}")
                for obj in remaining:
                    self._build_independent_object(obj)
                break

            remaining = still_remaining

    def _build_related_object(self, blueprint_obj: BlueprintObject):
        """构建有关联的对象"""
        obj_def = get_object_def(blueprint_obj.type)
        if not obj_def:
            print(f"Warning: Unknown object type '{blueprint_obj.type}'")
            return

        # 解析relation
        rel_type, target_id = self._parse_relation(blueprint_obj.relation)
        target_obj = self._built_objects.get(target_id)

        if not target_obj:
            # 降级为独立对象
            self._build_independent_object(blueprint_obj)
            return

        # 计算相对位置
        position = self._calculate_relative_position(
            blueprint_obj, obj_def.size, rel_type, target_obj
        )

        # 估算rotation，传入relation类型
        rotation = self._estimate_rotation(blueprint_obj, obj_def, rel_type)

        obj = InstanceObject(
            id=blueprint_obj.id,
            type=blueprint_obj.type,
            position=position,
            rotation=rotation,
            scale=obj_def.size,
            color=obj_def.color,
            parent=target_id
        )

        self._built_objects[obj.id] = obj
        self._object_positions[obj.id] = position

    def _calculate_independent_position(self, blueprint_obj: BlueprintObject) -> Tuple[float, float, float]:
        """
        计算独立对象的位置

        使用确定性算法，基于对象ID和场景内容
        根据模板边界动态调整分布范围
        """
        # 获取模板锚点和边界
        anchor = self.template.anchor_points.get("center", (0, 0, 0)) if self.template else (0, 0, 0)
        boundary = self.template.boundary if self.template else {}

        # 计算边界范围
        min_x, max_x = boundary.get("min_x", -4), boundary.get("max_x", 4)
        min_z, max_z = boundary.get("min_z", -4), boundary.get("max_z", 4)
        min_y = boundary.get("min_y", 0)

        x_range = max_x - min_x
        z_range = max_z - min_z

        # 使用对象ID哈希来确定偏移，确保相同ID总是相同位置
        id_hash = hashlib.md5(blueprint_obj.id.encode()).hexdigest()
        hash_int = int(id_hash[:8], 16)

        # 在边界范围内均匀分布（使用20%-40%的边界范围）
        radius_ratio = 0.2 + (hash_int % 20) / 100  # 0.2 - 0.4
        x_offset = x_range * radius_ratio * (hash_int % 2 * 2 - 1)  # 左或右
        z_offset = z_range * radius_ratio * ((hash_int // 2) % 2 * 2 - 1)  # 前或后

        # 边界约束
        x = max(min_x, min(max_x, anchor[0] + x_offset))
        z = max(min_z, min(max_z, anchor[2] + z_offset))

        return (x, min_y, z)

    def _estimate_rotation(
        self,
        blueprint_obj: BlueprintObject,
        obj_def: Any,
        rel_type: Optional[str]
    ) -> Tuple[float, float, float]:
        """
        估算物体的rotation值

        基于:
        1. 物体类型 (不同物体有不同默认朝向)
        2. relation类型 (如on_top_of通常需要调整)
        3. description描述 (如"打开的书"、"靠在墙上的梯子")

        Returns:
            (rx, ry, rz) 欧拉角，单位：弧度
        """
        rotation = [0.0, 0.0, 0.0]
        desc = (blueprint_obj.description or "").lower()

        # =====================
        # 1. 基于物体类型的默认朝向
        # =====================
        if blueprint_obj.type == "book":
            # 书的特殊处理
            if "打开" in desc or "翻开" in desc or "open" in desc:
                # 打开的书，封面朝上翻开
                rotation = [0, 0, 0]  # 平放
            elif "立" in desc or "竖" in desc or "stand" in desc or "upright" in desc:
                # 立起来的书（书架上的书）
                rotation = [-math.pi / 2, 0, 0]  # -90度绕X轴，封面朝前
            elif "倒" in desc or "倒放" in desc or "upside down" in desc:
                # 倒放的书，封面朝下
                rotation = [math.pi, 0, 0]  # 180度，封面朝下
            elif "斜" in desc or "倾斜" in desc or "tilt" in desc:
                # 倾斜的书
                rotation = [-math.pi / 6, 0, 0]  # -30度倾斜
            else:
                # 默认：平放在桌面上
                rotation = [0, 0, 0]

        elif blueprint_obj.type in ["flowerpot", "lamp"]:
            # 花盆和台灯默认直立
            if "倒" in desc or "倒放" in desc:
                rotation = [math.pi, 0, 0]
            elif "斜" in desc or "倾斜" in desc:
                rotation = [-math.pi / 8, 0, 0]

        elif blueprint_obj.type in ["child", "adult"]:
            # 人物默认直立
            if "躺" in desc or "躺卧" in desc or "lie" in desc or "laying" in desc:
                rotation = [-math.pi / 2, 0, 0]  # 平躺
            elif "坐" in desc or "坐下" in desc or "sit" in desc:
                # 坐着，保持直立但需要调整高度（在构建时处理）
                rotation = [0, 0, 0]

        # =====================
        # 2. 基于relation的调整
        # =====================
        if rel_type == "on_top_of":
            # 放在...上面
            if blueprint_obj.type == "book":
                # 书放在桌子上，默认平放 (cover朝上)
                # 如果描述中没有特殊说明，保持平放
                if not any(kw in desc for kw in ["立", "竖", "stand", "upright"]):
                    rotation = [0, 0, 0]

        elif rel_type == "beside":
            # 在旁边，通常保持默认朝向
            pass

        elif rel_type in ["in_front_of", "behind"]:
            # 前后位置，可能需要调整Y轴朝向
            # 使用哈希确保确定性
            hash_val = hash(blueprint_obj.id)
            rotation[1] = (hash_val % 360) * math.pi / 180

        # =====================
        # 3. 基于描述的特殊处理
        # =====================
        if "面向左" in desc or "facing left" in desc:
            rotation[1] = -math.pi / 2
        elif "面向右" in desc or "facing right" in desc:
            rotation[1] = math.pi / 2
        elif "面向后" in desc or "背对" in desc or "facing back" in desc:
            rotation[1] = math.pi

        return tuple(rotation)

    def _calculate_relative_position(
        self,
        blueprint_obj: BlueprintObject,
        obj_size: Tuple[float, float, float],
        rel_type: str,
        target_obj: InstanceObject
    ) -> Tuple[float, float, float]:
        """
        计算关联对象的相对位置

        确定性计算，相同输入总是返回相同输出
        """
        target_pos = target_obj.position
        target_size = target_obj.scale

        if rel_type == "on_top_of":
            # 放在目标上面
            target_top = target_pos[1] + target_size[1]
            return (target_pos[0], target_top, target_pos[2])

        elif rel_type == "beside":
            # 在旁边 - 使用对象ID哈希确定左右
            offset = target_size[0] * 0.8
            direction = 1 if hash(blueprint_obj.id) % 2 == 0 else -1
            return (
                target_pos[0] + offset * direction,
                target_pos[1],
                target_pos[2]
            )

        elif rel_type == "beside_left":
            offset = target_size[0] * 0.8
            return (target_pos[0] - offset, target_pos[1], target_pos[2])

        elif rel_type == "beside_right":
            offset = target_size[0] * 0.8
            return (target_pos[0] + offset, target_pos[1], target_pos[2])

        elif rel_type == "in_front_of":
            offset = target_size[2] * 0.8
            return (target_pos[0], target_pos[1], target_pos[2] + offset)

        elif rel_type == "behind":
            offset = target_size[2] * 0.8
            return (target_pos[0], target_pos[1], target_pos[2] - offset)

        elif rel_type == "inside":
            return (target_pos[0], target_pos[1] + 0.1, target_pos[2])

        elif rel_type == "near":
            # 附近 - 较远的位置
            id_hash = hash(blueprint_obj.id)
            distance = target_size[0] * 2.0
            return (
                target_pos[0] + distance * (id_hash % 2 * 2 - 1),
                target_pos[1],
                target_pos[2] + distance * ((id_hash // 2) % 2 * 2 - 1)
            )

        else:
            # 默认
            return (target_pos[0] + target_size[0], target_pos[1], target_pos[2])

    def _parse_relation(self, relation: str) -> Tuple[str, str]:
        """解析relation字符串"""
        parts = relation.split(":")
        if len(parts) != 2:
            return ("beside", "")
        return (parts[0], parts[1])

    def _extract_target_id(self, relation: str) -> Optional[str]:
        """从relation中提取目标ID"""
        parts = relation.split(":")
        if len(parts) == 2:
            return parts[1]
        return None

    def _apply_character_bindings(
        self,
        instance: SceneInstance,
        bindings: Dict[str, str]
    ):
        """应用角色绑定到Instance"""
        for object_id, character_id in bindings.items():
            obj = instance.get_object_by_id(object_id)
            if obj and obj.type in ["child", "adult", "boy", "girl", "man", "woman"]:
                binding = CharacterBinding(
                    object_id=object_id,
                    character_id=character_id,
                    character_description=f"Character {character_id}",
                    reference_images=[]
                )
                instance.character_bindings[object_id] = binding


class InstanceCache:
    """
    Instance缓存管理器

    基于Blueprint ID + Style ID缓存Instance
    """

    def __init__(self, cache_dir: str = "./data/cache/instances"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, SceneInstance] = {}

    def _get_cache_key(self, blueprint_id: str, style_id: str) -> str:
        """生成缓存key"""
        return f"{blueprint_id}_{style_id}"

    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.json"

    def get_cached_instance(
        self,
        blueprint_id: str,
        style_id: str
    ) -> Optional[SceneInstance]:
        """获取缓存的Instance"""
        cache_key = self._get_cache_key(blueprint_id, style_id)

        # 先检查内存
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]

        # 再检查磁盘
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                instance = SceneInstance.from_dict(data)
                self._memory_cache[cache_key] = instance
                return instance
            except Exception as e:
                print(f"Failed to load instance cache: {e}")

        return None

    def save_instance(
        self,
        instance: SceneInstance
    ):
        """保存Instance到缓存"""
        cache_key = self._get_cache_key(instance.blueprint_id, instance.style_id)

        # 保存到内存
        self._memory_cache[cache_key] = instance

        # 保存到磁盘
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(instance.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save instance cache: {e}")

    def get_or_build_instance(
        self,
        blueprint: SceneBlueprint,
        style_id: str = "default",
        character_bindings: Optional[Dict[str, str]] = None,
        force_rebuild: bool = False
    ) -> SceneInstance:
        """
        获取或构建Instance

        如果缓存存在且force_rebuild=False，返回缓存
        否则构建新的Instance
        """
        if not force_rebuild:
            cached = self.get_cached_instance(blueprint.blueprint_id, style_id)
            if cached:
                print(f"Instance cache HIT: {blueprint.blueprint_id} + {style_id}")
                return cached

        print(f"Instance cache MISS: {blueprint.blueprint_id} + {style_id}")
        builder = InstanceBuilder(blueprint)
        instance = builder.build_instance(
            style_id=style_id,
            character_bindings=character_bindings
        )
        self.save_instance(instance)
        return instance

    def get_instance_by_id(self, instance_id: str) -> Optional[SceneInstance]:
        """
        通过instance_id获取Instance

        遍历所有缓存查找匹配的instance_id
        """
        # 先检查内存缓存
        for instance in self._memory_cache.values():
            if instance.instance_id == instance_id:
                return instance

        # 再检查磁盘缓存
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get("instance_id") == instance_id:
                    instance = SceneInstance.from_dict(data)
                    # 加载到内存缓存
                    cache_key = self._get_cache_key(instance.blueprint_id, instance.style_id)
                    self._memory_cache[cache_key] = instance
                    return instance
            except Exception:
                continue

        return None

    def clear_cache(self):
        """清除所有缓存"""
        self._memory_cache.clear()
        for f in self.cache_dir.glob("*.json"):
            f.unlink()


def build_instance_from_shot_json(
    shot_json: Dict[str, Any],
    style_id: str = "default",
    cache: Optional[InstanceCache] = None
) -> SceneInstance:
    """
    从旧的Shot JSON格式构建Instance

    兼容层函数，用于过渡期间
    """
    blueprint = SceneBlueprint.from_shot_json(shot_json)

    if cache is None:
        cache = InstanceCache()

    # 提取角色绑定
    character_bindings = {}
    for obj in shot_json.get("objects", []):
        obj_type = obj.get("type", "")
        if obj_type in ["child", "adult", "boy", "girl", "man", "woman"]:
            # 基于对象类型和场景生成角色ID
            char_id = f"char_{obj_type}_{blueprint.blueprint_id[:8]}"
            character_bindings[obj["id"]] = char_id

    return cache.get_or_build_instance(
        blueprint,
        style_id=style_id,
        character_bindings=character_bindings
    )
