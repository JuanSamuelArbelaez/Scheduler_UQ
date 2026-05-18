from __future__ import annotations

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
from bot.telegram_app import TelegramDependencies, build_application as build_telegram_application
from config.settings import load_settings
from db.database import Database
from db.repositories import EventRepository, HistoryRepository, ReminderRepository, UserRepository
from services.calendar_sync_service import CalendarSyncService
from services.email_service import EmailService, EmailSettings
from services.local_llm import LocalOllamaClient
from services.providers.mcp_calendar_provider import HttpJsonRpcMCPTransport, MCPCalendarProvider
from services.telegram_service import TelegramService


def build_application() -> dict[str, object]:
	settings = load_settings()
	database = Database(settings.sqlite_path)
	database.initialize()
	connection = database.connect()

	user_repository = UserRepository(connection)
	event_repository = EventRepository(connection)
	reminder_repository = ReminderRepository(connection)
	history_repository = HistoryRepository(connection)

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

	return {
		"settings": settings,
		"database": database,
		"connection": connection,
		"repositories": {
			"users": user_repository,
			"events": event_repository,
			"reminders": reminder_repository,
			"history": history_repository,
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
		},
	}


def run_internal_health_check(application: dict[str, Any]) -> tuple[bool, str]:
	try:
		connection = application["connection"]
		connection.execute("SELECT 1").fetchone()
	except Exception as error:
		return False, f"db error: {error}"

	return True, "db ok"


def main() -> None:
	application = build_application()
	settings = application["settings"]
	health_ok, health_message = run_internal_health_check(application)
	print(f"Health check interno: {health_message}")
	if not health_ok:
		print("Deteniendo inicio por fallo en health check interno.")
		return

	if settings.telegram_bot_token is None:
		print("TELEGRAM_BOT_TOKEN no esta configurado. Solo se inicializo la base local.")
		print("El sistema ya esta preparado para devolver mensajes naturales tras agendar, modificar o cancelar citas.")
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

	if settings.run_telegram_bot or settings.telegram_bot_token is not None:
		if not settings.run_telegram_bot:
			print("RUN_TELEGRAM_BOT no estaba activo, pero se iniciara el bot porque existe token configurado.")
		dependencies = TelegramDependencies(
			orchestrator=application["agents"]["orchestrator"],
			scheduling=application["agents"]["scheduling"],
			preferences=application["agents"]["preferences"],
			notification=application["agents"]["notification"],
			history=application["agents"]["history"],
			llm_client=application["agents"]["llm_client"],
			default_timezone=settings.default_timezone,
		)
		telegram_application = build_telegram_application(settings.telegram_bot_token, dependencies)
		print("Iniciando bot de Telegram con mensajes naturales y handlers de agenda.")
		telegram_application.run_polling()
		return

	print("Configuracion cargada correctamente. El siguiente paso es conectar el bot de Telegram.")
	print("El sistema ya esta preparado para devolver mensajes naturales tras agendar, modificar o cancelar citas.")


if __name__ == "__main__":
	main()
