from __future__ import annotations

from media_service.model.schemas import PreferMediaType, QueryIntent
from media_service.utils.text import estimate_text_duration, split_texts, tokenize_text


PACE_KEYWORDS = {
    "fast": ["快", "快速", "激烈", "追逐", "冲刺", "action", "fast"],
    "slow": ["慢", "安静", "舒缓", "平静", "空镜", "slow", "calm"],
}
EMOTION_KEYWORDS = {
    "joyful": ["开心", "快乐", "温暖", "明亮", "joy", "happy"],
    "melancholic": ["忧郁", "伤感", "孤独", "冷清", "sad", "blue"],
    "tense": ["紧张", "压迫", "危险", "悬疑", "tense", "thriller"],
    "dramatic": ["戏剧", "高潮", "震撼", "dramatic"],
    "calm": ["平静", "治愈", "轻松", "calm", "quiet"],
}
ROLE_KEYWORDS = {
    "background": ["背景", "空镜", "环境", "场景", "远景"],
    "action": ["动作", "奔跑", "打斗", "追逐", "运动"],
    "transition": ["转场", "过渡"],
}


class QueryUnderstandingAnalyzer:
    def analyze(self, text: str, texts: str | list[str] | None = None, index: int | None = None, prefer_media_type: PreferMediaType = "auto") -> QueryIntent:
        all_lines = split_texts(texts)
        current_text = text.strip()
        joined_context = " ".join(all_lines) if all_lines else current_text
        tokens = tokenize_text(f"{current_text} {joined_context}")
        preferred_pace = self._match_bucket(current_text, PACE_KEYWORDS)
        preferred_emotion = self._match_bucket(current_text, EMOTION_KEYWORDS)
        preferred_role = self._match_bucket(current_text, ROLE_KEYWORDS)
        preferred_temperature = "warm" if any(word in current_text for word in ["温暖", "暖色", "夕阳", "warm"]) else "cool" if any(word in current_text for word in ["冷", "蓝", "夜", "cool"]) else "unknown"
        preferred_brightness = "bright" if any(word in current_text for word in ["明亮", "阳光", "白天", "bright"]) else "dark" if any(word in current_text for word in ["昏暗", "黑夜", "dark"]) else "unknown"
        preferred_saturation = "vivid" if any(word in current_text for word in ["鲜艳", "彩色", "vivid"]) else "muted" if any(word in current_text for word in ["低饱和", "灰", "muted"]) else "unknown"
        resolved_media_type = prefer_media_type
        if resolved_media_type == "auto":
            if any(word in current_text for word in ["视频", "镜头", "片段", "运动", "转场"]):
                resolved_media_type = "video"
            elif any(word in current_text for word in ["图片", "海报", "插图", "静态"]):
                resolved_media_type = "image"
            else:
                resolved_media_type = "mixed"
        duration = estimate_text_duration(current_text)
        if index is not None and 0 <= index < len(all_lines):
            duration = estimate_text_duration(all_lines[index])
        return QueryIntent(
            keywords=list(dict.fromkeys(tokens))[:20],
            prefer_media_type=resolved_media_type,
            preferred_pace=preferred_pace,
            preferred_emotion=preferred_emotion,
            preferred_temperature=preferred_temperature,
            preferred_brightness=preferred_brightness,
            preferred_saturation=preferred_saturation,
            preferred_role=preferred_role,
            estimated_duration=duration,
        )

    def _match_bucket(self, text: str, mapping: dict[str, list[str]]) -> str:
        for bucket, words in mapping.items():
            if any(word in text for word in words):
                return bucket
        return "unknown"
