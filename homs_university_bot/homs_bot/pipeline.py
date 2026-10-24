"""Question → intent → approved answer. Feedback never publishes a new answer."""

from __future__ import annotations

import json
import logging
from datetime import date

from homs_bot.answering import select_answer
from homs_bot.catalog import FIELD_LABELS_AR, load_catalog
from homs_bot.config import Settings
from homs_bot.context_flow import load_context
from homs_bot.db import Store
from homs_bot.matching import decide_hits, rank_intents
from homs_bot.messages import (
    CLARIFY,
    CONFIRM,
    CONFLICT,
    NO_MATCH,
    NO_VERIFIED,
    OFFICIAL_NOTE,
    REJECTED,
    SYNTHETIC_BANNER,
    need_context_message,
)
from homs_bot.models import AskResult, Button, Intent, Source
from homs_bot.similarity import LexicalSimilarityIndex, SimilarityIndex
from homs_bot.text_norm import normalize_arabic

logger = logging.getLogger(__name__)


def ask(
    store: Store,
    settings: Settings,
    *,
    telegram_user_id: int,
    text: str,
    today: date | None = None,
    chosen_intent_id: str | None = None,
    parent_interaction_id: int | None = None,
    similarity: SimilarityIndex | None = None,
    link_clarification: bool = False,
) -> AskResult:
    today = today or date.today()
    original = (text or "").strip()
    normalized = normalize_arabic(original)
    catalog = load_catalog()
    ctx = load_context(store, telegram_user_id)
    index = similarity or LexicalSimilarityIndex()

    if not original:
        return AskResult(outcome="empty", text="اكتب السؤال أولاً.")

    chosen: Intent | None = None
    hits = []
    if chosen_intent_id:
        chosen = _resolve_intent(store, chosen_intent_id)
        if (
            chosen is None
            or chosen.status != "approved"
            or (chosen.is_synthetic and not settings.allow_synthetic)
        ):
            return _record(
                store,
                user_id=telegram_user_id,
                original=original,
                normalized=normalized,
                outcome="unmatched",
                text=NO_MATCH,
                needs_review=True,
                parent_interaction_id=parent_interaction_id,
            )
        decision = "matched"
        score = None
        question_id = None
        intent = chosen
    else:
        variants = store.list_matchable_questions(settings.allow_synthetic)
        hits = rank_intents(normalized, variants, index)
        decision = decide_hits(hits, settings)
        if decision == "unmatched":
            return _record(
                store,
                user_id=telegram_user_id,
                original=original,
                normalized=normalized,
                outcome="unmatched",
                text=NO_MATCH,
                score=hits[0].score if hits else None,
                needs_review=True,
            )
        top = hits[0]
        intent = store.get_intent(top.intent_id)
        score = top.score
        question_id = top.question_id
        if intent is None:
            return _record(
                store,
                user_id=telegram_user_id,
                original=original,
                normalized=normalized,
                outcome="unmatched",
                text=NO_MATCH,
                needs_review=True,
            )

    if decision in {"clarify", "confirm"}:
        shown = [hit for hit in hits if hit.score >= settings.match_clarify][:3]
        if decision == "confirm":
            shown = hits[:1]
            prompt = CONFIRM
            buttons = [
                Button(kind="confirm", label=f"نعم: {shown[0].intent_title}", intent_id=shown[0].intent_code),
                Button(kind="reject", label="لا، ليس هذا"),
            ]
            outcome = "confirm"
        else:
            prompt = CLARIFY
            buttons = [
                Button(kind="clarify", label=hit.intent_title, intent_id=hit.intent_code)
                for hit in shown
            ]
            buttons.append(Button(kind="reject", label="ولا واحد منهم"))
            outcome = "clarification"
        result = _record(
            store,
            user_id=telegram_user_id,
            original=original,
            normalized=normalized,
            outcome=outcome,
            text=prompt,
            score=hits[0].score,
            intent_id=None,
            question_id=None,
            needs_review=False,
            candidate_ids=[hit.intent_id for hit in shown],
            buttons=buttons,
        )
        return result

    if link_clarification and parent_interaction_id and intent is not None:
        parent = store.get_interaction(parent_interaction_id)
        offered: list[str] = []
        if parent and parent.candidate_intent_ids:
            offered = [item for item in parent.candidate_intent_ids.split(",") if item]
        if parent and parent.telegram_user_id == telegram_user_id:
            store.add_clarification(
                interaction_id=parent_interaction_id,
                offered_intent_ids=offered,
                chosen_intent_id=intent.id,
            )
            store.set_interaction_review(parent_interaction_id, "reviewed")

    assert intent is not None
    selection = select_answer(
        store.list_answers_with_sources(intent.id),
        ctx,
        today,
        settings.allow_synthetic,
    )
    if selection.kind == "need_context" and selection.field_name:
        label = FIELD_LABELS_AR[selection.field_name]
        buttons = [
            Button(
                kind="context",
                label=catalog.label_for(selection.field_name, code, ctx.faculty_code),
                field=selection.field_name,
                value=code,
            )
            for code in selection.options
        ]
        return _record(
            store,
            user_id=telegram_user_id,
            original=original,
            normalized=normalized,
            outcome="need_context",
            text=need_context_message(label),
            score=score,
            intent_id=intent.id,
            intent_code=intent.code,
            intent_title=intent.title_ar,
            question_id=question_id,
            buttons=buttons,
            parent_interaction_id=parent_interaction_id,
        )

    if selection.kind == "conflict":
        return _record(
            store,
            user_id=telegram_user_id,
            original=original,
            normalized=normalized,
            outcome="conflict_review",
            text=CONFLICT,
            score=score,
            intent_id=intent.id,
            intent_code=intent.code,
            intent_title=intent.title_ar,
            question_id=question_id,
            needs_review=True,
            sources=[_source_payload(source) for _answer, source in selection.pairs],
            parent_interaction_id=parent_interaction_id,
        )

    if selection.kind != "answer":
        return _record(
            store,
            user_id=telegram_user_id,
            original=original,
            normalized=normalized,
            outcome="no_verified_answer",
            text=NO_VERIFIED,
            score=score,
            intent_id=intent.id,
            intent_code=intent.code,
            intent_title=intent.title_ar,
            question_id=question_id,
            needs_review=True,
            parent_interaction_id=parent_interaction_id,
        )

    synthetic = any(answer.is_synthetic or source.is_synthetic for answer, source in selection.pairs)
    body = _format_answer(selection.pairs, synthetic)
    return _record(
        store,
        user_id=telegram_user_id,
        original=original,
        normalized=normalized,
        outcome="answered",
        text=body,
        score=score,
        intent_id=intent.id,
        intent_code=intent.code,
        intent_title=intent.title_ar,
        question_id=question_id,
        answer_id=selection.pairs[0][0].id,
        sources=[_source_payload(source) for _answer, source in selection.pairs],
        authoritative=not synthetic,
        synthetic=synthetic,
        parent_interaction_id=parent_interaction_id,
    )


