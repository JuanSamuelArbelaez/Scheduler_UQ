from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from db.repositories import UserRepository
from models.entities import User


class UserPreferencesAgent:
    name = "preferences"

    def __init__(self, users: UserRepository, default_timezone: str = "America/Bogota") -> None:
        self.users = users
        self.default_timezone = default_timezone

    def get_user(self, user_key: str) -> User:
        return self.users.get_by_user_key(user_key)

    def upsert_user(self, user: User) -> User:
        merged_preferences = dict(user.preferences)
        merged_preferences.setdefault("timezone", self.default_timezone)
        return self.users.upsert(User(id=user.id, user_key=user.user_key, email=user.email, preferences=merged_preferences))

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

    def get_calendar_email(self, user: User) -> str | None:
        email = (user.email or "").strip()
        return email or None

    def get_google_calendar_credentials(self, user: User) -> dict[str, Any] | None:
        if user.id is None:
            return None
        return self.users.get_google_calendar_credentials(user.id)

    def is_google_calendar_connected(self, user: User) -> bool:
        if user.id is None:
            return False
        return self.users.has_google_calendar_credentials(user.id)

    def update_google_calendar_credentials(self, user: User, credentials: dict[str, Any]) -> User:
        if user.id is None:
            raise ValueError("User id is required")
        self.users.set_google_calendar_credentials(user.id, credentials)
        return self.users.get_by_id(user.id)

    def clear_google_calendar_credentials(self, user: User) -> User:
        if user.id is None:
            raise ValueError("User id is required")
        self.users.clear_google_calendar_credentials(user.id)
        return self.users.get_by_id(user.id)

    def has_configured_timezone(self, user: User) -> bool:
        timezone_name = str(user.preferences.get("timezone") or "").strip()
        return bool(timezone_name)

    def update_preference(self, user: User, key: str, value: Any) -> User:
        preferences = dict(user.preferences)
        preferences[key] = value
        return self.users.update_email_and_preferences(user.id or 0, user.email, preferences)