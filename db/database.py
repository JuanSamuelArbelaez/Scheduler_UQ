from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Callable, Iterator


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.enable_load_extension(False)
        connection.set_authorizer(self._build_authorizer())
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
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
            if action in blocked_actions:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        return authorizer