def reject_clarification(
    store: Store,
    *,
    telegram_user_id: int,
    interaction_id: int,
) -> AskResult:
    parent = store.get_interaction(interaction_id)
    if parent is None or parent.telegram_user_id != telegram_user_id:
        return AskResult(outcome="error", text="ما لقيت السؤال المطلوب.")
    offered = []
    if parent.candidate_intent_ids:
        offered = [item for item in parent.candidate_intent_ids.split(",") if item]
    store.add_clarification(
        interaction_id=interaction_id,
        offered_intent_ids=offered,
        chosen_intent_id=None,
    )
    store.set_interaction_review(interaction_id, "reviewed")
    return _record(
        store,
        user_id=telegram_user_id,
        original=parent.original_text,
        normalized=parent.normalized_text,
        outcome="unmatched",
        text=REJECTED,
        needs_review=True,
        parent_interaction_id=interaction_id,
    )


def record_feedback(
    store: Store,
    *,
    telegram_user_id: int,
    interaction_id: int,
    verdict: str,
) -> str:
    """Store a review signal. This function must not edit answers or sources."""
    if verdict not in {"helpful", "incorrect"}:
        return "نوع الملاحظة غير معروف."
    interaction = store.get_interaction(interaction_id)
    if interaction is None or interaction.telegram_user_id != telegram_user_id:
        return "ما قدرت أربط الملاحظة بهاد الجواب."
    before = _answer_bodies(store)
    store.add_feedback(
        interaction_id=interaction_id,
        user_id=telegram_user_id,
        verdict=verdict,
    )
    after = _answer_bodies(store)
    if before != after:
        logger.error("feedback mutated answers; this is a bug")
    if verdict == "helpful":
        return "شكراً. سجّلت أن الجواب كان مفيداً. الملاحظة ما بتغيّر النص المعتمد لحاله."
    return (
        "شكراً. سجّلت أن الجواب غير صحيح أو لا علاقة له، ورح يراجعها مسؤول. "
        "ما تغيّر أي نص تلقائياً."
    )


