"""Shared fixtures. Rows created here are test data, not university regulations."""

from __future__ import annotations

import unittest

from homs_bot.config import Settings
from homs_bot.db import Store, connect, init_db


def make_settings(**overrides) -> Settings:
    values = dict(
        bot_token="",
        db_path=":memory:",
        allow_synthetic=False,
        admin_key="test-admin-key",
        admin_ids=frozenset(),
        match_auto=0.84,
        match_clarify=0.62,
        match_margin=0.06,
        rate_limit_count=3,
        rate_limit_window_seconds=30,
        log_level="INFO",
    )
    values.update(overrides)
    return Settings(**values)


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = connect(":memory:")
        init_db(self.conn)
        self.store = Store(self.conn)
        self.settings = make_settings()

    def tearDown(self) -> None:
        self.conn.close()


def add_real(
    store: Store,
    *,
    code: str = "rule",
    wording: str = "كيف أقدم الطلب الرسمي",
    body: str = "نص معتمد داخل الاختبار فقط.",
    title: str | None = None,
    source_status: str = "approved",
    answer_status: str = "approved",
    question_status: str = "approved",
    intent_status: str = "approved",
    effective_from: str | None = "2020-01-01",
    effective_to: str | None = None,
    **answer_fields,
) -> None:
    store.add_source(
        id=f"src_{code}",
        title=title or f"مصدر اختبار {code}",
        issuer="جهة اختبار",
        reference=f"file://tests/{code}",
        article_or_page=f"بند اختبار {code}",
        effective_from=effective_from,
        effective_to=effective_to,
        review_status=source_status,
        is_synthetic=False,
    )
    store.add_intent(
        id=f"intent_{code}",
        code=code,
        title_ar=f"عنوان {code}",
        status=intent_status,
        is_synthetic=False,
    )
    store.add_question(
        id=f"q_{code}",
        intent_id=f"intent_{code}",
        wording=wording,
        status=question_status,
        is_synthetic=False,
    )
    store.add_answer(
        id=f"ans_{code}",
        intent_id=f"intent_{code}",
        source_id=f"src_{code}",
        body_ar=body,
        status=answer_status,
        effective_from=effective_from,
        effective_to=effective_to,
        is_synthetic=False,
        **answer_fields,
    )
