"""Save the few study fields the matcher may need, and delete them on request."""

from __future__ import annotations

from homs_bot.catalog import CONSTRAINT_FIELDS, Catalog
from homs_bot.db import Store
from homs_bot.models import StudentContext


def load_context(store: Store, user_id: int) -> StudentContext:
    return store.get_context(user_id) or StudentContext(telegram_user_id=user_id)


def apply_context_field(
    store: Store,
    catalog: Catalog,
    user_id: int,
    field: str,
    value: str,
) -> StudentContext:
    if field not in CONSTRAINT_FIELDS:
        raise ValueError(f"Unknown context field: {field}")
    ctx = load_context(store, user_id)
    setattr(ctx, field, value)
    if field == "faculty_code":
        if not catalog.has_specializations(value):
            ctx.specialization_code = None
        elif ctx.specialization_code and not catalog.specialization(value, ctx.specialization_code):
            ctx.specialization_code = None
    store.save_context(ctx)
    return ctx


def next_onboarding_field(catalog: Catalog, ctx: StudentContext) -> str | None:
    if not ctx.faculty_code:
        return "faculty_code"
    if not ctx.academic_year:
        return "academic_year"
    if not ctx.study_system:
        return "study_system"
    if catalog.has_specializations(ctx.faculty_code) and not ctx.specialization_code:
        return "specialization_code"
    return None


def context_summary(catalog: Catalog, ctx: StudentContext) -> str:
    lines = [
        f"الكلية: {catalog.label_for('faculty_code', ctx.faculty_code)}",
        f"السنة: {catalog.label_for('academic_year', ctx.academic_year)}",
        f"نظام الدراسة: {catalog.label_for('study_system', ctx.study_system)}",
    ]
    if catalog.has_specializations(ctx.faculty_code) or ctx.specialization_code:
        lines.append(
            "الاختصاص: "
            + catalog.label_for(
                "specialization_code",
                ctx.specialization_code,
                ctx.faculty_code,
            )
        )
    return "\n".join(lines)
