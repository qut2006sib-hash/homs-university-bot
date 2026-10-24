"""Approved answers only: drafts, retired rules, conflicts, and synthetic rows."""

from datetime import date

from homs_bot.models import StudentContext
from homs_bot.pipeline import ask
from homs_bot.seed import seed_demo

from helpers import StoreTestCase, add_real, make_settings


class ApprovedAnswerTest(StoreTestCase):
    def test_exact_variant_returns_the_approved_answer_and_source(self) -> None:
        add_real(
            self.store,
            code="docs",
            wording="كيف بجيب كشف علامات",
            body="يُسلّم النموذج من الديوان في هذا الاختبار.",
            title="تعليمات الوثائق الاختبارية",
        )
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text="كيف بجيب كشف علامات؟",
            today=date(2026, 3, 1),
        )
        self.assertEqual(result.outcome, "answered")
        self.assertTrue(result.authoritative)
        self.assertFalse(result.synthetic)
        self.assertEqual(result.answer_id, "ans_docs")
        self.assertEqual(result.question_id, "q_docs")
        self.assertIn("الديوان", result.text)
        self.assertIn("تعليمات الوثائق الاختبارية", result.text)
        self.assertIn("بند اختبار docs", result.text)
        self.assertEqual(result.sources[0]["reviewStatus"], "approved")

    def test_draft_answer_is_not_returned(self) -> None:
        add_real(
            self.store,
            code="drafted",
            wording="شو المسودة",
            body="مسودة سرية لا تُعرض",
            answer_status="draft",
        )
        result = ask(self.store, self.settings, telegram_user_id=1, text="شو المسودة")
        self.assertEqual(result.outcome, "no_verified_answer")
        self.assertNotIn("سرية", result.text)
        self.assertFalse(result.authoritative)
        self.assertTrue(result.needs_review)

    def test_unapproved_source_blocks_an_approved_answer(self) -> None:
        add_real(
            self.store,
            code="loose",
            wording="سؤال المصدر المسودة",
            body="لا يجب أن يظهر هذا النص",
            source_status="draft",
        )
        result = ask(self.store, self.settings, telegram_user_id=1, text="سؤال المصدر المسودة")
        self.assertEqual(result.outcome, "no_verified_answer")
        self.assertNotIn("لا يجب", result.text)

    def test_retired_answer_stays_in_history_and_is_not_served(self) -> None:
        add_real(self.store, code="old", wording="شو القاعدة القديمة", body="قاعدة تقاعدَت")
        self.store.set_answer_status("ans_old", "retired")
        self.store.add_answer(
            id="ans_old_v2",
            intent_id="intent_old",
            source_id="src_old",
            body_ar="النسخة السارية بعد إلغاء القديمة",
            status="approved",
            version=2,
            supersedes_answer_id="ans_old",
            effective_from="2020-01-01",
        )
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text="شو القاعدة القديمة",
            today=date(2026, 1, 1),
        )
        self.assertEqual(result.outcome, "answered")
        self.assertEqual(result.answer_id, "ans_old_v2")
        self.assertNotIn("قاعدة تقاعد", result.text)
        self.assertIn("النسخة السارية", result.text)
        history = self.store.list_answers_by_intent("intent_old")
        self.assertEqual([item.id for item in history], ["ans_old", "ans_old_v2"])
        self.assertEqual(history[0].status, "retired")

    def test_approved_replacement_serves_without_retiring_the_old_version(self) -> None:
        add_real(self.store, code="ver", wording="شو النظام الحالي", body="النسخة الأولى")
        self.store.add_answer(
            id="ans_ver_v2",
            intent_id="intent_ver",
            source_id="src_ver",
            body_ar="النسخة الثانية المصححة",
            status="approved",
            version=2,
            supersedes_answer_id="ans_ver",
            effective_from="2020-01-01",
        )
        self.store.add_answer(
            id="ans_ver_v3",
            intent_id="intent_ver",
            source_id="src_ver",
            body_ar="النسخة الثالثة",
            status="approved",
            version=3,
            supersedes_answer_id="ans_ver_v2",
            effective_from="2027-01-01",
        )

        before = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text="شو النظام الحالي",
            today=date(2026, 6, 1),
        )
        self.assertEqual(before.outcome, "answered")
        self.assertEqual(before.answer_id, "ans_ver_v2")

        after = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text="شو النظام الحالي",
            today=date(2027, 6, 1),
        )
        self.assertEqual(after.outcome, "answered")
        self.assertEqual(after.answer_id, "ans_ver_v3")
        self.assertEqual(self.store.get_answer("ans_ver").status, "approved")

    def test_draft_replacement_keeps_the_old_version_live(self) -> None:
        add_real(self.store, code="pend", wording="شو النظام المعلق", body="النسخة المعتمدة")
        self.store.add_answer(
            id="ans_pend_v2",
            intent_id="intent_pend",
            source_id="src_pend",
            body_ar="مسودة بديلة",
            status="draft",
            version=2,
            supersedes_answer_id="ans_pend",
        )
        result = ask(self.store, self.settings, telegram_user_id=1, text="شو النظام المعلق")
        self.assertEqual(result.answer_id, "ans_pend")

    def test_retired_without_replacement_is_not_invented(self) -> None:
        add_real(self.store, code="gone", wording="قاعدة ملغاة بالكامل", body="نص ملغى")
        self.store.set_answer_status("ans_gone", "retired")
        result = ask(self.store, self.settings, telegram_user_id=1, text="قاعدة ملغاة بالكامل")
        self.assertEqual(result.outcome, "no_verified_answer")
        self.assertNotIn("نص ملغى", result.text)
        self.assertIsNotNone(self.store.get_answer("ans_gone"))

    def test_expired_window_is_not_served(self) -> None:
        add_real(
            self.store,
            code="dated",
            wording="سؤال منتهي",
            body="نافذ في الماضي فقط",
            effective_to="2024-01-01",
        )
        result = ask(
            self.store,
            self.settings,
            telegram_user_id=1,
            text="سؤال منتهي",
            today=date(2026, 5, 1),
        )
        self.assertEqual(result.outcome, "no_verified_answer")
        self.assertNotIn("الماضي", result.text)

    def test_conflicting_approved_answers_are_flagged(self) -> None:
        add_real(self.store, code="clash", wording="وريني التعارض", body="النص الأول المختلف")
        self.store.add_source(
            id="src_clash_b",
            title="مصدر متعارض ب",
            issuer="جهة اختبار",
            reference="file://tests/clash-b",
            article_or_page="بند ب",
            effective_from="2020-01-01",
            review_status="approved",
        )
        self.store.add_answer(
            id="ans_clash_b",
            intent_id="intent_clash",
            source_id="src_clash_b",
            body_ar="النص الثاني المختلف",
            status="approved",
            effective_from="2020-01-01",
        )
        result = ask(self.store, self.settings, telegram_user_id=1, text="وريني التعارض")
        self.assertEqual(result.outcome, "conflict_review")
        self.assertFalse(result.authoritative)
        self.assertIsNone(result.answer_id)
        self.assertNotIn("النص الأول", result.text)
        self.assertNotIn("النص الثاني", result.text)
        self.assertTrue(result.needs_review)

    def test_missing_field_is_requested_only_when_it_changes_the_answer(self) -> None:
        add_real(
            self.store,
            code="suspend",
            wording="كيف أوقف تسجيلي",
            body="جواب النظامي",
            study_system="regular",
        )
        self.store.add_source(
            id="src_open",
            title="مصدر المفتوح",
            issuer="جهة اختبار",
            effective_from="2020-01-01",
            review_status="approved",
        )
        self.store.add_answer(
            id="ans_open",
            intent_id="intent_suspend",
            source_id="src_open",
            body_ar="جواب المفتوح",
            status="approved",
            study_system="open",
            effective_from="2020-01-01",
        )
        missing = ask(self.store, self.settings, telegram_user_id=4, text="كيف أوقف تسجيلي")
        self.assertEqual(missing.outcome, "need_context")
        self.assertEqual(missing.buttons[0].field, "study_system")

        self.store.save_context(StudentContext(telegram_user_id=4, study_system="open"))
        chosen = ask(
            self.store,
            self.settings,
            telegram_user_id=4,
            text="كيف أوقف تسجيلي",
            today=date(2026, 1, 1),
        )
        self.assertEqual(chosen.answer_id, "ans_open")
        self.assertIn("المفتوح", chosen.text)

    def test_same_text_does_not_trigger_a_follow_up(self) -> None:
        body = "النص لا يتغير بين السنة العامة والسنة الثانية."
        add_real(self.store, code="same", wording="سؤال الغياب", body=body, faculty_code="informatics")
        self.store.add_answer(
            id="ans_same_y2",
            intent_id="intent_same",
            source_id="src_same",
            body_ar=body,
            status="approved",
            faculty_code="informatics",
            academic_year="2",
            effective_from="2020-01-01",
        )
        self.store.save_context(StudentContext(telegram_user_id=8, faculty_code="informatics"))
        result = ask(self.store, self.settings, telegram_user_id=8, text="سؤال الغياب")
        self.assertEqual(result.outcome, "answered")
        self.assertNotEqual(result.outcome, "need_context")

    def test_different_year_text_does_trigger_a_follow_up(self) -> None:
        add_real(
            self.store,
            code="exam",
            wording="غبت عن الامتحان شو بعمل",
            body="جواب بقية السنوات",
            faculty_code="informatics",
        )
        self.store.add_answer(
            id="ans_exam_y2",
            intent_id="intent_exam",
            source_id="src_exam",
            body_ar="جواب السنة الثانية فقط",
            status="approved",
            faculty_code="informatics",
            academic_year="2",
            effective_from="2020-01-01",
        )
        self.store.save_context(StudentContext(telegram_user_id=8, faculty_code="informatics"))
        result = ask(self.store, self.settings, telegram_user_id=8, text="غبت عن الامتحان شو بعمل")
        self.assertEqual(result.outcome, "need_context")
        self.assertEqual(result.buttons[0].field, "academic_year")


