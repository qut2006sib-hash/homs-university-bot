"""Context buttons: choose, change, and delete student fields."""

from homs_bot.catalog import load_catalog
from homs_bot.context_flow import apply_context_field, context_summary, next_onboarding_field
from homs_bot.models import StudentContext
from homs_bot.rate_limit import RateLimiter

from helpers import StoreTestCase


class ContextSelectionTest(StoreTestCase):
    def test_student_can_select_and_change_context(self) -> None:
        catalog = load_catalog()
        user_id = 42
        apply_context_field(self.store, catalog, user_id, "faculty_code", "informatics")
        self.assertEqual(next_onboarding_field(catalog, self.store.get_context(user_id)), "academic_year")
        apply_context_field(self.store, catalog, user_id, "academic_year", "2")
        apply_context_field(self.store, catalog, user_id, "study_system", "regular")
        apply_context_field(self.store, catalog, user_id, "specialization_code", "software")

        saved = self.store.get_context(user_id)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertEqual(saved.faculty_code, "informatics")
        self.assertEqual(saved.academic_year, "2")
        self.assertEqual(saved.study_system, "regular")
        self.assertEqual(saved.specialization_code, "software")
        self.assertIsNone(next_onboarding_field(catalog, saved))
        self.assertIn("هندسة البرمجيات", context_summary(catalog, saved))

        apply_context_field(self.store, catalog, user_id, "academic_year", "3")
        self.assertEqual(self.store.get_context(user_id).academic_year, "3")

    def test_changing_faculty_clears_unrelated_specialization(self) -> None:
        catalog = load_catalog()
        user_id = 7
        apply_context_field(self.store, catalog, user_id, "faculty_code", "informatics")
        apply_context_field(self.store, catalog, user_id, "academic_year", "2")
        apply_context_field(self.store, catalog, user_id, "study_system", "regular")
        apply_context_field(self.store, catalog, user_id, "specialization_code", "networks")
        apply_context_field(self.store, catalog, user_id, "faculty_code", "law")
        saved = self.store.get_context(user_id)
        assert saved is not None
        self.assertEqual(saved.faculty_code, "law")
        self.assertIsNone(saved.specialization_code)
        self.assertIsNone(next_onboarding_field(catalog, saved))

    def test_delete_removes_context_and_interactions(self) -> None:
        catalog = load_catalog()
        user_id = 9
        apply_context_field(self.store, catalog, user_id, "faculty_code", "science")
        self.store.add_interaction(
            telegram_user_id=user_id,
            original_text="سؤال شخصي",
            normalized_text="سؤال شخصي",
            outcome="unmatched",
        )
        self.store.add_feedback(interaction_id=1, user_id=user_id, verdict="incorrect")
        self.store.delete_student(user_id)
        self.assertIsNone(self.store.get_context(user_id))
        self.assertEqual(self.store.list_recent_interactions(user_id), [])
        self.assertEqual(self.store.list_recent_feedback(user_id), [])
        self.assertIsNone(self.store.get_interaction(1))

    def test_empty_context_object_is_not_stored_until_a_choice(self) -> None:
        self.assertIsNone(self.store.get_context(3))
        self.assertEqual(
            next_onboarding_field(load_catalog(), StudentContext(telegram_user_id=3)),
            "faculty_code",
        )


class RateLimitTest(StoreTestCase):
    def test_limit_blocks_the_fourth_event_in_the_window(self) -> None:
        limiter = RateLimiter(max_events=3, window_seconds=30)
        self.assertTrue(limiter.allow("student", now=10))
        self.assertTrue(limiter.allow("student", now=11))
        self.assertTrue(limiter.allow("student", now=12))
        self.assertFalse(limiter.allow("student", now=13))
        self.assertTrue(limiter.allow("student", now=50))
        self.assertTrue(limiter.allow("other", now=13))
