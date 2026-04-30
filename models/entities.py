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
    start_time: datetime
    end_time: datetime
    description: str | None = None
    location: str | None = None
    priority: int = 3
    status: str = "scheduled"
    source: str = "telegram"  # telegram, web, api
    timezone: str = "America/Bogota"
    created_at: datetime = field(default_factory=lambda: datetime.now())
    updated_at: datetime = field(default_factory=lambda: datetime.now())
    confirmed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    recurrence_rule: str | None = None  # Para futuras expansiones


@dataclass(slots=True)
class Reminder:
    id: int | None
    event_id: int
    remind_at: datetime
    channel: str = "both"  # telegram, email, both


@dataclass(slots=True)
class HistoryEntry:
    id: int | None
    user_id: int
    event_id: int | None
    action: str
    timestamp: datetime
    details: str | None = None