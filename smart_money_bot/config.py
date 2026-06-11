from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bybit_api_key: str
    bybit_api_secret: str
    telegram_token: str
    telegram_chat_id: str
    scan_interval_seconds: int = 60
    signal_cooldown_minutes: int = 45
    watchlist_file: str = "smc_watchlist.json"


def load_settings() -> Settings:
    load_dotenv()

    settings = Settings(
        bybit_api_key=_required_env("BYBIT_API_KEY"),
        bybit_api_secret=_required_env("BYBIT_API_SECRET"),
        telegram_token=_required_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required_env("TELEGRAM_CHAT_ID"),
        scan_interval_seconds=_int_env("SCAN_INTERVAL_SECONDS", 60),
        signal_cooldown_minutes=_int_env("SIGNAL_COOLDOWN_MINUTES", 45),
        watchlist_file=os.getenv("WATCHLIST_FILE", "smc_watchlist.json"),
    )

    return settings


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} in .env")
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
