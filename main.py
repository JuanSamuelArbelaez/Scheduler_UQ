from __future__ import annotations

import os
import socket
import threading
import time
from typing import Any

from agents.confirmation import ConfirmationAgent
from agents.history import HistoryAgent
from agents.intent import IntentAgent
from agents.nlp import NLPAgent
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.priority import PriorityAgent
from agents.scheduling import SchedulingAgent
from config.settings import load_settings
from db.database import Database
from db.repositories import ChatRepository, EventRepository, HistoryRepository, OTPRepository, ReminderRepository, UserRepository
from services.calendar_sync_service import CalendarSyncService
from services.email_service import EmailService, EmailSettings
from services.google_calendar_oauth import GoogleCalendarOAuthManager
from services.local_llm import LocalOllamaClient
from services.providers.mcp_calendar_provider import HttpJsonRpcMCPTransport, MCPCalendarProvider
from services.speech_to_text_service import SpeechToTextService
from services.text_to_speech_service import TextToSpeechService
from services.telegram_service import TelegramService
from services.web_auth_service import WebAuthService
from web.app import WebDependencies, create_web_app


def build_application() -> dict[str, object]:
	settings = load_settings()
	if settings.app_encryption_key:
		os.environ["APP_ENCRYPTION_KEY"] = settings.app_encryption_key
	database = Database(settings.sqlite_path)
	database.initialize()
	connection = database.connect()

	user_repository = UserRepository(connection)
	event_repository = EventRepository(connection)
	reminder_repository = ReminderRepository(connection)
	history_repository = HistoryRepository(connection)
	otp_repository = OTPRepository(connection)
	chat_repository = ChatRepository(connection)

	nlp_agent = NLPAgent()
	llm_client = None
	if settings.llm_provider == "ollama":
		llm_client = LocalOllamaClient(settings.ollama_base_url, settings.ollama_model)
	intent_agent = IntentAgent(llm_client=llm_client)
	priority_agent = PriorityAgent()
	confirmation_agent = ConfirmationAgent()
	notification_agent = NotificationAgent()
	calendar_provider = None
	calendar_sync_service = None
	if settings.mcp_enabled and settings.mcp_http_endpoint:
		transport = HttpJsonRpcMCPTransport(settings.mcp_http_endpoint, timeout_seconds=settings.mcp_timeout_seconds)
		calendar_provider = MCPCalendarProvider(
			transport,
			create_tool=settings.mcp_google_calendar_create_tool,
			update_tool=settings.mcp_google_calendar_update_tool,
			delete_tool=settings.mcp_google_calendar_delete_tool,
			list_tools_method=settings.mcp_list_tools_method,
			list_templates_method=settings.mcp_list_templates_method,
			list_resources_method=settings.mcp_list_resources_method,
			default_calendar_id=settings.google_calendar_calendar_id,
		)
		calendar_sync_service = CalendarSyncService(calendar_provider, history=None, retry_count=settings.mcp_retry_count)
	orchestrator_agent = OrchestratorAgent(nlp_agent, intent_agent, priority_agent, confirmation_agent, calendar_provider=calendar_provider)
	email_service = EmailService(
		EmailSettings(
			host=settings.smtp_host,
			port=settings.smtp_port,
			username=settings.smtp_username,
			password=settings.smtp_password,
			from_email=settings.smtp_from_email,
			use_tls=settings.smtp_use_tls,
		)
	)
	telegram_service = None
	if settings.telegram_bot_token:
		telegram_service = TelegramService(settings.telegram_bot_token)
	history_agent = HistoryAgent(history_repository)
	if calendar_sync_service is not None:
		calendar_sync_service.history = history_agent

	scheduling_agent = SchedulingAgent(
		event_repository,
		reminder_repository,
		user_repository,
		email_service,
		telegram_service,
		history=history_agent,
		calendar_sync=calendar_sync_service,
		default_timezone=settings.default_timezone,
		default_reminder_minutes=settings.default_reminder_minutes,
	)
	preferences_agent = UserPreferencesAgent(user_repository, default_timezone=settings.default_timezone)
	web_auth_service = WebAuthService(
		users=user_repository,
		otp_repository=otp_repository,
		email_service=email_service,
		default_timezone=settings.default_timezone,
		otp_expiration_minutes=settings.otp_expiration_minutes,
	)
	stt_service = SpeechToTextService(model_name=settings.whisper_model)
	tts_service = TextToSpeechService(provider=settings.tts_provider, model_name=settings.tts_model_name)
	oauth_manager = GoogleCalendarOAuthManager(
		preferences_agent,
		client_secrets_file=settings.google_oauth_client_secrets_file,
		redirect_host=settings.google_oauth_redirect_host,
		redirect_port=settings.web_port if settings.run_web_app else settings.google_oauth_redirect_port,
		scopes=settings.google_oauth_scopes,
		telegram_bot_token=settings.telegram_bot_token,
	)
	if not oauth_manager.is_configured():
		print("Google OAuth no está configurado: falta GOOGLE_OAUTH_CLIENT_SECRETS_FILE o el archivo no existe.")
	web_app = create_web_app(
		settings,
		WebDependencies(
			users=user_repository,
			preferences=preferences_agent,
			orchestrator=orchestrator_agent,
			scheduling=scheduling_agent,
			notification=notification_agent,
			oauth_manager=oauth_manager,
			auth_service=web_auth_service,
			chat_repository=chat_repository,
			stt_service=stt_service,
			tts_service=tts_service,
			default_timezone=settings.default_timezone,
		),
	)

	return {
		"settings": settings,
		"database": database,
		"connection": connection,
		"repositories": {
			"users": user_repository,
			"events": event_repository,
			"reminders": reminder_repository,
			"history": history_repository,
			"otp": otp_repository,
			"chat": chat_repository,
		},
		"agents": {
			"orchestrator": orchestrator_agent,
			"nlp": nlp_agent,
			"intent": intent_agent,
			"priority": priority_agent,
			"confirmation": confirmation_agent,
			"notification": notification_agent,
			"scheduling": scheduling_agent,
			"preferences": preferences_agent,
			"history": history_agent,
			"llm_client": llm_client,
			"email_service": email_service,
			"telegram_service": telegram_service,
			"oauth_manager": oauth_manager,
			"web_auth": web_auth_service,
			"stt": stt_service,
			"tts": tts_service,
		},
		"web_app": web_app,
	}


