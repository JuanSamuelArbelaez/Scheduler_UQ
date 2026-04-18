from __future__ import annotations

from db.repositories import UserRepository
from models.entities import User


class UserPreferencesAgent:
    name = "preferences"

    def __init__(self, users: UserRepository) -> None:
        self.users = users

    def get_user(self, telegram_chat_id: str) -> User:
        return self.users.get_by_chat_id(telegram_chat_id)

    def upsert_user(self, user: User) -> User:
        return self.users.upsert(user)