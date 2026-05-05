"""
角色库 - 管理已知角色定义

角色库用于区分主要角色和路人角色，存储角色的元数据（名称、特征等）。
主要角色会自动生成参考图，路人角色则不生成。

角色库文件格式（JSON）：
[
  {
    "character_id": "lucy_001",
    "name": "Lucy",
    "object_type": "child",
    "key_features": ["golden hair", "blue eyes", "red dress"],
    "description": "一个金色长发、蓝眼睛的小女孩，穿着红色连衣裙",
    "is_main_character": true
  }
]
"""
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from .character_consistency import CharacterIdentity


@dataclass
class CharacterDefinition:
    """角色库中的角色定义"""
    character_id: str  # 角色唯一标识
    name: str  # 角色名称
    object_type: str  # 对象类型（如"child", "adult"）
    key_features: List[str]  # 关键特征列表
    description: str  # 详细描述
    is_main_character: bool = True  # 是否为主要角色

    # 可选的匹配关键词（用于从描述中识别角色）
    match_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "object_type": self.object_type,
            "key_features": self.key_features,
            "description": self.description,
            "is_main_character": self.is_main_character,
            "match_keywords": self.match_keywords
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterDefinition":
        return cls(
            character_id=data["character_id"],
            name=data["name"],
            object_type=data["object_type"],
            key_features=data.get("key_features", []),
            description=data["description"],
            is_main_character=data.get("is_main_character", True),
            match_keywords=data.get("match_keywords", [])
        )

    def to_character_identity(self) -> CharacterIdentity:
        """转换为CharacterIdentity对象（用于一致性管理）"""
        return CharacterIdentity(
            character_id=self.character_id,
            description=self.description,
            reference_images=[],
            seed=42,
            name=self.name,
            key_features=self.key_features,
            is_main_character=self.is_main_character,
            object_type=self.object_type
        )


class CharacterLibrary:
    """角色库管理器"""

    def __init__(self, library_path: str = "./data/character_library.json"):
        self.library_path = Path(library_path)
        self.characters: Dict[str, CharacterDefinition] = {}
        self._load_library()

    def _load_library(self):
        """加载角色库"""
        if not self.library_path.exists():
            print(f"[CharacterLibrary] 角色库文件不存在: {self.library_path}")
            # 创建默认角色库（包含Lucy示例）
            self._create_default_library()
            return

        try:
            with open(self.library_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    char_def = CharacterDefinition.from_dict(item)
                    self.characters[char_def.character_id] = char_def

            print(f"[CharacterLibrary] 已加载 {len(self.characters)} 个角色")
        except Exception as e:
            print(f"[CharacterLibrary] 加载角色库失败: {e}")
            self._create_default_library()

    def _create_default_library(self):
        """创建默认角色库（包含Lucy示例）"""
        lucy = CharacterDefinition(
            character_id="lucy_001",
            name="Lucy",
            object_type="child",
            key_features=["golden hair", "blue eyes", "red dress"],
            description="一个金色长发、蓝眼睛的小女孩，穿着红色连衣裙",
            is_main_character=True,
            match_keywords=["lucy", "金色长发", "金发", "蓝眼睛"]
        )

        self.characters = {"lucy_001": lucy}
        self.save_library()
        print(f"[CharacterLibrary] 已创建默认角色库，包含角色: Lucy")

    def save_library(self):
        """保存角色库到文件"""
        try:
            self.library_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.library_path, 'w', encoding='utf-8') as f:
                json.dump(
                    [char.to_dict() for char in self.characters.values()],
                    f,
                    indent=2,
                    ensure_ascii=False
                )
            print(f"[CharacterLibrary] 已保存角色库: {self.library_path}")
        except Exception as e:
            print(f"[CharacterLibrary] 保存角色库失败: {e}")

    def add_character(self, char_def: CharacterDefinition):
        """添加角色到库"""
        self.characters[char_def.character_id] = char_def
        self.save_library()

    def get_character(self, character_id: str) -> Optional[CharacterDefinition]:
        """获取角色定义"""
        return self.characters.get(character_id)

    def find_character_by_name(self, name: str) -> Optional[CharacterDefinition]:
        """通过名称查找角色（不区分大小写）"""
        name_lower = name.lower()
        for char in self.characters.values():
            if char.name.lower() == name_lower:
                return char
        return None

    def find_matching_character(self, object_type: str, description: str = "") -> Optional[CharacterDefinition]:
        """
        根据对象类型和描述匹配角色

        Args:
            object_type: 对象类型（如"child"）
            description: 对象描述文本（可能包含角色特征）

        Returns:
            匹配的角色定义，如果没有匹配则返回None
        """
        # 首先检查描述中是否包含角色名称
        desc_lower = description.lower()
        for char in self.characters.values():
            # 类型匹配
            if char.object_type != object_type:
                continue

            # 检查名称关键词匹配
            if char.name.lower() in desc_lower:
                return char

            # 检查匹配关键词
            for keyword in char.match_keywords:
                if keyword.lower() in desc_lower:
                    return char

        # 如果没有精确匹配，返回第一个类型匹配的主要角色
        for char in self.characters.values():
            if char.object_type == object_type and char.is_main_character:
                return char

        return None

    def list_characters(self, main_only: bool = False) -> List[CharacterDefinition]:
        """列出所有角色（可选仅主要角色）"""
        if main_only:
            return [char for char in self.characters.values() if char.is_main_character]
        return list(self.characters.values())

    def ensure_character_in_manager(
        self,
        character_manager,
        char_def: CharacterDefinition,
        generate_references: bool = True
    ) -> Optional[CharacterIdentity]:
        """
        确保角色已注册到CharacterConsistencyManager

        Args:
            character_manager: CharacterConsistencyManager实例
            char_def: 角色定义
            generate_references: 如果角色没有参考图，是否生成参考图

        Returns:
            注册后的CharacterIdentity对象
        """
        # 检查是否已注册
        existing_char = character_manager.get_character(char_def.character_id)

        if existing_char:
            # 已注册，更新信息（如果必要）
            if not existing_char.name and char_def.name:
                existing_char.name = char_def.name
                existing_char.key_features = char_def.key_features
                existing_char.object_type = char_def.object_type
                character_manager._save_character(existing_char)

            return existing_char

        # 注册新角色
        char_identity = character_manager.register_character(
            character_id=char_def.character_id,
            description=char_def.description,
            name=char_def.name,
            key_features=char_def.key_features,
            is_main_character=char_def.is_main_character,
            object_type=char_def.object_type,
            seed=42
        )

        print(f"[CharacterLibrary] 已注册角色到一致性管理器: {char_def.name} ({char_def.character_id})")

        # 如果需要生成参考图且是主要角色
        if generate_references and char_def.is_main_character:
            # 注意：这里只注册，参考图生成由外部流程处理
            pass

        return char_identity