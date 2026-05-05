"""
Spatial Projector — 将 3D 场景对象的包围盒投影到 2D 屏幕空间

用途：为区域 IP-Adapter / 区域提示词提供 per-object 的注意力 mask
"""
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectedRegion:
    """单个对象的 2D 投影结果"""
    object_id: str
    object_type: str
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) 像素坐标，左上原点
    mask: np.ndarray  # (H, W) uint8, 255=对象区域, 0=背景
    center_2d: Tuple[float, float]  # 投影中心点
    depth_mean: float  # 平均深度（用于遮挡排序）


class SpatialProjector:
    """
    3D → 2D 投影器

    使用针孔相机模型，将 3D 包围盒投影到屏幕空间，
    输出每个对象的 2D bbox 和二值 mask。
    """

    def __init__(
        self,
        camera_position: Tuple[float, float, float],
        camera_target: Tuple[float, float, float],
        fov: float = 50.0,
        width: int = 1024,
        height: int = 1024,
        near: float = 0.1,
        far: float = 1000.0,
        mask_blur: int = 5,
    ):
        """
        Args:
            camera_position: 相机位置 (x, y, z)
            camera_target: 注视点 (x, y, z)
            fov: 垂直视场角（度）
            width: 输出图像宽度
            height: 输出图像高度
            near: 近裁剪面
            far: 远裁剪面
            mask_blur: mask 高斯模糊核大小（奇数），0 表示不模糊
        """
        self.camera_position = np.array(camera_position, dtype=np.float64)
        self.camera_target = np.array(camera_target, dtype=np.float64)
        self.fov = fov
        self.width = width
        self.height = height
        self.near = near
        self.far = far
        self.mask_blur = mask_blur

        self.view_matrix = self._build_view_matrix()
        self.proj_matrix = self._build_projection_matrix()

    def _build_view_matrix(self) -> np.ndarray:
        """构建 LookAt 视图矩阵（右手坐标系，Y-up）"""
        eye = self.camera_position
        target = self.camera_target
        up = np.array([0.0, 1.0, 0.0], dtype=np.float64)

        forward = target - eye
        forward = forward / np.linalg.norm(forward)

        right = np.cross(up, forward)
        right_norm = np.linalg.norm(right)
        if right_norm < 1e-8:
            right = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            right = right / right_norm

        camera_up = np.cross(forward, right)
        camera_up = camera_up / np.linalg.norm(camera_up)

        view = np.eye(4, dtype=np.float64)
        view[0, :3] = right
        view[1, :3] = camera_up
        view[2, :3] = -forward
        view[0, 3] = -np.dot(right, eye)
        view[1, 3] = -np.dot(camera_up, eye)
        view[2, 3] = np.dot(forward, eye)
        return view

    def _build_projection_matrix(self) -> np.ndarray:
        """构建透视投影矩阵"""
        aspect = self.width / self.height
        fov_rad = np.radians(self.fov)
        f = 1.0 / np.tan(fov_rad / 2.0)

        proj = np.zeros((4, 4), dtype=np.float64)
        proj[0, 0] = f / aspect
        proj[1, 1] = f
        proj[2, 2] = (self.far + self.near) / (self.near - self.far)
        proj[2, 3] = (2.0 * self.far * self.near) / (self.near - self.far)
        proj[3, 2] = -1.0
        return proj

    def _project_point(self, point_3d: np.ndarray) -> Tuple[float, float, float]:
        """投影单个 3D 点 → 屏幕坐标 + 深度"""
        p4 = np.append(point_3d, 1.0)
        clip = self.proj_matrix @ (self.view_matrix @ p4)
        w = clip[3]
        if abs(w) < 1e-10:
            return (float('inf'), float('inf'), float('inf'))
        ndc = clip[:3] / w
        x = (ndc[0] + 1.0) * 0.5 * self.width
        y = (1.0 - ndc[1]) * 0.5 * self.height  # NDC y-up → 屏幕 y-down
        return (x, y, ndc[2])

    def project_bbox(
        self,
        center: Tuple[float, float, float],
        scale: Tuple[float, float, float],
        object_id: str = "",
        object_type: str = "",
    ) -> Optional[ProjectedRegion]:
        """
        投影一个 3D 包围盒到 2D

        Args:
            center: 几何中心 (x, y, z)
            scale: 包围盒半尺寸 (sx, sy, sz)

        Returns:
            ProjectedRegion 或 None（对象完全在屏幕外 / 在相机后方）
        """
        cx, cy, cz = center
        sx, sy, sz = scale[0] / 2.0, scale[1] / 2.0, scale[2] / 2.0

        corners_3d = np.array([
            [cx - sx, cy - sy, cz - sz],
            [cx + sx, cy - sy, cz - sz],
            [cx - sx, cy - sy, cz + sz],
            [cx + sx, cy - sy, cz + sz],
            [cx - sx, cy + sy, cz - sz],
            [cx + sx, cy + sy, cz - sz],
            [cx - sx, cy + sy, cz + sz],
            [cx + sx, cy + sy, cz + sz],
        ], dtype=np.float64)

        points_2d = []
        depths = []
        for corner in corners_3d:
            x, y, z = self._project_point(corner)
            if np.isfinite(x):
                points_2d.append((x, y))
                depths.append(z)

        if not points_2d:
            return None

        pts = np.array(points_2d)
        x1, y1 = pts[:, 0].min(), pts[:, 1].min()
        x2, y2 = pts[:, 0].max(), pts[:, 1].max()

        # 裁剪到图像范围
        x1 = max(0, int(np.floor(x1)))
        y1 = max(0, int(np.floor(y1)))
        x2 = min(self.width - 1, int(np.ceil(x2)))
        y2 = min(self.height - 1, int(np.ceil(y2)))

        if x2 <= x1 or y2 <= y1:
            return None

        # 生成 mask
        mask = np.zeros((self.height, self.width), dtype=np.uint8)
        mask[y1:y2 + 1, x1:x2 + 1] = 255

        # 可选：高斯模糊软化边缘
        if self.mask_blur > 0:
            from scipy.ndimage import gaussian_filter
            mask = gaussian_filter(mask.astype(np.float32), sigma=self.mask_blur / 2.0)
            mask = np.clip(mask, 0, 255).astype(np.uint8)

        return ProjectedRegion(
            object_id=object_id,
            object_type=object_type,
            bbox=(x1, y1, x2, y2),
            mask=mask,
            center_2d=((x1 + x2) / 2.0, (y1 + y2) / 2.0),
            depth_mean=float(np.mean(depths)),
        )

    def project_all(
        self,
        objects: List[Dict[str, Any]],
        object_types: Optional[Dict[str, str]] = None,
    ) -> List[ProjectedRegion]:
        """
        批量投影所有对象

        Args:
            objects: 对象列表，每个包含 'id', 'position', 'size'（或 'scale'）
            object_types: {object_id: type} 补充类型信息

        Returns:
            按深度排序（近→远）的投影区域列表
        """
        results = []
        for obj in objects:
            obj_id = obj.get("id", "")
            obj_type = ""
            if object_types:
                obj_type = object_types.get(obj_id, obj.get("type", ""))

            pos = obj.get("position", (0, 0, 0))
            size = obj.get("size") or obj.get("scale", (1, 1, 1))

            region = self.project_bbox(
                center=tuple(pos),
                scale=tuple(size),
                object_id=obj_id,
                object_type=obj_type,
            )
            if region:
                results.append(region)

        results.sort(key=lambda r: r.depth_mean)
        return results

    def save_masks(
        self,
        regions: List[ProjectedRegion],
        output_dir: str,
        prefix: str = "mask",
    ) -> Dict[str, str]:
        """保存所有 mask 为 PNG 文件，返回 {object_id: filepath}"""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        paths = {}
        for region in regions:
            filename = f"{prefix}_{region.object_id}.png"
            filepath = out / filename
            _save_mask_image(region.mask, str(filepath))
            paths[region.object_id] = str(filepath)

        return paths


