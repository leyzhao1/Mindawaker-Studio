from __future__ import annotations

from media_service.model.schemas import MediaAnnotation, QueryIntent


class CoherenceScorer:
    def score(self, annotation: MediaAnnotation, intent: QueryIntent, previous_annotation: MediaAnnotation | None = None) -> tuple[float, list[str]]:
        score = 0.0
        notes: list[str] = []
        if annotation.retrieval_hints.media_role == intent.preferred_role and intent.preferred_role != "unknown":
            score += 0.4
            notes.append("role matched")
        if annotation.retrieval_hints.emotion_bucket == intent.preferred_emotion and intent.preferred_emotion != "unknown":
            score += 0.3
            notes.append("emotion continuity matched")
        if annotation.retrieval_hints.pace_bucket == intent.preferred_pace and intent.preferred_pace != "unknown":
            score += 0.3
            notes.append("pace continuity matched")
        if previous_annotation is not None and previous_annotation.source_path == annotation.source_path:
            score -= 0.5
            notes.append("repeat penalty")
        return max(0.0, min(1.0, score)), notes
