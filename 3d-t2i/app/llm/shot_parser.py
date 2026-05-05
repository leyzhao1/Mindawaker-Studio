"""
Shot Parser - 使用 LLM 将自然语言文本解析为结构化 Shot JSON
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.schema.shot_model import ShotJSON, validate_shot_json, safe_validate_shot_json


# 默认系统提示词
DEFAULT_SYSTEM_PROMPT = """You are a specialized parser for converting scene descriptions into structured JSON format for 3D scene generation.

Your task is to analyze the input text and output a valid JSON object following this exact schema:

{
  "template": "indoor_room" | "street" | "bridge_river",
  "camera": {
    "view": "front" | "side" | "top" | "three_quarter" | "low_angle" | "high_angle",
    "shot": "extreme_closeup" | "closeup" | "medium" | "full" | "wide" | "establishing"
  },
  "objects": [
    {
      "id": "unique_id",
      "type": "child" | "adult" | "table" | "chair" | "flowerpot" | "book" | "lamp" | "building" | "tree" | "car" | "bridge" | "river",
      "position": "left" | "center" | "right" | "front" | "back",
      "relation": "on_top_of:id" | "beside:id" | "behind:id" | "in_front_of:id" (optional)
    }
  ],
  "lighting": {
    "type": "day" | "night" | "sunset" | "indoor_warm" | "indoor_cool"
  },
  "style_prompt": "descriptive style keywords for image generation"
}

Rules:
1. Determine template based on scene type (室内->indoor_room, 街道->street, 桥/河->bridge_river)
2. Infer camera view from perspective descriptions (侧面->side, 正面->front, etc.)
3. Map objects to predefined types (孩子->child, 桌子->table, 花盆->flowerpot)
4. Use "relation" for objects that are "on top of", "beside", "behind", or "in front of" other objects
5. Generate an appropriate style_prompt based on the mood/atmosphere described
6. Output ONLY valid JSON, no markdown, no explanations

Examples:

Input: "室内，一个孩子站在桌边，桌上有花盆，侧面视角，温暖的灯光"
Output:
{
  "template": "indoor_room",
  "camera": {"view": "side", "shot": "medium"},
  "objects": [
    {"id": "child1", "type": "child", "position": "left"},
    {"id": "table1", "type": "table", "position": "center"},
    {"id": "flowerpot1", "type": "flowerpot", "relation": "on_top_of:table1"}
  ],
  "lighting": {"type": "indoor_warm"},
  "style_prompt": "warm indoor lighting, cozy atmosphere, storybook illustration"
}

