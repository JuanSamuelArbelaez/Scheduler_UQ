from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppSettings:
    sqlite_path: Path
    default_reminder_minutes: int = 15
    default_timezone: str = "America/Bogota"
    llm_provider: str = "none"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True
    mcp_enabled: bool = False
    mcp_http_endpoint: str = ""
    mcp_timeout_seconds: int = 15
    mcp_retry_count: int = 2
    mcp_google_calendar_create_tool: str = "google_calendar.create_event"
    mcp_google_calendar_update_tool: str = "google_calendar.update_event"
    mcp_google_calendar_delete_tool: str = "google_calendar.delete_event"
    mcp_list_tools_method: str = "tools/list"
    mcp_list_templates_method: str = "prompts/list"
    mcp_list_resources_method: str = "resources/list"
    google_calendar_calendar_id: str = ""
    google_oauth_client_secrets_file: str = ""
    google_oauth_redirect_host: str = "127.0.0.1"
    google_oauth_redirect_port: int = 5000
    google_oauth_scopes: str = "https://www.googleapis.com/auth/calendar"
    run_web_app: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 5000
    flask_secret_key: str = ""
    app_encryption_key: str = ""
    otp_expiration_minutes: int = 10
    whisper_model: str = "base"
    tts_provider: str = "coqui"
    tts_model_name: str = "tts_models/es/css10/vits"


def load_settings() -> AppSettings:
    _load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    sqlite_path = Path(os.getenv("SQLITE_PATH", "scheduler.db"))
    default_reminder_minutes = int(os.getenv("DEFAULT_REMINDER_MINUTES", "15"))
    default_timezone = os.getenv("DEFAULT_TIMEZONE", "America/Bogota").strip() or "America/Bogota"
    llm_provider = os.getenv("LLM_PROVIDER", "none").strip().lower()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls = _parse_bool(os.getenv("SMTP_USE_TLS", "true"))
    mcp_enabled = _parse_bool(os.getenv("MCP_ENABLED", "false"))
    mcp_http_endpoint = os.getenv("MCP_HTTP_ENDPOINT", "").strip()
    mcp_timeout_seconds = int(os.getenv("MCP_TIMEOUT_SECONDS", "15"))
    mcp_retry_count = int(os.getenv("MCP_RETRY_COUNT", "2"))
    mcp_google_calendar_create_tool = os.getenv("MCP_GOOGLE_CALENDAR_CREATE_TOOL", "google_calendar.create_event").strip()
    mcp_google_calendar_update_tool = os.getenv("MCP_GOOGLE_CALENDAR_UPDATE_TOOL", "google_calendar.update_event").strip()
    mcp_google_calendar_delete_tool = os.getenv("MCP_GOOGLE_CALENDAR_DELETE_TOOL", "google_calendar.delete_event").strip()
    mcp_list_tools_method = os.getenv("MCP_LIST_TOOLS_METHOD", "tools/list").strip()
    mcp_list_templates_method = os.getenv("MCP_LIST_TEMPLATES_METHOD", "prompts/list").strip()
    mcp_list_resources_method = os.getenv("MCP_LIST_RESOURCES_METHOD", "resources/list").strip()
    google_calendar_calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "").strip()
    google_oauth_client_secrets_file = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", "").strip()
    google_oauth_redirect_host = os.getenv("GOOGLE_OAUTH_REDIRECT_HOST", "127.0.0.1").strip() or "127.0.0.1"
    google_oauth_redirect_port = int(os.getenv("GOOGLE_OAUTH_REDIRECT_PORT", "5000"))
    google_oauth_scopes = os.getenv(
        "GOOGLE_OAUTH_SCOPES",
        "https://www.googleapis.com/auth/calendar",
    ).strip() or "https://www.googleapis.com/auth/calendar"
    run_web_app = _parse_bool(os.getenv("RUN_WEB_APP", "true"))
    web_host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    web_port = int(os.getenv("WEB_PORT", "5000"))
    flask_secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
    app_encryption_key = os.getenv("APP_ENCRYPTION_KEY", "").strip()
    otp_expiration_minutes = int(os.getenv("OTP_EXPIRATION_MINUTES", "10"))
    whisper_model = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    tts_provider = os.getenv("TTS_PROVIDER", "coqui").strip().lower() or "coqui"
    tts_model_name = os.getenv("TTS_MODEL_NAME", "tts_models/es/css10/vits").strip() or "tts_models/es/css10/vits"

    return AppSettings(
        sqlite_path=sqlite_path,
        default_reminder_minutes=default_reminder_minutes,
        default_timezone=default_timezone,
        llm_provider=llm_provider,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_from_email=smtp_from_email,
        smtp_use_tls=smtp_use_tls,
        mcp_enabled=mcp_enabled,
        mcp_http_endpoint=mcp_http_endpoint,
        mcp_timeout_seconds=mcp_timeout_seconds,
        mcp_retry_count=mcp_retry_count,
        mcp_google_calendar_create_tool=mcp_google_calendar_create_tool,
        mcp_google_calendar_update_tool=mcp_google_calendar_update_tool,
        mcp_google_calendar_delete_tool=mcp_google_calendar_delete_tool,
        mcp_list_tools_method=mcp_list_tools_method,
        mcp_list_templates_method=mcp_list_templates_method,
        mcp_list_resources_method=mcp_list_resources_method,
        google_calendar_calendar_id=google_calendar_calendar_id,
        google_oauth_client_secrets_file=google_oauth_client_secrets_file,
        google_oauth_redirect_host=google_oauth_redirect_host,
        google_oauth_redirect_port=google_oauth_redirect_port,
        google_oauth_scopes=google_oauth_scopes,
        run_web_app=run_web_app,
        web_host=web_host,
        web_port=web_port,
        flask_secret_key=flask_secret_key,
        app_encryption_key=app_encryption_key,
        otp_expiration_minutes=otp_expiration_minutes,
        whisper_model=whisper_model,
        tts_provider=tts_provider,
        tts_model_name=tts_model_name,
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