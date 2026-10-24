"""Local administrator commands. Student feedback cannot publish an answer."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

from homs_bot.config import Settings, load_dotenv_file
from homs_bot.db import Store, open_store
from homs_bot.seed import seed_demo

CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
STATUSES = ("draft", "approved", "retired")
MIN_KEY_LENGTH = 12


def hash_admin_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _refuse(reason: str) -> None:
    print(f"مرفوض: {reason}", file=sys.stderr)
    raise SystemExit(2)


def require_admin(env_path: Path | None = None) -> None:
    """Compare the key typed for this session with the hash stored in .env.

    The key is read before .env is loaded, so a plain key saved in .env does not
    unlock the commands by itself.
    """
    supplied = os.environ.get("HU_ADMIN_KEY", "").strip()
    load_dotenv_file(env_path)
    expected = os.environ.get("HU_ADMIN_KEY_SHA256", "").strip().lower()
    if not expected:
        _refuse(
            "ما في HU_ADMIN_KEY_SHA256 في .env. "
            "ولّده بالأمر: python -m homs_bot.admin_cli admin-key-hash"
        )
    if len(supplied) < MIN_KEY_LENGTH:
        _refuse(f"أوامر الإدارة تحتاج HU_ADMIN_KEY بطول {MIN_KEY_LENGTH} محرفاً على الأقل.")
    if not hmac.compare_digest(hash_admin_key(supplied), expected):
        _refuse("HU_ADMIN_KEY لا يطابق HU_ADMIN_KEY_SHA256.")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _check_code(code: str) -> None:
    if not CODE_RE.match(code):
        raise SystemExit("رمز القصد يجب أن يكون أحرفاً إنجليزية صغيرة وأرقاماً وشرطة سفلية.")


def _check_status(status: str) -> None:
    if status not in STATUSES:
        raise SystemExit("الحالة يجب أن تكون draft أو approved أو retired.")


def _check_date(value: str | None) -> None:
    if not value:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"تاريخ غير صالح: {value}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m homs_bot.admin_cli",
        description="Manage intents, variants, answers, and the review queue.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("admin-key-hash")
    sub.add_parser("intent-list")
    add_intent = sub.add_parser("intent-add")
    add_intent.add_argument("--code", required=True)
    add_intent.add_argument("--title", required=True)
    add_intent.add_argument("--description", default="")
    add_intent.add_argument("--status", default="draft")

    retire_intent = sub.add_parser("intent-retire")
    retire_intent.add_argument("--id", required=True)

    questions = sub.add_parser("question-list")
    questions.add_argument("--intent")
    add_question = sub.add_parser("question-add")
    add_question.add_argument("--intent", required=True, help="Intent code")
    add_question.add_argument("--wording", required=True)
    add_question.add_argument("--status", default="draft")
    approve_question = sub.add_parser("question-approve")
    approve_question.add_argument("--id", required=True)
    retire_question = sub.add_parser("question-retire")
    retire_question.add_argument("--id", required=True)

    sub.add_parser("source-list")
    add_source = sub.add_parser("source-add")
    add_source.add_argument("--title", required=True)
    add_source.add_argument("--issuer", required=True)
    add_source.add_argument("--reference", default="")
    add_source.add_argument("--article", default="")
    add_source.add_argument("--effective-from")
    add_source.add_argument("--effective-to")
    add_source.add_argument("--status", default="draft")

    answers = sub.add_parser("answer-list")
    answers.add_argument("--intent", required=True)
    add_answer = sub.add_parser("answer-add")
    add_answer.add_argument("--intent", required=True)
    add_answer.add_argument("--body", required=True)
    add_answer.add_argument("--source", required=True)
    add_answer.add_argument("--faculty")
    add_answer.add_argument("--year")
    add_answer.add_argument("--system")
    add_answer.add_argument("--specialization")
    add_answer.add_argument("--effective-from")
    add_answer.add_argument("--effective-to")
    add_answer.add_argument("--supersedes")
    add_answer.add_argument("--status", default="draft")
    retire_answer = sub.add_parser("answer-retire")
    retire_answer.add_argument("--id", required=True)
    history = sub.add_parser("answer-history")
    history.add_argument("--intent", required=True)

    sub.add_parser("review-unmatched")
    sub.add_parser("review-feedback")
    mapped = sub.add_parser("review-map")
    mapped.add_argument("--interaction", required=True, type=int)
    mapped.add_argument("--intent", required=True)
    resolved = sub.add_parser("review-resolve-feedback")
    resolved.add_argument("--id", required=True, type=int)
    resolved.add_argument("--note", required=True)
    dismissed = sub.add_parser("review-dismiss")
    dismissed.add_argument("--interaction", required=True, type=int)

    sub.add_parser("seed-demo")
    delete_context = sub.add_parser("delete-context")
    delete_context.add_argument("--telegram-id", required=True, type=int)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "admin-key-hash":
        admin_key_hash()
        return
    require_admin()
    settings = Settings.from_env()
    store = open_store(settings.db_path)
    commands = {
        "intent-list": intent_list,
        "intent-add": intent_add,
        "intent-retire": intent_retire,
        "question-list": question_list,
        "question-add": question_add,
        "question-approve": question_approve,
        "question-retire": question_retire,
        "source-list": source_list,
        "source-add": source_add,
        "answer-list": answer_list,
        "answer-add": answer_add,
        "answer-retire": answer_retire,
        "answer-history": answer_history,
        "review-unmatched": review_unmatched,
        "review-feedback": review_feedback,
        "review-map": review_map,
        "review-resolve-feedback": review_resolve_feedback,
        "review-dismiss": review_dismiss,
        "seed-demo": run_seed,
        "delete-context": delete_context,
    }
    commands[args.command](store, args)


def admin_key_hash() -> None:
    key = getpass.getpass("المفتاح الجديد: ").strip()
    if len(key) < MIN_KEY_LENGTH:
        raise SystemExit(f"المفتاح لازم يكون {MIN_KEY_LENGTH} محرفاً على الأقل.")
    if getpass.getpass("أعد كتابة المفتاح: ").strip() != key:
        raise SystemExit("المفتاحان غير متطابقين.")
    print(f"HU_ADMIN_KEY_SHA256={hash_admin_key(key)}")


def intent_list(store: Store, _args: argparse.Namespace) -> None:
    for intent in store.list_intents():
        mark = "synthetic" if intent.is_synthetic else "real"
        print(f"{intent.id}\t{intent.code}\t{intent.status}\t{mark}\t{intent.title_ar}")


def intent_add(store: Store, args: argparse.Namespace) -> None:
    _check_code(args.code)
    _check_status(args.status)
    intent_id = _new_id("intent")
    store.add_intent(
        id=intent_id,
        code=args.code,
        title_ar=args.title,
        description_ar=args.description or None,
        status=args.status,
        is_synthetic=False,
    )
    print(f"أُضيف القصد {intent_id} بحالة {args.status}.")


def intent_retire(store: Store, args: argparse.Namespace) -> None:
    if store.get_intent(args.id) is None:
        raise SystemExit("القصد غير موجود.")
    store.set_intent_status(args.id, "retired")
    print(f"تقاعد القصد {args.id}. الصيغ والأجوبة القديمة بقيت في السجل.")


def _intent_from_code(store: Store, code: str):
    intent = store.get_intent_by_code(code)
    if intent is None:
        raise SystemExit(f"ما في قصد بهذا الرمز: {code}")
    return intent


def question_list(store: Store, args: argparse.Namespace) -> None:
    intent_id = None
    if args.intent:
        intent_id = _intent_from_code(store, args.intent).id
    for question in store.list_questions(intent_id):
        mark = "synthetic" if question.is_synthetic else "real"
        print(f"{question.id}\t{question.status}\t{mark}\t{question.wording}")


def question_add(store: Store, args: argparse.Namespace) -> None:
    _check_status(args.status)
    intent = _intent_from_code(store, args.intent)
    question_id = _new_id("q")
    store.add_question(
        id=question_id,
        intent_id=intent.id,
        wording=args.wording,
        status=args.status,
        is_synthetic=False,
    )
    print(f"أُضيفت صيغة السؤال {question_id} بحالة {args.status}.")


def question_approve(store: Store, args: argparse.Namespace) -> None:
    if store.get_question(args.id) is None:
        raise SystemExit("صيغة السؤال غير موجودة.")
    store.set_question_status(args.id, "approved")
    print(f"اعتُمدت صيغة السؤال {args.id}.")


def question_retire(store: Store, args: argparse.Namespace) -> None:
    if store.get_question(args.id) is None:
        raise SystemExit("صيغة السؤال غير موجودة.")
    store.set_question_status(args.id, "retired")
    print(f"تقاعدت صيغة السؤال {args.id} وبقيت في السجل.")


def source_list(store: Store, _args: argparse.Namespace) -> None:
    for source in store.list_sources():
        mark = "synthetic" if source.is_synthetic else "real"
        print(f"{source.id}\t{source.review_status}\t{mark}\t{source.title}")


def source_add(store: Store, args: argparse.Namespace) -> None:
    _check_status(args.status)
    _check_date(args.effective_from)
    _check_date(args.effective_to)
    source_id = _new_id("src")
    store.add_source(
        id=source_id,
        title=args.title,
        issuer=args.issuer,
        reference=args.reference or None,
        article_or_page=args.article or None,
        effective_from=args.effective_from,
        effective_to=args.effective_to,
        review_status=args.status,
        is_synthetic=False,
    )
    print(f"أُضيف المصدر {source_id} بحالة {args.status}.")


def answer_list(store: Store, args: argparse.Namespace) -> None:
    intent = _intent_from_code(store, args.intent)
    for answer in store.list_answers_by_intent(intent.id):
        mark = "synthetic" if answer.is_synthetic else "real"
        print(
            f"{answer.id}\tv{answer.version}\t{answer.status}\t{mark}\t"
            f"faculty={answer.faculty_code or '-'}\tyear={answer.academic_year or '-'}\t"
            f"system={answer.study_system or '-'}"
        )


def answer_add(store: Store, args: argparse.Namespace) -> None:
    _check_status(args.status)
    _check_date(args.effective_from)
    _check_date(args.effective_to)
    intent = _intent_from_code(store, args.intent)
    source = store.get_source(args.source)
    if source is None:
        raise SystemExit("المصدر غير موجود.")
    if args.status == "approved" and source.review_status != "approved":
        raise SystemExit("لا يمكن اعتماد جواب ومصدره غير معتمد.")
    version = 1
    if args.supersedes:
        previous = store.get_answer(args.supersedes)
        if previous is None:
            raise SystemExit("الجواب السابق المذكور في --supersedes غير موجود.")
        if previous.intent_id != intent.id:
            raise SystemExit("الجواب المذكور في --supersedes تابع لقصد آخر.")
        version = previous.version + 1
    answer_id = _new_id("ans")
    store.add_answer(
        id=answer_id,
        intent_id=intent.id,
        source_id=source.id,
        body_ar=args.body,
        status=args.status,
        faculty_code=args.faculty,
        academic_year=args.year,
        study_system=args.system,
        specialization_code=args.specialization,
        effective_from=args.effective_from,
        effective_to=args.effective_to,
        version=version,
        supersedes_answer_id=args.supersedes,
        is_synthetic=False,
    )
    print(f"أُضيف الجواب {answer_id} إصدار {version} بحالة {args.status}.")


def answer_retire(store: Store, args: argparse.Namespace) -> None:
    if store.get_answer(args.id) is None:
        raise SystemExit("الجواب غير موجود.")
    store.set_answer_status(args.id, "retired")
    print(f"تقاعد الجواب {args.id} وبقي في السجل التاريخي.")


def answer_history(store: Store, args: argparse.Namespace) -> None:
    intent = _intent_from_code(store, args.intent)
    answers = store.list_answers_by_intent(intent.id)
    if not answers:
        print("ما في أجوبة لهذا القصد.")
        return
    for answer in answers:
        print(
            f"{answer.id}\tv{answer.version}\t{answer.status}\t"
            f"supersedes={answer.supersedes_answer_id or '-'}"
        )
        print(answer.body_ar)
        print("---")


def review_unmatched(store: Store, _args: argparse.Namespace) -> None:
    rows = store.list_review_queue()
    if not rows:
        print("طابور المراجعة فاضي.")
        return
    for row in rows:
        print(
            f"#{row.id}\t{row.outcome}\tintent={row.intent_id or '-'}\t"
            f"score={row.similarity_score if row.similarity_score is not None else '-'}"
        )
        print(row.original_text)
        print("---")


def review_feedback(store: Store, _args: argparse.Namespace) -> None:
    rows = store.list_pending_feedback()
    if not rows:
        print("ما في ملاحظات بانتظار المراجعة.")
        return
    for row in rows:
        print(f"#{row.id}\tinteraction={row.interaction_id}\t{row.verdict}")


def review_map(store: Store, args: argparse.Namespace) -> None:
    interaction = store.get_interaction(args.interaction)
    if interaction is None:
        raise SystemExit("التفاعل غير موجود.")
    intent = _intent_from_code(store, args.intent)
    question_id = _new_id("q")
    store.add_question(
        id=question_id,
        intent_id=intent.id,
        wording=interaction.original_text,
        status="draft",
        is_synthetic=False,
    )
    store.set_interaction_review(interaction.id, "reviewed")
    print(
        f"أُنشئت صيغة مسودة {question_id} من التفاعل #{interaction.id}. "
        "لن تُستخدم في المطابقة قبل question-approve."
    )


def review_resolve_feedback(store: Store, args: argparse.Namespace) -> None:
    if store.get_feedback(args.id) is None:
        raise SystemExit("الملاحظة غير موجودة.")
    store.resolve_feedback(args.id, args.note)
    print(f"أُغلقت الملاحظة #{args.id} من دون تعديل أي جواب.")


def review_dismiss(store: Store, args: argparse.Namespace) -> None:
    if store.get_interaction(args.interaction) is None:
        raise SystemExit("التفاعل غير موجود.")
    store.set_interaction_review(args.interaction, "dismissed")
    print(f"أُغلق التفاعل #{args.interaction} من دون إضافة صيغة.")


def run_seed(store: Store, _args: argparse.Namespace) -> None:
    counts = seed_demo(store)
    print(
        "حُمّلت بيانات تجريبية مصطنعة وممنوعة في وضع الإنتاج: "
        f"مصادر {counts['sources']}، مقاصد {counts['intents']}، "
        f"صيغ {counts['questions']}، أجوبة {counts['answers']}."
    )


def delete_context(store: Store, args: argparse.Namespace) -> None:
    store.delete_student(args.telegram_id)
    print(f"حُذف سياق الطالب وسجل تفاعلاته للمعرّف {args.telegram_id}.")


if __name__ == "__main__":
    main()
