"""
场景模板定义 - v0.1 支持 indoor_room, street, bridge_river
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class SceneTemplate:
    """场景模板定义"""
    name: str
    description: str
    base_elements: List[Dict[str, Any]] = field(default_factory=list)
    default_camera: Dict[str, Any] = field(default_factory=dict)
    anchor_points: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)
    boundary: Dict[str, float] = field(default_factory=dict)


# ========== 模板 1: 室内房间 ==========
INDOOR_ROOM = SceneTemplate(
    name="indoor_room",
    description="标准室内房间场景，包含地面、后墙和侧墙",
    base_elements=[
        {
            "id": "floor",
            "type": "floor",
            "size": [10, 0.1, 10],
            "position": [0, 0, 0],
            "color": "#d4c4a8"
        },
        {
            "id": "back_wall",
            "type": "box",
            "size": [10, 5, 0.2],
            "position": [0, 0, -5],
            "color": "#f5f5dc"
        },
        {
            "id": "left_wall",
            "type": "box",
            "size": [0.2, 5, 10],
            "position": [-5, 0, 0],
            "color": "#f0f0e0"
        },
    ],
    default_camera={
        "position": [8, 3, 8],
        "target": [0, 1, 0],
        "fov": 100
    },
    anchor_points={
        "center": (0, 0, 0),
        "left": (-2, 0, 0),
        "right": (2, 0, 0),
        "front": (0, 0, 2),
        "back": (0, 0, -2),
        "table_position": (0, 0.4, -1),
    },
    boundary={
        "min_x": -4, "max_x": 4,
        "min_y": 0, "max_y": 5,
        "min_z": -4, "max_z": 4
    }
)


# ========== 模板 2: 街道 ==========
STREET = SceneTemplate(
    name="street",
    description="城市街道场景，包含道路和两侧建筑",
    base_elements=[
        {
            "id": "road",
            "type": "ground",
            "size": [6, 0.05, 100],
            "position": [0, 0, 0],
            "color": "#333333"
        },
        {
            "id": "sidewalk_left",
            "type": "ground",
            "size": [2, 0.1, 100],
            "position": [-4, 0.05, 0],
            "color": "#999999"
        },
        {
            "id": "sidewalk_right",
            "type": "ground",
            "size": [2, 0.1, 100],
            "position": [4, 0.05, 0],
            "color": "#999999"
        },
    ],
    default_camera={
        "position": [5, 3, 10],
        "target": [0, 1, 0],
        "fov": 60
    },
    anchor_points={
        "center": (0, 0, 0),
        "left_building": (-8, 0, 0),
        "right_building": (8, 0, 0),
        "left_sidewalk": (-3, 0, 0),
        "right_sidewalk": (3, 0, 0),
    },
    boundary={
        "min_x": -10, "max_x": 10,
        "min_y": 0, "max_y": 20,
        "min_z": -50, "max_z": 50
    }
)


# ========== 模板 3: 河边桥 ==========
BRIDGE_RIVER = SceneTemplate(
    name="bridge_river",
    description="河边桥梁场景，包含桥面和河流",
    base_elements=[
        {
            "id": "ground_left",
            "type": "ground",
            "size": [20, 0.1, 50],
            "position": [-15, 0, 0],
            "color": "#90EE90"
        },
        {
            "id": "ground_right",
            "type": "ground",
            "size": [20, 0.1, 50],
            "position": [15, 0, 0],
            "color": "#90EE90"
        },
        {
            "id": "river",
            "type": "water",
            "size": [20, 0.02, 50],
            "position": [0, -0.5, 0],
            "color": "#4682b4"
        },
        {
            "id": "bridge_deck",
            "type": "box",
            "size": [8, 0.3, 12],
            "position": [0, 2, 0],
            "color": "#808080"
        },
        {
            "id": "bridge_railing_left",
            "type": "box",
            "size": [0.2, 1, 12],
            "position": [-3.8, 2.5, 0],
            "color": "#696969"
        },
        {
            "id": "bridge_railing_right",
            "type": "box",
            "size": [0.2, 1, 12],
            "position": [3.8, 2.5, 0],
            "color": "#696969"
        },
    ],
    default_camera={
        "position": [12, 5, 15],
        "target": [0, 2, 0],
        "fov": 55
    },
    anchor_points={
        "center": (0, 2.3, 0),
        "bridge_left": (-2.5, 2.3, 0),
        "bridge_right": (2.5, 2.3, 0),
        "bridge_front": (0, 2.3, 4),
        "bridge_back": (0, 2.3, -4),
        "river_bank_left": (-8, 0, 0),
        "river_bank_right": (8, 0, 0),
    },
    boundary={
        "min_x": -20, "max_x": 20,
        "min_y": -1, "max_y": 10,
        "min_z": -25, "max_z": 25
    }
)


# ========== 模板 4: 白底背景（用于角色参考图生成）==========
WHITE_BACKGROUND = SceneTemplate(
    name="white_background",
    description="白底背景，用于生成干净的角色参考图",
    base_elements=[
        {
            "id": "background",
            "type": "ground",
            "size": [20, 0.1, 20],
            "position": [0, -0.05, 0],
            "color": "#FFFFFF"  # 纯白背景
        },
    ],
    default_camera={
        "position": [0, 1.5, 4],
        "target": [0, 1, 0],
        "fov": 40  # 较窄视角，聚焦角色
    },
    anchor_points={
        "center": (0, 0, 0),
        "front": (0, 0, 1),
    },
    boundary={
        "min_x": -2, "max_x": 2,
        "min_y": 0, "max_y": 3,
        "min_z": -2, "max_z": 2
    }
)


# 模板注册表
TEMPLATES = {
    "indoor_room": INDOOR_ROOM,
    "street": STREET,
    "bridge_river": BRIDGE_RIVER,
    "white_background": WHITE_BACKGROUND,
}


def get_template(name: str) -> Optional[SceneTemplate]:
    """获取场景模板"""
    return TEMPLATES.get(name)


def list_templates() -> List[str]:
    """列出所有可用模板"""
    return list(TEMPLATES.keys())


def get_template_info(name: str) -> Optional[Dict]:
    """获取模板的详细信息"""
    template = TEMPLATES.get(name)
    if not template:
        return None
    return {
        "name": template.name,
        "description": template.description,
        "anchor_points": list(template.anchor_points.keys()),
        "boundary": template.boundary
    }


def register_template(name: str, template: SceneTemplate) -> bool:
    """
    注册新的场景模板

    Args:
        name: 模板唯一标识名
        template: SceneTemplate 实例

    Returns:
        是否注册成功（如果名称已存在则返回 False）

    Example:
        >>> new_template = SceneTemplate(
        ...     name="garden",
        ...     description="花园场景",
        ...     base_elements=[...],
        ...     default_camera={...},
        ...     anchor_points={...},
        ...     boundary={...}
        ... )
        >>> register_template("garden", new_template)
        True
    """
    if name in TEMPLATES:
        print(f"Warning: Template '{name}' already exists, registration skipped")
        return False

    TEMPLATES[name] = template
    return True


def unregister_template(name: str) -> bool:
    """
    注销场景模板

    Args:
        name: 模板名称

    Returns:
        是否成功注销
    """
    if name not in TEMPLATES:
        return False

    del TEMPLATES[name]
    return True


def create_and_register_template(
    name: str,
    description: str,
    base_elements: List[Dict[str, Any]],
    default_camera: Dict[str, Any],
    anchor_points: Dict[str, Tuple[float, float, float]],
    boundary: Dict[str, float]
) -> bool:
    """
    便捷函数：创建并注册场景模板

    Args:
        name: 模板名称
        description: 描述
        base_elements: 基础元素列表
        default_camera: 默认相机配置
        anchor_points: 锚点字典
        boundary: 边界范围

    Returns:
        是否注册成功
    """
    template = SceneTemplate(
        name=name,
        description=description,
        base_elements=base_elements,
        default_camera=default_camera,
        anchor_points=anchor_points,
        boundary=boundary
    )
    return register_template(name, template)
