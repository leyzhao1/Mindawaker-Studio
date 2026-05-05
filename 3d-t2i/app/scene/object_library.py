"""
物体库 - 定义基础几何物体及其默认参数
支持视角特定的提示词和部件描述
"""
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ViewPromptRule:
    """
    特定视角下的提示词规则

    Attributes:
        positive: 视角特定的正向提示词
        negative: 可选的负向提示词
        visible_parts: 该视角可见的部件列表
    """
    positive: str
    negative: Optional[str] = None
    visible_parts: List[str] = field(default_factory=list)


@dataclass
class ObjectDef:
    """
    物体定义

    Attributes:
        name: 物体名称
        geometry_type: 几何类型 (box, plane, sphere, cylinder)
        size: 尺寸 (宽, 高, 深)
        color: 颜色
        tags: 标签列表
        parts: 对象的语义部件组成
        view_prompts: 不同视角下的提示词规则
        default_up: 默认上方向向量 (物体的自然朝向), 默认Y轴向上
        default_front: 默认前方向向量, 默认Z轴向前
    """
    name: str
    geometry_type: str  # box, plane, sphere, cylinder
    size: Tuple[float, float, float] = (1, 1, 1)
    color: str = "#cccccc"
    tags: List[str] = field(default_factory=list)
    parts: List[str] = field(default_factory=list)
    view_prompts: Dict[str, ViewPromptRule] = field(default_factory=dict)
    default_up: Tuple[float, float, float] = (0, 1, 0)  # Y轴向上
    default_front: Tuple[float, float, float] = (0, 0, 1)  # Z轴向前


