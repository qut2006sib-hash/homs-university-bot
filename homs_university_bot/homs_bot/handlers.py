"""Telegram conversation: context buttons, answers, clarification, and feedback."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, ErrorEvent, Message

from homs_bot.catalog import load_catalog
from homs_bot.config import Settings
from homs_bot.context_flow import (
    apply_context_field,
    context_summary,
    load_context,
    next_onboarding_field,
)
from homs_bot.db import Store
from homs_bot.keyboards import (
    delete_confirm_keyboard,
    edit_menu_keyboard,
    faculty_keyboard,
    result_keyboard,
    specialization_keyboard,
    system_keyboard,
    year_keyboard,
)
from homs_bot.models import StudentContext
from homs_bot.pipeline import ask, record_feedback, reject_clarification

logger = logging.getLogger(__name__)
router = Router()

WELCOME = (
    "أهلاً بك في بوت جامعة حمص.\n"
    "بجاوب فقط من إجابات راجعها مختص واعتمدها. "
    "ما بخترع نظاماً أو موعداً أو رقم مادة.\n\n"
    "اختر كليتك. فيك تغيّر البيانات لاحقاً بالأمر /context، "
    "وتحذفها بالأمر /delete_my_data. ما بنخزّن اسمك."
)

FIELD_PROMPTS = {
    "faculty_code": "اختر الكلية.",
    "academic_year": "اختر السنة الدراسية.",
    "study_system": "اختر نظام الدراسة.",
    "specialization_code": "اختر الاختصاص. إذا ما انطبق، اختر «لم أحدد».",
}


def _welcome(settings: Settings) -> str:
    if not settings.allow_synthetic:
        return WELCOME
    return (
        WELCOME
        + "\n\nوضع التجربة شغال: إذا ظهر جواب مصطنع فرح يكون مكتوب عليه أنه ليس نظام الجامعة."
    )


async def _show(callback: CallbackQuery, text: str, markup=None) -> None:
    message = callback.message
    if message is not None:
        try:
            await message.edit_text(text, reply_markup=markup)
            return
        except Exception:
            logger.debug("edit failed; sending a new message")
    if message is not None:
        await message.answer(text, reply_markup=markup)


def _prompt_for(field: str, ctx: StudentContext, prefix: str):
    if field == "faculty_code":
        return FIELD_PROMPTS[field], faculty_keyboard(prefix, 0)
    if field == "academic_year":
        return FIELD_PROMPTS[field], year_keyboard(prefix)
    if field == "study_system":
        return FIELD_PROMPTS[field], system_keyboard(prefix)
    markup = specialization_keyboard(prefix, ctx.faculty_code or "")
    if markup is None:
        return "ما في اختصاصات محفوظة لهالكلية ضمن النموذج الحالي.", edit_menu_keyboard()
    return FIELD_PROMPTS[field], markup


def _ready_text(ctx: StudentContext) -> str:
    catalog = load_catalog()
    return "تمام، سجّلت السياق. اكتب سؤالك بصياغتك.\n\n" + context_summary(catalog, ctx)


@router.message(CommandStart())
async def start(message: Message, store: Store, settings: Settings) -> None:
    if message.from_user is None:
        return
    ctx = load_context(store, message.from_user.id)
    field = next_onboarding_field(load_catalog(), ctx)
    if field is None and store.get_context(message.from_user.id) is not None:
        await message.answer(_ready_text(ctx), reply_markup=edit_menu_keyboard())
        return
    await message.answer(_welcome(settings), reply_markup=faculty_keyboard("onb", 0))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "اكتب سؤالك كما تقوله لزميل.\n"
        "/context يعرض بياناتك الدراسية ويتيح تعديلها.\n"
        "/delete_my_data يحذف السياق وسجل أسئلتك على هذا البوت.\n"
        "إذا ما في جواب معتمد، البوت بيقول ذلك وما بيؤلّف قاعدة."
    )


@router.message(Command("context"))
async def show_context(message: Message, store: Store) -> None:
    if message.from_user is None:
        return
    ctx = load_context(store, message.from_user.id)
    catalog = load_catalog()
    await message.answer(context_summary(catalog, ctx), reply_markup=edit_menu_keyboard())


@router.message(Command("delete_my_data"))
async def delete_request(message: Message) -> None:
    await message.answer(
        "رح ينحذف سياق الدراسة وسجل الأسئلة المرتبط بحساب تيليغرام هذا على البوت. المتابعة؟",
        reply_markup=delete_confirm_keyboard(),
    )


@router.message(Command("admin"))
async def admin_hint(message: Message, settings: Settings) -> None:
    user = message.from_user
    if user is None or not settings.is_telegram_admin(user.id):
        await message.answer("هذا الأمر مخصص للإدارة، وحسابك غير مخوّل.")
        return
    await message.answer(
        "إدارة المحتوى تتم من واجهة الأوامر على الجهاز الذي يشغّل البوت، وليس من المحادثة. "
        "ملاحظة الطالب ما بتنشر جواباً جديداً لحاله."
    )


@router.message(F.text)
async def on_text(message: Message, store: Store, settings: Settings) -> None:
    if message.from_user is None or not message.text or message.text.startswith("/"):
        return
    result = ask(
        store,
        settings,
        telegram_user_id=message.from_user.id,
        text=message.text,
    )
    await message.answer(result.text, reply_markup=result_keyboard(result))


@router.callback_query(F.data.startswith("onb:"))
async def onboarding(callback: CallbackQuery, store: Store) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "facpage":
        page = int(parts[2])
        await _show(callback, "اختر الكلية.", faculty_keyboard("onb", page))
        return
    field, value = _onboarding_value(parts)
    if field is None or value is None:
        return
    ctx = apply_context_field(store, load_catalog(), callback.from_user.id, field, value)
    nxt = next_onboarding_field(load_catalog(), ctx)
    if nxt is None:
        await _show(callback, _ready_text(ctx), edit_menu_keyboard())
        return
    text, markup = _prompt_for(nxt, ctx, "onb")
    await _show(callback, text, markup)


def _onboarding_value(parts: list[str]) -> tuple[str | None, str | None]:
    if len(parts) < 3:
        return None, None
    kind, value = parts[1], parts[2]
    mapping = {
        "fac": "faculty_code",
        "year": "academic_year",
        "sys": "study_system",
        "spec": "specialization_code",
    }
    return mapping.get(kind), value


@router.callback_query(F.data.startswith("edit:"))
async def edit_context(callback: CallbackQuery, store: Store) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    ctx = load_context(store, callback.from_user.id)
    if action == "facpage":
        page = int(parts[2])
        await _show(callback, "اختر الكلية الجديدة.", faculty_keyboard("edit", page))
        return
    if action == "yearpage":
        await _show(callback, "اختر السنة الدراسية.", year_keyboard("edit"))
        return
    if action == "syspage":
        await _show(callback, "اختر نظام الدراسة.", system_keyboard("edit"))
        return
    if action == "specpage":
        text, markup = _prompt_for("specialization_code", ctx, "edit")
        await _show(callback, text, markup)
        return
    field, value = _onboarding_value(parts)
    if field is None or value is None:
        return
    updated = apply_context_field(store, load_catalog(), callback.from_user.id, field, value)
    catalog = load_catalog()
    await _show(
        callback,
        "تحدّث السياق.\n\n" + context_summary(catalog, updated),
        edit_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("del:"))
async def delete_context(callback: CallbackQuery, store: Store) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    if callback.data == "del:ask":
        await _show(
            callback,
            "رح ينحذف سياق الدراسة وسجل الأسئلة المرتبط بهذا الحساب. المتابعة؟",
            delete_confirm_keyboard(),
        )
        return
    if callback.data == "del:no":
        ctx = load_context(store, callback.from_user.id)
        await _show(callback, context_summary(load_catalog(), ctx), edit_menu_keyboard())
        return
    if callback.data == "del:yes":
        store.delete_student(callback.from_user.id)
        await _show(
            callback,
            "انحذفت بيانات السياق وسجل الأسئلة. اختر كليتك من جديد إذا بدك تكمل.",
            faculty_keyboard("onb", 0),
        )


@router.callback_query(F.data.startswith("need:"))
async def fill_needed_context(callback: CallbackQuery, store: Store, settings: Settings) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    _tag, raw_id, field, value = callback.data.split(":", 3)
    interaction = store.get_interaction(int(raw_id))
    if interaction is None or interaction.telegram_user_id != callback.from_user.id:
        await _show(callback, "ما لقيت السؤال المطلوب.")
        return
    apply_context_field(store, load_catalog(), callback.from_user.id, field, value)
    result = ask(
        store,
        settings,
        telegram_user_id=callback.from_user.id,
        text=interaction.original_text,
        chosen_intent_id=interaction.intent_id,
        parent_interaction_id=interaction.id,
    )
    await _show(callback, result.text, result_keyboard(result))


@router.callback_query(F.data.startswith("pick:") | F.data.startswith("ok:"))
async def choose_intent(callback: CallbackQuery, store: Store, settings: Settings) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    _action, raw_id, code = callback.data.split(":", 2)
    interaction = store.get_interaction(int(raw_id))
    if interaction is None or interaction.telegram_user_id != callback.from_user.id:
        await _show(callback, "ما لقيت السؤال المطلوب.")
        return
    result = ask(
        store,
        settings,
        telegram_user_id=callback.from_user.id,
        text=interaction.original_text,
        chosen_intent_id=code,
        parent_interaction_id=interaction.id,
        link_clarification=True,
    )
    await _show(callback, result.text, result_keyboard(result))


@router.callback_query(F.data.startswith("no:"))
async def reject_intent(callback: CallbackQuery, store: Store) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    interaction_id = int(callback.data.split(":", 1)[1])
    result = reject_clarification(
        store,
        telegram_user_id=callback.from_user.id,
        interaction_id=interaction_id,
    )
    await _show(callback, result.text)


@router.callback_query(F.data.startswith("fb:"))
async def feedback(callback: CallbackQuery, store: Store) -> None:
    await callback.answer()
    if callback.from_user is None or callback.data is None:
        return
    _tag, raw_id, verdict = callback.data.split(":", 2)
    note = record_feedback(
        store,
        telegram_user_id=callback.from_user.id,
        interaction_id=int(raw_id),
        verdict=verdict,
    )
    await _show(callback, note)


@router.error()
async def on_error(event: ErrorEvent) -> None:
    logger.exception("handler failed")
    message = None
    if event.update.message is not None:
        message = event.update.message
    elif event.update.callback_query is not None:
        message = event.update.callback_query.message
    if message is not None:
        try:
            await message.answer("صار خلل مؤقت وما قدرت أكمّل الطلب. جرّب مرة ثانية.")
        except Exception:
            logger.exception("failed to notify the student")
