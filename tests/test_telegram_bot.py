from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
import sqlite3
import unittest

from agents.confirmation import ConfirmationAgent
from agents.history import HistoryAgent
from agents.intent import IntentAgent
from agents.nlp import NLPAgent
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.priority import PriorityAgent
from agents.scheduling import SchedulingAgent
from bot.telegram_app import (
    ParsedCancelRequest,
    TelegramDependencies,
    _looks_like_confirmation,
    _normalize_text,
    _parse_natural_cancel_request,
    _parse_natural_create,
    _parse_natural_update,
    _resolve_event_selection,
    _split_payload,
    build_application,
    health_command,
    text_router,
)
from db.repositories import EventRepository, HistoryRepository, ReminderRepository, UserRepository
from models.entities import Event, User


class TelegramBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = _create_in_memory_connection()

        users = UserRepository(self.connection)
        events = EventRepository(self.connection)
        reminders = ReminderRepository(self.connection)
        history = HistoryRepository(self.connection)

        self.dependencies = TelegramDependencies(
            orchestrator=OrchestratorAgent(NLPAgent(), IntentAgent(), PriorityAgent(), ConfirmationAgent()),
            scheduling=SchedulingAgent(events, reminders, default_reminder_minutes=15),
            preferences=UserPreferencesAgent(users),
            notification=NotificationAgent(),
            history=HistoryAgent(history),
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_build_application_wires_dependencies(self) -> None:
        app = build_application("123456:ABCDEF1234567890", self.dependencies)
        self.assertIn("dependencies", app.bot_data)
        self.assertIs(app.bot_data["dependencies"], self.dependencies)

    def test_parse_natural_create(self) -> None:
        parsed = _parse_natural_create("agenda demo tecnica el 2030-06-01 a las 14:30")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.title, "demo tecnica")
        self.assertEqual(parsed.start_time.hour, 14)
        self.assertEqual(parsed.start_time.minute, 30)

    def test_parse_natural_create_invalid_time(self) -> None:
        parsed = _parse_natural_create("programa demo tecnica manana a las 99:99")
        self.assertIsNone(parsed)

    def test_parse_natural_update(self) -> None:
        parsed = _parse_natural_update("mueve la cita 7 a manana 18:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.event_id, 7)
        self.assertEqual(parsed.new_start.hour, 18)

    def test_parse_natural_cancel_by_title_query(self) -> None:
        parsed = _parse_natural_cancel_request("cancela reunion semanal")
        self.assertIsNotNone(parsed)
        self.assertIsNone(parsed.event_id)
        self.assertEqual(parsed.title_query, "reunion semanal")

    def test_resolve_event_selection_ambiguous(self) -> None:
        now = datetime.now() + timedelta(days=2)
        events = [
            Event(1, 10, "Reunion semanal equipo", None, None, now, now + timedelta(hours=1), 3),
            Event(2, 10, "Reunion semanal producto", None, None, now + timedelta(days=1), now + timedelta(days=1, hours=1), 3),
            Event(3, 10, "Doctor", None, None, now + timedelta(days=3), now + timedelta(days=3, hours=1), 3),
        ]
        selection = _resolve_event_selection(ParsedCancelRequest(event_id=None, title_query="reunion semanal"), events)
        self.assertIsInstance(selection, list)
        self.assertEqual(len(selection), 2)

    def test_normalization_and_confirmation_helpers(self) -> None:
        self.assertEqual(_normalize_text("  Mañana   a las 3  "), "manana a las 3")
        self.assertTrue(_looks_like_confirmation("Sí"))
        self.assertTrue(_looks_like_confirmation("no"))
        self.assertFalse(_looks_like_confirmation("quizas"))

    def test_split_payload(self) -> None:
        payload = "titulo | 2030-01-01T10:00:00 | 2030-01-01T11:00:00 | descripcion"
        parts = _split_payload(payload, 4)
        self.assertIsNotNone(parts)
        self.assertEqual(parts[0], "titulo")


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _FakeUpdate:
    def __init__(self, text: str, chat_id: int = 12345) -> None:
        self.effective_message = _FakeMessage(text)
        self.effective_chat = SimpleNamespace(id=chat_id)


class TelegramConversationFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.connection = _create_in_memory_connection()

        users = UserRepository(self.connection)
        events = EventRepository(self.connection)
        reminders = ReminderRepository(self.connection)
        history = HistoryRepository(self.connection)

        self.dependencies = TelegramDependencies(
            orchestrator=OrchestratorAgent(NLPAgent(), IntentAgent(), PriorityAgent(), ConfirmationAgent()),
            scheduling=SchedulingAgent(events, reminders, default_reminder_minutes=15),
            preferences=UserPreferencesAgent(users),
            notification=NotificationAgent(),
            history=HistoryAgent(history),
        )
        self.context = SimpleNamespace(
            application=SimpleNamespace(bot_data={"dependencies": self.dependencies}),
            user_data={},
            args=[],
        )

    def tearDown(self) -> None:
        self.connection.close()

    async def test_health_command_reports_db_ok(self) -> None:
        update = _FakeUpdate("/health")
        await health_command(update, self.context)
        self.assertIn("db: ok", update.effective_message.replies[0])

    async def test_natural_create_requires_confirmation_then_persists_event(self) -> None:
        first_update = _FakeUpdate("programa demo de producto manana a las 15:30")
        await text_router(first_update, self.context)

        self.assertIn("Confirmas crear la cita", first_update.effective_message.replies[0])
        self.assertIn("pending_action", self.context.user_data)

        confirm_update = _FakeUpdate("si")
        await text_router(confirm_update, self.context)

        self.assertTrue(any("Listo, agend" in reply for reply in confirm_update.effective_message.replies))
        events = self.dependencies.scheduling.list_agenda(1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "demo de producto")

    async def test_natural_cancel_ambiguous_requires_option_then_confirmation(self) -> None:
        user = self.dependencies.preferences.upsert_user(User(id=None, telegram_chat_id="12345"))
        start_time = datetime.now() + timedelta(days=2)
        self.dependencies.scheduling.create_event(
            Event(None, user.id or 0, "Reunion semanal equipo", None, None, start_time, start_time + timedelta(hours=1), 3)
        )
        self.dependencies.scheduling.create_event(
            Event(None, user.id or 0, "Reunion semanal producto", None, None, start_time + timedelta(days=1), start_time + timedelta(days=1, hours=1), 3)
        )

        ask_update = _FakeUpdate("cancela reunion semanal")
        await text_router(ask_update, self.context)
        self.assertIn("Encontré varias citas", ask_update.effective_message.replies[0])
        self.assertIn("pending_disambiguation", self.context.user_data)

        choose_update = _FakeUpdate("2")
        await text_router(choose_update, self.context)
        self.assertIn("Confirmas cancelar la cita", choose_update.effective_message.replies[0])

        confirm_update = _FakeUpdate("si")
        await text_router(confirm_update, self.context)
        self.assertTrue(any("Cancelé la cita" in reply for reply in confirm_update.effective_message.replies))

    async def test_natural_update_invalid_time_prompts_for_valid_data(self) -> None:
        update = _FakeUpdate("mueve reunion equipo a manana 99:99")
        await text_router(update, self.context)
        self.assertIn("necesito fecha/hora", update.effective_message.replies[0])

    async def test_natural_create_blocks_suspicious_content(self) -> None:
        first_update = _FakeUpdate("programa drop table users manana a las 10:00")
        await text_router(first_update, self.context)
        self.assertIn("No voy a ejecutar instrucciones peligrosas", first_update.effective_message.replies[0])
        self.assertNotIn("pending_action", self.context.user_data)


def _create_in_memory_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_chat_id TEXT NOT NULL UNIQUE,
            email TEXT,
            preferences TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            location TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'scheduled',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            remind_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'telegram',
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL
        );
        """
    )
    return connection


if __name__ == "__main__":
    unittest.main()
