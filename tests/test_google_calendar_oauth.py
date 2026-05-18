from __future__ import annotations

import json
import unittest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agents.preferences import UserPreferencesAgent
from db.repositories import UserRepository
from models.entities import User
from services.google_calendar_oauth import GoogleCalendarOAuthManager


class GoogleCalendarOAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_chat_id TEXT NOT NULL UNIQUE,
                email TEXT,
                preferences TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE google_calendar_credentials (
                user_id INTEGER PRIMARY KEY,
                credentials_json TEXT NOT NULL,
                connected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        self.connection.commit()
        self.users = UserRepository(self.connection)
        self.preferences = UserPreferencesAgent(self.users)
        self.user = self.users.upsert(
            User(
                id=None,
                telegram_chat_id="chat-oauth",
                email="user@example.com",
                preferences={"timezone": "America/Bogota"},
            )
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_preferences_store_google_calendar_credentials(self) -> None:
        updated = self.preferences.update_google_calendar_credentials(
            self.user,
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": ["https://www.googleapis.com/auth/calendar"],
            },
        )

        self.assertTrue(self.preferences.is_google_calendar_connected(updated))
        self.assertEqual(
            self.preferences.get_google_calendar_credentials(updated)["token"],
            "access-token",
        )
        self.assertTrue(self.users.has_google_calendar_credentials(updated.id or 0))

    @patch("services.google_calendar_oauth.Flow")
    def test_manager_builds_authorization_url_and_completes_connection(self, flow_class: MagicMock) -> None:
        fake_credentials = MagicMock()
        fake_credentials.to_json.return_value = json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": ["https://www.googleapis.com/auth/calendar"],
            }
        )

        fake_flow = MagicMock()
        fake_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?state=abc", "state-123")
        fake_flow.credentials = fake_credentials
        flow_class.from_client_secrets_file.return_value = fake_flow

        client_secrets = Path(self.temp_dir.name) / "client_secrets.json"
        client_secrets.write_text("{}", encoding="utf-8")

        manager = GoogleCalendarOAuthManager(
            self.preferences,
            client_secrets_file=str(client_secrets),
            telegram_bot_token=None,
        )

        auth_url = manager.build_authorization_url(self.user)
        self.assertTrue(auth_url.startswith("https://accounts.google.com/"))

        pending_state = next(iter(manager._pending_states))
        result = manager.complete_authorization(pending_state, "auth-code")
        self.assertTrue(result.success)
        self.assertTrue(self.preferences.is_google_calendar_connected(self.preferences.get_user(self.user.telegram_chat_id)))


if __name__ == "__main__":
    unittest.main()