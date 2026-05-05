"""
故事视频 Pipeline
解析故事文本，生成角色、场景、分镜结构
支持混合编排：预留数学动画插入点
"""

import json
import re
import time
from collections import OrderedDict
from typing import Optional, List, Dict, Tuple, Any
from httpx import RemoteProtocolError

from app.langchain_pipeline.story_structure import (
    Character,
    Scene,
    Shot,
    StorySturctureChainGenerator,
)
from app.configs.constants import (
    CHARACTER_PROMPT_TEMPLATE,
    SCENE_PROMPT_TEMPLATE,
    SHOT_PROMPT_TEMPLATE,
    STYLE_REALISTIC,
)
from app.service.base_pipeline import BasePipeline
from app.service.math_pipeline import run_math_pipeline
from app.utils.language_utils import estimate_narration_duration


AnchorStore = Dict[Tuple[str, int, str], dict]


class StoryPipeline(BasePipeline):
    """
    故事视频生成 Pipeline

    职责：
    - 解析故事文本为角色、场景、分镜结构
    - 生成图像提示词（保持角色一致性）
    - 支持标记数学动画插入点 {{MATH:article_id}}

    输出：
    - segments: 分镜列表，每个分镜包含：
        - shot_text: 旁白/TTS文本
        - image_prompt: 图像提示词
        - character_ids: 涉及的角色
        - type: "story" | "math_marker"
    """

    def __init__(self):
        super().__init__(StorySturctureChainGenerator)
        self.items: Optional[dict] = None
        self.scenes: Optional[List[Scene]] = None
        self.anchor_store: AnchorStore = {}
        self.character_dict: Dict[str, Character] = {}

    def parse(self, story: str) -> List[Scene]:
        """
        三阶段解析：角色 -> 场景 -> 分镜
        """
        # 1. 提取角色
        items = self._extract_characters(story)
        character_list = [Character(**c) for c in items.get("characters", [])]
        self.character_dict: Dict[str, Character] = {c.character_id: c for c in character_list}

        # 2. 划分场景
        scenes = self._segment_scenes(story, items)

        # 3. 为每个场景生成分镜
        for scene in scenes:
            shots = self._generate_shots(scene)
            scene.shots = shots

        self.scenes = scenes
        return scenes

    def generate(
        self,
        story: str,
        style_tokens: str = STYLE_REALISTIC,
        math_model_name: str = None,
        math_api_key: str = "",
        math_output_dir=None,
    ) -> Dict[str, Any]:
        """
        执行完整故事生成流程

        Args:
            story: 故事文本（可包含 {{MATH:article_id}} 标记）
            style_tokens: 视觉风格
            math_model_name: 数学模型名称（可选，用于处理数学标记）
            math_api_key: 数学模型API密钥（可选）

        Returns:
            Dict 包含：
            - segments: 分镜列表（含类型标记）
            - characters: 角色列表
            - anchor_store: 一致性存储
        """
        # 检查是否包含数学动画标记
        math_markers = list(re.finditer(r"\{\{MATH:(.*?)\}\}", story))
        math_contents = [match.group(1).strip() for match in math_markers]
        math_positions = [match.start() for match in math_markers]  # 字符位置

        # 移除标记后解析故事结构
        clean_story = re.sub(r"\{\{MATH:.*?\}\}", "", story)
        scenes = self.parse(clean_story)

        # 为 mw 生成结构化世界状态
        character_specs = self._export_character_specs()
        world_scenes, scene_to_world_scene = self._build_world_scenes(scenes)

        # 建立shot_text在clean_story中的位置映射
        shot_position_map = self._map_shots_to_text_positions(scenes, clean_story)

        # 生成故事segments并与位置映射关联
        story_segments_with_pos = []  # [(story_segment, shot, scene, start, end), ...]
        shot_idx = 0

        for scene_idx, scene in enumerate(scenes):
            for shot in scene.shots:
                # 查找这个shot在位置映射中的条目
                pos_entry = None
                for entry in shot_position_map:
                    if entry[0] == shot:  # entry[0]是shot对象
                        pos_entry = entry
                        break

                # 构建图像提示词（保持角色一致性）
                prompt = self._build_image_prompt(scene=scene, shot=shot, style_tokens=style_tokens)

                scene_id = str(scene.scene_info.scene_id)
                story_segment = {
                    "scene_idx": scene_idx,
                    "scene_id": scene_id,
                    "world_scene_id": scene_to_world_scene.get(scene_id, ""),
                    "shot_idx": shot_idx,
                    "shot_id": shot.shot_id,
                    "type": "story",
                    "text": shot.shot_text,
                    "image_prompt": prompt,
                    "focus_characters": shot.focus_characters,
                    "duration": self._estimate_duration(shot.shot_text),
                    "background_prompt": prompt,  # 用于后续math segment继承背景
                }

                if pos_entry:
                    # entry格式: (shot, scene, start, end)
                    story_segments_with_pos.append(
                        (story_segment, pos_entry[0], pos_entry[1], pos_entry[2], pos_entry[3])
                    )
                else:
                    # 如果没有找到位置映射，使用默认值
                    story_segments_with_pos.append((story_segment, shot, scene, 0, 0))

                shot_idx += 1

        flat_shots = [shot for scene in scenes for shot in scene.shots]

        # 如果没有数学标记或未提供数学模型，直接返回故事segments
        if not math_contents or math_model_name is None:
            story_segments_only = [seg for seg, _, _, _, _ in story_segments_with_pos]
            return {
                "segments": story_segments_only,
                "characters": list(self.character_dict.values()),
                "character_specs": character_specs,
                "items": self.items or {},
                "scenes": scenes,
                "world_scenes": world_scenes,
                "scene_to_world_scene": scene_to_world_scene,
                "shots": flat_shots,
                "anchor_store": self.anchor_store,
                "scene_count": len(scenes),
                "world_scene_count": len(world_scenes),
                "shot_count": len(story_segments_only),
            }

        # 转换数学标记位置：原始位置 -> clean_story位置
        math_clean_positions = []
        for math_pos in math_positions:
            clean_pos = self._convert_to_clean_position(math_pos, story, math_markers)
            math_clean_positions.append(clean_pos)

        # 为每个数学标记确定插入点（在哪个shot之后）
        # 规则：数学标记在clean_story中的位置落在哪个shot的文本范围内（start <= pos < end）
        # 或者在前一个shot之后
        insertion_plan = []  # [(insert_after_shot_idx, math_idx), ...]

        for math_idx, clean_pos in enumerate(math_clean_positions):
            insert_after_idx = -1  # -1表示插入在开头（第一个shot之前）

            # 查找数学标记应该在哪个shot之后插入
            for seg_idx, (story_seg, shot, scene, start, end) in enumerate(story_segments_with_pos):
                if start <= clean_pos < end:
                    # 数学标记在这个shot的文本范围内，插入在这个shot之后
                    insert_after_idx = seg_idx
                    break
                elif clean_pos < start and insert_after_idx == -1:
                    # 数学标记在这个shot之前，且还没有找到插入点
                    # 插入在前一个shot之后（或开头）
                    insert_after_idx = seg_idx - 1
                    break

            # 如果遍历完所有shots还没有找到，插入在最后一个shot之后
            if insert_after_idx == -1:
                insert_after_idx = len(story_segments_with_pos) - 1

            insertion_plan.append((insert_after_idx, math_idx))

        # 处理每个数学标记，生成数学segments
        math_segments_by_idx = {}  # math_idx -> list of math segments
        math_animation_files_all = []  # 收集所有数学动画文件路径

        for math_idx, math_content in enumerate(math_contents):
            # 调用数学pipeline生成动画
            try:
                math_result = run_math_pipeline(
                    article=math_content,
                    model_name=math_model_name,
                    api_key=math_api_key,
                    output_dir=math_output_dir,
                )
                math_lines = math_result.get("lines", [])
                math_animations = math_result.get("math_animations", [])
            except Exception as e:
                print(f"数学pipeline处理失败（标记{math_idx}）: {e}")
                # 跳过该数学标记，继续处理后续
                continue

            # 确定这个数学标记的插入点
            insert_after_idx = next((idx for idx, midx in insertion_plan if midx == math_idx), -1)

            # 获取背景提示词
            background_prompt = None
            if insert_after_idx >= 0 and insert_after_idx < len(story_segments_with_pos):
                # 使用插入点之前的story segment的背景
                story_seg, shot, scene, start, end = story_segments_with_pos[insert_after_idx]
                # background_prompt = story_seg.get("background_prompt")
                background_prompt = "use previous background"
            elif story_segments_with_pos:
                # 回退到第一个story segment的背景
                # background_prompt = story_segments_with_pos[0][0].get("background_prompt")
                background_prompt = "use first background"
            else:
                # 没有story segment，使用默认背景
                background_prompt = "abstract background, neutral colors"

            # 为每个数学shot创建segment
            segments_for_this_math = []
            for anim_idx, (narration, anim_path) in enumerate(zip(math_lines, math_animations)):
                math_segment = {
                    "type": "math",
                    "math_idx": math_idx,
                    "anim_idx": anim_idx,
                    "narration": narration,
                    "math_animation_path": anim_path,
                    "background_prompt": background_prompt,
                    "duration": self._estimate_duration(narration),
                    "math_content": math_content[:100] + "..."
                    if len(math_content) > 100
                    else math_content,
                }
                segments_for_this_math.append(math_segment)
                math_animation_files_all.append(anim_path)

            math_segments_by_idx[math_idx] = segments_for_this_math

        # 组合segments：按插入位置将数学segments插入到故事segments中
        all_segments = []

        # 构建插入映射：每个插入点之后要插入哪些数学segments
        # 注意：insert_after_idx = n 表示在第n个story segment之后插入
        insertion_map = {}
        for insert_after_idx, math_idx in insertion_plan:
            if math_idx in math_segments_by_idx:
                if insert_after_idx not in insertion_map:
                    insertion_map[insert_after_idx] = []
                insertion_map[insert_after_idx].extend(math_segments_by_idx[math_idx])

        # 按顺序构建all_segments
        for seg_idx in range(len(story_segments_with_pos)):
            # 添加当前的story segment
            story_seg, _, _, _, _ = story_segments_with_pos[seg_idx]
            all_segments.append(story_seg)

            # 检查是否有数学segments需要插入在这个story segment之后
            if seg_idx in insertion_map:
                all_segments.extend(insertion_map[seg_idx])

        # 检查是否有数学segments需要插入在最后（在最后一个story segment之后）
        last_idx = len(story_segments_with_pos) - 1
        if last_idx in insertion_map:
            # 已经在上面的循环中处理了（当seg_idx == last_idx时）
            pass
        # 特殊情况：插入在开头之前（insert_after_idx = -1）
        if -1 in insertion_map:
            all_segments = insertion_map[-1] + all_segments

        return {
            "segments": all_segments,
            "characters": list(self.character_dict.values()),
            "character_specs": character_specs,
            "items": self.items or {},
            "scenes": scenes,
            "world_scenes": world_scenes,
            "scene_to_world_scene": scene_to_world_scene,
            "shots": flat_shots,
            "anchor_store": self.anchor_store,
            "scene_count": len(scenes),
            "world_scene_count": len(world_scenes),
            "shot_count": len(all_segments),
            "math_animation_files": math_animation_files_all,
            "has_math": len(math_segments_by_idx) > 0,
        }

    def _extract_characters(self, story: str) -> dict:
        """提取角色信息"""
        prompt = self._render_template(CHARACTER_PROMPT_TEMPLATE, story=story)
        raw = self._call_llm(prompt)
        cleaned = raw.replace("```json", "").replace("```", "")
        self.items = json.loads(cleaned)
        return self.items

    def _segment_scenes(self, story: str, items: dict) -> List[Scene]:
        """划分场景"""
        prompt = self._render_template(SCENE_PROMPT_TEMPLATE, story=story, items=items)
        raw = self._call_llm(prompt)
        cleaned = raw.replace("```json", "").replace("```", "")
        scene_list = json.loads(cleaned)
        return [Scene(**s) for s in scene_list]

    def _generate_shots(self, scene: Scene) -> List[Shot]:
        """为场景生成分镜"""
        prompt = self._render_template(
            SHOT_PROMPT_TEMPLATE,
            scene_text=scene.scene_text,
            scene_info=scene.scene_info.model_dump_json(),
        )
        raw = self._call_llm(prompt)
        cleaned = raw.replace("```json", "").replace("```", "")
        shot_list = json.loads(cleaned)
        return [Shot(**sd) for sd in shot_list]

    def _export_character_specs(self) -> List[Dict[str, Any]]:
        """导出适合 mw 的角色规格。"""
        specs = []
        for char in self.character_dict.values():
            specs.append(
                {
                    "character_id": char.character_id,
                    "name": char.name,
                    "object_type": self._normalize_character_object_type(char.type),
                    "description": char.visual_core,
                    "visual_core": char.visual_core,
                    "visual_variants_allowed": char.visual_variants_allowed,
                    "key_features": self._extract_key_features(char),
                    "style_tags": char.style_tags,
                    "is_main_character": char.is_main,
                }
            )
        return specs

    def _build_world_scenes(self, scenes: List[Scene]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """将时序 scenes 归并为固定场景层。"""
        world_scene_index: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        scene_to_world_scene: Dict[str, str] = {}

        for scene in scenes:
            scene_info = scene.scene_info
            location = (scene_info.location or "unknown_location").strip().lower()
            time_value = (scene_info.time or "unspecified_time").strip().lower()
            characters = sorted(scene_info.characters_in_scene or [])
            objects = sorted(scene_info.objects_in_scene or [])
            world_key = self._build_world_scene_key(location, time_value, characters, objects)

            if world_key not in world_scene_index:
                world_scene_index[world_key] = {
                    "world_scene_id": world_key,
                    "source_scene_ids": [str(scene_info.scene_id)],
                    "location": scene_info.location,
                    "time": scene_info.time,
                    "emotion": scene_info.emotion,
                    "chain_id": scene_info.chain_id,
                    "characters_in_scene": characters,
                    "objects_in_scene": objects,
                    "scene_visual_overrides": dict(scene_info.scene_visual_overrides or {}),
                    "template": self._infer_template(scene_info.location, objects),
                    "style_id": "default",
                }
            else:
                entry = world_scene_index[world_key]
                entry["source_scene_ids"].append(str(scene_info.scene_id))
                entry["characters_in_scene"] = sorted(set(entry["characters_in_scene"]) | set(characters))
                entry["objects_in_scene"] = sorted(set(entry["objects_in_scene"]) | set(objects))
                entry["scene_visual_overrides"].update(scene_info.scene_visual_overrides or {})
                if not entry.get("emotion") and scene_info.emotion:
                    entry["emotion"] = scene_info.emotion
                if not entry.get("chain_id") and scene_info.chain_id:
                    entry["chain_id"] = scene_info.chain_id

            scene_to_world_scene[str(scene_info.scene_id)] = world_key

        return list(world_scene_index.values()), scene_to_world_scene

    def _build_world_scene_key(
        self,
        location: str,
        time_value: str,
        characters: List[str],
        objects: List[str],
    ) -> str:
        normalized_location = re.sub(r"[^a-z0-9]+", "_", location).strip("_") or "scene"
        normalized_time = re.sub(r"[^a-z0-9]+", "_", time_value).strip("_") or "time"
        char_token = str(len(characters))
        obj_token = str(len(objects))
        return f"{normalized_location}_{normalized_time}_{char_token}c_{obj_token}o"

    def _infer_template(self, location: Optional[str], objects: List[str]) -> str:
        location_text = (location or "").lower()
        object_text = " ".join(objects).lower()
        combined = f"{location_text} {object_text}"
        if any(token in combined for token in ["bridge", "river", "lake", "stream"]):
            return "bridge_river"
        if any(token in combined for token in ["street", "road", "city", "avenue"]):
            return "street"
        return "indoor_room"

    def _normalize_character_object_type(self, char_type: str) -> str:
        normalized = (char_type or "").lower()
        if normalized in {"human", "person"}:
            return "adult"
        if normalized in {"animal", "object"}:
            return normalized
        return normalized or "adult"

    def _extract_key_features(self, char: Character) -> List[str]:
        source = char.visual_core or ""
        features = [part.strip() for part in source.split(",") if part.strip()]
        return features[:8]

    def _build_image_prompt(self, scene: Scene, shot: Shot, style_tokens: str) -> str:
        """
        构建图像提示词（支持角色一致性）
        """
        # 1. 角色描述
        char_desc_list = []
        for cid in shot.focus_characters:
            char = self.character_dict.get(cid)
            if not char:
                continue
            base = char.visual_core
            override = scene.scene_info.scene_visual_overrides.get(cid, "")
            char_desc = base
            if override:
                char_desc += f", {override}"
            char_desc_list.append(char_desc)

        characters_part = ", ".join(char_desc_list)

        # 2. 环境描述
        env_parts = [scene.scene_info.location]
        if scene.scene_info.time:
            env_parts.append(scene.scene_info.time)
        if scene.scene_info.emotion:
            env_parts.append(f"mood: {scene.scene_info.emotion}")
        environment_part = ", ".join(env_parts)

        # 3. 镜头语言
        shot_desc = []
        if shot.shot_type:
            shot_desc.append(f"{shot.shot_type} shot")
        if shot.camera_move and shot.camera_move != "static":
            shot_desc.append(f"camera {shot.camera_move.replace('_', ' ')}")
        if shot.lighting:
            shot_desc.append(shot.lighting)
        if shot.additional_detail:
            if isinstance(shot.additional_detail, list):
                shot_desc.extend(shot.additional_detail)
            else:
                shot_desc.append(shot.additional_detail)
        shot_part = ", ".join(shot_desc)

        # 组合
        prompt = f"{characters_part}, in {environment_part}, {shot_part}, {style_tokens}"
        return prompt

    def _estimate_duration(self, text: str) -> float:
        return estimate_narration_duration(text)

    def _map_shots_to_text_positions(self, scenes, clean_story):
        """
        建立shot_text在clean_story中的位置映射

        Args:
            scenes: 解析后的场景列表
            clean_story: 移除数学标记后的干净故事文本

        Returns:
            list: [(shot, scene, start_pos, end_pos), ...]
        """
        position_map = []
        current_pos = 0

        for scene in scenes:
            for shot in scene.shots:
                shot_text = shot.shot_text
                # 在clean_story中查找shot_text
                if not shot_text:
                    continue

                # 尝试从current_pos开始查找
                found_pos = clean_story.find(shot_text, current_pos)
                if found_pos != -1:
                    start = found_pos
                    end = found_pos + len(shot_text)
                    position_map.append((shot, scene, start, end))
                    current_pos = end  # 继续查找下一个
                else:
                    # 如果找不到，尝试从头查找（fallback）
                    found_pos = clean_story.find(shot_text)
                    if found_pos != -1:
                        start = found_pos
                        end = found_pos + len(shot_text)
                        position_map.append((shot, scene, start, end))
                        current_pos = end
                    else:
                        # 仍然找不到，使用估计位置
                        print(f"警告：无法找到shot_text在clean_story中: {shot_text[:50]}...")
                        # 使用当前位置作为估计
                        position_map.append(
                            (shot, scene, current_pos, current_pos + len(shot_text))
                        )
                        current_pos += len(shot_text)

        return position_map

    def _convert_to_clean_position(self, original_pos, _story, math_markers):
        """
        将原始位置转换为clean_story中的位置
        减去之前所有数学标记的长度

        Args:
            original_pos: 在原始story中的位置
            _story: 原始故事文本（未使用，为兼容性保留）
            math_markers: re.finditer结果列表

        Returns:
            int: clean_story中的位置
        """
        clean_pos = original_pos

        # 计算在original_pos之前的所有数学标记的总长度
        for marker in math_markers:
            if marker.start() < original_pos:
                # 减去{{MATH:...}}的完整长度
                clean_pos -= len(marker.group(0))

        return clean_pos

    def _get_scene_background_prompt(self, scene, style_tokens):
        """
        获取场景的通用背景提示词
        用于数学segment的背景继承

        Args:
            scene: 场景对象
            style_tokens: 视觉风格

        Returns:
            str: 背景提示词
        """
        # 基于场景的环境描述构建背景
        env_parts = [scene.scene_info.location]
        if scene.scene_info.time:
            env_parts.append(scene.scene_info.time)
        if scene.scene_info.emotion:
            env_parts.append(f"mood: {scene.scene_info.emotion}")

        environment_part = ", ".join(env_parts)
        return f"{environment_part}, {style_tokens}"

    def call_llm_with_retry(self, messages, max_retries: int = 3):
        """带重试的 LLM 调用"""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return self._call_llm(messages)
            except RemoteProtocolError as e:
                last_exc = e
                print(f"[LLM] attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    raise
                time.sleep(2 * attempt)


def run_story_pipeline(
    story: str,
    model_name: str,
    api_key: str,
    style_tokens: str = STYLE_REALISTIC,
    math_model_name: str = None,
    math_api_key: str = "",
    math_output_dir=None,
):
    """
    便捷的故事 Pipeline 运行函数

    Args:
        story: 故事文本（可包含 {{MATH:...}} 标记）
        model_name: 故事解析模型名称
        api_key: 故事解析API密钥
        style_tokens: 视觉风格
        math_model_name: 数学模型名称（可选，用于处理数学标记）
        math_api_key: 数学模型API密钥（可选）

    Returns:
        如果 math_model_name 为 None：返回 (lines, prompts) 元组（向后兼容）
        否则：返回 Dict 包含 segments, characters, anchor_store 等
    """
    pipeline = StoryPipeline()
    pipeline.use_model(model_name, api_key)

    try:
        result = pipeline.generate(
            story,
            style_tokens,
            math_model_name,
            math_api_key,
            math_output_dir=math_output_dir,
        )
    finally:
        pipeline.release_model()

    # 向后兼容：如果未提供数学模型，返回 (lines, prompts) 元组
    if math_model_name is None:
        segments = result.get("segments", [])
        # 只提取story类型的segments
        lines = [seg.get("text", "") for seg in segments if seg.get("type") == "story"]
        prompts = [seg.get("image_prompt", "") for seg in segments if seg.get("type") == "story"]
        return (lines, prompts)
    else:
        return result
