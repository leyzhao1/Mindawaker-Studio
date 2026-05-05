#!/usr/bin/env python3
"""
测试角色库功能
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.pipeline.character_library import CharacterLibrary
from app.pipeline.character_consistency import CharacterConsistencyManager

print("=" * 70)
print("Test Character Library Function")
print("=" * 70)

# 1. Test character library creation
print("\n1. Create character library...")
lib_path = "./data/character_library.json"
print(f"   Library path: {lib_path}")

lib = CharacterLibrary(library_path=lib_path)
print(f"   Loaded {len(lib.characters)} characters")

# 2. Check Lucy character
print("\n2. Check Lucy character...")
lucy = lib.find_character_by_name("Lucy")
if lucy:
    print(f"   Found Lucy: {lucy.character_id}")
    print(f"   Features: {lucy.key_features}")
else:
    print("   ERROR: Lucy not found!")

# 3. Test character matching
print("\n3. Test character matching...")
test_cases = [
    ("child", "a golden-haired child", "should match Lucy"),
    ("child", "a normal child", "should match Lucy (type match)"),
    ("adult", "an adult", "should not match"),
]

for obj_type, description, expected in test_cases:
    char = lib.find_matching_character(obj_type, description)
    if char:
        print(f"   '{description}' ({obj_type}) -> match: {char.name}")
    else:
        print(f"   '{description}' ({obj_type}) -> no match")

# 4. Test consistency manager
print("\n4. Test character registration to consistency manager...")
cache_dir = "./data/cache"
manager = CharacterConsistencyManager(storage_dir=f"{cache_dir}/characters")

if lucy:
    # Ensure Lucy is registered
    char_identity = lib.ensure_character_in_manager(manager, lucy, generate_references=False)
    if char_identity:
        print(f"   Lucy registered to consistency manager")
        print(f"   Character ID: {char_identity.character_id}")

        # Check cache file
        cache_file = Path(f"{cache_dir}/characters/{lucy.character_id}.json")
        if cache_file.exists():
            print(f"   Cache file exists: {cache_file}")
        else:
            print(f"   ERROR: Cache file not exists: {cache_file}")
    else:
        print("   ERROR: Registration failed")

# 5. Check file system
print("\n5. File system check...")
print(f"   Library file: {Path(lib_path).absolute()}")
print(f"   File exists: {Path(lib_path).exists()}")

cache_dir_path = Path(cache_dir)
if cache_dir_path.exists():
    print(f"   Cache directory: {cache_dir_path.absolute()}")
    char_files = list(cache_dir_path.glob("characters/*.json"))
    print(f"   Character cache files: {len(char_files)}")
    for f in char_files:
        print(f"     - {f.name}")
else:
    print(f"   Cache directory not exists: {cache_dir_path}")

print("\n" + "=" * 70)
print("Test completed")