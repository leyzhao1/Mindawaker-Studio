"""
Prompt Builder - 将 Shot JSON 构建为完整的生成提示词
支持视角特定的物体描述
"""
from typing import Dict, Any, List

from ..scene.object_library import get_object_def, ObjectDef, ViewPromptRule


class PromptBuilder:
    """提示词构建器"""

    # 镜头景别描述
    SHOT_DESCRIPTIONS = {
        "extreme_closeup": "extreme close-up, face detail",
        "closeup": "close-up shot, upper body",
        "medium": "medium shot, waist up",
        "full": "full body shot",
        "wide": "wide shot, full scene",
        "establishing": "establishing shot, wide view",
    }

    # 视角描述
    VIEW_DESCRIPTIONS = {
        "front": "front view",
        "side": "side view, profile",
        "top": "top-down view, aerial",
        "three_quarter": "three-quarter view",
        "low_angle": "low angle shot, looking up",
        "high_angle": "high angle shot, looking down",
    }

    # 物体自然语言描述
    OBJECT_DESCRIPTIONS = {
        "child": "a young child",
        "adult": "an adult person",
        "table": "a wooden table",
        "chair": "a chair",
        "flowerpot": "a potted plant",
        "book": "a book",
        "lamp": "a lamp",
        "building": "a building",
        "tree": "a tree",
        "car": "a car",
        "bridge": "a bridge",
        "river": "a river",
    }

    # 位置描述
    POSITION_DESCRIPTIONS = {
        "left": "on the left",
        "right": "on the right",
        "center": "in the center",
        "front": "in the front",
        "back": "in the back",
    }

    # 光照描述
    LIGHTING_DESCRIPTIONS = {
        "day": "bright daylight, natural lighting",
        "night": "night time, dark atmosphere",
        "sunset": "golden hour, sunset lighting",
        "indoor_warm": "warm indoor lighting, cozy atmosphere",
        "indoor_cool": "cool indoor lighting",
    }

    def __init__(self, shot_json: Dict[str, Any]):
        self.shot = shot_json

    def build_prompt(self) -> str:
        """构建完整的生成提示词"""
        parts = []

        # 1. 主体描述（物体）
        subject_desc = self._build_subject_description()
        if subject_desc:
            parts.append(subject_desc)

        # 2. 场景/环境描述
        setting_desc = self._build_setting_description()
        if setting_desc:
            parts.append(setting_desc)

        # 3. 镜头描述
        shot_desc = self._build_shot_description()
        if shot_desc:
            parts.append(shot_desc)

        # 4. 光照描述
        lighting_desc = self._build_lighting_description()
        if lighting_desc:
            parts.append(lighting_desc)

        # 5. 风格提示词
        style_prompt = self.shot.get("style_prompt", "")
        if style_prompt:
            parts.append(style_prompt)

        # 6. 质量增强词
        parts.append(self._build_quality_tags())

        return ", ".join(parts)

    def build_negative_prompt(self) -> str:
        """构建负面提示词，包含视角特定的负面标签"""
        negative_tags = [
            "blur",
            "low quality",
            "distorted",
            "deformed",
            "extra limbs",
            "bad anatomy",
            "disfigured",
            "poorly drawn face",
            "mutation",
            "mutated",
            "extra fingers",
            "mutated hands",
            "poorly drawn hands",
            "poorly drawn face",
            "mutation",
            "deformed",
            "ugly",
            "blurry",
            "bad anatomy",
            "bad proportions",
            "extra limbs",
            "cloned face",
            "disfigured",
            "out of frame",
            "ugly",
            "extra limbs",
            "bad anatomy",
            "gross proportions",
            "malformed limbs",
            "missing arms",
            "missing legs",
            "extra arms",
            "extra legs",
            "mutated hands",
            "fused fingers",
            "too many fingers",
            "long neck",
            "Photoshop",
            "video game",
            "3d render",
            "unreal engine",
            "cgi",
            # 防止无关物体出现
            "airplane", "plane", "aircraft", "jet", "aeroplane",
            "car", "vehicle", "truck", "bus",
            "extra objects", "unrelated objects", "random objects",
        ]

        # 添加视角特定的负面提示词
        view_negative_tags = self.shot.get("view_negative_tags", [])
        if view_negative_tags:
            negative_tags.extend(view_negative_tags)

        return ", ".join(negative_tags)

    def _build_subject_description(self) -> str:
        """构建主体描述，支持视角特定的提示词"""
        objects = self.shot.get("objects", [])
        if not objects:
            return ""

        # 获取当前视角
        camera = self.shot.get("camera", {})
        current_view = camera.get("view", "front")

        descriptions = []
        view_specific_negative_tags = []  # 收集视角特定的负面提示词

        for obj in objects:
            obj_type = obj.get("type", "")

            # 尝试获取物体定义
            obj_def = get_object_def(obj_type)

            if obj_def and obj_def.view_prompts and current_view in obj_def.view_prompts:
                # 使用视角特定的提示词
                view_rule = obj_def.view_prompts[current_view]
                desc = view_rule.positive

                # 收集视角特定的负面提示词
                if view_rule.negative:
                    view_specific_negative_tags.append(view_rule.negative)
            else:
                # 回退到默认描述
                desc = self.OBJECT_DESCRIPTIONS.get(obj_type, obj_type)

            # 添加位置信息
            position = obj.get("position")
            if position and position in self.POSITION_DESCRIPTIONS:
                desc += f" {self.POSITION_DESCRIPTIONS[position]}"

            # 处理关系
            relation = obj.get("relation", "")
            if relation:
                desc = self._add_relation_description(desc, relation)

            descriptions.append(desc)

        # 如果有视角特定的负面提示词，添加到shot中供后续使用
        if view_specific_negative_tags:
            if "view_negative_tags" not in self.shot:
                self.shot["view_negative_tags"] = []
            self.shot["view_negative_tags"].extend(view_specific_negative_tags)

        return " with ".join(descriptions) if len(descriptions) > 1 else descriptions[0]

    def _add_relation_description(self, desc: str, relation: str) -> str:
        """添加关系描述"""
        parts = relation.split(":")
        if len(parts) != 2:
            return desc

        rel_type, target_id = parts[0], parts[1]

        # 尝试找到目标物体的类型
        target_type = target_id
        for obj in self.shot.get("objects", []):
            if obj.get("id") == target_id:
                target_type = obj.get("type", target_id)
                break

        target_desc = self.OBJECT_DESCRIPTIONS.get(target_type, target_type)

        relation_phrases = {
            "on_top_of": f"on top of {target_desc}",
            "beside": f"next to {target_desc}",
            "behind": f"behind {target_desc}",
            "in_front_of": f"in front of {target_desc}",
            "inside": f"inside {target_desc}",
        }

        if rel_type in relation_phrases:
            desc += f" {relation_phrases[rel_type]}"

        return desc

    def _build_setting_description(self) -> str:
        """构建场景/环境描述"""
        template = self.shot.get("template", "indoor_room")

        setting_map = {
            "indoor_room": "indoor room",
            "street": "city street scene",
            "bridge_river": "bridge over river",
        }

        return setting_map.get(template, "scene")

    def _build_shot_description(self) -> str:
        """构建镜头描述"""
        camera = self.shot.get("camera", {})
        view = camera.get("view", "side")
        shot = camera.get("shot", "medium")

        parts = []

        if shot in self.SHOT_DESCRIPTIONS:
            parts.append(self.SHOT_DESCRIPTIONS[shot])

        if view in self.VIEW_DESCRIPTIONS:
            parts.append(self.VIEW_DESCRIPTIONS[view])

        return ", ".join(parts)

    def _build_lighting_description(self) -> str:
        """构建光照描述"""
        lighting = self.shot.get("lighting", {})
        lighting_type = lighting.get("type", "day")

        return self.LIGHTING_DESCRIPTIONS.get(lighting_type, "")

    def _build_quality_tags(self) -> str:
        """构建质量增强标签"""
        return "high quality, detailed, masterpiece, best quality"

    def _build_subject_anchor_tags(self) -> str:
        objects = self.shot.get("objects", [])
        if not objects:
            return ""

        tokens = []
        for obj in objects:
            obj_type = obj.get("type", "")
            if obj_type:
                tokens.append(self.OBJECT_DESCRIPTIONS.get(obj_type, obj_type))

        if not tokens:
            return ""

        deduped = list(dict.fromkeys(tokens))
        return ", ".join(deduped)

    def _build_relation_anchor_tags(self) -> str:
        objects = self.shot.get("objects", [])
        if not objects:
            return ""

        relations = []
        obj_type_map = {obj.get("id"): obj.get("type", "object") for obj in objects}

        for obj in objects:
            relation = obj.get("relation", "")
            if not relation or ":" not in relation:
                continue

            rel_type, target_id = relation.split(":", 1)
            source_type = obj.get("type", "object")
            target_type = obj_type_map.get(target_id, target_id)
            source_desc = self.OBJECT_DESCRIPTIONS.get(source_type, source_type)
            target_desc = self.OBJECT_DESCRIPTIONS.get(target_type, target_type)

            if rel_type == "on_top_of":
                relations.append(f"{source_desc} on top of {target_desc}")
            elif rel_type == "beside":
                relations.append(f"{source_desc} beside {target_desc}")
            elif rel_type == "behind":
                relations.append(f"{source_desc} behind {target_desc}")
            elif rel_type == "in_front_of":
                relations.append(f"{source_desc} in front of {target_desc}")
            elif rel_type == "inside":
                relations.append(f"{source_desc} inside {target_desc}")

        if not relations:
            return ""

        deduped = list(dict.fromkeys(relations))
        return ", ".join(deduped)

    def build_per_object_prompt(self, object_id: str) -> str:
        """为单个对象构建独立提示词"""
        objects = self.shot.get("objects", [])
        target_obj = None
        for obj in objects:
            if obj.get("id") == object_id:
                target_obj = obj
                break

        if not target_obj:
            return ""

        obj_type = target_obj.get("type", "object")
        obj_def = get_object_def(obj_type)
        camera = self.shot.get("camera", {})
        view = camera.get("view", "front")

        # 对象本身描述（优先使用视角特定描述）
        if obj_def and obj_def.view_prompts and view in obj_def.view_prompts:
            desc = obj_def.view_prompts[view].positive
        else:
            desc = self.OBJECT_DESCRIPTIONS.get(obj_type, obj_type)

        # 添加风格和质量标记
        style_prompt = self.shot.get("style_prompt", "")
        lighting_desc = self._build_lighting_description()

        parts = [desc]
        if lighting_desc:
            parts.append(lighting_desc)
        if style_prompt:
            parts.append(style_prompt)
        parts.append(self._build_quality_tags())

        return ", ".join(parts)

    def build_per_object_prompts(self) -> Dict[str, str]:
        """为所有对象生成独立提示词 {object_id: prompt}"""
        objects = self.shot.get("objects", [])
        return {
            obj["id"]: self.build_per_object_prompt(obj["id"])
            for obj in objects
        }

    def build_regional_prompt_set(self) -> Dict[str, Any]:
        """
        构建区域生成所需的完整提示词集

        Returns:
            {
                "global_positive": "全局正向提示词",
                "global_negative": "全局负向提示词",
                "regions": {
                    "child_1": {"positive": "...", "negative": "...", "type": "child"},
                    ...
                }
            }
        """
        objects = self.shot.get("objects", [])
        camera = self.shot.get("camera", {})
        view = camera.get("view", "front")

        lighting_desc = self._build_lighting_description()
        style_prompt = self.shot.get("style_prompt", "")

        regions = {}
        for obj in objects:
            obj_id = obj["id"]
            obj_type = obj.get("type", "object")
            obj_def = get_object_def(obj_type)

            if obj_def and obj_def.view_prompts and view in obj_def.view_prompts:
                view_rule = obj_def.view_prompts[view]
                pos_prompt = view_rule.positive
                neg_prompt = view_rule.negative or ""
            else:
                pos_prompt = self.OBJECT_DESCRIPTIONS.get(obj_type, obj_type)
                neg_prompt = ""

            region_parts = [pos_prompt]
            if lighting_desc:
                region_parts.append(lighting_desc)
            if style_prompt:
                region_parts.append(style_prompt)
            region_parts.append("focused subject, clean silhouette, clear shape, proper proportions")

            regions[obj_id] = {
                "positive": ", ".join(p for p in region_parts if p),
                "negative": neg_prompt,
                "type": obj_type,
            }

        quality_tags = self._build_quality_tags()

        background_template = self.shot.get("template", "indoor_room")
        bg_map = {"indoor_room": "indoor room background", "street": "city street background",
                   "bridge_river": "bridge over river background"}
        background_desc = bg_map.get(background_template, "scene background")

        global_positive = ", ".join(
            p for p in [background_desc, lighting_desc, style_prompt, quality_tags] if p
        )

        return {
            "global_positive": global_positive,
            "global_negative": self.build_negative_prompt(),
            "regions": regions,
        }

    def export_prompts(self) -> Dict[str, str]:
        """导出正负提示词"""
        return {
            "positive": self.build_prompt(),
            "negative": self.build_negative_prompt()
        }


