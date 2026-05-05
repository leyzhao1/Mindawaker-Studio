from __future__ import annotations

from typing import Dict, List, Optional, Set

from media_service.retrieval.coarse_filter import WindowCandidate, get_synonyms
from media_service.retrieval.query_builder import QueryState


def _semantic_score(candidate: WindowCandidate, query_state: QueryState) -> tuple[float, List[str]]:
    def _normalize(text: str) -> str:
        return str(text).strip().lower()

    def _token_variants(term: str) -> List[str]:
        term = _normalize(term)
        variants = {term}

        if term.endswith("s") and len(term) > 3:
            variants.add(term[:-1])
        else:
            variants.add(term + "s")

        for alt in get_synonyms(term):
            variants.add(_normalize(alt.replace("_", " ")))

        return [v for v in variants if v]

    def _match_strength(term: str, values: List[str]) -> float:
        normalized_values = [_normalize(v) for v in values if _normalize(v)]
        if not normalized_values:
            return 0.0

        joined = " ".join(normalized_values)
        variants = _token_variants(term)

        for v in variants:
            if v in joined:
                return 1.0 if v == _normalize(term) else 0.75

        term_tokens = [t for t in _normalize(term).replace("-", " ").split() if t]
        if term_tokens:
            overlap_hits = 0
            for token in term_tokens:
                if token in joined:
                    overlap_hits += 1
            if overlap_hits > 0:
                ratio = overlap_hits / len(term_tokens)
                return max(0.55, ratio * 0.7)

        return 0.0

    def _field_score(query_terms: List[str], values: List[str]) -> tuple[float, List[str]]:
        if not query_terms:
            return 0.55, []

        matched_terms: List[str] = []
        strengths: List[float] = []

        for raw_term in query_terms:
            term = _normalize(raw_term)
            if not term:
                continue

            strength = _match_strength(term, values)
            strengths.append(strength)

            if strength >= 0.55:
                matched_terms.append(term)

        if not strengths:
            return 0.35, []

        raw = sum(strengths) / len(strengths)
        score = 0.35 + 0.65 * raw
        return min(score, 1.0), list(dict.fromkeys(matched_terms))

    caption_values = [candidate.window.semantic.caption or ""]
    object_values = list(candidate.window.semantic.objects)
    scene_values = list(candidate.window.semantic.scene_tags)
    action_values = list(candidate.window.semantic.action_tags)
    keyword_values = list(candidate.window.key.semantic_keywords)

    caption_score, m1 = _field_score(query_state.keywords, caption_values)
    object_score, m2 = _field_score(query_state.keywords, object_values)
    scene_score, m3 = _field_score(query_state.keywords, scene_values)
    action_score, m4 = _field_score(query_state.keywords, action_values)
    key_score, m5 = _field_score(query_state.keywords, keyword_values)

    best_score = max(
        caption_score,
        object_score * 0.95,
        scene_score * 0.90,
        action_score * 0.90,
        key_score,
    )

    matched_terms = list(dict.fromkeys(m1 + m2 + m3 + m4 + m5))
    return min(best_score, 1.0), matched_terms


def _brightness_rule_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    pref = query_state.preferred_brightness
    value = candidate.window.features.brightness_mean
    if pref == "bright":
        if value < 50:
            return 0.0
        return min(max((value - 50) / 50.0, 0.0), 1.0)
    if pref == "dark":
        if value > 65:
            return 0.0
        return min(max((50.0 - value) / 50.0, 0.0), 1.0)
    return 0.5


def _saturation_rule_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    pref = query_state.preferred_saturation
    value = candidate.window.features.saturation_mean
    if pref == "vivid":
        if value < 35:
            return 0.0
        return min(max((value - 35) / 65.0, 0.0), 1.0)
    if pref == "muted":
        if value > 60:
            return 0.0
        return min(max((45.0 - value) / 45.0, 0.0), 1.0)
    return 0.5


def _role_hint_rule_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    pref = query_state.preferred_role
    if pref == "unknown":
        return 0.5
    if candidate.window.key.preferred_role_hint == pref:
        return 1.0
    if pref == "background" and candidate.window.key.preferred_role_hint == "transition":
        return 0.6
    return 0.0


def _style_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    brightness_score = _brightness_rule_score(candidate, query_state)
    saturation_score = _saturation_rule_score(candidate, query_state)
    role_hint_score = _role_hint_rule_score(candidate, query_state)
    return (brightness_score * 0.4) + (saturation_score * 0.3) + (role_hint_score * 0.3)


def _emotion_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    if query_state.preferred_emotion == "unknown":
        return 0.5
    return 1.0 if candidate.window.key.emotion_bucket == query_state.preferred_emotion else 0.0


def _motion_rule_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    pref = query_state.preferred_pace
    bucket = candidate.window.key.motion_bucket
    if pref in {"fast", "slow", "medium"}:
        mapping = {
            "fast": {"high", "medium"},
            "medium": {"medium", "high", "low"},
            "slow": {"low", "medium"},
        }
        return 1.0 if bucket in mapping.get(pref, {"low", "medium", "high"}) else 0.0
    return 0.5


