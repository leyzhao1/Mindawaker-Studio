"""
Tests for Prompt Builder
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.prompt_builder import PromptBuilder, build_prompt_from_shot


class TestPromptBuilder:
    """Prompt Builder 测试类"""

    def test_basic_prompt_building(self):
        """测试基础提示词构建"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [
                {"id": "child1", "type": "child", "position": "left"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "storybook illustration"
        }

        prompts = build_prompt_from_shot(shot_json)

        assert "positive" in prompts
        assert "negative" in prompts
        assert "child" in prompts["positive"].lower() or "young" in prompts["positive"].lower()
        assert "storybook illustration" in prompts["positive"]

    def test_object_descriptions(self):
        """测试物体描述生成"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "front", "shot": "medium"},
            "objects": [
                {"id": "table1", "type": "table", "position": "center"},
                {"id": "flowerpot1", "type": "flowerpot", "relation": "on_top_of:table1"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "cozy indoor"
        }

        prompts = build_prompt_from_shot(shot_json)
        positive = prompts["positive"]

        assert "table" in positive.lower()
        assert "on top of" in positive.lower()

    def test_camera_view_description(self):
        """测试相机视角描述"""
        test_cases = [
            ({"view": "side", "shot": "medium"}, "side view"),
            ({"view": "front", "shot": "closeup"}, "front view"),
            ({"view": "low_angle", "shot": "wide"}, "low angle"),
        ]

        for camera, expected in test_cases:
            shot_json = {
                "template": "indoor_room",
                "camera": camera,
                "objects": [],
                "lighting": {"type": "day"},
                "style_prompt": "test"
            }

            prompts = build_prompt_from_shot(shot_json)
            assert expected in prompts["positive"].lower()

    def test_lighting_description(self):
        """测试光照描述"""
        test_cases = [
            ("day", "daylight"),
            ("sunset", "sunset"),
            ("indoor_warm", "warm indoor"),
            ("night", "night"),
        ]

        for lighting_type, expected_keyword in test_cases:
            shot_json = {
                "template": "indoor_room",
                "camera": {"view": "side", "shot": "medium"},
                "objects": [],
                "lighting": {"type": lighting_type},
                "style_prompt": "test"
            }

            prompts = build_prompt_from_shot(shot_json)
            assert expected_keyword in prompts["positive"].lower()

    def test_negative_prompt_content(self):
        """测试负面提示词内容"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "test"
        }

        prompts = build_prompt_from_shot(shot_json)
        negative = prompts["negative"]

        # 负面提示词应包含常见负面标签
        assert "blur" in negative.lower() or "low quality" in negative.lower()

    def test_quality_tags_present(self):
        """测试质量标签存在"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [],
            "lighting": {"type": "day"},
            "style_prompt": "masterpiece"
        }

        prompts = build_prompt_from_shot(shot_json)
        positive = prompts["positive"]

        # 应包含质量标签
        assert "high quality" in positive.lower() or "masterpiece" in positive.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
