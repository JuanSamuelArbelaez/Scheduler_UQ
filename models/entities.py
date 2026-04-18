from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class User:
    id: int | None
    telegram_chat_id: str
    email: str | None = None
    preferences: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Event:
    id: int | None
    user_id: int
    title: str
    description: str | None
    location: str | None
    start_time: datetime
    end_time: datetime
    priority: int = 3
    status: str = "scheduled"


@dataclass(slots=True)
class Reminder:
    id: int | None
    event_id: int
    remind_at: datetime
    channel: str = "telegram"


@dataclass(slots=True)
class HistoryEntry:
    id: int | None
    user_id: int
    event_id: int | None
    action: str
    timestamp: datetime
    details: str | None = None