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
    TelegramDependencies,
    _looks_like_confirmation,
    _normalize_text,
    _parse_natural_cancel,
    _parse_natural_create,
    _parse_natural_update,
    _split_payload,
    build_application,
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

    def test_parse_natural_update(self) -> None:
        parsed = _parse_natural_update("mueve la cita 7 a manana 18:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.event_id, 7)
        self.assertEqual(parsed.new_start.hour, 18)

    def test_parse_natural_cancel_by_title(self) -> None:
        now = datetime.now() + timedelta(days=2)
        events = [
            Event(
                id=1,
                user_id=10,
                title="Reunion semanal",
                description=None,
                location=None,
                start_time=now,
                end_time=now + timedelta(hours=1),
                priority=3,
            ),
            Event(
                id=2,
                user_id=10,
                title="Doctor",
                description=None,
                location=None,
                start_time=now + timedelta(days=1),
                end_time=now + timedelta(days=1, hours=1),
                priority=3,
            ),
        ]
        selected = _parse_natural_cancel("cancela la reunion", events)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.id, 1)

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


if __name__ == "__main__":
    unittest.main()


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
        )

    def tearDown(self) -> None:
        self.connection.close()

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

    async def test_natural_cancel_requires_confirmation_then_cancels_event(self) -> None:
        user = self.dependencies.preferences.upsert_user(User(id=None, telegram_chat_id="12345"))
        start_time = datetime.now() + timedelta(days=2)
        created = self.dependencies.scheduling.create_event(
            Event(
                id=None,
                user_id=user.id or 0,
                title="Reunion de estado",
                description=None,
                location=None,
                start_time=start_time,
                end_time=start_time + timedelta(hours=1),
                priority=3,
            )
        )
        self.assertIsNotNone(created.event)

        first_update = _FakeUpdate("cancela reunion de estado")
        await text_router(first_update, self.context)
        self.assertIn("Confirmas cancelar la cita", first_update.effective_message.replies[0])

        reject_update = _FakeUpdate("no")
        await text_router(reject_update, self.context)
        self.assertIn("Acción cancelada", reject_update.effective_message.replies[0])

        second_update = _FakeUpdate("cancela reunion de estado")
        await text_router(second_update, self.context)
        confirm_update = _FakeUpdate("si")
        await text_router(confirm_update, self.context)

        self.assertTrue(any("Cancelé la cita" in reply for reply in confirm_update.effective_message.replies))
        event_after = self.dependencies.scheduling.service.events.get_by_id(created.event.id or 0)
        self.assertEqual(event_after.status, "cancelled")


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