def _pace_bucket_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    if query_state.preferred_pace == "unknown":
        return 0.5
    if candidate.window.key.pace_bucket == query_state.preferred_pace:
        return 1.0
    if query_state.preferred_pace in {"slow", "fast"} and candidate.window.key.pace_bucket == "medium":
        return 0.5
    return 0.0


def _pace_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    motion_score = _motion_rule_score(candidate, query_state)
    pace_bucket_score = _pace_bucket_score(candidate, query_state)
    return (motion_score * 0.5) + (pace_bucket_score * 0.5)


def _readability_score(candidate: WindowCandidate) -> float:
    raw = candidate.window.features.readability_score
    if raw < 15:
        return 0.0
    return min(max(raw / 100.0, 0.0), 1.0)


def _duration_score(candidate: WindowCandidate, query_state: QueryState) -> float:
    estimated = query_state.estimated_duration
    if estimated <= 0:
        return 0.5
    diff = abs(candidate.window.duration_sec - estimated)
    ratio = diff / max(candidate.window.duration_sec, estimated, 1.0)
    return max(0.0, min(1.0, 1.0 - ratio))


def _continuity_score(candidate: WindowCandidate, query_state: QueryState) -> tuple[float, List[str]]:
    if not query_state.previous_style_signature:
        return 0.5, []
    notes: List[str] = []
    prev_brightness = float(query_state.previous_style_signature.get("brightness_mean", 50.0))
    prev_motion = float(query_state.previous_style_signature.get("motion_mean", 0.0))
    current_brightness = candidate.window.features.brightness_mean
    current_motion = candidate.window.features.motion_mean
    brightness_gap = abs(current_brightness - prev_brightness)
    motion_gap = abs(current_motion - prev_motion)
    brightness_score = max(0.0, 1.0 - brightness_gap / 100.0)
    motion_score = max(0.0, 1.0 - motion_gap / 100.0)
    if query_state.previous_source_path and candidate.window.source_path == query_state.previous_source_path:
        notes.append("repeat source penalty")
        source_score = 0.2
    else:
        source_score = 1.0
    total = (brightness_score * 0.4) + (motion_score * 0.4) + (source_score * 0.2)
    return max(0.0, min(1.0, total)), notes


def _candidate_key(candidate: WindowCandidate) -> str:
    return f"{candidate.window.source_path}::{candidate.window.window_id}"


def rank_candidates(
    candidates: List[WindowCandidate],
    query_state: QueryState,
    fine_top_k: int = 10,
    semantic_overrides: Optional[Dict[str, float]] = None,
    matched_terms_overrides: Optional[Dict[str, List[str]]] = None,
    excluded_source_paths: Optional[Set[str]] = None,
    excluded_window_ids: Optional[Set[str]] = None,
) -> List[WindowCandidate]:
    ranked: List[WindowCandidate] = []
    semantic_overrides = semantic_overrides or {}
    matched_terms_overrides = matched_terms_overrides or {}
    excluded_source_paths = excluded_source_paths or set()
    excluded_window_ids = excluded_window_ids or set()

    for candidate in candidates:
        semantic_score, matched_terms = _semantic_score(candidate, query_state)
        candidate_key = _candidate_key(candidate)
        override_semantic = semantic_overrides.get(candidate_key)
        if override_semantic is not None:
            semantic_score = override_semantic
            matched_terms = matched_terms_overrides.get(candidate_key, candidate.matched_terms or [])

        style_score = _style_score(candidate, query_state)
        emotion_score = _emotion_score(candidate, query_state)
        pace_score = _pace_score(candidate, query_state)
        readability_score = _readability_score(candidate)
        duration_score = _duration_score(candidate, query_state)
        continuity_score, continuity_notes = _continuity_score(candidate, query_state)

        total = (
            style_score * 0.10
            + emotion_score * 0.07
            + pace_score * 0.17
            + readability_score * 0.06
            + duration_score * 0.50
            + continuity_score * 0.07
        )

        window_id = candidate.window.window_id
        source_path = candidate.window.source_path
        if window_id in excluded_window_ids:
            total -= 100.0
            continuity_notes = list(continuity_notes) + ["exclude repeated window in batch"]
        elif source_path in excluded_source_paths:
            total -= 100.0
            continuity_notes = list(continuity_notes) + ["exclude repeated source in batch"]

        candidate.total_score = round(total, 4)
        candidate.matched_terms = matched_terms
        candidate.continuity_notes = continuity_notes
        candidate.score_breakdown = {
            "semantic_score": 0.0,
            "style_score": round(style_score, 4),
            "emotion_score": round(emotion_score, 4),
            "pace_score": round(pace_score, 4),
            "readability_score": round(readability_score, 4),
            "duration_score": round(duration_score, 4),
            "continuity_score": round(continuity_score, 4),
        }
        ranked.append(candidate)

    ranked.sort(key=lambda item: item.total_score, reverse=True)

    hard_filtered = [
        item for item in ranked
        if item.window.window_id not in excluded_window_ids and item.window.source_path not in excluded_source_paths
    ]
    if len(hard_filtered) >= fine_top_k:
        return hard_filtered[:fine_top_k]

    return ranked[:fine_top_k]

