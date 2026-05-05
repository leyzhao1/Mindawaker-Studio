"""
场景构建器 - 将 Shot JSON 转换为 Three.js 可用的场景数据
"""
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from .templates import get_template, SceneTemplate
from .object_library import get_object_def, ObjectDef


@dataclass
class SceneObject:
    """场景中的物体实例"""
    id: str
    type: str
    geometry_type: str
    position: Tuple[float, float, float]  # 底部中心点 (x, y_bottom, z)
    size: Tuple[float, float, float]
    rotation: Tuple[float, float, float]
    color: str
    parent: Optional[str] = None


@dataclass
class CameraConfig:
    """相机配置"""
    position: Tuple[float, float, float]
    target: Tuple[float, float, float]
    fov: float = 50


@dataclass
class SceneData:
    """完整的场景数据"""
    template: str
    objects: List[SceneObject]
    camera: CameraConfig
    lighting: Dict[str, Any]


class SceneBuilder:
    """场景构建器 - 改进版，支持完整的 relation 系统和底部中心点语义"""

    # 模板类型对应的位置偏移比例（相对于模板边界）
    # 室内场景用小偏移，室外场景用大偏移
    TEMPLATE_OFFSET_SCALES = {
        "indoor_room": 0.25,    # 室内：偏移为边界范围的 25%
        "street": 0.1,          # 街道：偏移为边界范围的 10%（但绝对值更大）
        "bridge_river": 0.15,   # 河边：偏移为边界范围的 15%
    }

    # 基础位置偏移（单位：比例，会根据模板缩放）
    BASE_POSITION_OFFSETS = {
        "left": (-1.0, 0, 0),
        "right": (1.0, 0, 0),
        "front": (0, 0, 1.0),
        "back": (0, 0, -1.0),
        "center": (0, 0, 0),
        "left_front": (-0.8, 0, 0.8),
        "right_front": (0.8, 0, 0.8),
        "left_back": (-0.8, 0, -0.8),
        "right_back": (0.8, 0, -0.8),
    }

    # 视角对应的相机位置（适合室内 10x10m 场景）
    VIEW_CAMERA_POSITIONS = {
        "front": (0, 2, 5),         # 前方 5m，高度 2m（平视）
        "side": (5, 2, 0),          # 侧面 5m
        "top": (0, 8, 0),           # 顶部俯视，高度 8m
        "three_quarter": (4, 3, 4), # 斜45度角
        "low_angle": (4, 0.5, 4),   # 低角度仰视
        "high_angle": (4, 6, 4),    # 高角度俯视
    }

    def __init__(self, shot_json: Dict[str, Any]):
        self.shot = shot_json
        self.template = get_template(shot_json.get("template", "indoor_room"))
        if not self.template:
            raise ValueError(f"Unknown template: {shot_json.get('template')}")

        # 用于存储已创建的对象引用（用于 relation 查找）
        self._created_objects: Dict[str, SceneObject] = {}

    def build(self) -> SceneData:
        """构建完整场景"""
        objects = self._build_base_elements()

        # 先构建独立对象（无 relation 的）
        shot_objects = self.shot.get("objects", [])
        independent_objects = [o for o in shot_objects if not o.get("relation")]
        related_objects = [o for o in shot_objects if o.get("relation")]

        # 创建独立对象
        for obj_def in independent_objects:
            scene_obj = self._create_object(obj_def)
            if scene_obj:
                objects.append(scene_obj)
                self._created_objects[scene_obj.id] = scene_obj

        # 创建有关联的对象（按依赖顺序）
        max_iterations = len(related_objects) * 2
        iteration = 0
        remaining = related_objects[:]

        while remaining and iteration < max_iterations:
            iteration += 1
            still_remaining = []

            for obj_def in remaining:
                relation = obj_def.get("relation", "")
                target_id = self._extract_target_id(relation)

                if target_id and target_id in self._created_objects:
                    scene_obj = self._create_object_with_relation(obj_def)
                    if scene_obj:
                        objects.append(scene_obj)
                        self._created_objects[scene_obj.id] = scene_obj
                else:
                    still_remaining.append(obj_def)

            if len(still_remaining) == len(remaining):
                # 无法继续解析，跳出
                print(f"Warning: Could not resolve relations for {len(remaining)} objects")
                break

            remaining = still_remaining

        # 处理剩余对象（作为独立对象创建）
        for obj_def in remaining:
            print(f"Warning: Creating object '{obj_def.get('id')}' without relation")
            scene_obj = self._create_object(obj_def)
            if scene_obj:
                objects.append(scene_obj)
                self._created_objects[scene_obj.id] = scene_obj

        camera = self._build_camera()
        lighting = self._build_lighting()

        return SceneData(
            template=self.shot.get("template"),
            objects=objects,
            camera=camera,
            lighting=lighting
        )

    # 模板几何类型到标准几何类型的映射
    GEOMETRY_TYPE_MAP = {
        "floor": "box",      # 地板用扁平的 box
        "ground": "box",     # 地面用扁平的 box
        "water": "box",      # 水面用扁平的 box
        "wall": "box",       # 墙壁用 box
        "box": "box",
        "plane": "plane",
        "sphere": "sphere",
        "cylinder": "cylinder",
    }

    def _map_geometry_type(self, template_type: str) -> str:
        """将模板类型映射为标准几何类型"""
        return self.GEOMETRY_TYPE_MAP.get(template_type, "box")

    def _build_base_elements(self) -> List[SceneObject]:
        """构建场景基础元素"""
        objects = []
        for elem in self.template.base_elements:
            # 映射几何类型
            geom_type = self._map_geometry_type(elem["type"])

            # 基础元素的位置已经是绝对坐标
            scene_obj = SceneObject(
                id=elem["id"],
                type=elem["type"],
                geometry_type=geom_type,
                position=tuple(elem["position"]),
                size=tuple(elem["size"]),
                rotation=(0, 0, 0),
                color=elem["color"]
            )
            objects.append(scene_obj)
            self._created_objects[scene_obj.id] = scene_obj
        return objects

    def _create_object(self, obj_def: Dict) -> Optional[SceneObject]:
        """创建独立物体（无 relation）"""
        obj_id = obj_def.get("id")
        obj_type = obj_def.get("type")

        obj_lib = get_object_def(obj_type)
        if not obj_lib:
            print(f"Warning: Unknown object type '{obj_type}'")
            return None

        # 计算位置（底部中心点）
        position = self._calculate_position(obj_def)

        # 处理缩放
        scale = obj_def.get("scale", {})
        size = (
            obj_lib.size[0] * scale.get("x", 1),
            obj_lib.size[1] * scale.get("y", 1),
            obj_lib.size[2] * scale.get("z", 1)
        )

        # 处理旋转
        rotation = obj_def.get("rotation", {})
        rotation = (
            rotation.get("x", 0),
            rotation.get("y", 0),
            rotation.get("z", 0)
        )

        return SceneObject(
            id=obj_id,
            type=obj_type,
            geometry_type=obj_lib.geometry_type,
            position=position,  # 底部中心点
            size=size,
            rotation=rotation,
            color=obj_lib.color
        )

    def _create_object_with_relation(self, obj_def: Dict) -> Optional[SceneObject]:
        """创建有关联的物体"""
        obj_id = obj_def.get("id")
        obj_type = obj_def.get("type")
        relation = obj_def.get("relation", "")

        obj_lib = get_object_def(obj_type)
        if not obj_lib:
            print(f"Warning: Unknown object type '{obj_type}'")
            return None

        # 提取 relation 信息
        rel_type, target_id = self._parse_relation(relation)
        target_obj = self._created_objects.get(target_id)

        if not target_obj:
            print(f"Warning: Target object '{target_id}' not found for relation")
            return self._create_object(obj_def)  # 降级为独立对象

        # 计算基于 relation 的位置
        position = self._calculate_relative_position(
            obj_def, obj_lib, rel_type, target_obj
        )

        # 处理缩放
        scale = obj_def.get("scale", {})
        size = (
            obj_lib.size[0] * scale.get("x", 1),
            obj_lib.size[1] * scale.get("y", 1),
            obj_lib.size[2] * scale.get("z", 1)
        )

        # 处理旋转
        rotation = obj_def.get("rotation", {})
        rotation = (
            rotation.get("x", 0),
            rotation.get("y", 0),
            rotation.get("z", 0)
        )

        return SceneObject(
            id=obj_id,
            type=obj_type,
            geometry_type=obj_lib.geometry_type,
            position=position,  # 底部中心点
            size=size,
            rotation=rotation,
            color=obj_lib.color,
            parent=target_id
        )

    def _get_scaled_offsets(self) -> Dict[str, Tuple[float, float, float]]:
        """
        根据模板边界计算缩放后的位置偏移

        不同模板有不同尺度，需要动态计算合理的偏移距离
        """
        # 获取模板边界
        boundary = self.template.boundary
        x_range = boundary.get("max_x", 4) - boundary.get("min_x", -4)
        z_range = boundary.get("max_z", 4) - boundary.get("min_z", -4)

        # 获取模板类型的缩放比例
        scale = self.TEMPLATE_OFFSET_SCALES.get(self.template.name, 0.25)

        # 计算实际偏移量（取X和Z范围的平均值乘以比例）
        avg_range = (x_range + z_range) / 2
        offset_magnitude = avg_range * scale

        # 生成缩放后的偏移
        scaled_offsets = {}
        for key, (ox, oy, oz) in self.BASE_POSITION_OFFSETS.items():
            scaled_offsets[key] = (
                ox * offset_magnitude,
                oy,
                oz * offset_magnitude
            )

        return scaled_offsets

    def _clamp_to_boundary(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """
        将位置约束在模板边界内
        """
        boundary = self.template.boundary

        min_x = boundary.get("min_x", -float('inf'))
        max_x = boundary.get("max_x", float('inf'))
        min_y = boundary.get("min_y", 0)
        max_y = boundary.get("max_y", float('inf'))
        min_z = boundary.get("min_z", -float('inf'))
        max_z = boundary.get("max_z", float('inf'))

        return (
            max(min_x, min(max_x, x)),
            max(min_y, min(max_y, y)),
            max(min_z, min(max_z, z))
        )

    def _get_ground_height(self) -> float:
        """
        获取模板定义的地面高度
        """
        return self.template.boundary.get("min_y", 0)

    def _calculate_position(self, obj_def: Dict) -> Tuple[float, float, float]:
        """
        计算独立物体的位置（底部中心点）

        返回: (x, y_bottom, z) - y_bottom 是物体底部接触地面的高度
        """
        # 如果提供了精确坐标，直接使用（但仍进行边界检查）
        if "coordinates" in obj_def:
            coords = obj_def["coordinates"]
            x, y, z = coords.get("x", 0), coords.get("y", 0), coords.get("z", 0)
            return self._clamp_to_boundary(x, y, z)

        # 获取位置描述
        position_desc = obj_def.get("position", "center")

        # 使用模板锚点 + 缩放后的偏移
        anchor = self.template.anchor_points.get(position_desc, (0, 0, 0))
        offsets = self._get_scaled_offsets()
        offset = offsets.get(position_desc, (0, 0, 0))

        # 计算原始位置
        raw_x = anchor[0] + offset[0]
        raw_y = anchor[1] if len(anchor) > 1 else self._get_ground_height()
        raw_z = anchor[2] + offset[2]

        # 边界约束
        return self._clamp_to_boundary(raw_x, raw_y, raw_z)

    def _calculate_relative_position(
        self,
        obj_def: Dict,
        obj_lib: Any,
        rel_type: str,
        target_obj: SceneObject
    ) -> Tuple[float, float, float]:
        """
        计算关联物体的位置（底部中心点）

        Args:
            obj_def: 对象定义
            obj_lib: 对象库定义（包含 size）
            rel_type: 关系类型
            target_obj: 目标对象

        Returns:
            (x, y_bottom, z) - 底部中心点坐标
        """
        target_pos = target_obj.position
        target_size = target_obj.size
        obj_height = obj_lib.size[1]  # 物体自身高度

        if rel_type == "on_top_of":
            # 放在目标物体上面：底部中心点 = 目标顶部高度
            # target_pos[1] 是目标底部，加上目标高度就是目标顶部
            target_top = target_pos[1] + target_size[1]
            return (target_pos[0], target_top, target_pos[2])

        elif rel_type == "beside":
            # 在目标旁边：水平偏移
            offset = target_size[0] * 0.8  # 稍微重叠
            # 使用对象 id 哈希保持一致性（确定性计算）
            direction = 1 if hash(obj_def.get("id", "")) % 2 == 0 else -1
            return (
                target_pos[0] + offset * direction,
                target_pos[1],  # 同一水平面
                target_pos[2]
            )

        elif rel_type == "beside_left":
            # 明确在目标左侧
            offset = target_size[0] * 0.8
            return (
                target_pos[0] - offset,
                target_pos[1],
                target_pos[2]
            )

        elif rel_type == "beside_right":
            # 明确在目标右侧
            offset = target_size[0] * 0.8
            return (
                target_pos[0] + offset,
                target_pos[1],
                target_pos[2]
            )

        elif rel_type == "in_front_of":
            # 在目标前方
            offset = target_size[2] * 0.8
            return (
                target_pos[0],
                target_pos[1],
                target_pos[2] + offset
            )

        elif rel_type == "behind":
            # 在目标后方
            offset = target_size[2] * 0.8
            return (
                target_pos[0],
                target_pos[1],
                target_pos[2] - offset
            )

        elif rel_type == "inside":
            # 在目标内部（如：人在车里）
            # 稍微偏移一点避免完全重叠
            return (
                target_pos[0],
                target_pos[1] + 0.1,
                target_pos[2]
            )

        elif rel_type == "near":
            # 在目标附近（距离较远，用于人物和物体的关系）
            # 使用哈希确定位置以确保一致性
            id_hash = hash(obj_def.get("id", ""))
            distance = target_size[0] * 1.5
            return (
                target_pos[0] + distance * (id_hash % 2 * 2 - 1),  # 左或右
                target_pos[1],
                target_pos[2] + distance * ((id_hash // 2) % 2 * 2 - 1)  # 前或后
            )

        else:
            # 默认：放在目标旁边
            pos = (
                target_pos[0] + target_size[0],
                target_pos[1],
                target_pos[2]
            )

        # 边界约束
        return self._clamp_to_boundary(pos[0], pos[1], pos[2])

    def _parse_relation(self, relation: str) -> Tuple[str, str]:
        """解析 relation 字符串"""
        parts = relation.split(":")
        if len(parts) != 2:
            return ("beside", "")
        return (parts[0], parts[1])

    def _extract_target_id(self, relation: str) -> Optional[str]:
        """从 relation 中提取目标 id"""
        parts = relation.split(":")
        if len(parts) == 2:
            return parts[1]
        return None

    def _build_camera(self) -> CameraConfig:
        """构建相机配置"""
        camera_def = self.shot.get("camera", {})
        view = camera_def.get("view", "side")

        # 获取视图预设位置
        default_pos = self.VIEW_CAMERA_POSITIONS.get(
            view,
            self.template.default_camera.get("position", (8, 3, 8))
        )

        # 允许覆盖
        if "position" in camera_def:
            pos = camera_def["position"]
            default_pos = (pos.get("x", default_pos[0]),
                          pos.get("y", default_pos[1]),
                          pos.get("z", default_pos[2]))

        target = camera_def.get("target", self.template.default_camera.get("target", [0, 1, 0]))
        target = tuple(target) if isinstance(target, list) else (
            target.get("x", 0),
            target.get("y", 1),
            target.get("z", 0)
        )

        fov = camera_def.get("fov", self.template.default_camera.get("fov", 50))

        return CameraConfig(
            position=default_pos,
            target=target,
            fov=fov
        )

    def _build_lighting(self) -> Dict[str, Any]:
        """构建光照配置"""
        lighting_def = self.shot.get("lighting", {})
        lighting_type = lighting_def.get("type", "indoor_warm")

        lighting_presets = {
            "day": {
                "ambient": {"color": "#ffffff", "intensity": 0.6},
                "directional": {"color": "#fff5e6", "intensity": 1.0, "position": [10, 20, 10]}
            },
            "night": {
                "ambient": {"color": "#1a1a2e", "intensity": 0.3},
                "directional": {"color": "#4a4a6a", "intensity": 0.5, "position": [-10, 10, -5]}
            },
            "sunset": {
                "ambient": {"color": "#ffecd2", "intensity": 0.5},
                "directional": {"color": "#ff9a56", "intensity": 0.8, "position": [15, 5, 5]}
            },
            "indoor_warm": {
                "ambient": {"color": "#fff8f0", "intensity": 0.5},
                "directional": {"color": "#ffe4c4", "intensity": 0.7, "position": [5, 10, 5]}
            },
            "indoor_cool": {
                "ambient": {"color": "#f0f8ff", "intensity": 0.5},
                "directional": {"color": "#e6f3ff", "intensity": 0.7, "position": [5, 10, 5]}
            },
        }

        return lighting_presets.get(lighting_type, lighting_presets["indoor_warm"])

    def export_to_threejs(self) -> Dict[str, Any]:
        """
        导出为 Three.js 可用的 JSON 格式

        注意：Three.js 中 box 的 position 是几何中心，需要转换
        """
        scene_data = self.build()

        objects_export = []
        for obj in scene_data.objects:
            # 转换底部中心点到几何中心（仅对 box 和 cylinder）
            if obj.geometry_type in ["box", "cylinder"]:
                # 几何中心 = 底部中心 + (0, height/2, 0)
                render_position = (
                    obj.position[0],
                    obj.position[1] + obj.size[1] / 2,
                    obj.position[2]
                )
            else:
                # plane 等特殊处理
                render_position = obj.position

            objects_export.append({
                "id": obj.id,
                "type": obj.geometry_type,
                "position": list(render_position),
                "size": list(obj.size),
                "rotation": list(obj.rotation),
                "color": obj.color
            })

        return {
            "template": scene_data.template,
            "objects": objects_export,
            "camera": {
                "position": list(scene_data.camera.position),
                "target": list(scene_data.camera.target),
                "fov": scene_data.camera.fov
            },
            "lighting": scene_data.lighting
        }


def build_scene_from_json(shot_json: Dict[str, Any]) -> Dict[str, Any]:
    """便捷函数：从 Shot JSON 构建 Three.js 场景数据"""
    builder = SceneBuilder(shot_json)
    return builder.export_to_threejs()


if __name__ == "__main__":
    # 测试示例
    test_shot = {
        "template": "indoor_room",
        "camera": {
            "view": "side",
            "shot": "medium"
        },
        "objects": [
            {
                "id": "obj1",
                "type": "child",
                "position": "left"
            },
            {
                "id": "obj2",
                "type": "table",
                "position": "center"
            },
            {
                "id": "obj3",
                "type": "flowerpot",
                "relation": "on_top_of:obj2"
            }
        ],
        "style_prompt": "warm indoor lighting, storybook illustration"
    }

    builder = SceneBuilder(test_shot)
    scene_data = builder.export_to_threejs()
    print(json.dumps(scene_data, indent=2, ensure_ascii=False))
