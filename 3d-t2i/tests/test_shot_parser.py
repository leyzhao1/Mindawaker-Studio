"""
Tests for Shot Parser
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.llm.shot_parser import ShotParser, parse_shot
from app.schema.shot_model import validate_shot_json


class TestShotParser:
    """Shot Parser 测试类"""

    def test_parse_basic_indoor_scene(self):
        """测试基础室内场景解析"""
        text = "室内，一个孩子站在桌边，侧面视角"
        result = parse_shot(text, provider="rule")

        assert result["template"] == "indoor_room"
        assert result["camera"]["view"] == "side"
        assert len(result["objects"]) >= 2  # child and table

    def test_environmental_words_not_objects(self):
        """测试环境词不应生成实体"""
        text = "室内，温暖灯光，柔和氛围"
        result = parse_shot(text, provider="rule")

        obj_types = [o["type"] for o in result["objects"]]
        assert "lamp" not in obj_types, "灯光不应生成 lamp 实体"

    def test_long_word_priority(self):
        """测试长词优先匹配"""
        text = "房间里有一张桌子和椅子"
        result = parse_shot(text, provider="rule")

        table_count = len([o for o in result["objects"] if o["type"] == "table"])
        assert table_count == 1, "桌子应只被匹配一次"

    def test_street_template_detection(self):
        """测试街道模板识别"""
        text = "城市街道，远景拍摄，日落时分"
        result = parse_shot(text, provider="rule")

        assert result["template"] == "street"
        assert result["lighting"]["type"] == "sunset"

    def test_relation_extraction(self):
        """测试关系提取"""
        text = "室内，桌上有花盆"
        result = parse_shot(text, provider="rule")

        flowerpots = [o for o in result["objects"] if o["type"] == "flowerpot"]
        if flowerpots:
            assert "relation" in flowerpots[0], "花盆应有 relation"
            assert "on_top_of" in flowerpots[0]["relation"]

    def test_pydantic_validation(self):
        """测试 Pydantic 验证"""
        text = "室内，一个孩子站在桌边，侧面视角，温暖灯光"
        result = parse_shot(text, provider="rule", validate=True)

        # 验证结果是有效的 ShotJSON
        validated = validate_shot_json(result)
        assert validated.template == "indoor_room"
        assert validated.camera.view == "side"

    def test_camera_view_detection(self):
        """测试相机视角识别"""
        test_cases = [
            ("正面视角", "front"),
            ("侧面拍摄", "side"),
            ("俯视角度", "top"),
            ("仰角拍摄", "low_angle"),
        ]

        for text, expected_view in test_cases:
            result = parse_shot(text, provider="rule")
            assert result["camera"]["view"] == expected_view, f"Failed for {text}"

    def test_shot_type_detection(self):
        """测试镜头景别识别"""
        test_cases = [
            ("特写镜头", "closeup"),
            ("中景拍摄", "medium"),
            ("远景", "wide"),
        ]

        for text, expected_shot in test_cases:
            result = parse_shot(text, provider="rule")
            assert result["camera"]["shot"] == expected_shot, f"Failed for {text}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