def _save_mask_image(mask: np.ndarray, filepath: str):
    """保存 mask 为 RGBA PNG，alpha 通道携带 mask 数据供 ComfyUI LoadImage 使用

    ComfyUI LoadImage 的 MASK 输出 = 1.0 - alpha_normalized:
      - alpha=0   → MASK=1.0 (white, conditioning 生效)
      - alpha=255 → MASK=0.0 (black, conditioning 不生效)

    因此 object 区域 (mask=255) → alpha=0, background (mask=0) → alpha=255
    """
    try:
        from PIL import Image
        h, w = mask.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)
        rgba[:, :, 0] = 255  # R
        rgba[:, :, 1] = 255  # G
        rgba[:, :, 2] = 255  # B
        rgba[:, :, 3] = 255 - mask  # A: 反转，让 ComfyUI MASK 输出与原始 mask 一致
        Image.fromarray(rgba, mode='RGBA').save(filepath)
    except ImportError:
        import cv2
        cv2.imwrite(filepath, mask)


def build_projector_from_camera_config(
    camera_config: Dict[str, Any],
    width: int = 1024,
    height: int = 1024,
) -> SpatialProjector:
    """从 camera config dict 创建 SpatialProjector"""
    position = tuple(camera_config.get("position", (5, 2, 0)))
    target = tuple(camera_config.get("target", (0, 1, 0)))
    fov = camera_config.get("fov", 50)
    return SpatialProjector(
        camera_position=position,
        camera_target=target,
        fov=fov,
        width=width,
        height=height,
    )


