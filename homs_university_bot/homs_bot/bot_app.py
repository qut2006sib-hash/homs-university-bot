"""Telegram process. Exits with a clear message when the token is absent."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import TelegramObject
from aiogram import BaseMiddleware

from homs_bot.config import Settings
from homs_bot.db import Store, open_store
from homs_bot.handlers import router
from homs_bot.logging_config import setup_logging
from homs_bot.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, limiter: RateLimiter):
        self.limiter = limiter

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if user is not None and not self.limiter.allow(str(user.id)):
            from aiogram.types import CallbackQuery, Message

            if isinstance(event, Message):
                await event.answer("وصلت لحد الرسائل المؤقت. انتظر قليلاً ثم أعد الإرسال.")
            elif isinstance(event, CallbackQuery):
                await event.answer("وصلت لحد الرسائل المؤقت.")
            return None
        return await handler(event, data)


async def run_bot(settings: Settings, store: Store | None = None) -> None:
    if not settings.bot_token:
        raise SystemExit(1)
    store = store or open_store(settings.db_path)
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher["store"] = store
    dispatcher["settings"] = settings
    limiter = RateLimiter(settings.rate_limit_count, settings.rate_limit_window_seconds)
    middleware = RateLimitMiddleware(limiter)
    dispatcher.message.middleware(middleware)
    dispatcher.callback_query.middleware(middleware)
    dispatcher.include_router(router)
    logger.info("telegram polling started")
    await dispatcher.start_polling(bot)


def main() -> None:
    settings = Settings.from_env()
    setup_logging(settings)
    if not settings.bot_token:
        print(
            "ما في TELEGRAM_BOT_TOKEN. "
            "المحرك وأوامر الإدارة يشتغلان من دونه. "
            "أضف الرمز إلى ملف .env ثم أعد تشغيل البوت حتى يتصل بتيليغرام.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    asyncio.run(run_bot(settings))
