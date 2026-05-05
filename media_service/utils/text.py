from __future__ import annotations

import re
from typing import List


def split_texts(texts: str | List[str] | None) -> List[str]:
    if texts is None:
        return []
    if isinstance(texts, list):
        return [item.strip() for item in texts if item and item.strip()]
    return [item.strip() for item in texts.split("\n") if item and item.strip()]


def estimate_text_duration(text: str, min_duration: float = 2.0) -> float:
    char_count = len((text or "").strip())
    if char_count <= 0:
        return min_duration
    return max(min_duration, char_count / 4.5)


def normalize_text(text: str) -> str:
    lowered = (text or "").lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def tokenize_text(text: str) -> List[str]:
    normalized = normalize_text(text)
    tokens = re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]{1,}", normalized)
    return [token for token in tokens if token]
