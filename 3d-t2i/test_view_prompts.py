#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试视角特定提示词功能

运行: python test_view_prompts.py
"""
import sys
import io

# 设置UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.llm.prompt_builder import PromptBuilder
from app.scene.object_library import get_object_def


def test_view_prompts():
    """测试不同视角的提示词生成"""

    print("=" * 80)
    print("测试视角特定提示词功能")
    print("=" * 80)

    # 测试用例
    test_cases = [
        {
            "name": "侧面看人",
            "view": "side",
            "objects": ["child"],
            "expected": "side view of a child"
        },
        {
            "name": "俯视看人",
            "view": "top",
            "objects": ["child"],
            "expected": "top view of a child, mostly head"
        },
        {
            "name": "正面看人",
            "view": "front",
            "objects": ["child"],
            "expected": "front view of a child, full face"
        },
        {
            "name": "俯视看树",
            "view": "top",
            "objects": ["tree"],
            "expected": "top view of a tree, mostly dense crown"
        },
        {
            "name": "侧面看树",
            "view": "side",
            "objects": ["tree"],
            "expected": "side view of a tree, visible trunk"
        },
        {
            "name": "俯视看桌子",
            "view": "top",
            "objects": ["table"],
            "expected": "top view of a table, flat tabletop"
        },
        {
            "name": "组合场景（俯视）",
            "view": "top",
            "objects": ["child", "table"],
            "expected": "top view"
        },
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"测试 {i}/{len(test_cases)}: {test['name']}")
        print(f"视角: {test['view']}")
        print(f"对象: {', '.join(test['objects'])}")
        print("=" * 80)

        # 构建 shot_json
        shot_json = {
            "template": "indoor_room" if "table" in test["objects"] else "outdoor",
            "camera": {"view": test["view"], "shot": "medium"},
            "objects": [
                {"id": f"obj{j+1}", "type": obj_type, "position": "center" if j == 0 else "left"}
                for j, obj_type in enumerate(test["objects"])
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "storybook illustration"
        }

        # 显示 ObjectDef 的 view_prompts
        print("\n[ObjectDef view_prompts]:")
        for obj_type in test["objects"]:
            obj_def = get_object_def(obj_type)
            if obj_def and obj_def.view_prompts:
                if test["view"] in obj_def.view_prompts:
                    rule = obj_def.view_prompts[test["view"]]
                    print(f"  {obj_type}.{test['view']}: {rule.positive}")
                    if rule.negative:
                        print(f"    negative: {rule.negative}")
                else:
                    print(f"  {obj_type}.{test['view']}: (未配置，使用默认)")
            else:
                print(f"  {obj_type}: (无 view_prompts)")

        # 生成提示词
        builder = PromptBuilder(shot_json)
        prompts = builder.export_prompts()

        print("\n[生成的提示词]:")
        print(f"Positive: {prompts['positive']}")

        # 检查是否包含期望的关键词
        if test["expected"].lower() in prompts["positive"].lower():
            print(f"\n✓ 成功包含期望关键词: '{test['expected']}'")
        else:
            print(f"\n✗ 未找到期望关键词: '{test['expected']}'")
            print(f"  (可能使用了默认描述)")

        # 显示负面提示词（如果有视角特定的）
        view_negative = shot_json.get("view_negative_tags", [])
        if view_negative:
            print(f"\n[视角特定负面提示词]: {', '.join(view_negative)}")

    print("\n" + "=" * 80)
    print("测试完成!")
    print("=" * 80)


def test_parts_field():
    """测试 parts 字段"""
    print("\n" + "=" * 80)
    print("测试 parts 字段")
    print("=" * 80)

    objects_to_check = ["child", "tree", "table", "chair"]

    for obj_type in objects_to_check:
        obj_def = get_object_def(obj_type)
        if obj_def:
            print(f"\n{obj_type}:")
            print(f"  parts: {obj_def.parts}")
            print(f"  view_prompts 数量: {len(obj_def.view_prompts)}")
            for view, rule in obj_def.view_prompts.items():
                print(f"    {view}: visible_parts = {rule.visible_parts}")


if __name__ == "__main__":
    test_view_prompts()
    test_parts_field()
