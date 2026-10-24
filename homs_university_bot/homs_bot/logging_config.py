"""Logs that must not keep tokens or the admin key."""

from __future__ import annotations

import logging
import os

from homs_bot.config import Settings


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        secrets = [
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("HU_ADMIN_KEY", ""),
        ]
        message = record.getMessage()
        redacted = message
        for secret in secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, "[REDACTED]")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger().addFilter(SecretFilter())
