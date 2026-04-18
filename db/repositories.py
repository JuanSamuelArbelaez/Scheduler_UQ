from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import sqlite3
from typing import Any

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
        self.connection.commit()
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

    def get_by_id(self, user_id: int) -> User:
        row = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise LookupError("User not found")
        return User(
            id=row["id"],
            telegram_chat_id=row["telegram_chat_id"],
            email=row["email"],
            preferences=json.loads(row["preferences"] or "{}"),
        )

    def update_email_and_preferences(self, user_id: int, email: str | None, preferences: dict[str, Any]) -> User:
        self.connection.execute(
            "UPDATE users SET email = ?, preferences = ? WHERE id = ?",
            (email, json.dumps(preferences), user_id),
        )
        self.connection.commit()
        return self.get_by_id(user_id)


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
        self.connection.commit()
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
        self.connection.commit()
        return event

    def cancel(self, event_id: int) -> None:
        self.connection.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
        self.connection.commit()

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
            "INSERT INTO reminders (event_id, remind_at, channel, sent_at, delivery_status) VALUES (?, ?, ?, NULL, NULL)",
            (reminder.event_id, reminder.remind_at.isoformat(), reminder.channel),
        )
        self.connection.commit()
        return replace(reminder, id=cursor.lastrowid)

    def list_due_unsent(self, now_at: datetime) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT
                reminders.id AS reminder_id,
                reminders.event_id AS event_id,
                reminders.remind_at AS remind_at,
                events.user_id AS user_id,
                events.title AS event_title,
                events.start_time AS event_start_time,
                users.email AS user_email,
                users.preferences AS user_preferences
            FROM reminders
            JOIN events ON events.id = reminders.event_id
            JOIN users ON users.id = events.user_id
            WHERE reminders.sent_at IS NULL
              AND reminders.remind_at <= ?
              AND events.status != 'cancelled'
            ORDER BY reminders.remind_at ASC
            """,
            (now_at.isoformat(),),
        ).fetchall()

        payload: list[dict[str, Any]] = []
        for row in rows:
            payload.append(
                {
                    "reminder_id": row["reminder_id"],
                    "event_id": row["event_id"],
                    "remind_at": _parse_datetime(row["remind_at"]),
                    "user_id": row["user_id"],
                    "event_title": row["event_title"],
                    "event_start_time": _parse_datetime(row["event_start_time"]),
                    "user_email": row["user_email"],
                    "user_preferences": json.loads(row["user_preferences"] or "{}"),
                }
            )
        return payload

    def mark_delivery(self, reminder_id: int, delivery_status: str) -> None:
        self.connection.execute(
            "UPDATE reminders SET sent_at = ?, delivery_status = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), delivery_status, reminder_id),
        )
        self.connection.commit()


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
        self.connection.commit()
        return replace(entry, id=cursor.lastrowid)