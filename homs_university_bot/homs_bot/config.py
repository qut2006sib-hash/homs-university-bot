"""Environment settings. Secrets stay in the environment, never in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv_file(path: Path | None = None) -> None:
    """Load KEY=VALUE lines without overriding variables that already exist."""
    env_path = path or (PROJECT_ROOT / ".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _admin_ids(raw: str | None) -> frozenset[int]:
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        ids.add(int(part))
    return frozenset(ids)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: str
    allow_synthetic: bool
    admin_key: str
    admin_ids: frozenset[int]
    match_auto: float
    match_clarify: float
    match_margin: float
    rate_limit_count: int
    rate_limit_window_seconds: float
    log_level: str

    def is_telegram_admin(self, user_id: int | None) -> bool:
        return user_id is not None and user_id in self.admin_ids

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv_file()
        auto = _float("HU_MATCH_AUTO", 0.84)
        clarify = _float("HU_MATCH_CLARIFY", 0.62)
        margin = _float("HU_MATCH_MARGIN", 0.06)
        if not (0 <= clarify <= auto <= 1) or margin <= 0:
            raise SystemExit(
                "إعدادات المطابقة غير صالحة. يجب أن تكون 0 ≤ clarify ≤ auto ≤ 1 وهامشاً موجباً."
            )
        db_default = str(PROJECT_ROOT / "data" / "homs_bot.sqlite")
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            db_path=os.environ.get("HU_DB_PATH", db_default).strip() or db_default,
            allow_synthetic=_flag("HU_ALLOW_SYNTHETIC", False),
            admin_key=os.environ.get("HU_ADMIN_KEY", ""),
            admin_ids=_admin_ids(os.environ.get("HU_ADMIN_IDS")),
            match_auto=auto,
            match_clarify=clarify,
            match_margin=margin,
            rate_limit_count=_int("HU_RATE_LIMIT_COUNT", 8),
            rate_limit_window_seconds=float(_int("HU_RATE_LIMIT_WINDOW", 30)),
            log_level=os.environ.get("HU_LOG_LEVEL", "INFO").strip() or "INFO",
        )