def run_internal_health_check(application: dict[str, Any]) -> tuple[bool, str]:
	try:
		connection = application["connection"]
		connection.execute("SELECT 1").fetchone()
	except Exception as error:
		return False, f"db error: {error}"

	return True, "db ok"


def _is_tcp_port_open(host: str, port: int) -> bool:
	try:
		with socket.create_connection((host, port), timeout=1):
			return True
	except OSError:
		return False


def _start_mcp_server_thread(settings: Any) -> None:
	"""Start the MCP calendar server in a background daemon thread."""
	import urllib.parse as _urlparse
	parsed = _urlparse.urlparse(settings.mcp_http_endpoint)
	host = parsed.hostname or "localhost"
	port = parsed.port or 8088
	service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip() or None
	local_hosts = {"localhost", "127.0.0.1", "::1"}
	if host not in local_hosts:
		print(f"MCP externo configurado en {settings.mcp_http_endpoint}; no inicio MCP embebido.")
		return

	if _is_tcp_port_open(host, port):
		print(f"MCP server ya disponible en http://{host}:{port}/mcp")
		return

	def _run() -> None:
		try:
			from mcp_server.server import run_server
			run_server(host=host, port=port, service_account_file=service_account_file)
		except Exception as exc:
			print(f"MCP server error: {exc}")

	thread = threading.Thread(target=_run, name="mcp-server", daemon=True)
	thread.start()
	# Give the server a moment to bind before Flask starts accepting requests
	time.sleep(1.5)
	print(f"MCP server iniciado en http://{host}:{port}/mcp")


def main() -> None:
	application = build_application()
	settings = application["settings"]
	health_ok, health_message = run_internal_health_check(application)
	print(f"Health check interno: {health_message}")
	if not health_ok:
		print("Deteniendo inicio por fallo en health check interno.")
		return

	if settings.llm_provider == "ollama":
		llm_client = application["agents"]["llm_client"]
		if llm_client is None:
			print("LLM_PROVIDER=ollama, pero no se pudo construir el cliente local.")
			print("Deteniendo inicio para evitar comportamiento inconsistente del Intent Agent.")
			return

		ready, message = llm_client.ensure_ready()
		print(f"Verificación Ollama: {message}")
		if not ready:
			print("Deteniendo inicio hasta que Ollama esté operativo y con el modelo configurado.")
			return

	if settings.run_web_app:
		web_app = application["web_app"]
		if settings.mcp_enabled and settings.mcp_http_endpoint:
			_start_mcp_server_thread(settings)
		print(f"Iniciando Flask app en http://{settings.web_host}:{settings.web_port}")
		web_app.run(host=settings.web_host, port=settings.web_port, debug=False)
		return

	print("RUN_WEB_APP está desactivado. No se inició interfaz local.")


if __name__ == "__main__":
	main()
