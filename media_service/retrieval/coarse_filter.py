from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set

from nltk.corpus import wordnet as wn
from pydantic import BaseModel, Field

from media_service.retrieval.query_builder import QueryState
from media_service.windowing.schema import VideoWindowAnnotation


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

FIELD_WEIGHTS: Dict[str, float] = {
    "caption": 0.8,
    "scene": 0.85,
    "semantic_keyword": 1.0,
    "object": 1.25,
    "action": 1.25,
}

MAX_FIELD_WEIGHT = max(FIELD_WEIGHTS.values())
MAX_SYNONYMS_PER_TERM = 12

_EN_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_ZH_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+")
_ENGLISH_TERM_PATTERN = re.compile(r"^[a-z0-9]+$")


@dataclass(frozen=True)
class QueryTermBuckets:
    all_terms: Set[str]
    head_terms: Set[str]
    context_terms: Set[str]
    modifier_terms: Set[str]
    dropped_terms: Set[str]


@dataclass(frozen=True)
class WindowTermBuckets:
    caption_terms: Set[str]
    object_terms: Set[str]
    scene_terms: Set[str]
    action_terms: Set[str]
    semantic_keyword_terms: Set[str]

    @property
    def window_terms_all(self) -> Set[str]:
        return (
            self.caption_terms
            | self.object_terms
            | self.scene_terms
            | self.action_terms
            | self.semantic_keyword_terms
        )

    def field_weight_for_term(self, term: str) -> float:
        weight = 0.0
        if term in self.caption_terms:
            weight = max(weight, FIELD_WEIGHTS["caption"])
        if term in self.scene_terms:
            weight = max(weight, FIELD_WEIGHTS["scene"])
        if term in self.semantic_keyword_terms:
            weight = max(weight, FIELD_WEIGHTS["semantic_keyword"])
        if term in self.object_terms:
            weight = max(weight, FIELD_WEIGHTS["object"])
        if term in self.action_terms:
            weight = max(weight, FIELD_WEIGHTS["action"])
        return weight if weight > 0 else FIELD_WEIGHTS["caption"]


class WindowCandidate(BaseModel):
    window: VideoWindowAnnotation
    coarse_score: float = 0.0
    total_score: float = 0.0
    matched_terms: List[str] = Field(default_factory=list)
    continuity_notes: List[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)


def get_synonyms(word: str) -> List[str]:
    synonyms = set()
    try:
        for syn in wn.synsets(word):
            for lemma in syn.lemmas():
                synonyms.add(lemma.name().lower())
    except LookupError:
        return []
    return list(synonyms)


def _tokenize_semantic_terms(text: str) -> Set[str]:
    normalized = (text or "").lower()
    return set(_EN_TOKEN_PATTERN.findall(normalized) + _ZH_TOKEN_PATTERN.findall(normalized))


def _tokenize_values(values: List[str]) -> Set[str]:
    terms: Set[str] = set()
    for value in values:
        terms.update(_tokenize_semantic_terms(value))
    return terms


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


def _split_query_terms(keywords: List[str]) -> QueryTermBuckets:
    raw_terms: Set[str] = set()
    for keyword in keywords:
        raw_terms.update(_tokenize_semantic_terms(str(keyword)))

    # Example: "fox running in grass winter" => head={fox}, context={grass,winter}, dropped={running,in}
    head_terms: Set[str] = set()
    context_terms: Set[str] = set()
    modifier_terms: Set[str] = set()
    dropped_terms: Set[str] = set()

    for term in raw_terms:
        category = _classify_query_term(term)
        if category == "head":
            head_terms.add(term)
        elif category == "context":
            context_terms.add(term)
        elif category == "modifier":
            modifier_terms.add(term)
        else:
            dropped_terms.add(term)

    all_terms = head_terms | context_terms | modifier_terms
    return QueryTermBuckets(
        all_terms=all_terms,
        head_terms=head_terms,
        context_terms=context_terms,
        modifier_terms=modifier_terms,
        dropped_terms=dropped_terms,
    )


def _build_window_term_buckets(window: VideoWindowAnnotation) -> WindowTermBuckets:
    return WindowTermBuckets(
        caption_terms=_tokenize_semantic_terms(window.semantic.caption or ""),
        object_terms=_tokenize_values(window.semantic.objects),
        scene_terms=_tokenize_values(window.semantic.scene_tags),
        action_terms=_tokenize_values(window.semantic.action_tags),
        semantic_keyword_terms=_tokenize_values(window.key.semantic_keywords),
    )


def _query_term_weight(term: str, query_terms: QueryTermBuckets) -> float:
    if term in query_terms.head_terms:
        return 2.2
    if term in query_terms.context_terms:
        return 0.75
    if term in query_terms.modifier_terms:
        return 0.2
    return 0.0


def _window_term_weight(term: str, field_weight: float) -> float:
    modifier_factor = 0.25 if term in LOW_VALUE_TERMS else 1.0
    return modifier_factor * field_weight


def _expand_query_term_variants(term: str, query_terms: QueryTermBuckets) -> Set[str]:
    variants = {term}
    if term not in query_terms.head_terms:
        return variants
    if not _ENGLISH_TERM_PATTERN.match(term):
        return variants

    added = 0
    for synonym in sorted(get_synonyms(term)):
        for synonym_term in _tokenize_semantic_terms(synonym.replace("_", " ")):
            if synonym_term in variants:
                continue
            variants.add(synonym_term)
            added += 1
            if added >= MAX_SYNONYMS_PER_TERM:
                return variants
    return variants


