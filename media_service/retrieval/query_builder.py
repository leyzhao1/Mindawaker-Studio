from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from media_service.model.schemas import QueryIntent
from media_service.utils.text import tokenize_text


class QueryState(BaseModel):
    text: str
    keywords: List[str] = Field(default_factory=list)
    estimated_duration: float = 0.0
    preferred_pace: str = "unknown"
    preferred_emotion: str = "unknown"
    preferred_temperature: str = "unknown"
    preferred_brightness: str = "unknown"
    preferred_saturation: str = "unknown"
    preferred_role: str = "unknown"
    previous_selected_window_id: Optional[str] = None
    previous_style_signature: Optional[Dict[str, Any]] = None
    previous_source_path: Optional[str] = None


def build_query_state(
    text: str,
    intent: QueryIntent,
    previous_selected_window_id: str | None = None,
    previous_style_signature: Dict[str, Any] | None = None,
    previous_source_path: str | None = None,
) -> QueryState:
    # normalized_keywords = list(dict.fromkeys([*intent.keywords, *tokenize_text(text)]))[:40]
    normalized_keywords = intent.keywords
    return QueryState(
        text=text,
        keywords=normalized_keywords,
        estimated_duration=float(intent.estimated_duration),
        preferred_pace=intent.preferred_pace,
        preferred_emotion=intent.preferred_emotion,
        preferred_temperature=intent.preferred_temperature,
        preferred_brightness=intent.preferred_brightness,
        preferred_saturation=intent.preferred_saturation,
        preferred_role=intent.preferred_role,
        previous_selected_window_id=previous_selected_window_id,
        previous_style_signature=previous_style_signature,
        previous_source_path=previous_source_path,
    )