class SyntheticBlockTest(StoreTestCase):
    def test_demo_rows_are_invisible_unless_explicitly_enabled(self) -> None:
        seed_demo(self.store)
        self.store.save_context(
            StudentContext(
                telegram_user_id=1,
                faculty_code="informatics",
                academic_year="2",
                study_system="regular",
                specialization_code="software",
            )
        )
        hidden = ask(
            self.store,
            make_settings(allow_synthetic=False),
            telegram_user_id=1,
            text="كيف أوقف تسجيلي",
        )
        self.assertEqual(hidden.outcome, "unmatched")
        self.assertFalse(hidden.authoritative)
        self.assertNotIn("مكتب التجربة", hidden.text)

        shown = ask(
            self.store,
            make_settings(allow_synthetic=True),
            telegram_user_id=1,
            text="كيف أوقف تسجيلي",
            today=date(2026, 1, 1),
        )
        self.assertEqual(shown.outcome, "answered")
        self.assertFalse(shown.authoritative)
        self.assertTrue(shown.synthetic)
        self.assertIn("مصطنعة", shown.text)
        self.assertIn("SYN-DEMO-01", shown.text)

    def test_seeded_retired_and_draft_demo_rows_are_not_served(self) -> None:
        seed_demo(self.store)
        settings = make_settings(allow_synthetic=True)
        retired = ask(self.store, settings, telegram_user_id=1, text="شو القاعدة التجريبية الملغاة")
        draft = ask(self.store, settings, telegram_user_id=1, text="شو المسودة التجريبية غير المعتمدة")
        self.assertEqual(retired.outcome, "no_verified_answer")
        self.assertNotIn("SYN-OLD", retired.text)
        self.assertEqual(draft.outcome, "no_verified_answer")
        self.assertNotIn("SYN-DRAFT", draft.text)

    def test_seeded_conflict_is_not_resolved_by_guessing(self) -> None:
        seed_demo(self.store)
        result = ask(
            self.store,
            make_settings(allow_synthetic=True),
            telegram_user_id=1,
            text="وريني التعارض التجريبي",
        )
        self.assertEqual(result.outcome, "conflict_review")
        self.assertNotIn("SYN-CONFLICT-A", result.text)
        self.assertNotIn("SYN-CONFLICT-B", result.text)
