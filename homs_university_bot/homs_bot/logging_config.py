"""Logs that must not keep tokens or the admin key."""

from __future__ import annotations

import logging
import os

from homs_bot.config import Settings


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, "[REDACTED]")
    return text


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("HU_ADMIN_KEY", ""),
        ]
        message = record.getMessage()
        redacted = _redact(message, secrets)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        # Tracebacks are formatted after filters run, so format them here to redact them.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = _redact(record.exc_text, secrets)
        if record.stack_info:
            record.stack_info = _redact(record.stack_info, secrets)
        return True


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Logger filters skip records propagated from child loggers (homs_bot.*, aiogram.*).
    # Handler filters see every record that reaches the handler.
    secret_filter = SecretFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)