def project_instance_objects(
    instance,  # SceneInstance
    camera_config: Dict[str, Any],
    width: int = 1024,
    height: int = 1024,
) -> List[ProjectedRegion]:
    """
    便捷函数：投影 SceneInstance 中所有对象

    自动使用 geometry-center 坐标（与深度渲染器一致）
    """
    projector = build_projector_from_camera_config(camera_config, width, height)

    objects_for_projection = []
    for obj in instance.objects:
        # 将 InstanceObject 几何中心化为屏幕坐标（与 to_threejs_scene / 深度渲染器一致）
        geometry_type = _get_geometry_type(obj.type)
        if geometry_type in ("box", "cylinder"):
            center = (
                obj.position[0],
                obj.position[1] + obj.scale[1] / 2.0,
                obj.position[2],
            )
        else:
            center = obj.position

        objects_for_projection.append({
            "id": obj.id,
            "type": obj.type,
            "position": center,
            "size": obj.scale,
        })

    return projector.project_all(objects_for_projection)


def project_scene_data_objects(
    scene_data: Dict[str, Any],
    camera_config: Dict[str, Any],
    width: int = 1024,
    height: int = 1024,
) -> List[ProjectedRegion]:
    """
    从 scene_data 的 objects 列表直接投影（使用 scene_data 中已保存的位置）

    scene_data 中的 position 已经是几何中心坐标（to_threejs_scene 已调整），
    无需再次做 bottom-center → geometry-center 转换。
    """
    projector = build_projector_from_camera_config(camera_config, width, height)

    objects_for_projection = []
    object_types = {}
    for obj in scene_data.get("objects", []):
        obj_id = obj["id"]
        obj_type = obj.get("object_type", obj.get("type", "object"))
        object_types[obj_id] = obj_type
        objects_for_projection.append({
            "id": obj_id,
            "type": obj_type,
            "position": tuple(obj["position"]),
            "size": tuple(obj["size"]),
        })

    return projector.project_all(objects_for_projection, object_types=object_types)


def _get_geometry_type(object_type: str) -> str:
    type_map = {
        "child": "box", "adult": "box", "boy": "box", "girl": "box",
        "man": "box", "woman": "box",
        "table": "box", "chair": "box", "lamp": "cylinder", "book": "box",
        "flowerpot": "cylinder",
        "floor": "plane", "ground": "plane", "road": "plane",
        "sidewalk": "plane", "water": "plane", "river": "plane",
        "wall": "plane", "building": "box", "tree": "cylinder",
        "car": "box", "bridge": "box",
    }
    return type_map.get(object_type, "box")