def _safe_f1(precision: float, recall: float) -> float:
    if precision <= 0.0 or recall <= 0.0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _semantic_score_details(
    window: VideoWindowAnnotation,
    query_state: QueryState,
) -> tuple[float, List[str], dict[str, float]]:
    query_terms = _split_query_terms(query_state.keywords)
    if not query_terms.all_terms:
        return 0.5, [], {
            "query_recall": 0.0,
            "window_precision": 0.0,
            "base_f1": 0.0,
            "weighted_query_recall": 0.0,
            "weighted_window_precision": 0.0,
            "weighted_f1": 0.0,
            "head_hit_ratio": 1.0,
            "head_gate": 1.0,
            "all_term_count": 0.0,
            "head_term_count": 0.0,
            "context_term_count": 0.0,
            "modifier_term_count": 0.0,
            "dropped_term_count": float(len(query_terms.dropped_terms)),
            "window_term_count": 0.0,
            "matched_term_count": 0.0,
        }

    buckets = _build_window_term_buckets(window)
    window_terms_all = buckets.window_terms_all

    query_variants: Dict[str, Set[str]] = {
        term: _expand_query_term_variants(term, query_terms) for term in query_terms.all_terms
    }

    matched_query_terms: Set[str] = set()
    matched_window_terms: Set[str] = set()
    matched_terms: Set[str] = set()

    weighted_query_hit_sum = 0.0
    weighted_query_total_sum = 0.0

    for term in query_terms.all_terms:
        term_weight = _query_term_weight(term, query_terms)
        weighted_query_total_sum += term_weight

        overlap = query_variants[term] & window_terms_all
        if not overlap:
            continue

        matched_query_terms.add(term)
        matched_window_terms.update(overlap)
        matched_terms.add(term)

        best_field_weight = max((buckets.field_weight_for_term(item) for item in overlap), default=FIELD_WEIGHTS["caption"])
        weighted_query_hit_sum += term_weight * (best_field_weight / MAX_FIELD_WEIGHT)

    query_recall = len(matched_query_terms) / max(len(query_terms.all_terms), 1)
    window_precision = len(matched_window_terms) / max(len(window_terms_all), 1)
    base_f1 = _safe_f1(window_precision, query_recall)

    weighted_query_recall = weighted_query_hit_sum / max(weighted_query_total_sum, 1e-6)

    weighted_window_total_sum = 0.0
    weighted_window_hit_sum = 0.0
    for term in window_terms_all:
        field_weight = buckets.field_weight_for_term(term)
        term_weight = _window_term_weight(term, field_weight)
        weighted_window_total_sum += term_weight
        if term in matched_window_terms:
            weighted_window_hit_sum += term_weight

    weighted_window_precision = weighted_window_hit_sum / max(weighted_window_total_sum, 1e-6)
    weighted_f1 = _safe_f1(weighted_window_precision, weighted_query_recall)

    if not query_terms.head_terms:
        head_hit_ratio = 1.0
        head_gate = 1.0
    else:
        head_hits = len(query_terms.head_terms & matched_query_terms)
        head_hit_ratio = head_hits / max(len(query_terms.head_terms), 1)
        if head_hits == 0:
            head_gate = 0.0
        else:
            head_gate = 0.7 + 0.3 * head_hit_ratio

    final_score = ((weighted_f1 * 0.75) + (base_f1 * 0.25)) * head_gate
    final_score = max(0.0, min(final_score, 1.0))

    score_breakdown = {
        "query_recall": round(query_recall, 4),
        "window_precision": round(window_precision, 4),
        "base_f1": round(base_f1, 4),
        "weighted_query_recall": round(weighted_query_recall, 4),
        "weighted_window_precision": round(weighted_window_precision, 4),
        "weighted_f1": round(weighted_f1, 4),
        "head_hit_ratio": round(head_hit_ratio, 4),
        "head_gate": round(head_gate, 4),
        "all_term_count": float(len(query_terms.all_terms)),
        "head_term_count": float(len(query_terms.head_terms)),
        "context_term_count": float(len(query_terms.context_terms)),
        "modifier_term_count": float(len(query_terms.modifier_terms)),
        "dropped_term_count": float(len(query_terms.dropped_terms)),
        "window_term_count": float(len(window_terms_all)),
        "matched_term_count": float(len(matched_query_terms)),
    }

    return final_score, sorted(matched_terms), score_breakdown


def _semantic_score_with_matches(window: VideoWindowAnnotation, query_state: QueryState) -> tuple[float, List[str]]:
    score, matched_terms, _ = _semantic_score_details(window, query_state)
    return score, matched_terms


def filter_candidates_semantic(
    windows: List[VideoWindowAnnotation],
    query_state: QueryState,
    coarse_top_n: int = 50,
) -> List[WindowCandidate]:
    candidates: List[WindowCandidate] = []
    query_terms = _split_query_terms(query_state.keywords)

    for window in windows:
        score, matched_terms, score_breakdown = _semantic_score_details(window, query_state)
        if query_terms.head_terms and len(query_terms.head_terms & set(matched_terms)) == 0:
            continue
        if score < 0.15 or len(matched_terms) == 0:
            continue
        candidates.append(
            WindowCandidate(
                window=window,
                coarse_score=round(score, 4),
                total_score=round(score, 4),
                matched_terms=matched_terms,
                score_breakdown=score_breakdown,
            )
        )

    candidates.sort(key=lambda item: item.coarse_score, reverse=True)
    # return candidates[:coarse_top_n]
    return candidates[:3]

