from __future__ import annotations

from typing import Any

from db.repositories import UserRepository
from models.entities import User


class UserPreferencesAgent:
    name = "preferences"

    def __init__(self, users: UserRepository, default_timezone: str = "America/Bogota") -> None:
        self.users = users
        self.default_timezone = default_timezone

    def get_user(self, telegram_chat_id: str) -> User:
        return self.users.get_by_chat_id(telegram_chat_id)

    def upsert_user(self, user: User) -> User:
        merged_preferences = dict(user.preferences)
        merged_preferences.setdefault("timezone", self.default_timezone)
        return self.users.upsert(User(id=user.id, telegram_chat_id=user.telegram_chat_id, email=user.email, preferences=merged_preferences))

    def update_email(self, user: User, email: str) -> User:
        preferences = dict(user.preferences)
        preferences.setdefault("timezone", self.default_timezone)
        return self.users.update_email_and_preferences(user.id or 0, email.strip(), preferences)

    def update_timezone(self, user: User, timezone_name: str) -> User:
        preferences = dict(user.preferences)
        preferences["timezone"] = timezone_name.strip()
        return self.users.update_email_and_preferences(user.id or 0, user.email, preferences)

    def get_timezone(self, user: User) -> str:
        timezone_name = str(user.preferences.get("timezone") or "").strip()
        return timezone_name or self.default_timezone

    def has_configured_timezone(self, user: User) -> bool:
        timezone_name = str(user.preferences.get("timezone") or "").strip()
        return bool(timezone_name)

    def update_preference(self, user: User, key: str, value: Any) -> User:
        preferences = dict(user.preferences)
        preferences[key] = value
        return self.users.update_email_and_preferences(user.id or 0, user.email, preferences)