# 基础物体库
OBJECT_LIBRARY = {
    # 人物
    "child": ObjectDef(
        name="child",
        geometry_type="box",
        size=(0.4, 1.0, 0.3),
        color="#f5d0b0",
        tags=["human", "character"],
        parts=["head", "hair", "face", "torso", "arm", "leg"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a child, full face and body visible, looking forward",
                visible_parts=["head", "hair", "face", "torso", "arm", "leg"]
            ),
            "side": ViewPromptRule(
                positive="side view of a child, profile visible, showing side silhouette",
                visible_parts=["head", "hair", "face_profile", "torso", "arm", "leg"]
            ),
            "top": ViewPromptRule(
                positive="top view of a child, mostly head and hair visible from above, body obscured",
                negative="full body, legs, standing pose from front",
                visible_parts=["head", "hair"]
            ),
            "three_quarter": ViewPromptRule(
                positive="three-quarter view of a child, partial face and body visible",
                visible_parts=["head", "hair", "face", "torso", "arm", "leg"]
            )
        }
    ),
    "adult": ObjectDef(
        name="adult",
        geometry_type="box",
        size=(0.5, 1.7, 0.35),
        color="#e8c4a0",
        tags=["human", "character"],
        parts=["head", "hair", "face", "torso", "arm", "leg"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of an adult, full face and body visible",
                visible_parts=["head", "hair", "face", "torso", "arm", "leg"]
            ),
            "side": ViewPromptRule(
                positive="side view of an adult, profile visible, showing side silhouette",
                visible_parts=["head", "hair", "face_profile", "torso", "arm", "leg"]
            ),
            "top": ViewPromptRule(
                positive="top view of an adult, mostly head and shoulders visible from above",
                negative="full body, legs",
                visible_parts=["head", "hair", "shoulders"]
            )
        }
    ),

    # 家具
    "table": ObjectDef(
        name="table",
        geometry_type="box",
        size=(1.5, 0.8, 0.8),
        color="#8b6f47",
        tags=["furniture", "surface"],
        parts=["tabletop", "legs", "surface"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a table, visible tabletop surface and front legs",
                visible_parts=["tabletop", "legs"]
            ),
            "side": ViewPromptRule(
                positive="side view of a table, showing tabletop depth and side legs",
                visible_parts=["tabletop", "legs"]
            ),
            "top": ViewPromptRule(
                positive="top view of a table, flat tabletop surface visible from above, legs mostly hidden",
                negative="table legs from below",
                visible_parts=["tabletop", "surface"]
            )
        }
    ),
    "chair": ObjectDef(
        name="chair",
        geometry_type="box",
        size=(0.5, 0.9, 0.5),
        color="#a08060",
        tags=["furniture", "seat"],
        parts=["seat", "backrest", "legs"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a chair, visible backrest and seat",
                visible_parts=["seat", "backrest", "legs"]
            ),
            "side": ViewPromptRule(
                positive="side view of a chair, showing seat profile and legs",
                visible_parts=["seat", "legs"]
            ),
            "top": ViewPromptRule(
                positive="top view of a chair, seat surface visible from above",
                visible_parts=["seat"]
            )
        }
    ),

    # 装饰
    "flowerpot": ObjectDef(
        name="flowerpot",
        geometry_type="cylinder",
        size=(0.2, 0.25, 0.2),
        color="#8b4513",
        tags=["decoration", "plant"],
        parts=["pot", "soil", "plant", "leaves"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a flowerpot, visible pot and plant",
                visible_parts=["pot", "soil", "plant", "leaves"]
            ),
            "side": ViewPromptRule(
                positive="side view of a flowerpot, showing pot profile and plant",
                visible_parts=["pot", "soil", "plant", "leaves"]
            ),
            "top": ViewPromptRule(
                positive="top view of a flowerpot, soil surface and plant top visible",
                negative="pot base from below",
                visible_parts=["soil", "plant", "leaves"]
            )
        }
    ),
    "book": ObjectDef(
        name="book",
        geometry_type="box",
        size=(0.3, 0.05, 0.4),
        color="#4169e1",
        tags=["decoration", "small"],
        parts=["cover", "pages", "spine"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a book, cover facing forward",
                visible_parts=["cover"]
            ),
            "back": ViewPromptRule(
                positive="back view of a book, back cover visible",
                visible_parts=["cover"]
            ),
            "side": ViewPromptRule(
                positive="side view of a book, pages and spine visible",
                visible_parts=["pages", "spine"]
            ),
            "top": ViewPromptRule(
                positive="top view of a book, front cover visible from above",
                visible_parts=["cover"]
            ),
            "bottom": ViewPromptRule(
                positive="bottom view of a book, back cover visible from below",
                visible_parts=["cover"]
            )
        },
        # 书的朝向:
        # - 平放在桌上: rotation=(0,0,0), 封面朝上(Y+), 俯视看到 cover (top视角)
        # - 立在书架上: rotation=(-90°,0,0), 封面朝前(Z+), 正视看到 cover (front视角)
        default_up=(0, 1, 0),
        default_front=(0, 0, 1)
    ),
    "lamp": ObjectDef(
        name="lamp",
        geometry_type="box",
        size=(0.3, 0.6, 0.3),
        color="#ffd700",
        tags=["light", "furniture"],
        parts=["base", "stem", "lampshade", "bulb"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a lamp, visible lampshade and base",
                visible_parts=["base", "stem", "lampshade"]
            ),
            "side": ViewPromptRule(
                positive="side view of a lamp, showing lamp profile",
                visible_parts=["base", "stem", "lampshade"]
            ),
            "top": ViewPromptRule(
                positive="top view of a lamp, lampshade top visible from above",
                negative="lamp base from below",
                visible_parts=["lampshade"]
            )
        }
    ),

    # 建筑/环境
    "building": ObjectDef(
        name="building",
        geometry_type="box",
        size=(4, 8, 4),
        color="#808080",
        tags=["architecture", "structure"],
        parts=["walls", "roof", "windows", "doors", "facade"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a building, visible facade and entrance",
                visible_parts=["walls", "windows", "doors", "facade"]
            ),
            "side": ViewPromptRule(
                positive="side view of a building, showing building depth and side walls",
                visible_parts=["walls", "roof"]
            ),
            "top": ViewPromptRule(
                positive="top view of a building, roof visible from above",
                negative="building entrance, doors from front",
                visible_parts=["roof"]
            )
        }
    ),
    "tree": ObjectDef(
        name="tree",
        geometry_type="cylinder",
        size=(0.8, 3, 0.8),
        color="#228b22",
        tags=["nature", "vegetation"],
        parts=["trunk", "crown", "branches", "leaves"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a tree, visible trunk and rounded crown",
                visible_parts=["trunk", "crown", "branches", "leaves"]
            ),
            "side": ViewPromptRule(
                positive="side view of a tree, visible trunk and layered crown",
                visible_parts=["trunk", "crown", "branches", "leaves"]
            ),
            "top": ViewPromptRule(
                positive="top view of a tree, mostly dense crown visible, trunk barely visible",
                negative="full front trunk details",
                visible_parts=["crown", "leaves"]
            ),
            "three_quarter": ViewPromptRule(
                positive="three-quarter view of a tree, visible crown volume and partial trunk",
                visible_parts=["trunk", "crown", "branches", "leaves"]
            )
        }
    ),
    "car": ObjectDef(
        name="car",
        geometry_type="box",
        size=(1.8, 1.2, 4),
        color="#c0c0c0",
        tags=["vehicle"],
        parts=["body", "wheels", "windows", "roof", "headlights", "doors"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a car, visible headlights and front grille",
                visible_parts=["body", "headlights", "windows"]
            ),
            "side": ViewPromptRule(
                positive="side view of a car, showing car profile and wheels",
                visible_parts=["body", "wheels", "windows", "doors"]
            ),
            "top": ViewPromptRule(
                positive="top view of a car, roof and windows visible from above",
                negative="wheels from below, car undercarriage",
                visible_parts=["roof", "windows", "body"]
            ),
            "three_quarter": ViewPromptRule(
                positive="three-quarter view of a car, showing front and side",
                visible_parts=["body", "wheels", "windows", "headlights", "doors"]
            )
        }
    ),

    # 场景元素
    "bridge": ObjectDef(
        name="bridge",
        geometry_type="box",
        size=(6, 0.5, 15),
        color="#696969",
        tags=["structure", "architecture"],
        parts=["deck", "supports", "railings", "pillars"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a bridge, visible support pillars and deck edge",
                visible_parts=["supports", "railings"]
            ),
            "side": ViewPromptRule(
                positive="side view of a bridge, showing bridge span and railings",
                visible_parts=["deck", "railings", "supports"]
            ),
            "top": ViewPromptRule(
                positive="top view of a bridge, deck surface visible from above",
                negative="bridge supports from below",
                visible_parts=["deck"]
            ),
            "three_quarter": ViewPromptRule(
                positive="three-quarter view of a bridge, showing span and supports",
                visible_parts=["deck", "supports", "railings"]
            )
        }
    ),
    "river": ObjectDef(
        name="river",
        geometry_type="plane",
        size=(30, 0, 100),
        color="#4682b4",
        tags=["nature", "water"],
        parts=["water_surface", "current", "reflection"],
        view_prompts={
            "front": ViewPromptRule(
                positive="front view of a river, water surface stretching forward",
                visible_parts=["water_surface", "current"]
            ),
            "side": ViewPromptRule(
                positive="side view of a river, showing water flow direction",
                visible_parts=["water_surface", "current"]
            ),
            "top": ViewPromptRule(
                positive="top view of a river, water surface and flow patterns visible",
                visible_parts=["water_surface", "current", "reflection"]
            )
        }
    ),
}


