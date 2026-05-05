from __future__ import annotations

from media_service.model.schemas import EmotionTag, RhythmTag, StyleTag


class EmotionAnalyzer:
    def analyze(self, style: StyleTag, rhythm: RhythmTag) -> EmotionTag:
        motion = rhythm.motion_intensity if rhythm.motion_intensity is not None else 0.0
        scores = {
            "joyful": 0.0,
            "calm": 0.0,
            "tense": 0.0,
            "melancholic": 0.0,
            "romantic": 0.0,
            "dramatic": 0.0,
        }
        if style.brightness >= 65:
            scores["joyful"] += 1.2
            scores["calm"] += 0.5
        if style.brightness <= 35:
            scores["melancholic"] += 1.2
            scores["tense"] += 0.5
        if style.saturation >= 60:
            scores["joyful"] += 1.0
            scores["romantic"] += 0.4
            scores["dramatic"] += 0.5
        if style.saturation <= 30:
            scores["calm"] += 0.6
            scores["melancholic"] += 0.8
        if style.contrast >= 60:
            scores["tense"] += 1.0
            scores["dramatic"] += 1.0
        if style.contrast <= 30:
            scores["calm"] += 0.8
        if style.color_temperature == "warm":
            scores["joyful"] += 0.5
            scores["romantic"] += 0.9
        elif style.color_temperature == "cool":
            scores["melancholic"] += 0.8
            scores["tense"] += 0.4
        else:
            scores["calm"] += 0.3
        if motion >= 70:
            scores["tense"] += 1.2
            scores["dramatic"] += 1.0
        elif motion >= 40:
            scores["joyful"] += 0.4
            scores["dramatic"] += 0.6
        else:
            scores["calm"] += 0.8
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        total = sum(max(score, 0.0) for _, score in ranked)
        primary, primary_score = ranked[0]
        secondary, secondary_score = ranked[1]
        confidence = float(primary_score / total) if total > 0 else 0.0
        return EmotionTag(
            primary=primary if primary_score > 0 else "unknown",
            secondary=secondary if secondary_score > 0 else "unknown",
            confidence=round(confidence, 4),
        )
