from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
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
)
from db.database import Database
from db.repositories import EventRepository, HistoryRepository, ReminderRepository, UserRepository
from models.entities import Event


class TelegramBotTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(Path(":memory:"))
        database.initialize()
        self.connection = database.connect()

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