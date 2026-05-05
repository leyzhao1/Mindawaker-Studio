from __future__ import annotations

from media_service.model.schemas import MediaAnnotation, QueryIntent, RetrievalResult, ScoreBreakdown


class RetrievalScorer:
    def score(self, annotation: MediaAnnotation, annotation_path: str, intent: QueryIntent, coherence_score: float = 0.0, continuity_notes: list[str] | None = None, explain: bool = False) -> RetrievalResult:
        matched_terms = []
        keyword_hits = 0
        for keyword in intent.keywords:
            if keyword in annotation.retrieval_hints.keywords or keyword in annotation.content.caption.lower():
                keyword_hits += 1
                matched_terms.append(keyword)
        keyword_score = min(keyword_hits*3 / max(len(intent.keywords), 1), 1.0)
        style_score = 0.0
        if intent.preferred_temperature != "unknown" and annotation.style.color_temperature == intent.preferred_temperature:
            style_score += 0.4
        if intent.preferred_brightness == "bright" and annotation.style.brightness >= 60:
            style_score += 0.3
        elif intent.preferred_brightness == "dark" and annotation.style.brightness <= 40:
            style_score += 0.3
        if intent.preferred_saturation == "vivid" and annotation.style.saturation >= 55:
            style_score += 0.3
        elif intent.preferred_saturation == "muted" and annotation.style.saturation <= 35:
            style_score += 0.3
        style_score = min(style_score, 1.0)
        emotion_score = 1.0 if intent.preferred_emotion != "unknown" and annotation.emotion.primary == intent.preferred_emotion else 0.5 if intent.preferred_emotion == "unknown" else 0.0
        rhythm_score = 0.5
        if annotation.media_type == "video":
            rhythm_score = 0.0
            if intent.preferred_pace == "unknown":
                rhythm_score = 0.5
            elif annotation.rhythm.pace == intent.preferred_pace:
                rhythm_score = 1.0
        duration_fit_score = self._duration_fit(intent.estimated_duration, annotation.rhythm.duration, annotation.media_type)
        total = (
            keyword_score * 0.35
            + style_score * 0.15
            + emotion_score * 0.15
            + rhythm_score * 0.10
            # + duration_fit_score * 0.15
            + coherence_score * 0.10
        )
        breakdown = ScoreBreakdown(
            keyword_score=round(keyword_score, 4),
            style_score=round(style_score, 4),
            emotion_score=round(emotion_score, 4),
            rhythm_score=round(rhythm_score, 4),
            duration_fit_score=round(duration_fit_score, 4),
            coherence_score=round(coherence_score, 4),
            total=round(total, 4),
        )
        return RetrievalResult(
            source_path=annotation.source_path,
            relative_path=annotation.relative_path,
            media_type=annotation.media_type,
            annotation_path=annotation_path,
            score=breakdown,
            matched_terms=matched_terms,
            estimated_text_duration=intent.estimated_duration,
            media_duration=annotation.rhythm.duration,
            duration_fit_score=round(duration_fit_score, 4),
            continuity_notes=continuity_notes or [],
            annotation=annotation.model_dump(mode="json") if explain else None,
        )

    def _duration_fit(self, estimated_duration: float, media_duration: float | None, media_type: str) -> float:
        if media_type == "image":
            return 0.5
        if media_duration is None or media_duration <= 0:
            return 0.0
        diff = abs(estimated_duration - media_duration)
        ratio = diff / max(estimated_duration, media_duration, 1.0)
        score = 1.0 - ratio
        if media_duration < estimated_duration:
            score -= 0.1
        return max(0.0, min(1.0, score))