def get_object_def(object_type: str) -> Optional[ObjectDef]:
    """获取物体定义"""
    return OBJECT_LIBRARY.get(object_type)


def list_object_types() -> List[str]:
    """列出所有可用的物体类型"""
    return list(OBJECT_LIBRARY.keys())


def get_objects_by_tag(tag: str) -> List[ObjectDef]:
    """根据标签获取物体"""
    return [obj for obj in OBJECT_LIBRARY.values() if tag in obj.tags]


def euler_to_rotation_matrix(rx: float, ry: float, rz: float) -> List[List[float]]:
    """
    将欧拉角(弧度)转换为旋转矩阵
    旋转顺序: ZYX (先绕X轴, 再绕Y轴, 最后绕Z轴)
    """
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # 组合旋转矩阵 Rz * Ry * Rx
    return [
        [cy*cz, sx*sy*cz - cx*sz, cx*sy*cz + sx*sz],
        [cy*sz, sx*sy*sz + cx*cz, cx*sy*sz - sx*cz],
        [-sy,   sx*cy,            cx*cy           ]
    ]


def multiply_matrix_vector(m: List[List[float]], v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """矩阵乘以向量"""
    x = m[0][0]*v[0] + m[0][1]*v[1] + m[0][2]*v[2]
    y = m[1][0]*v[0] + m[1][1]*v[1] + m[1][2]*v[2]
    z = m[2][0]*v[0] + m[2][1]*v[1] + m[2][2]*v[2]
    return (x, y, z)


def normalize(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """归一化向量"""
    length = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if length < 1e-6:
        return (0, 0, 1)
    return (v[0]/length, v[1]/length, v[2]/length)


def dot_product(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """向量点积"""
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def get_effective_view(
    object_type: str,
    rotation: Tuple[float, float, float],
    camera_position: Tuple[float, float, float],
    object_position: Tuple[float, float, float] = (0, 0, 0)
) -> Optional[str]:
    """
    根据物体的旋转和相机位置，计算有效的视角标签

    Args:
        object_type: 物体类型
        rotation: 物体的欧拉角旋转 (rx, ry, rz) 单位：弧度
        camera_position: 相机在世界坐标系中的位置
        object_position: 物体在世界坐标系中的位置

    Returns:
        匹配的视角标签 (front/back/side/top/bottom/three_quarter) 或 None
    """
    obj_def = get_object_def(object_type)
    if not obj_def or not obj_def.view_prompts:
        return None

    # 计算旋转矩阵
    rot_matrix = euler_to_rotation_matrix(rotation[0], rotation[1], rotation[2])

    # 计算物体旋转后的局部坐标轴在世界坐标系中的方向
    # default_up 旋转后变为物体的实际 "上" 方向
    # default_front 旋转后变为物体的实际 "前" 方向
    world_up = multiply_matrix_vector(rot_matrix, obj_def.default_up)
    world_front = multiply_matrix_vector(rot_matrix, obj_def.default_front)

    # 计算右方向 (front × up)
    world_right = (
        world_front[1]*world_up[2] - world_front[2]*world_up[1],
        world_front[2]*world_up[0] - world_front[0]*world_up[2],
        world_front[0]*world_up[1] - world_front[1]*world_up[0]
    )
    world_right = normalize(world_right)

    # 重新计算正交的前方向 (right × up)
    world_front = (
        world_right[1]*world_up[2] - world_right[2]*world_up[1],
        world_right[2]*world_up[0] - world_right[0]*world_up[2],
        world_right[0]*world_up[1] - world_right[1]*world_up[0]
    )
    world_front = normalize(world_front)
    world_up = normalize(world_up)

    # 计算从物体指向相机的方向向量
    cam_dir = (
        camera_position[0] - object_position[0],
        camera_position[1] - object_position[1],
        camera_position[2] - object_position[2]
    )
    cam_dir = normalize(cam_dir)

    # 计算相机方向相对于物体局部坐标系的点积
    # 点积 > 0 表示相机在该轴的正方向
    up_dot = dot_product(cam_dir, world_up)      # >0 从上方看, <0 从下方看
    front_dot = dot_product(cam_dir, world_front) # >0 从前方看, <0 从后方看
    right_dot = dot_product(cam_dir, world_right) # >0 从右侧看, <0 从左侧看

    # 根据点积判断视角
    # 使用阈值避免边缘情况
    threshold = 0.5
    abs_up = abs(up_dot)
    abs_front = abs(front_dot)
    abs_right = abs(right_dot)

    # 先判断主要方向
    is_top = up_dot > threshold and abs_up > abs_front and abs_up > abs_right
    is_bottom = up_dot < -threshold and abs_up > abs_front and abs_up > abs_right
    is_front = front_dot > threshold and abs_front > abs_up and abs_front > abs_right
    is_back = front_dot < -threshold and abs_front > abs_up and abs_front > abs_right

    # 确定视角标签 (优先使用物体定义的视角)
    available_views = list(obj_def.view_prompts.keys())

    # 映射逻辑
    if is_top and "top" in available_views:
        return "top"
    elif is_bottom and "bottom" in available_views:
        return "bottom"
    elif is_front and "front" in available_views:
        return "front"
    elif is_back and "back" in available_views:
        return "back"
    elif abs_right > threshold:
        # 侧视图
        if "side" in available_views:
            return "side"
        elif right_dot > 0 and "right" in available_views:
            return "right"
        elif right_dot < 0 and "left" in available_views:
            return "left"

    # 如果没有精确匹配，检查是否有 three_quarter 作为备选
    if "three_quarter" in available_views:
        return "three_quarter"

    # 返回第一个可用的视角作为默认
    return available_views[0] if available_views else None


def get_view_prompt_for_object(
    object_type: str,
    rotation: Tuple[float, float, float],
    camera_position: Tuple[float, float, float],
    object_position: Tuple[float, float, float] = (0, 0, 0)
) -> Optional[ViewPromptRule]:
    """
    获取物体在特定旋转和相机位置下的视角提示词

    示例:
        # 书平放在桌子上 (rotation = (0, 0, 0))
        # 相机从上方俯视 camera = (0, 5, 0)
        prompt = get_view_prompt_for_object(
            "book",
            rotation=(0, 0, 0),
            camera_position=(0, 5, 0),
            object_position=(0, 0, 0)
        )
        # 返回 "top" 视角 (看到书页)

        # 书立起来 (rotation = (math.pi/2, 0, 0))
        # 相机从上方俯视
        prompt = get_view_prompt_for_object(
            "book",
            rotation=(math.pi/2, 0, 0),  # 90度绕X轴旋转
            camera_position=(0, 5, 0),
            object_position=(0, 0, 0)
        )
        # 返回 "front" 视角 (看到封面)
    """
    obj_def = get_object_def(object_type)
    if not obj_def:
        return None

    view_label = get_effective_view(object_type, rotation, camera_position, object_position)
    if view_label:
        return obj_def.view_prompts.get(view_label)
    return None
