"""Inline buttons. Callback data stays short ASCII; Arabic is only the label."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from homs_bot.catalog import load_catalog
from homs_bot.models import AskResult

PAGE_SIZE = 5


def _markup(pairs: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, data in pairs:
        builder.button(text=label, callback_data=data)
    builder.adjust(1)
    return builder.as_markup()


def faculty_keyboard(prefix: str, page: int) -> InlineKeyboardMarkup:
    catalog = load_catalog()
    start = page * PAGE_SIZE
    chunk = catalog.faculties[start : start + PAGE_SIZE]
    pairs = [(item.label, f"{prefix}:fac:{item.code}") for item in chunk]
    if page > 0:
        pairs.append(("السابق", f"{prefix}:facpage:{page - 1}"))
    if start + PAGE_SIZE < len(catalog.faculties):
        pairs.append(("التالي", f"{prefix}:facpage:{page + 1}"))
    return _markup(pairs)


def year_keyboard(prefix: str) -> InlineKeyboardMarkup:
    catalog = load_catalog()
    return _markup([(item.label, f"{prefix}:year:{item.code}") for item in catalog.years])


def system_keyboard(prefix: str) -> InlineKeyboardMarkup:
    catalog = load_catalog()
    return _markup([(item.label, f"{prefix}:sys:{item.code}") for item in catalog.study_systems])


def specialization_keyboard(prefix: str, faculty_code: str) -> InlineKeyboardMarkup | None:
    catalog = load_catalog()
    specs = catalog.specializations.get(faculty_code, ())
    if not specs:
        return None
    return _markup([(item.label, f"{prefix}:spec:{item.code}") for item in specs])


def edit_menu_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            ("تغيير الكلية", "edit:facpage:0"),
            ("تغيير السنة", "edit:yearpage"),
            ("تغيير نظام الدراسة", "edit:syspage"),
            ("تغيير الاختصاص", "edit:specpage"),
            ("حذف بياناتي المحفوظة", "del:ask"),
        ]
    )


def delete_confirm_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            ("نعم، احذف السياق وسجل أسئلتي", "del:yes"),
            ("لا، أبقِ البيانات", "del:no"),
        ]
    )


def result_keyboard(result: AskResult) -> InlineKeyboardMarkup | None:
    interaction_id = result.interaction_id
    pairs: list[tuple[str, str]] = []
    for button in result.buttons:
        if interaction_id is None:
            break
        if button.kind in {"clarify", "confirm"} and button.intent_id:
            action = "pick" if button.kind == "clarify" else "ok"
            pairs.append((button.label, f"{action}:{interaction_id}:{button.intent_id}"))
        elif button.kind == "reject":
            pairs.append((button.label, f"no:{interaction_id}"))
        elif button.kind == "context" and button.field and button.value:
            pairs.append((button.label, f"need:{interaction_id}:{button.field}:{button.value}"))
    if result.outcome == "answered" and interaction_id is not None:
        pairs.append(("مفيد", f"fb:{interaction_id}:helpful"))
        pairs.append(("غير صحيح أو لا علاقة له", f"fb:{interaction_id}:incorrect"))
    if not pairs:
        return None
    return _markup(pairs)
