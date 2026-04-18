from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import sqlite3

from models.entities import Event, HistoryEntry, Reminder, User


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


class UserRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert(self, user: User) -> User:
        self.connection.execute(
            """
            INSERT INTO users (telegram_chat_id, email, preferences)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_chat_id) DO UPDATE SET
                email = excluded.email,
                preferences = excluded.preferences
            """,
            (user.telegram_chat_id, user.email, json.dumps(user.preferences)),
        )
        return self.get_by_chat_id(user.telegram_chat_id)

    def get_by_chat_id(self, telegram_chat_id: str) -> User:
        row = self.connection.execute(
            "SELECT * FROM users WHERE telegram_chat_id = ?",
            (telegram_chat_id,),
        ).fetchone()
        if row is None:
            raise LookupError("User not found")
        return User(
            id=row["id"],
            telegram_chat_id=row["telegram_chat_id"],
            email=row["email"],
            preferences=json.loads(row["preferences"] or "{}"),
        )


class EventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, event: Event) -> Event:
        cursor = self.connection.execute(
            """
            INSERT INTO events (user_id, title, description, location, start_time, end_time, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.user_id,
                event.title,
                event.description,
                event.location,
                event.start_time.isoformat(),
                event.end_time.isoformat(),
                event.priority,
                event.status,
            ),
        )
        return replace(event, id=cursor.lastrowid)

    def get_by_id(self, event_id: int) -> Event:
        row = self.connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise LookupError("Event not found")
        return self._row_to_event(row)

    def list_by_user(self, user_id: int) -> list[Event]:
        rows = self.connection.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY start_time ASC",
            (user_id,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def update(self, event: Event) -> Event:
        if event.id is None:
            raise ValueError("Event id is required")
        self.connection.execute(
            """
            UPDATE events
            SET title = ?, description = ?, location = ?, start_time = ?, end_time = ?, priority = ?, status = ?
            WHERE id = ?
            """,
            (
                event.title,
                event.description,
                event.location,
                event.start_time.isoformat(),
                event.end_time.isoformat(),
                event.priority,
                event.status,
                event.id,
            ),
        )
        return event

    def cancel(self, event_id: int) -> None:
        self.connection.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))

    def has_overlap(self, user_id: int, start_time: datetime, end_time: datetime, exclude_event_id: int | None = None) -> bool:
        query = """
            SELECT 1
            FROM events
            WHERE user_id = ?
              AND status != 'cancelled'
              AND start_time < ?
              AND end_time > ?
        """
        params: list[object] = [user_id, end_time.isoformat(), start_time.isoformat()]
        if exclude_event_id is not None:
            query += " AND id != ?"
            params.append(exclude_event_id)
        row = self.connection.execute(query, params).fetchone()
        return row is not None

    def _row_to_event(self, row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            description=row["description"],
            location=row["location"],
            start_time=_parse_datetime(row["start_time"]),
            end_time=_parse_datetime(row["end_time"]),
            priority=row["priority"],
            status=row["status"],
        )


class ReminderRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, reminder: Reminder) -> Reminder:
        cursor = self.connection.execute(
            "INSERT INTO reminders (event_id, remind_at, channel) VALUES (?, ?, ?)",
            (reminder.event_id, reminder.remind_at.isoformat(), reminder.channel),
        )
        return replace(reminder, id=cursor.lastrowid)


class HistoryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create(self, entry: HistoryEntry) -> HistoryEntry:
        cursor = self.connection.execute(
            """
            INSERT INTO history (user_id, event_id, action, timestamp, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entry.user_id,
                entry.event_id,
                entry.action,
                entry.timestamp.isoformat(),
                entry.details,
            ),
        )
        return replace(entry, id=cursor.lastrowid)