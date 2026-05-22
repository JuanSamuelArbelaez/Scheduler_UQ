from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Callable, Iterator


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.enable_load_extension(False)
        connection.set_authorizer(self._build_authorizer())
        return connection

    def initialize(self) -> None:
        with sqlite3.connect(self.path, check_same_thread=False) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_chat_id TEXT NOT NULL UNIQUE,
                    email TEXT,
                    preferences TEXT NOT NULL DEFAULT '{}',
                    username TEXT,
                    password_hash TEXT,
                    email_verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS google_calendar_credentials (
                    user_id INTEGER PRIMARY KEY,
                    credentials_json TEXT NOT NULL,
                    connected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
                    source TEXT NOT NULL DEFAULT 'telegram',
                    timezone TEXT NOT NULL DEFAULT 'America/Bogota',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    confirmed INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    recurrence_rule TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    remind_at TEXT NOT NULL,
                    channel TEXT NOT NULL DEFAULT 'both',
                    sent_at TEXT,
                    delivery_status TEXT,
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

                CREATE TABLE IF NOT EXISTS email_otp_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    otp_hash TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    encrypted_content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_column(connection, "reminders", "sent_at", "TEXT")
            self._ensure_column(connection, "reminders", "delivery_status", "TEXT")
            self._ensure_column(connection, "users", "username", "TEXT")
            self._ensure_column(connection, "users", "password_hash", "TEXT")
            self._ensure_column(connection, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "users", "created_at", "TEXT")
            self._ensure_column(connection, "users", "updated_at", "TEXT")

            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_unique ON users(username)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_otp_user_id ON email_otp_codes(user_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id)")
            connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _build_authorizer(self) -> Callable[[int, str | None, str | None, str | None, str | None], int]:
        blocked_action_names = (
            "SQLITE_ATTACH",
            "SQLITE_DETACH",
            "SQLITE_DROP_TABLE",
            "SQLITE_DROP_INDEX",
            "SQLITE_DROP_VIEW",
            "SQLITE_DROP_TRIGGER",
            "SQLITE_DROP_TEMP_TABLE",
            "SQLITE_DROP_TEMP_INDEX",
            "SQLITE_DROP_TEMP_VIEW",
            "SQLITE_DROP_TEMP_TRIGGER",
            "SQLITE_ALTER_TABLE",
            "SQLITE_PRAGMA",
        )
        blocked_actions = {
            getattr(sqlite3, action_name)
            for action_name in blocked_action_names
            if hasattr(sqlite3, action_name)
        }

        def authorizer(
            action: int,
            _arg1: str | None,
            _arg2: str | None,
            _db_name: str | None,
            _trigger_name: str | None,
        ) -> int:
            if hasattr(sqlite3, "SQLITE_PRAGMA") and action == sqlite3.SQLITE_PRAGMA:
                pragma_name = (_arg1 or "").lower()
                if pragma_name in {"table_info"}:
                    return sqlite3.SQLITE_OK
            if hasattr(sqlite3, "SQLITE_ALTER_TABLE") and action == sqlite3.SQLITE_ALTER_TABLE:
                if (_arg1 or "").lower() in {"reminders", "users"}:
                    return sqlite3.SQLITE_OK
            if action in blocked_actions:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        return authorizer

    def _ensure_column(self, connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row[1] for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")