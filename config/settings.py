from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppSettings:
    telegram_bot_token: str | None
    telegram_bot_url: str | None
    sqlite_path: Path
    default_reminder_minutes: int = 15
    run_telegram_bot: bool = False


def load_settings() -> AppSettings:
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    sqlite_path = Path(os.getenv("SQLITE_PATH", "scheduler.db"))
    default_reminder_minutes = int(os.getenv("DEFAULT_REMINDER_MINUTES", "15"))
    run_telegram_bot = _parse_bool(os.getenv("RUN_TELEGRAM_BOT", "false"))

    return AppSettings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_bot_url=os.getenv("TELEGRAM_BOT_URL"),
        sqlite_path=sqlite_path,
        default_reminder_minutes=default_reminder_minutes,
        run_telegram_bot=run_telegram_bot,
    )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue

        key, value = stripped_line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}