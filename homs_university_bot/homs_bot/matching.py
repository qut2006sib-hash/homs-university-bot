"""Map a normalized question onto approved variants, then onto one intent."""

from __future__ import annotations

from dataclasses import dataclass

from homs_bot.config import Settings
from homs_bot.models import QuestionRow
from homs_bot.similarity import SimilarityIndex


@dataclass(frozen=True)
class IntentHit:
    intent_id: str
    intent_code: str
    intent_title: str
    question_id: str
    score: float


def rank_intents(
    normalized_query: str,
    variants: list[QuestionRow],
    index: SimilarityIndex,
) -> list[IntentHit]:
    """Keep the best variant score for each intent. Scores are not calibrated."""
    best: dict[str, IntentHit] = {}
    for variant in variants:
        score = index.score(normalized_query, variant.normalized_wording)
        current = best.get(variant.intent_id)
        if current is None or score > current.score:
            best[variant.intent_id] = IntentHit(
                intent_id=variant.intent_id,
                intent_code=variant.intent_code,
                intent_title=variant.intent_title,
                question_id=variant.id,
                score=score,
            )
    return sorted(best.values(), key=lambda hit: hit.score, reverse=True)


def decide_hits(hits: list[IntentHit], settings: Settings) -> str:
    """Return matched, confirm, clarify, or unmatched.

    A match is reliable only when the top score clears the auto threshold and
    leads the next intent by the configured margin. Close scores stay buttons.
    """
    if not hits or hits[0].score < settings.match_clarify:
        return "unmatched"
    best = hits[0]
    second = hits[1] if len(hits) > 1 else None
    if second and second.score >= settings.match_clarify:
        gap = best.score - second.score
        if best.score >= settings.match_auto and gap >= settings.match_margin:
            return "matched"
        return "clarify"
    if best.score >= settings.match_auto:
        return "matched"
    return "confirm"
