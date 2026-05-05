"""
场景分层架构数据模型

三层结构：
1. SceneBlueprint - 场景语义模板（对象类型和关系）
2. SceneInstance - 实际落位后的场景（具体坐标、样式绑定）
3. Shot - 镜头（只包含相机信息，引用SceneInstance）

使用示例：
    # 创建Blueprint
    blueprint = SceneBlueprint(
        template="indoor_room",
        objects=[
            BlueprintObject(id="child_1", type="child"),
            BlueprintObject(id="table_1", type="table"),
            BlueprintObject(id="flowerpot_1", type="flowerpot", relation="on_top_of:table_1")
        ]
    )

    # 构建Instance（实际落位）
    builder = SceneInstanceBuilder(blueprint)
    instance = builder.build_instance(style_id="storybook_warm_v1")

    # 创建不同视角的Shots
    shot_side = Shot(scene_id=instance.instance_id, camera=CameraConfig(view="side"))
    shot_top = Shot(scene_id=instance.instance_id, camera=CameraConfig(view="top"))
"""
import json
import hashlib
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from copy import deepcopy


# =============================================================================
# Layer 1: Scene Blueprint - 语义模板层
# =============================================================================

@dataclass
class BlueprintObject:
    """
    Blueprint中的对象定义 - 只包含语义信息，不包含具体位置

    Attributes:
        id: 对象唯一标识
        type: 对象类型（如"child", "table"）
        relation: 关系描述（如"on_top_of:table_1", "beside:child_1"）
        attributes: 额外属性（如{"color": "red"}）
        description: 对象描述/提示词，用于判断rotation等属性
            例如: "一本打开的书", "靠在墙上的梯子", "倒在地上的花瓶"
    """
    id: str
    type: str
    relation: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "relation": self.relation,
            "attributes": self.attributes,
            "description": self.description
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlueprintObject":
        return cls(
            id=data["id"],
            type=data["type"],
            relation=data.get("relation"),
            attributes=data.get("attributes", {}),
            description=data.get("description")
        )


@dataclass
class SceneBlueprint:
    """
    场景蓝图 - 纯语义描述，不含任何空间信息

    这是缓存的关键：相同Blueprint应该生成相同的SceneInstance结构
    """
    template: str
    objects: List[BlueprintObject]
    blueprint_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.blueprint_id is None:
            self.blueprint_id = self.compute_hash()

    def compute_hash(self) -> str:
        """计算蓝图哈希 - 用于缓存匹配"""
        content = {
            "template": self.template,
            "objects": sorted([
                {"id": obj.id, "type": obj.type, "relation": obj.relation}
                for obj in self.objects
            ], key=lambda x: x["id"])
        }
        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content_str.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "template": self.template,
            "objects": [obj.to_dict() for obj in self.objects],
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneBlueprint":
        blueprint = cls(
            blueprint_id=data.get("blueprint_id"),
            template=data["template"],
            objects=[BlueprintObject.from_dict(o) for o in data["objects"]],
            metadata=data.get("metadata", {})
        )
        return blueprint

    @classmethod
    def from_shot_json(cls, shot_json: Dict[str, Any]) -> "SceneBlueprint":
        """从旧的Shot JSON格式创建Blueprint"""
        objects = []
        for obj_def in shot_json.get("objects", []):
            obj = BlueprintObject(
                id=obj_def["id"],
                type=obj_def["type"],
                relation=obj_def.get("relation"),
                attributes={k: v for k, v in obj_def.items()
                           if k not in ["id", "type", "relation", "position", "scale", "rotation"]}
            )
            objects.append(obj)

        return cls(
            template=shot_json.get("template", "indoor_room"),
            objects=objects,
            metadata={
                "style_prompt": shot_json.get("style_prompt", ""),
                "lighting": shot_json.get("lighting", {})
            }
        )


# =============================================================================
# Layer 2: Scene Instance - 实际落位层
# =============================================================================

