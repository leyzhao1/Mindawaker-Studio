from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from app.service.media_retrieval_client import MediaRetrievalClient


_EN_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ZH_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")

LOW_VALUE_TERMS: Set[str] = {
    "color",
    "colour",
    "colored",
    "coloured",
    "colorful",
    "colourful",
    "beautiful",
    "pretty",
    "bright",
    "outdoor",
    "nature",
}

STOP_TERMS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "into",
    "onto",
    "is",
    "are",
    "was",
    "were",
    "its",
}

COMMON_ACTION_TERMS: Set[str] = {
    "run",
    "runs",
    "running",
    "walk",
    "walks",
    "walking",
    "move",
    "moves",
    "moving",
    "jog",
    "jogging",
    "jump",
    "jumping",
}

SCENE_CONTEXT_TERMS: Set[str] = {
    "grass",
    "forest",
    "snow",
    "river",
    "mountain",
    "beach",
    "desert",
    "street",
    "city",
    "road",
    "lake",
    "sky",
}

SEASON_TERMS: Set[str] = {
    "spring",
    "summer",
    "autumn",
    "fall",
    "winter",
}


def _tokenize_semantic_terms(text: str) -> Set[str]:
    normalized = (text or "").lower()
    return set(_EN_TOKEN_PATTERN.findall(normalized) + _ZH_TOKEN_PATTERN.findall(normalized))


def _classify_query_term(term: str) -> str:
    if term in STOP_TERMS:
        return "drop"
    if term in LOW_VALUE_TERMS:
        return "modifier"
    if term in SEASON_TERMS or term in SCENE_CONTEXT_TERMS:
        return "context"
    if term in COMMON_ACTION_TERMS:
        return "drop"
    return "head"


def _extract_head_keywords(item: Dict[str, Any], fallback_text: str = "") -> List[str]:
    intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
    raw_keywords = intent.get("keywords") if isinstance(intent, dict) else []

    terms: Set[str] = set()
    if isinstance(raw_keywords, list):
        for keyword in raw_keywords:
            terms.update(_tokenize_semantic_terms(str(keyword)))

    if not terms:
        terms.update(_tokenize_semantic_terms(str(item.get("text") or fallback_text or "")))

    heads = [term for term in sorted(terms) if _classify_query_term(term) == "head"]
    return heads


def _build_missing_head_keywords(
    retrieval_items: List[Dict[str, Any]],
    lines: List[str],
    empty_result_indices: List[int],
) -> List[Dict[str, Any]]:
    items_by_index: Dict[int, Dict[str, Any]] = {}
    for idx, item in enumerate(retrieval_items):
        item_index = item.get("index", idx)
        if isinstance(item_index, int):
            items_by_index[item_index] = item

    missing: List[Dict[str, Any]] = []
    for index in empty_result_indices:
        item = items_by_index.get(index, {})
        fallback_text = lines[index] if index < len(lines) else ""
        text = str(item.get("text") or fallback_text)
        missing.append(
            {
                "index": index,
                "text": text,
                "head_keywords": _extract_head_keywords(item, fallback_text=fallback_text),
            }
        )
    return missing


def split_lines(text: str | List[str]) -> List[str]:
    if isinstance(text, list):
        return [line.strip() for line in text if isinstance(line, str) and line.strip()]
    return [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]


def build_background_assets(
    retrieval_items: List[Dict[str, Any]],
    audio_paths: List[str],
    audio_durations: List[float],
) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for index, item in enumerate(retrieval_items):
        results = item.get("results") or []
        best = results[0] if results else {}
        assets.append(
            {
                "index": item.get("index", index),
                "text": item.get("text", ""),
                "source_path": best.get("source_path", ""),
                "media_type": best.get("media_type", "unknown"),
                "annotation_path": best.get("annotation_path", ""),
                "score": ((best.get("score") or {}).get("total") or 0.0),
                "start_sec": best.get("start_sec"),
                "end_sec": best.get("end_sec"),
                "audio_path": audio_paths[index] if index < len(audio_paths) else "",
                "audio_duration": audio_durations[index] if index < len(audio_durations) else 0.0,
                "retrieval_result": best,
            }
        )
    return assets


def retrieve_background_assets(
    *,
    client: MediaRetrievalClient,
    text: str | List[str],
    annotation_root: str,
    audio_paths: List[str],
    audio_durations: List[float],
    top_k_per_line: int = 3,
    prefer_media_type: str = "auto",
    search_mode: str = "window_level",
    ranking_strategy: str = "cascade_sequence_v1",
    window_annotation_root: str | None = None,
    window_level_preferred: bool = True,
    coarse_top_n: int = 50,
    fine_top_k: int = 10,
) -> Dict[str, Any]:
    lines = split_lines(text)
    if not lines:
        return {"success": True, "lines": [], "items": [], "background_assets": []}

    durations = audio_durations[: len(lines)] if audio_durations else None

    retrieval = client.batch_search(
        texts=lines,
        durations=durations,
        annotation_root=annotation_root,
        top_k_per_line=top_k_per_line,
        prefer_media_type=prefer_media_type,
        search_mode=search_mode,
        ranking_strategy=ranking_strategy,
        window_annotation_root=window_annotation_root,
        window_level_preferred=window_level_preferred,
        coarse_top_n=coarse_top_n,
        fine_top_k=fine_top_k,
    )
    items = retrieval.get("items") or []
    empty_result_indices = retrieval.get("empty_result_indices") or [
        item.get("index", idx)
        for idx, item in enumerate(items)
        if len(item.get("results") or []) == 0
    ]

    missing_head_keywords = _build_missing_head_keywords(items, lines, empty_result_indices) if empty_result_indices else []
    background_assets = build_background_assets(items, audio_paths, audio_durations)

    response: Dict[str, Any] = {
        "success": True,
        "lines": lines,
        "items": items,
        "background_assets": background_assets,
        "empty_result_indices": empty_result_indices,
        "missing_head_keywords": missing_head_keywords,
    }
    if empty_result_indices:
        response["has_empty_results"] = True
        response["message"] = "some queries returned no retrieval results"
    else:
        response["has_empty_results"] = False
    return response
