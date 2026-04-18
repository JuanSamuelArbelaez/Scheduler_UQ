from __future__ import annotations

from datetime import datetime

from db.repositories import HistoryRepository
from models.entities import HistoryEntry


class HistoryAgent:
    name = "history"

    def __init__(self, repository: HistoryRepository) -> None:
        self.repository = repository

    def record(self, user_id: int, action: str, event_id: int | None = None, details: str | None = None) -> HistoryEntry:
        entry = HistoryEntry(
            id=None,
            user_id=user_id,
            event_id=event_id,
            action=action,
            timestamp=datetime.now(),
            details=details,
        )
        return self.repository.create(entry)