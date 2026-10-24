"""JSON entry used by the local lab. It cannot approve or edit regulations."""

from __future__ import annotations

import json
import sys
from dataclasses import replace

from homs_bot.catalog import load_catalog
from homs_bot.config import Settings
from homs_bot.db import open_store
from homs_bot.models import StudentContext
from homs_bot.pipeline import ask, dumps_result, record_feedback, reject_clarification
from homs_bot.seed import seed_demo


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"ask", "feedback", "delete", "queue", "catalog"}:
        print(
            "usage: python -m homs_bot.lab_cli ask|feedback|delete|queue|catalog",
            file=sys.stderr,
        )
        raise SystemExit(2)
    command = args[0]
    if command == "catalog":
        _emit(_catalog_payload())
        return
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    settings = Settings.from_env()
    if "allowSynthetic" in payload:
        settings = replace(settings, allow_synthetic=bool(payload["allowSynthetic"]))
    store = open_store(settings.db_path)
    seed_demo(store)
    user_id = int(payload.get("userId") or 0)
    if command == "ask":
        _save_context(store, user_id, payload)
        if payload.get("rejectInteractionId"):
            result = reject_clarification(
                store,
                telegram_user_id=user_id,
                interaction_id=int(payload["rejectInteractionId"]),
            )
        else:
            result = ask(
                store,
                settings,
                telegram_user_id=user_id,
                text=str(payload.get("text") or ""),
                chosen_intent_id=payload.get("chosenIntentId") or None,
                parent_interaction_id=payload.get("parentInteractionId"),
                link_clarification=bool(payload.get("linkClarification")),
            )
        _emit(json.loads(dumps_result(result)))
        return
    if command == "feedback":
        note = record_feedback(
            store,
            telegram_user_id=user_id,
            interaction_id=int(payload["interactionId"]),
            verdict=str(payload.get("verdict") or ""),
        )
        _emit({"ok": True, "text": note})
        return
    if command == "delete":
        store.delete_student(user_id)
        _emit({"ok": True, "text": "انحذفت بيانات المختبر لهذا المستخدم."})
        return
    interactions = []
    for row in store.list_recent_interactions(user_id, limit=8):
        interactions.append(
            {
                "id": row.id,
                "outcome": row.outcome,
                "text": row.original_text,
                "intentId": row.intent_id,
                "questionId": row.question_id,
                "answerId": row.answer_id,
                "score": row.similarity_score,
                "needsReview": row.needs_review,
                "reviewStatus": row.review_status,
            }
        )
    feedback_rows = []
    for row in store.list_recent_feedback(user_id, limit=8):
        feedback_rows.append(
            {
                "id": row.id,
                "interactionId": row.interaction_id,
                "verdict": row.verdict,
                "reviewStatus": row.review_status,
            }
        )
    _emit({"ok": True, "interactions": interactions, "feedback": feedback_rows})


def _save_context(store, user_id: int, payload: dict) -> None:
    if user_id <= 0:
        return
    store.save_context(
        StudentContext(
            telegram_user_id=user_id,
            faculty_code=payload.get("facultyCode"),
            academic_year=payload.get("academicYear"),
            study_system=payload.get("studySystem"),
            specialization_code=payload.get("specializationCode"),
        )
    )


def _catalog_payload() -> dict:
    catalog = load_catalog()

    def dump(items):
        return [{"code": item.code, "label": item.label} for item in items]

    return {
        "ok": True,
        "faculties": dump(catalog.faculties),
        "years": dump(catalog.years),
        "studySystems": dump(catalog.study_systems),
        "specializations": {
            faculty: dump(items) for faculty, items in catalog.specializations.items()
        },
        "otherLabel": catalog.other_label,
    }


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
