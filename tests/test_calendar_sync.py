from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
import unittest

from agents.history import HistoryAgent
from agents.notification import NotificationAgent
from db.repositories import EventRepository, HistoryRepository, ReminderRepository, UserRepository
from models.entities import Event, User
from services.calendar_sync_service import CalendarSyncService
from services.email_service import EmailService, EmailSettings
from services.providers.calendar_provider import CalendarCapabilitySnapshot, CalendarProvider, CalendarSyncResult
from services.providers.google_calendar_provider import GoogleCalendarProvider
from services.scheduler_service import SchedulerService


class FakeGoogleCalendarService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def create_event(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"id": "ext-create-1"}

    def update_event(self, **kwargs):
        self.calls.append(("update", kwargs))
        return {"id": kwargs.get("event_id", "ext-update-1")}

    def delete_event(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return True


class FakeProvider(CalendarProvider):
    name = "fake-calendar"

    def __init__(self) -> None:
        self.available = True
        self.fail_next = False
        self.calls: list[tuple[str, dict[str, object]]] = []

    def is_available(self) -> bool:
        return self.available

    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        return CalendarCapabilitySnapshot(tools=["a"], templates=["b"], data_sources=["c"])

    def create_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._record("create", event, user)

    def update_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._record("update", event, user)

    def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
        return self._record("delete", event, user)

    def _record(self, action: str, event: Event, user: User) -> CalendarSyncResult:
        payload = {
            "event_id": event.id,
            "email": user.email,
            "timezone": user.preferences.get("timezone"),
        }
        self.calls.append((action, payload))
        if self.fail_next:
            self.fail_next = False
            return CalendarSyncResult(
                success=False,
                provider_name=self.name,
                action=action,
                message="provider failure",
                fallback_used=True,
                payload=payload,
            )
        return CalendarSyncResult(
            success=True,
            provider_name=self.name,
            action=action,
            message=f"synced-{action}",
            external_id=f"ext-{len(self.calls)}",
            fallback_used=False,
            payload=payload,
        )


class CalendarSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL UNIQUE,
                email TEXT,
                username TEXT,
                email_verified INTEGER NOT NULL DEFAULT 0,
                preferences TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE google_calendar_credentials (
                user_id INTEGER PRIMARY KEY,
                credentials_json TEXT NOT NULL,
                connected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                location TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL DEFAULT 'scheduled',
                source TEXT NOT NULL DEFAULT 'web',
                timezone TEXT NOT NULL DEFAULT 'America/Bogota',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed INTEGER NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}',
                recurrence_rule TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                remind_at TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'both',
                sent_at TEXT,
                delivery_status TEXT,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
            );
            CREATE TABLE history (
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

        self.users = UserRepository(self.connection)
        self.events = EventRepository(self.connection)
        self.reminders = ReminderRepository(self.connection)
        self.history_repo = HistoryRepository(self.connection)
        self.history = HistoryAgent(self.history_repo)
        self.user = self.users.upsert(
            User(
                id=None,
                user_key="chat-1",
                email="user@example.com",
                preferences={"timezone": "America/Bogota"},
            )
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_google_provider_exposes_capabilities_and_payload(self) -> None:
        calendar_service = FakeGoogleCalendarService()
        provider = GoogleCalendarProvider(calendar_service, default_calendar_id="calendar@example.com")

        self.assertTrue(provider.is_available())
        capabilities = provider.describe_capabilities()
        self.assertIn("google_calendar.create_event", capabilities.tools)
        self.assertIn("calendar-event-template", capabilities.templates)
        self.assertIn("google-calendar://primary", capabilities.data_sources)

        event = Event(
            id=None,
            user_id=self.user.id or 0,
            title="Reunión Google",
            start_time=datetime.now() + timedelta(hours=2),
            end_time=datetime.now() + timedelta(hours=3),
            description="demo",
            location="online",
        )
        result = provider.create_event(event, self.user)
        self.assertTrue(result.success)
        self.assertEqual(calendar_service.calls[0][0], "create")
        self.assertEqual(calendar_service.calls[0][1]["calendar_id"], "calendar@example.com")
        self.assertEqual(calendar_service.calls[0][1]["title"], "Reunión Google")
        self.assertIn("start_time_utc", calendar_service.calls[0][1])
        self.assertIn("end_time_utc", calendar_service.calls[0][1])

    def test_google_provider_includes_user_oauth_credentials(self) -> None:
        calendar_service = FakeGoogleCalendarService()
        provider = GoogleCalendarProvider(calendar_service, default_calendar_id="primary")
        self.users.set_google_calendar_credentials(
            self.user.id or 0,
            {
                "token": "token-value",
                "refresh_token": "refresh-value",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": ["https://www.googleapis.com/auth/calendar"],
            },
        )
        connected_user = self.users.get_by_id(self.user.id or 0)

        event = Event(
            id=None,
            user_id=connected_user.id or 0,
            title="Evento personal",
            start_time=datetime.now() + timedelta(hours=6),
            end_time=datetime.now() + timedelta(hours=7),
            description="demo",
            location="online",
        )

        result = provider.create_event(event, connected_user)
        self.assertTrue(result.success)
        self.assertIn("oauth_credentials", calendar_service.calls[0][1])
        self.assertEqual(calendar_service.calls[0][1]["oauth_credentials"]["token"], "token-value")

    def test_calendar_sync_service_falls_back_locally_and_logs_history(self) -> None:
        provider = FakeProvider()
        provider.fail_next = True
        sync_service = CalendarSyncService(provider, history=self.history, retry_count=0)

        event = Event(
            id=None,
            user_id=self.user.id or 0,
            title="Reunión fallback",
            start_time=datetime.now() + timedelta(hours=4),
            end_time=datetime.now() + timedelta(hours=5),
            description="demo",
            location="online",
        )

        outcome = sync_service.sync_create(event, self.user)
        self.assertFalse(outcome.success)
        self.assertTrue(outcome.fallback_used)

        history_rows = self.connection.execute("SELECT action, details FROM history ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(history_rows)
        self.assertIn("calendar_sync_create_failed", history_rows["action"])
        self.assertIn("fallback_used", history_rows["details"])

    def test_calendar_sync_service_allows_users_without_email_when_connected(self) -> None:
        provider = FakeProvider()
        sync_service = CalendarSyncService(provider, history=self.history, retry_count=0)

        user_without_email = self.users.upsert(
            User(
                id=None,
                user_key="chat-no-email",
                email=None,
                preferences={"timezone": "America/Bogota"},
            )
        )

        event = Event(
            id=None,
            user_id=user_without_email.id or 0,
            title="Reunión sin email",
            start_time=datetime.now() + timedelta(hours=8),
            end_time=datetime.now() + timedelta(hours=9),
            description="demo",
            location="online",
        )

        outcome = sync_service.sync_create(event, user_without_email)
        self.assertTrue(outcome.success)
        self.assertEqual(provider.calls[0][0], "create")

    def test_scheduler_service_sends_create_update_and_delete_to_calendar_sync(self) -> None:
        provider = FakeProvider()
        sync_service = CalendarSyncService(provider, history=self.history, retry_count=0)
        scheduler = SchedulerService(
            self.events,
            self.reminders,
            self.users,
            NotificationAgent(),
            EmailService(EmailSettings(host="", port=587, username="", password="", from_email="")),
            calendar_sync=sync_service,
        )

        start = datetime.now() + timedelta(hours=2)
        event = Event(
            id=None,
            user_id=self.user.id or 0,
            title="Reunión Google Calendar",
            start_time=start,
            end_time=start + timedelta(hours=1),
            description="demo",
            location="online",
        )

        create_result = scheduler.create_event_with_conflict_resolution(event)
        self.assertTrue(any(call[0] == "create" for call in provider.calls))
        self.assertIn("Sincronización Google Calendar", create_result.message)

        saved_event = self.events.list_by_user(self.user.id or 0)[0]
        self.assertEqual(saved_event.metadata.get("google_calendar_event_id"), "ext-1")
        updated = Event(
            id=saved_event.id,
            user_id=self.user.id or 0,
            title="Reunión actualizada",
            start_time=start + timedelta(hours=1),
            end_time=start + timedelta(hours=2),
            description="demo 2",
            location="online",
        )
        update_result = scheduler.update_event(updated)
        self.assertTrue(any(call[0] == "update" for call in provider.calls))
        self.assertIn("Sincronización Google Calendar", update_result.message)

        cancel_result = scheduler.cancel_event(saved_event.id or 0)
        self.assertTrue(any(call[0] == "delete" for call in provider.calls))
        self.assertIn("Sincronización Google Calendar", cancel_result.message)

        cancelled_event = self.events.get_by_id(saved_event.id or 0)
        self.assertEqual(cancelled_event.status, "cancelled")
        self.assertEqual(self.events.list_by_user(self.user.id or 0), [])


if __name__ == "__main__":
    unittest.main()