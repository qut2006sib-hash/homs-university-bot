"""Load labelled synthetic rows. Every seeded row is forced to is_synthetic=1."""

from __future__ import annotations

import json
from pathlib import Path

from homs_bot.db import Store

DEMO_PATH = Path(__file__).resolve().parent.parent / "data" / "synthetic_demo.json"


def seed_demo(store: Store, path: Path | None = None) -> dict[str, int]:
    payload = json.loads((path or DEMO_PATH).read_text(encoding="utf-8"))
    for source in payload["sources"]:
        store.add_source(
            id=source["id"],
            title=source["title"],
            issuer=source["issuer"],
            reference=source.get("reference"),
            article_or_page=source.get("article_or_page"),
            effective_from=source.get("effective_from"),
            effective_to=source.get("effective_to"),
            review_status=source["review_status"],
            is_synthetic=True,
        )
    for intent in payload["intents"]:
        store.add_intent(
            id=intent["id"],
            code=intent["code"],
            title_ar=intent["title_ar"],
            description_ar=intent.get("description_ar"),
            status=intent["status"],
            is_synthetic=True,
        )
    for question in payload["questions"]:
        store.add_question(
            id=question["id"],
            intent_id=question["intent_id"],
            wording=question["wording"],
            status=question["status"],
            is_synthetic=True,
        )
    for answer in payload["answers"]:
        store.add_answer(
            id=answer["id"],
            intent_id=answer["intent_id"],
            source_id=answer.get("source_id"),
            body_ar=answer["body_ar"],
            status=answer["status"],
            faculty_code=answer.get("faculty_code"),
            academic_year=answer.get("academic_year"),
            study_system=answer.get("study_system"),
            specialization_code=answer.get("specialization_code"),
            effective_from=answer.get("effective_from"),
            effective_to=answer.get("effective_to"),
            version=int(answer.get("version") or 1),
            supersedes_answer_id=answer.get("supersedes_answer_id"),
            is_synthetic=True,
        )
    return {
        "sources": len(payload["sources"]),
        "intents": len(payload["intents"]),
        "questions": len(payload["questions"]),
        "answers": len(payload["answers"]),
    }
