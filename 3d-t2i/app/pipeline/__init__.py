"""
Pipeline模块 - 整合场景缓存和角色一致性的端到端生成
"""
from .scene_cache import SceneCache, get_scene_with_cache
from .character_consistency import (
    CharacterConsistencyManager,
    CharacterIdentity,
    ConsistencyMethod,
    MultiViewGenerator,
    add_character_consistency_to_prompt,
)
from .character_library import CharacterLibrary, CharacterDefinition
from .consistent_pipeline import ConsistentPipeline
from .hierarchical_pipeline import HierarchicalPipeline, quick_generate_views

__all__ = [
    "SceneCache",
    "get_scene_with_cache",
    "CharacterConsistencyManager",
    "CharacterIdentity",
    "ConsistencyMethod",
    "MultiViewGenerator",
    "add_character_consistency_to_prompt",
    "CharacterLibrary",
    "CharacterDefinition",
    "ConsistentPipeline",
    "HierarchicalPipeline",
    "quick_generate_views",
]
