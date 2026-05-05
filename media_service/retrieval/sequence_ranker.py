from __future__ import annotations

from typing import List

from media_service.retrieval.coarse_filter import WindowCandidate


TRANSITION_KEYWORDS = ["然后", "接着", "随后", "转场", "过渡", "next", "then", "transition"]


def _is_transition_text(text: str) -> bool:
    content = (text or "").lower()
    return any(token in content for token in TRANSITION_KEYWORDS)


def rerank_with_previous(current_candidates: List[WindowCandidate], previous_selected: WindowCandidate | None, text: str = "") -> List[WindowCandidate]:
    if not current_candidates:
        return []
    transition_text = _is_transition_text(text)
    reranked: List[WindowCandidate] = []
    for candidate in current_candidates:
        score = candidate.total_score
        notes = list(candidate.continuity_notes)
        if previous_selected is not None:
            prev = previous_selected.window
            curr = candidate.window
            if curr.source_path == prev.source_path:
                score -= 0.12
                notes.append("avoid repeated source_path")
            brightness_gap = abs(curr.features.brightness_mean - prev.features.brightness_mean)
            if brightness_gap > 35:
                score -= min((brightness_gap - 35) / 100.0, 0.12)
                notes.append("brightness jump penalty")
            motion_gap = abs(curr.features.motion_mean - prev.features.motion_mean)
            if motion_gap > 35:
                score -= min((motion_gap - 35) / 100.0, 0.12)
                notes.append("motion jump penalty")
            if prev.key.motion_bucket == "high" and curr.key.motion_bucket == "high":
                score -= 0.08
                notes.append("consecutive high motion penalty")

        if transition_text and candidate.window.key.preferred_role_hint in {"transition", "background"}:
            score += 0.08
            notes.append("transition text bonus")

        candidate.total_score = round(score, 4)
        candidate.continuity_notes = notes
        reranked.append(candidate)

    reranked.sort(key=lambda item: item.total_score, reverse=True)
    return reranked
