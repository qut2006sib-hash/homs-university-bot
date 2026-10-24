"""Feedback and the admin queue never publish or rewrite an answer."""

import os
import tempfile
from datetime import date

from homs_bot.admin_cli import main as admin_main
from homs_bot.db import open_store
from homs_bot.pipeline import ask, record_feedback

from helpers import StoreTestCase, add_real, make_settings


class FeedbackReviewTest(StoreTestCase):
    def test_incorrect_feedback_is_queued_and_does_not_change_the_answer(self) -> None:
        add_real(self.store, code="docs", wording="كيف بجيب كشف علامات", body="الجواب المعتمد الثابت")
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=11,
            text="كيف بجيب كشف علامات",
            today=date(2026, 2, 2),
        )
        note = record_feedback(
            self.store,
            telegram_user_id=11,
            interaction_id=result.interaction_id,
            verdict="incorrect",
        )
        self.assertIn("ما تغيّر", note)
        self.assertEqual(self.store.get_answer("ans_docs").body_ar, "الجواب المعتمد الثابت")
        pending = self.store.list_pending_feedback()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].verdict, "incorrect")
        self.assertEqual(pending[0].review_status, "pending")

        again = ask(self.store, self.settings, telegram_user_id=11, text="كيف بجيب كشف علامات")
        self.assertEqual(again.answer_id, "ans_docs")
        self.assertIn("الجواب المعتمد الثابت", again.text)

    def test_resolving_feedback_still_does_not_edit_the_answer(self) -> None:
        add_real(self.store, code="docs", wording="بدي وثيقة", body="يبقى كما هو")
        result = ask(self.store, self.settings, telegram_user_id=3, text="بدي وثيقة")
        record_feedback(
            self.store,
            telegram_user_id=3,
            interaction_id=result.interaction_id,
            verdict="helpful",
        )
        feedback_id = self.store.list_pending_feedback()[0].id
        self.store.resolve_feedback(feedback_id, "شُوهدت الملاحظة ولم يُعدَّل النص")
        closed = self.store.get_feedback(feedback_id)
        assert closed is not None
        self.assertEqual(closed.review_status, "reviewed")
        self.assertEqual(self.store.get_answer("ans_docs").body_ar, "يبقى كما هو")
        self.assertEqual(self.store.list_pending_feedback(), [])

    def test_stranger_cannot_attach_feedback_to_another_student(self) -> None:
        add_real(self.store, code="docs", wording="سؤال", body="جواب")
        result = ask(self.store, self.settings, telegram_user_id=1, text="سؤال")
        note = record_feedback(
            self.store,
            telegram_user_id=2,
            interaction_id=result.interaction_id,
            verdict="incorrect",
        )
        self.assertIn("ما قدرت", note)
        self.assertEqual(self.store.list_pending_feedback(), [])


class AdminQueueTest(StoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._old_env = {
            key: os.environ.get(key)
            for key in ("HU_ADMIN_KEY", "HU_DB_PATH", "HU_ALLOW_SYNTHETIC", "HU_MATCH_AUTO", "HU_MATCH_CLARIFY")
        }
        handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        handle.close()
        self.db_path = handle.name
        os.environ["HU_ADMIN_KEY"] = "local-admin-key"
        os.environ["HU_DB_PATH"] = self.db_path
        os.environ["HU_ALLOW_SYNTHETIC"] = "0"
        os.environ.pop("HU_MATCH_AUTO", None)
        os.environ.pop("HU_MATCH_CLARIFY", None)

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        super().tearDown()

    def test_admin_cli_is_refused_without_a_key(self) -> None:
        os.environ["HU_ADMIN_KEY"] = "short"
        with self.assertRaises(SystemExit) as caught:
            admin_main(["intent-list"])
        self.assertEqual(caught.exception.code, 2)

    def test_mapping_a_question_stays_draft_until_explicit_approval(self) -> None:
        store = open_store(self.db_path)
        add_real(store, code="rule", wording="صيغة معتمدة سابقة", body="الجواب الأصلي")
        interaction_id = store.add_interaction(
            telegram_user_id=15,
            original_text="بدي صيغة جديدة xyzuvw",
            normalized_text="بدي صيغه جديده xyzuvw",
            outcome="unmatched",
            needs_review=True,
        )
        before = store.get_answer("ans_rule").body_ar
        store.conn.close()

        admin_main(["review-map", "--interaction", str(interaction_id), "--intent", "rule"])
        store = open_store(self.db_path)
        drafts = [item for item in store.list_questions() if item.status == "draft"]
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].wording, "بدي صيغة جديدة xyzuvw")
        self.assertEqual(store.get_interaction(interaction_id).review_status, "reviewed")
        hidden = ask(
            store,
            make_settings(),
            telegram_user_id=15,
            text="بدي صيغة جديدة xyzuvw",
        )
        self.assertNotEqual(hidden.outcome, "answered")
        self.assertEqual(store.get_answer("ans_rule").body_ar, before)
        draft_id = drafts[0].id
        store.conn.close()

        admin_main(["question-approve", "--id", draft_id])
        store = open_store(self.db_path)
        matched = ask(
            store,
            make_settings(),
            telegram_user_id=15,
            text="بدي صيغة جديدة xyzuvw",
            today=date(2026, 4, 1),
        )
        self.assertEqual(matched.outcome, "answered")
        self.assertEqual(matched.intent_id, "intent_rule")
        self.assertEqual(matched.question_id, draft_id)
        self.assertEqual(store.get_answer("ans_rule").body_ar, before)
        store.conn.close()

    def test_seed_command_marks_rows_synthetic(self) -> None:
        admin_main(["seed-demo"])
        store = open_store(self.db_path)
        intents = store.list_intents()
        self.assertTrue(intents)
        self.assertTrue(all(item.is_synthetic for item in intents))
        self.assertTrue(all(item.is_synthetic for item in store.list_sources()))
        hidden = ask(
            store,
            make_settings(allow_synthetic=False),
            telegram_user_id=1,
            text="كيف بجيب كشف علامات",
        )
        self.assertEqual(hidden.outcome, "unmatched")
        store.conn.close()

    def test_cannot_approve_an_answer_whose_source_is_draft(self) -> None:
        store = open_store(self.db_path)
        store.add_intent(id="intent_x", code="extra", title_ar="إضافي", status="approved")
        store.add_source(
            id="src_x",
            title="مسودة",
            issuer="اختبار",
            review_status="draft",
        )
        store.conn.close()
        with self.assertRaises(SystemExit):
            admin_main(
                [
                    "answer-add",
                    "--intent",
                    "extra",
                    "--body",
                    "نص",
                    "--source",
                    "src_x",
                    "--status",
                    "approved",
                ]
            )
