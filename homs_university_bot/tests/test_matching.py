"""Matching: several wordings, one intent, and clarification when scores are close."""

import io
import logging
import os

from homs_bot.llm import DisabledModelProvider
from homs_bot.logging_config import SecretFilter, setup_logging
from homs_bot.matching import IntentHit, decide_hits
from homs_bot.models import StudentContext
from homs_bot.pipeline import ask
from homs_bot.similarity import EmbeddingSimilarityIndex, lexical_score
from homs_bot.text_norm import normalize_arabic

from helpers import StoreTestCase, add_real, make_settings


class ScriptedIndex:
    def __init__(self, scores: dict[str, float]):
        self.scores = scores

    def score(self, query: str, candidate: str) -> float:
        return self.scores.get(candidate, 0.0)


class NormalizationTest(StoreTestCase):
    def test_folds_spelling_and_keeps_the_original_elsewhere(self) -> None:
        self.assertEqual(normalize_arabic("إِيقاف التسجيل؟"), "ايقاف التسجيل")
        self.assertEqual(normalize_arabic("سنة ٢"), "سنه 2")
        self.assertEqual(normalize_arabic("بدي أجل"), "بدي اجل")
        original = "كيف أوقف تسجيلي؟"
        add_real(self.store, code="keep", wording="صيغة أخرى", body="جواب")
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text=original,
        )
        saved = self.store.get_interaction(result.interaction_id)
        assert saved is not None
        self.assertEqual(saved.original_text, original)
        self.assertNotEqual(saved.normalized_text, original)


class AmbiguousMatchTest(StoreTestCase):
    def test_close_scores_request_clarification(self) -> None:
        hits = [
            IntentHit("intent_pay", "fee_pay", "دفع الرسم", "q1", 0.80),
            IntentHit("intent_refund", "fee_refund", "استرداد الرسم", "q2", 0.76),
        ]
        self.assertEqual(decide_hits(hits, self.settings), "clarify")

    def test_reliable_score_with_margin_matches(self) -> None:
        hits = [
            IntentHit("intent_pay", "fee_pay", "دفع الرسم", "q1", 0.91),
            IntentHit("intent_refund", "fee_refund", "استرداد الرسم", "q2", 0.70),
        ]
        self.assertEqual(decide_hits(hits, self.settings), "matched")

    def test_pipeline_shows_clarification_buttons_for_close_scores(self) -> None:
        add_real(self.store, code="fee_pay", wording="دفع الرسوم", body="جواب الدفع.", title="دفع")
        self.store.add_intent(
            id="intent_fee_refund",
            code="fee_refund",
            title_ar="استرداد الرسم",
            status="approved",
        )
        self.store.add_question(
            id="q_fee_refund",
            intent_id="intent_fee_refund",
            wording="استرداد الرسوم",
            status="approved",
        )
        index = ScriptedIndex(
            {
                normalize_arabic("دفع الرسوم"): 0.80,
                normalize_arabic("استرداد الرسوم"): 0.76,
            }
        )
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=5,
            text="الرسوم",
            similarity=index,
        )
        self.assertEqual(result.outcome, "clarification")
        self.assertFalse(result.authoritative)
        self.assertIsNone(result.answer_id)
        labels = [button.label for button in result.buttons]
        self.assertIn("عنوان fee_pay", labels)
        self.assertIn("استرداد الرسم", labels)
        self.assertTrue(any(button.kind == "reject" for button in result.buttons))

    def test_two_wordings_share_one_intent(self) -> None:
        add_real(self.store, code="docs", wording="كيف بجيب كشف علامات", body="نموذج الوثائق.")
        self.store.add_question(
            id="q_docs_alt",
            intent_id="intent_docs",
            wording="بدي وثيقة علامات",
            status="approved",
        )
        first = ask(self.store, self.settings, telegram_user_id=1, text="كيف بجيب كشف علامات")
        second = ask(self.store, self.settings, telegram_user_id=1, text="بدي وثيقة علامات")
        self.assertEqual(first.intent_id, "intent_docs")
        self.assertEqual(second.intent_id, "intent_docs")
        self.assertNotEqual(first.question_id, second.question_id)
        self.assertEqual(lexical_score(normalize_arabic("بدي وثيقة علامات"), normalize_arabic("بدي وثيقة علامات")), 1)


class ThresholdShapeTest(StoreTestCase):
    def test_weak_single_score_asks_for_confirmation(self) -> None:
        hits = [IntentHit("intent_docs", "docs", "وثائق", "q", 0.70)]
        self.assertEqual(decide_hits(hits, self.settings), "confirm")

    def test_scores_are_not_treated_as_a_requirement_to_invent_text(self) -> None:
        self.store.save_context(StudentContext(telegram_user_id=1))
        result = ask(self.store, self.settings, telegram_user_id=1, text="سؤال لا يوجد له أي سجل")
        self.assertEqual(result.outcome, "unmatched")
        self.assertIn("ما عم أخترع", result.text)
        self.assertTrue(result.needs_review)
        queued = self.store.list_review_queue()
        self.assertEqual(queued[0].original_text, "سؤال لا يوجد له أي سجل")


class ExtensionPointsTest(StoreTestCase):
    def test_model_and_embeddings_stay_disabled(self) -> None:
        with self.assertRaises(NotImplementedError):
            DisabledModelProvider().rewrite_query("بدي أجل")
        with self.assertRaises(NotImplementedError):
            EmbeddingSimilarityIndex().score("ا", "ب")

    def test_log_filter_redacts_the_bot_token(self) -> None:
        os.environ["TELEGRAM_BOT_TOKEN"] = "999:SUPERSECRET"
        record = logging.LogRecord(
            "homs_bot",
            logging.INFO,
            __file__,
            1,
            "failed with 999:SUPERSECRET",
            (),
            None,
        )
        SecretFilter().filter(record)
        self.assertNotIn("SUPERSECRET", record.getMessage())
        self.assertIn("[REDACTED]", record.getMessage())
        del os.environ["TELEGRAM_BOT_TOKEN"]

    def test_child_logger_records_and_tracebacks_are_redacted(self) -> None:
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root.addHandler(handler)
        os.environ["TELEGRAM_BOT_TOKEN"] = "999:SUPERSECRET"
        try:
            setup_logging(make_settings())
            logging.getLogger("aiogram.event").error(
                "request to https://api.telegram.org/bot999:SUPERSECRET/getUpdates failed"
            )
            try:
                raise RuntimeError("url bot999:SUPERSECRET")
            except RuntimeError:
                logging.getLogger("homs_bot.handlers").exception("handler failed")
        finally:
            root.removeHandler(handler)
            del os.environ["TELEGRAM_BOT_TOKEN"]
        output = stream.getvalue()
        self.assertIn("getUpdates failed", output)
        self.assertIn("RuntimeError", output)
        self.assertNotIn("SUPERSECRET", output)
        self.assertGreaterEqual(output.count("[REDACTED]"), 2)


class SettingsGuardTest(StoreTestCase):
    def test_invalid_thresholds_are_rejected(self) -> None:
        os.environ["HU_MATCH_AUTO"] = "0.2"
        os.environ["HU_MATCH_CLARIFY"] = "0.9"
        with self.assertRaises(SystemExit):
            make_settings()  # direct constructor does not validate
            from homs_bot.config import Settings

            Settings.from_env()
        os.environ.pop("HU_MATCH_AUTO")
        os.environ.pop("HU_MATCH_CLARIFY")