def build_prompt_from_shot(shot_json: Dict[str, Any]) -> Dict[str, str]:
    """便捷函数：从 Shot JSON 构建提示词"""
    builder = PromptBuilder(shot_json)
    return builder.export_prompts()


if __name__ == "__main__":
    # 测试不同视角的提示词生成
    test_cases = [
        {
            "name": "侧面视角（人）",
            "shot": {
                "template": "indoor_room",
                "camera": {"view": "side", "shot": "medium"},
                "objects": [
                    {"id": "obj1", "type": "child", "position": "left"},
                    {"id": "obj2", "type": "table", "position": "center"},
                ],
                "lighting": {"type": "indoor_warm"},
                "style_prompt": "storybook illustration"
            }
        },
        {
            "name": "俯视视角（人）",
            "shot": {
                "template": "indoor_room",
                "camera": {"view": "top", "shot": "medium"},
                "objects": [
                    {"id": "obj1", "type": "child", "position": "left"},
                    {"id": "obj2", "type": "table", "position": "center"},
                ],
                "lighting": {"type": "indoor_warm"},
                "style_prompt": "storybook illustration"
            }
        },
        {
            "name": "俯视视角（树）",
            "shot": {
                "template": "outdoor",
                "camera": {"view": "top", "shot": "wide"},
                "objects": [
                    {"id": "obj1", "type": "tree", "position": "center"},
                ],
                "lighting": {"type": "day"},
                "style_prompt": "realistic"
            }
        },
    ]

    for test_case in test_cases:
        print(f"\n{'='*70}")
        print(f"测试: {test_case['name']}")
        print(f"{'='*70}")

        builder = PromptBuilder(test_case["shot"])
        prompts = builder.export_prompts()
        print("Positive:", prompts["positive"])
        print("\nNegative:", prompts["negative"][:200] + "...")
