"""
Schema module - Data models and validation
"""

# 旧版Shot模型
from .shot_model import (
    ShotJSON,
    CameraConfig,
    Object3D,
    LightingConfig,
    validate_shot_json,
    safe_validate_shot_json,
)

# 新版分层架构模型
from .scene_hierarchy import (
    SceneBlueprint,
    BlueprintObject,
    SceneInstance,
    InstanceObject,
    CharacterBinding,
    CameraConfig as ShotCameraConfig,
    Shot,
    create_shot_from_text,
)

__all__ = [
    # 旧版模型
    'ShotJSON',
    'CameraConfig',
    'Object3D',
    'LightingConfig',
    'validate_shot_json',
    'safe_validate_shot_json',
    # 新版分层架构
    'SceneBlueprint',
    'BlueprintObject',
    'SceneInstance',
    'InstanceObject',
    'CharacterBinding',
    'ShotCameraConfig',
    'Shot',
    'create_shot_from_text',
]
