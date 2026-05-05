"""
Tests for Scene Builder
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scene.scene_builder import SceneBuilder, build_scene_from_json


class TestSceneBuilder:
    """Scene Builder 测试类"""

    def test_basic_scene_building(self):
        """测试基础场景构建"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [
                {"id": "table1", "type": "table", "position": "center"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "test"
        }

        scene = build_scene_from_json(shot_json)

        assert scene["template"] == "indoor_room"
        assert len(scene["objects"]) > 0
        assert "camera" in scene

    def test_on_top_of_relation(self):
        """测试 on_top_of 关系"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [
                {"id": "table1", "type": "table", "position": "center"},
                {"id": "flowerpot1", "type": "flowerpot", "relation": "on_top_of:table1"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "test"
        }

        scene = build_scene_from_json(shot_json)

        # 找到 flowerpot
        flowerpot = next((o for o in scene["objects"] if o["id"] == "flowerpot1"), None)
        assert flowerpot is not None

        # 花盆应该在桌子上面（y 坐标大于地面）
        assert flowerpot["position"][1] > 0.5, "Flowerpot should be above ground"

    def test_beside_relation(self):
        """测试 beside 关系"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [
                {"id": "table1", "type": "table", "position": "center"},
                {"id": "chair1", "type": "chair", "relation": "beside:table1"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "test"
        }

        scene = build_scene_from_json(shot_json)

        table = next((o for o in scene["objects"] if o["id"] == "table1"), None)
        chair = next((o for o in scene["objects"] if o["id"] == "chair1"), None)

        assert table is not None
        assert chair is not None

        # 椅子应该在桌子旁边（x 坐标有偏移）
        assert abs(chair["position"][0] - table["position"][0]) > 0.5

    def test_position_semantics_bottom_center(self):
        """测试位置语义为底部中心点"""
        shot_json = {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [
                {"id": "table1", "type": "table", "position": "center"}
            ],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "test"
        }

        scene = build_scene_from_json(shot_json)

        table = next((o for o in scene["objects"] if o["id"] == "table1"), None)
        assert table is not None

        # 桌子高度约 0.8，渲染位置（几何中心）应该在 y = 0.4 左右
        # 注意：export_to_threejs 会将底部中心点转换为几何中心
        assert 0.3 < table["position"][1] < 0.5, "Table center should be at half height"

    def test_different_templates(self):
        """测试不同模板"""
        templates = ["indoor_room", "street", "bridge_river"]

        for template in templates:
            shot_json = {
                "template": template,
                "camera": {"view": "side", "shot": "medium"},
                "objects": [],
                "lighting": {"type": "day"},
                "style_prompt": "test"
            }

            scene = build_scene_from_json(shot_json)
            assert scene["template"] == template
            assert "objects" in scene
            assert "camera" in scene

    def test_camera_position_based_on_view(self):
        """测试根据视角设置相机位置"""
        test_cases = [
            ("front", [0, 3, 12]),
            ("side", [12, 3, 0]),
            ("top", [0, 18, 0]),
        ]

        for view, expected_pos in test_cases:
            shot_json = {
                "template": "indoor_room",
                "camera": {"view": view, "shot": "medium"},
                "objects": [],
                "lighting": {"type": "indoor_warm"},
                "style_prompt": "test"
            }

            scene = build_scene_from_json(shot_json)
            camera_pos = scene["camera"]["position"]

            assert camera_pos[0] == expected_pos[0]
            assert camera_pos[1] == expected_pos[1]
            assert camera_pos[2] == expected_pos[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