def _answer_bodies(store: Store) -> list[tuple[str, str]]:
    rows = store.conn.execute("SELECT id, body_ar FROM answers ORDER BY id").fetchall()
    return [(row["id"], row["body_ar"]) for row in rows]


def _resolve_intent(store: Store, token: str) -> Intent | None:
    return store.get_intent(token) or store.get_intent_by_code(token)


def _format_answer(pairs: list[tuple], synthetic: bool) -> str:
    answer = pairs[0][0]
    lines: list[str] = []
    if synthetic:
        lines.extend([SYNTHETIC_BANNER, ""])
    lines.append(answer.body_ar.strip())
    lines.append("")
    lines.append("المصادر:")
    seen: set[str] = set()
    for _answer, source in pairs:
        if source.id in seen:
            continue
        seen.add(source.id)
        lines.append(f"- {source.title}")
        lines.append(f"  الجهة: {source.issuer}")
        if source.article_or_page:
            lines.append(f"  البند أو الصفحة: {source.article_or_page}")
        if source.reference:
            lines.append(f"  المرجع: {source.reference}")
        start = source.effective_from or "غير محدد"
        end = source.effective_to or "مفتوح"
        lines.append(f"  السريان: {start} → {end}")
    if not synthetic:
        lines.extend(["", OFFICIAL_NOTE])
    return "\n".join(lines)


def _source_payload(source: Source) -> dict:
    return {
        "id": source.id,
        "title": source.title,
        "issuer": source.issuer,
        "reference": source.reference,
        "articleOrPage": source.article_or_page,
        "effectiveFrom": source.effective_from,
        "effectiveTo": source.effective_to,
        "reviewStatus": source.review_status,
    }


def _record(
    store: Store,
    *,
    user_id: int,
    original: str,
    normalized: str,
    outcome: str,
    text: str,
    score: float | None = None,
    intent_id: str | None = None,
    intent_code: str | None = None,
    intent_title: str | None = None,
    question_id: str | None = None,
    answer_id: str | None = None,
    sources: list[dict] | None = None,
    buttons: list[Button] | None = None,
    needs_review: bool = False,
    authoritative: bool = False,
    synthetic: bool = False,
    candidate_ids: list[str] | None = None,
    parent_interaction_id: int | None = None,
) -> AskResult:
    interaction_id = store.add_interaction(
        telegram_user_id=user_id,
        original_text=original,
        normalized_text=normalized,
        outcome=outcome,
        question_id=question_id,
        intent_id=intent_id,
        answer_id=answer_id,
        similarity_score=score,
        candidate_intent_ids=",".join(candidate_ids) if candidate_ids else None,
        needs_review=needs_review,
        parent_interaction_id=parent_interaction_id,
    )
    logger.info(
        "outcome=%s interaction=%s intent=%s answer=%s score=%s review=%s",
        outcome,
        interaction_id,
        intent_id,
        answer_id,
        None if score is None else round(score, 3),
        needs_review,
    )
    return AskResult(
        outcome=outcome,
        text=text,
        authoritative=authoritative,
        synthetic=synthetic,
        interaction_id=interaction_id,
        score=score,
        intent_id=intent_id,
        intent_code=intent_code,
        intent_title=intent_title,
        question_id=question_id,
        answer_id=answer_id,
        sources=sources or [],
        buttons=buttons or [],
        needs_review=needs_review,
    )


def result_to_json(result: AskResult) -> dict:
    return {
        "ok": True,
        "outcome": result.outcome,
        "text": result.text,
        "authoritative": result.authoritative,
        "synthetic": result.synthetic,
        "interactionId": result.interaction_id,
        "score": result.score,
        "intentId": result.intent_id,
        "intentCode": result.intent_code,
        "intentTitle": result.intent_title,
        "questionId": result.question_id,
        "answerId": result.answer_id,
        "sources": result.sources,
        "needsReview": result.needs_review,
        "buttons": [
            {
                "kind": button.kind,
                "label": button.label,
                "intentId": button.intent_id,
                "field": button.field,
                "value": button.value,
            }
            for button in result.buttons
        ],
    }


def dumps_result(result: AskResult) -> str:
    return json.dumps(result_to_json(result), ensure_ascii=False)