@dataclass
class InstanceObject:
    """
    Instance中的对象 - 包含实际3D坐标

    Attributes:
        id: 对象ID（继承自Blueprint）
        type: 对象类型
        position: 3D位置 (x, y, z)
        rotation: 旋转 (rx, ry, rz)
        scale: 缩放 (sx, sy, sz)
        color: 颜色
        parent: 父对象ID（如果有）
    """
    id: str
    type: str
    position: Tuple[float, float, float]
    rotation: Tuple[float, float, float]
    scale: Tuple[float, float, float]
    color: str
    parent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "color": self.color,
            "parent": self.parent
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstanceObject":
        return cls(
            id=data["id"],
            type=data["type"],
            position=tuple(data["position"]),
            rotation=tuple(data["rotation"]),
            scale=tuple(data["scale"]),
            color=data["color"],
            parent=data.get("parent")
        )


@dataclass
class CharacterBinding:
    """角色绑定 - 将Instance中的对象与全局角色关联"""
    object_id: str
    character_id: str
    character_description: str
    reference_images: List[str] = field(default_factory=list)


@dataclass
class SceneInstance:
    """
    场景实例 - 包含实际3D布局和样式绑定

    这是可复用的核心资产：
    - 多个Shots可以引用同一个Instance
    - 角色绑定在Instance层，确保多视角一致
    - 样式在Instance层定义
    """
    blueprint_id: str
    instance_id: str
    template: str
    objects: List[InstanceObject]
    style_id: str
    character_bindings: Dict[str, CharacterBinding] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        """确保每个Instance有唯一ID"""
        if not self.instance_id:
            self.instance_id = f"inst_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "instance_id": self.instance_id,
            "template": self.template,
            "objects": [obj.to_dict() for obj in self.objects],
            "style_id": self.style_id,
            "character_bindings": {
                k: {
                    "object_id": v.object_id,
                    "character_id": v.character_id,
                    "character_description": v.character_description,
                    "reference_images": v.reference_images
                }
                for k, v in self.character_bindings.items()
            },
            "metadata": self.metadata,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneInstance":
        bindings = {}
        for k, v in data.get("character_bindings", {}).items():
            bindings[k] = CharacterBinding(
                object_id=v["object_id"],
                character_id=v["character_id"],
                character_description=v["character_description"],
                reference_images=v.get("reference_images", [])
            )

        return cls(
            blueprint_id=data["blueprint_id"],
            instance_id=data.get("instance_id", f"inst_{uuid.uuid4().hex[:8]}"),
            template=data["template"],
            objects=[InstanceObject.from_dict(o) for o in data["objects"]],
            style_id=data.get("style_id", "default"),
            character_bindings=bindings,
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", "")
        )

    def get_object_by_id(self, object_id: str) -> Optional[InstanceObject]:
        """通过ID获取对象"""
        for obj in self.objects:
            if obj.id == object_id:
                return obj
        return None

    def to_threejs_scene(self) -> Dict[str, Any]:
        """转换为Three.js可用的场景格式"""
        objects_export = []
        for obj in self.objects:
            # 转换底部中心点到几何中心
            geometry_type = self._get_geometry_type(obj.type)
            if geometry_type in ["box", "cylinder"]:
                render_position = (
                    obj.position[0],
                    obj.position[1] + obj.scale[1] / 2,
                    obj.position[2]
                )
            else:
                render_position = obj.position

            objects_export.append({
                "id": obj.id,
                "type": geometry_type,
                "object_type": obj.type,
                "position": list(render_position),
                "size": list(obj.scale),
                "rotation": list(obj.rotation),
                "color": obj.color
            })

        return {
            "template": self.template,
            "objects": objects_export,
            "blueprint_id": self.blueprint_id,
            "instance_id": self.instance_id
        }

    def _get_geometry_type(self, object_type: str) -> str:
        """获取几何体类型 - 将语义类型映射到 Three.js 几何类型"""
        type_map = {
            # 人物
            "child": "box",
            "adult": "box",
            "boy": "box",
            "girl": "box",
            "man": "box",
            "woman": "box",
            # 家具
            "table": "box",
            "chair": "box",
            "lamp": "cylinder",
            "book": "box",
            # 装饰
            "flowerpot": "cylinder",
            # 环境 - 地面/水面使用 plane
            "floor": "plane",
            "ground": "plane",
            "road": "plane",
            "sidewalk": "plane",
            "water": "plane",
            "river": "plane",
            # 建筑
            "wall": "plane",
            "building": "box",
            "tree": "cylinder",
            "car": "box",
            "bridge": "box",
        }
        # 默认返回 box，避免未知类型出错
        return type_map.get(object_type, "box")


# =============================================================================
# Layer 3: Shot - 镜头层
# =============================================================================

