from __future__ import annotations

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
	intent_agent = IntentAgent()
	priority_agent = PriorityAgent()
	confirmation_agent = ConfirmationAgent()
	notification_agent = NotificationAgent()
	orchestrator_agent = OrchestratorAgent(nlp_agent, intent_agent, priority_agent, confirmation_agent)
	scheduling_agent = SchedulingAgent(
		event_repository,
		reminder_repository,
		default_reminder_minutes=settings.default_reminder_minutes,
	)
	preferences_agent = UserPreferencesAgent(user_repository)
	history_agent = HistoryAgent(history_repository)

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
		},
	}


def main() -> None:
	application = build_application()
	settings = application["settings"]
	if settings.telegram_bot_token is None:
		print("TELEGRAM_BOT_TOKEN no esta configurado. Solo se inicializo la base local.")
		print("El sistema ya esta preparado para devolver mensajes naturales tras agendar, modificar o cancelar citas.")
		return

	if settings.run_telegram_bot:
		dependencies = TelegramDependencies(
			orchestrator=application["agents"]["orchestrator"],
			scheduling=application["agents"]["scheduling"],
			preferences=application["agents"]["preferences"],
			notification=application["agents"]["notification"],
			history=application["agents"]["history"],
		)
		telegram_application = build_telegram_application(settings.telegram_bot_token, dependencies)
		print("Iniciando bot de Telegram con mensajes naturales y handlers de agenda.")
		telegram_application.run_polling()
		return

	print("Configuracion cargada correctamente. El siguiente paso es conectar el bot de Telegram.")
	print("El sistema ya esta preparado para devolver mensajes naturales tras agendar, modificar o cancelar citas.")


if __name__ == "__main__":
	main()