Input: "城市街道，远景拍摄，日落时分"
Output:
{
  "template": "street",
  "camera": {"view": "front", "shot": "establishing"},
  "objects": [],
  "lighting": {"type": "sunset"},
  "style_prompt": "urban street scene, golden hour sunset, cinematic wide shot"
}
"""


class ShotParser:
    """Shot 解析器"""

    def __init__(self, provider: str = "openai", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key or os.getenv(f"{provider.upper()}_API_KEY")
        self.system_prompt = DEFAULT_SYSTEM_PROMPT

    def parse(self, text: str, validate: bool = True) -> Dict[str, Any]:
        """
        解析文本为 Shot JSON

        Args:
            text: 自然语言描述
            validate: 是否使用 Pydantic 验证输出

        Returns:
            解析后的 Shot JSON 字典
        """
        if self.provider == "openai":
            result = self._parse_with_openai(text)
        elif self.provider == "anthropic":
            result = self._parse_with_anthropic(text)
        elif self.provider == "deepseek":
            result = self._parse_with_deepseek(text)
        else:
            result = self._parse_rule_based(text)

        # Pydantic 验证
        if validate:
            try:
                validated = validate_shot_json(result)
                return validated.to_dict()
            except Exception as e:
                print(f"Warning: Shot JSON validation failed: {e}")
                print("Returning unvalidated result")
                return result

        return result

    def parse_with_validation(self, text: str) -> Tuple[bool, Union[Dict[str, Any], str]]:
        """
        解析文本并返回详细的验证结果

        Returns:
            (是否成功, Shot JSON字典或错误信息)
        """
        try:
            if self.provider == "openai":
                result = self._parse_with_openai(text)
            elif self.provider == "anthropic":
                result = self._parse_with_anthropic(text)
            elif self.provider == "deepseek":
                result = self._parse_with_deepseek(text)
            else:
                result = self._parse_rule_based(text)

            success, validated = safe_validate_shot_json(result)
            if success:
                return True, validated.to_dict()
            else:
                return False, f"Validation error: {validated}"

        except Exception as e:
            return False, f"Parse error: {str(e)}"

    def _parse_with_openai(self, text: str) -> Dict[str, Any]:
        """使用 OpenAI API 解析"""
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            return self._extract_json(content)

        except ImportError:
            print("OpenAI package not installed, falling back to rule-based parser")
            return self._parse_rule_based(text)
        except Exception as e:
            print(f"OpenAI API error: {e}, falling back to rule-based parser")
            return self._parse_rule_based(text)

    def _parse_with_anthropic(self, text: str) -> Dict[str, Any]:
        """使用 Anthropic API 解析"""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.3,
                system=self.system_prompt,
                messages=[{"role": "user", "content": text}]
            )

            content = response.content[0].text
            return self._extract_json(content)

        except ImportError:
            print("Anthropic package not installed, falling back to rule-based parser")
            return self._parse_rule_based(text)
        except Exception as e:
            print(f"Anthropic API error: {e}, falling back to rule-based parser")
            return self._parse_rule_based(text)

    def _parse_with_deepseek(self, text: str) -> Dict[str, Any]:
        """使用 DeepSeek API 解析"""
        try:
            import requests
            # api_key 优先级：构造参数 > DEEPSEEK_API_KEY 环境变量
            api_key = self.api_key or os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                print("DEEPSEEK_API_KEY not set, falling back to rule-based parser")
                return self._parse_rule_based(text)

            resp = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.3,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return self._extract_json(content)

        except ImportError:
            print("requests package not installed, falling back to rule-based parser")
            return self._parse_rule_based(text)
        except Exception as e:
            print(f"DeepSeek API error: {e}, falling back to rule-based parser")
            return self._parse_rule_based(text)

    def _parse_rule_based(self, text: str) -> Dict[str, Any]:
        """
        基于规则的解析器（Fallback）
        修复：长词优先匹配、已命中片段不重复识别、环境词不生成实体
        """
        # 保留原始文本用于环境词检测
        original_text = text
        text_lower = text.lower()

        # ========== 检测模板 ==========
        template = "indoor_room"
        if "街道" in original_text or "街" in original_text or "马路" in original_text:
            template = "street"
        elif "桥" in original_text or "河" in original_text:
            template = "bridge_river"

        # ========== 检测相机视角 ==========
        view = "side"
        if "正面" in original_text or "前视" in original_text:
            view = "front"
        elif "侧面" in original_text or "侧视" in original_text:
            view = "side"
        elif "俯视" in original_text or "顶视" in original_text:
            view = "top"
        elif "仰角" in original_text or "低角度" in original_text:
            view = "low_angle"
        elif "俯角" in original_text or "高角度" in original_text:
            view = "high_angle"

        shot = "medium"
        if "特写" in original_text or "近景" in original_text:
            shot = "closeup"
        elif "中景" in original_text:
            shot = "medium"
        elif "远景" in original_text or "全景" in original_text:
            shot = "wide"

        # ========== 环境词检测（不生成实体） ==========
        # 这些词描述环境/氛围，不应创建为实体对象
        ENVIRONMENTAL_WORDS = {
            "灯光", "光", "照明",  # 灯光是环境，不是实体 lamp
            "天气", "气候",
            "氛围", "气氛",
            "色调", "色彩", "颜色",
            "背景", "前景",
            "阴影", "影子",
        }

        # 标记环境词位置，用于后续排除
        excluded_ranges = []
        for env_word in ENVIRONMENTAL_WORDS:
            idx = 0
            while True:
                pos = original_text.find(env_word, idx)
                if pos == -1:
                    break
                excluded_ranges.append((pos, pos + len(env_word)))
                idx = pos + 1

        def is_in_excluded_range(pos: int, length: int) -> bool:
            """检查位置是否在环境词范围内"""
            for start, end in excluded_ranges:
                if start <= pos < end or start < pos + length <= end:
                    return True
            return False

        # ========== 物体检测（长词优先 + 防重复） ==========
        objects = []
        object_counter = {}
        matched_ranges = []  # 记录已匹配的文本范围

        # 物体映射 - 按长度降序排列（长词优先匹配）
        object_mappings = [
            ("孩子", "child"),
            ("小孩", "child"),
            ("成人", "adult"),
            ("桌子", "table"),
            ("椅子", "chair"),
            ("花盆", "flowerpot"),
            ("建筑", "building"),
            ("房子", "building"),
            ("汽车", "car"),
            ("人", "adult"),      # 短词放后面
            ("桌", "table"),
            ("椅", "chair"),
            ("花", "flowerpot"),  # 注意："花"可能在"花盆"中被匹配，需要防重复
            ("书", "book"),
            ("灯", "lamp"),       # 但"灯光"已被排除
            ("楼", "building"),
            ("树", "tree"),
            ("木", "tree"),
            ("车", "car"),
            ("桥", "bridge"),
            ("河", "river"),
            ("江", "river"),
        ]

        position_mappings = [
            ("左边", "left"),
            ("右侧", "right"),
            ("左侧", "left"),
            ("右边", "right"),
            ("中央", "center"),
            ("中间", "center"),
            ("前面", "front"),
            ("后面", "back"),
            ("左", "left"),       # 短词放后面
            ("右", "right"),
            ("中", "center"),
            ("前", "front"),
            ("后", "back"),
        ]

        # 长词优先的物体检测
        for cn_name, en_type in object_mappings:
            idx = 0
            while True:
                pos = original_text.find(cn_name, idx)
                if pos == -1:
                    break

                # 检查是否与环境词重叠
                if is_in_excluded_range(pos, len(cn_name)):
                    idx = pos + len(cn_name)
                    continue

                # 检查是否与已匹配区域重叠
                overlap = False
                for matched_start, matched_end in matched_ranges:
                    if not (pos + len(cn_name) <= matched_start or pos >= matched_end):
                        overlap = True
                        break

                if overlap:
                    idx = pos + len(cn_name)
                    continue

                # 记录匹配范围
                matched_ranges.append((pos, pos + len(cn_name)))

                # 创建对象
                obj_id = f"{en_type}_{object_counter.get(en_type, 0) + 1}"
                object_counter[en_type] = object_counter.get(en_type, 0) + 1

                # 确定位置（查找附近的位置描述词）
                position = self._find_nearest_position(
                    original_text, pos, len(cn_name), position_mappings
                )

                obj_def = {
                    "id": obj_id,
                    "type": en_type,
                    "position": position
                }

                objects.append(obj_def)
                idx = pos + len(cn_name)

        # ========== 检测关系（改进版）==========
        # 基于文本中的关系词和对象位置建立关系
        objects = self._assign_relations(original_text, objects)

        # ========== 检测光照 ==========
        lighting_type = "day"
        if "室内" in original_text or "房间" in original_text:
            if "温暖" in original_text or "暖" in original_text or "黄" in original_text:
                lighting_type = "indoor_warm"
            else:
                lighting_type = "indoor_cool"
        elif "夜晚" in original_text or "晚上" in original_text or "夜" in original_text:
            lighting_type = "night"
        elif "日落" in original_text or "黄昏" in original_text or "夕阳" in original_text:
            lighting_type = "sunset"

        # ========== 生成风格提示词 ==========
        style_keywords = []
        if "插画" in original_text or "画" in original_text:
            style_keywords.append("illustration")
        if "温暖" in original_text or "暖" in original_text:
            style_keywords.append("warm lighting")
        if "冷" in original_text:
            style_keywords.append("cool tone")

        if not style_keywords:
            style_keywords = ["photorealistic"]

        style_prompt = ", ".join(style_keywords)

        return {
            "template": template,
            "camera": {
                "view": view,
                "shot": shot
            },
            "objects": objects,
            "lighting": {
                "type": lighting_type
            },
            "style_prompt": style_prompt
        }

    def _find_nearest_position(
        self,
        text: str,
        obj_pos: int,
        obj_len: int,
        position_mappings: list
    ) -> str:
        """
        查找物体附近的位置描述词

        Args:
            text: 完整文本
            obj_pos: 物体词在文本中的位置
            obj_len: 物体词长度
            position_mappings: 位置映射列表

        Returns:
            位置描述（left/right/center/front/back）
        """
        # 搜索范围：物体前后30个字符
        search_start = max(0, obj_pos - 30)
        search_end = min(len(text), obj_pos + obj_len + 30)
        search_text = text[search_start:search_end]

        # 按顺序查找第一个匹配的位置词
        for cn_pos, en_pos in position_mappings:
            if cn_pos in search_text:
                return en_pos

        return "center"

    def _assign_relations(self, text: str, objects: list) -> list:
        """
        基于文本分析为对象分配关系

        改进：基于句子结构和相对位置判断关系
        """
        if len(objects) < 2:
            return objects

        # 查找 "X 上/旁边/前面/后面 有 Y" 这样的句式
        relation_keywords = {
            "上": "on_top_of",
            "上面": "on_top_of",
            "之上": "on_top_of",
            "旁边": "beside",
            "边": "beside",
            "前面": "in_front_of",
            "前方": "in_front_of",
            "后面": "behind",
            "后方": "behind",
            "里": "inside",
            "里面": "inside",
            "内": "inside",
        }

        # 支持对象的类型（可以被其他物体放在上面的）
        support_types = {"table", "chair"}
        top_placeable_types = {"flowerpot", "book", "lamp"}

        # 简单启发式：如果文本中有 "上" 或 "上面"
        # 且有 support 类型对象和可放置对象，建立关系
        text_lower = text.lower()

        for i, obj in enumerate(objects):
            obj_type = obj["type"]

            # 只对可放置对象建立关系
            if obj_type not in top_placeable_types:
                continue

            # 查找最近的支撑物（在对象列表中排在前面的）
            for j in range(i):
                potential_support = objects[j]
                if potential_support["type"] in support_types:
                    # 检查文本中是否有关系词连接这两个概念
                    obj_pos = text.find(obj["id"].split("_")[0])  # 简化处理
                    support_pos = text.find(potential_support["id"].split("_")[0])

                    if obj_pos > support_pos:  # 物体在支撑物之后提到
                        # 检查中间是否有关系词
                        middle_text = text[support_pos:obj_pos]
                        if any(kw in middle_text for kw in ["上", "上面", "顶"]):
                            obj["relation"] = f"on_top_of:{potential_support['id']}"
                            break

        # 额外处理：如果文本中有 "桌上有X" 这样的明确表述
        for support_type in support_types:
            support_pattern = f"{support_type}"
            if support_type == "table":
                support_pattern = "桌"
            elif support_type == "chair":
                support_pattern = "椅"

            for rel_kw, rel_type in [("上", "on_top_of"), ("旁边", "beside")]:
                pattern = f"{support_pattern}{rel_kw}有"
                if pattern in text or f"{support_pattern}{rel_kw}放着" in text:
                    # 找到支撑物和其后的第一个可放置物体
                    support_obj = None
                    for obj in objects:
                        if obj["type"] == support_type:
                            support_obj = obj
                            break

                    if support_obj:
                        for obj in objects:
                            if obj["type"] in top_placeable_types and "relation" not in obj:
                                obj["relation"] = f"{rel_type}:{support_obj['id']}"
                                break

        return objects

    def _extract_json(self, content: str) -> Dict[str, Any]:
        """从 LLM 输出中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取代码块中的 JSON
        import re
        json_pattern = r'```(?:json)?\s*([\s\S]*?)```'
        matches = re.findall(json_pattern, content)

        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # 尝试查找花括号包裹的内容
        brace_pattern = r'\{[\s\S]*\}'
        match = re.search(brace_pattern, content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # 如果都失败了，返回一个默认结构
        print("Failed to extract valid JSON, using fallback")
        return {
            "template": "indoor_room",
            "camera": {"view": "side", "shot": "medium"},
            "objects": [],
            "lighting": {"type": "indoor_warm"},
            "style_prompt": "realistic rendering"
        }


def parse_shot(text: str, provider: str = "openai", validate: bool = True) -> Dict[str, Any]:
    """便捷函数：解析文本为 Shot JSON"""
    parser = ShotParser(provider=provider)
    return parser.parse(text, validate=validate)


def parse_shot_safe(text: str, provider: str = "openai") -> Tuple[bool, Union[Dict[str, Any], str]]:
    """
    安全解析文本为 Shot JSON，返回详细的验证结果

    Returns:
        (是否成功, Shot JSON字典或错误信息)
    """
    parser = ShotParser(provider=provider)
    return parser.parse_with_validation(text)


if __name__ == "__main__":
    # 测试
    test_text = "室内，一个孩子站在桌边，桌上有花盆，侧面视角，温暖灯光"
    result = parse_shot(test_text, provider="rule")
    print(json.dumps(result, indent=2, ensure_ascii=False))