@dataclass
class CameraConfig:
    """相机配置"""
    view: str = "side"  # front, side, top, three_quarter, etc.
    position: Optional[Tuple[float, float, float]] = None
    target: Tuple[float, float, float] = (0, 1, 0)
    fov: float = 50
    pitch: float = 0  # 俯仰角
    yaw: float = 0    # 偏航角
    distance: float = 8.0  # 距离中心点的距离

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view": self.view,
            "position": list(self.position) if self.position else None,
            "target": list(self.target),
            "fov": self.fov,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "distance": self.distance
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraConfig":
        pos = data.get("position")
        return cls(
            view=data.get("view", "side"),
            position=tuple(pos) if pos else None,
            target=tuple(data.get("target", [0, 1, 0])),
            fov=data.get("fov", 50),
            pitch=data.get("pitch", 0),
            yaw=data.get("yaw", 0),
            distance=data.get("distance", 8.0)
        )

    def compute_position_from_angles(self, target: Tuple[float, float, float] = None) -> Tuple[float, float, float]:
        """从角度和距离计算相机位置"""
        import math

        tgt = target or self.target

        # 将角度转换为弧度
        pitch_rad = math.radians(self.pitch)
        yaw_rad = math.radians(self.yaw)

        # 计算相机相对位置
        dx = self.distance * math.cos(pitch_rad) * math.sin(yaw_rad)
        dy = self.distance * math.sin(pitch_rad)
        dz = self.distance * math.cos(pitch_rad) * math.cos(yaw_rad)

        return (
            tgt[0] + dx,
            tgt[1] + dy,
            tgt[2] + dz
        )


@dataclass
class Shot:
    """
    镜头定义 - 只包含相机信息，引用SceneInstance

    这是最小生成单元：
    - 不同Shots可以共享同一个Instance
    - 只改变相机，不改变场景内容
    """
    scene_id: str
    camera: CameraConfig = field(default_factory=CameraConfig)
    shot_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.shot_id is None:
            self.shot_id = f"shot_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "scene_id": self.scene_id,
            "camera": self.camera.to_dict(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Shot":
        return cls(
            shot_id=data.get("shot_id"),
            scene_id=data["scene_id"],
            camera=CameraConfig.from_dict(data["camera"]),
            metadata=data.get("metadata", {})
        )

    def to_camera_config(self) -> Dict[str, Any]:
        """转换为旧的camera配置格式"""
        cam = self.camera

        # 如果有position直接使用，否则从角度计算
        if cam.position:
            pos = cam.position
        else:
            pos = cam.compute_position_from_angles()

        return {
            "view": cam.view,
            "position": list(pos),
            "target": list(cam.target),
            "fov": cam.fov
        }


# =============================================================================
# Helper Functions
# =============================================================================

def create_shot_from_text(
    scene_instance: SceneInstance,
    view_description: str
) -> Shot:
    """
    从文本描述创建Shot

    Args:
        scene_instance: 场景实例
        view_description: 视角描述（如"侧面", "俯视"）

    Returns:
        Shot对象
    """
    # 视角映射
    view_map = {
        "正面": "front",
        "侧面": "side",
        "俯视": "top",
        "四分之三": "three_quarter",
        "低角度": "low_angle",
        "高角度": "high_angle",
        "front": "front",
        "side": "side",
        "top": "top",
        "three_quarter": "three_quarter",
        "low_angle": "low_angle",
        "high_angle": "high_angle",
    }

    view = view_map.get(view_description, "side")

    # 预定义视角配置
    view_configs = {
        "front": {"pitch": 0, "yaw": 0, "distance": 8},
        "side": {"pitch": 0, "yaw": 90, "distance": 8},
        "top": {"pitch": 75, "yaw": 0, "distance": 12},
        "three_quarter": {"pitch": 10, "yaw": 45, "distance": 10},
        "low_angle": {"pitch": -15, "yaw": 45, "distance": 6},
        "high_angle": {"pitch": 30, "yaw": 45, "distance": 12},
    }

    config = view_configs.get(view, view_configs["side"])

    camera = CameraConfig(
        view=view,
        pitch=config["pitch"],
        yaw=config["yaw"],
        distance=config["distance"]
    )

    return Shot(
        scene_id=scene_instance.instance_id,
        camera=camera,
        metadata={"view_description": view_description}
    )
