"""
场景缓存系统 - 保持相同内容不同视角的3D结构一致性
"""
import json
import copy
import hashlib
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class CachedScene:
    """缓存的场景数据"""
    scene_data: Dict[str, Any]  # 完整的3D场景数据（包含默认相机）
    content_hash: str  # 内容哈希（用于验证）


class SceneCache:
    """
    场景缓存管理器

    核心思想：相同场景内容（物体及其关系）共享相同的3D结构
    不同视角通过修改相机参数来实现，而不重新生成整个场景
    """

    def __init__(self, cache_dir: str = "./data/scene_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, CachedScene] = {}

    def _compute_content_hash(self, shot_json: Dict[str, Any]) -> str:
        """
        计算场景内容的哈希（排除视角和相机信息）

        这样"侧面角度"和"俯视角度"会得到相同的content_hash
        """
        # 提取场景核心内容（与视角无关的部分）
        content = {
            "template": shot_json.get("template"),
            "objects": shot_json.get("objects", []),
            "lighting": shot_json.get("lighting", {}),
            "style_prompt": shot_json.get("style_prompt", ""),
        }

        # 对objects进行规范化排序，确保顺序不影响哈希
        if content["objects"]:
            content["objects"] = sorted(
                content["objects"],
                key=lambda x: x.get("id", "")
            )

        content_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content_str.encode()).hexdigest()[:16]

    def _get_cache_path(self, content_hash: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{content_hash}.json"

    def get_cached_scene(self, shot_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        获取缓存的场景数据

        Returns:
            如果缓存存在，返回场景数据；否则返回None
        """
        content_hash = self._compute_content_hash(shot_json)

        # 先检查内存缓存
        if content_hash in self._memory_cache:
            return self._memory_cache[content_hash].scene_data

        # 再检查磁盘缓存
        cache_path = self._get_cache_path(content_hash)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                # 加载到内存缓存
                self._memory_cache[content_hash] = CachedScene(
                    scene_data=cached_data,
                    content_hash=content_hash
                )
                return cached_data
            except Exception as e:
                print(f"Failed to load cache: {e}")
                return None

        return None

    def save_scene(self, shot_json: Dict[str, Any], scene_data: Dict[str, Any]):
        """
        保存场景到缓存

        Args:
            shot_json: 原始shot定义
            scene_data: 构建好的3D场景数据
        """
        content_hash = self._compute_content_hash(shot_json)

        # 保存到内存
        self._memory_cache[content_hash] = CachedScene(
            scene_data=scene_data,
            content_hash=content_hash
        )

        # 保存到磁盘
        cache_path = self._get_cache_path(content_hash)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(scene_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save cache: {e}")

    def apply_view_to_scene(
        self,
        base_scene: Dict[str, Any],
        shot_json: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将特定视角应用到基础场景

        这样可以在保持物体位置不变的情况下，只改变相机角度
        """
        import copy
        scene = copy.deepcopy(base_scene)

        # 从shot_json中提取视角信息
        camera_def = shot_json.get("camera", {})
        view = camera_def.get("view", "side")

        # 视角到相机位置的映射
        VIEW_CAMERA_POSITIONS = {
            "front": [0, 3, 12],
            "side": [12, 3, 0],
            "top": [0, 18, 0],
            "three_quarter": [8, 4, 8],
            "low_angle": [8, 1, 8],
            "high_angle": [8, 12, 8],
        }

        # 更新相机位置
        if view in VIEW_CAMERA_POSITIONS:
            scene["camera"]["position"] = VIEW_CAMERA_POSITIONS[view]

        # 允许自定义相机参数覆盖
        if "position" in camera_def:
            pos = camera_def["position"]
            if isinstance(pos, dict):
                scene["camera"]["position"] = [
                    pos.get("x", scene["camera"]["position"][0]),
                    pos.get("y", scene["camera"]["position"][1]),
                    pos.get("z", scene["camera"]["position"][2]),
                ]

        if "target" in camera_def:
            target = camera_def["target"]
            if isinstance(target, dict):
                scene["camera"]["target"] = [
                    target.get("x", 0),
                    target.get("y", 1),
                    target.get("z", 0),
                ]
            elif isinstance(target, list):
                scene["camera"]["target"] = target

        if "fov" in camera_def:
            scene["camera"]["fov"] = camera_def["fov"]

        return scene

    def clear_cache(self):
        """清空所有缓存"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()


def get_scene_with_cache(
    shot_json: Dict[str, Any],
    scene_builder_func,
    cache: Optional[SceneCache] = None
) -> Dict[str, Any]:
    """
    使用缓存获取场景（便捷函数）

    Args:
        shot_json: Shot JSON定义
        scene_builder_func: 构建场景的函数，接收shot_json返回scene_data
        cache: 场景缓存实例（为None时创建新缓存）

    Returns:
        带有正确相机配置的场景数据
    """
    if cache is None:
        cache = SceneCache()

    # 尝试获取缓存的基础场景（无特定视角）
    base_scene = cache.get_cached_scene(shot_json)

    if base_scene is None:
        # 缓存未命中，构建新场景
        # 使用一个默认视角构建基础场景
        base_shot = copy.deepcopy(shot_json)
        base_shot["camera"] = {"view": "side"}  # 使用默认视角构建

        base_scene = scene_builder_func(base_shot)
        cache.save_scene(shot_json, base_scene)

    # 应用当前视角到基础场景
    return cache.apply_view_to_scene(base_scene, shot_json)


# 便捷的缓存管理函数
_cache_instance: Optional[SceneCache] = None


def get_global_cache() -> SceneCache:
    """获取全局缓存实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SceneCache()
    return _cache_instance


def reset_global_cache():
    """重置全局缓存"""
    global _cache_instance
    _cache_instance = None
