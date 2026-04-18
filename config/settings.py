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
    default_timezone: str = "America/Bogota"
    run_telegram_bot: bool = False
    llm_provider: str = "none"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True


def load_settings() -> AppSettings:
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    sqlite_path = Path(os.getenv("SQLITE_PATH", "scheduler.db"))
    default_reminder_minutes = int(os.getenv("DEFAULT_REMINDER_MINUTES", "15"))
    default_timezone = os.getenv("DEFAULT_TIMEZONE", "America/Bogota").strip() or "America/Bogota"
    run_telegram_bot = _parse_bool(os.getenv("RUN_TELEGRAM_BOT", "false"))
    llm_provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls = _parse_bool(os.getenv("SMTP_USE_TLS", "true"))

    return AppSettings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_bot_url=os.getenv("TELEGRAM_BOT_URL"),
        sqlite_path=sqlite_path,
        default_reminder_minutes=default_reminder_minutes,
        default_timezone=default_timezone,
        run_telegram_bot=run_telegram_bot,
        llm_provider=llm_provider,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_from_email=smtp_from_email,
        smtp_use_tls=smtp_use_tls,
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
        os.environ[key] = value


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}