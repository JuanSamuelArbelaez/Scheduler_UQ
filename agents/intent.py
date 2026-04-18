from __future__ import annotations

from enum import StrEnum

from config.settings import load_settings
from services.local_llm import LocalOllamaClient


class IntentType(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    PREFERENCES = "preferences"
    UNKNOWN = "unknown"


class IntentAgent:
    name = "intent"

    def __init__(self, llm_client: LocalOllamaClient | None = None) -> None:
        self.llm_client = llm_client or self._build_default_llm_client()

    def classify(self, text: str) -> IntentType:
        llm_intent = self._classify_with_llm(text)
        if llm_intent is not None:
            return llm_intent

        normalized = text.lower()
        create_keywords = ("agrega", "crear", "añade", "programa", "cita")
        read_keywords = ("que tengo", "agenda", "consultar", "mañana", "hoy")
        update_keywords = ("mueve", "cambia", "modifica", "reprograma", "actualiza")
        delete_keywords = ("cancela", "elimina", "borra", "anula")
        preferences_keywords = (
            "preferencia",
            "preferencias",
            "idioma",
            "recordatorio",
            "correo",
            "email",
            "zona horaria",
            "utc",
        )

        if any(keyword in normalized for keyword in preferences_keywords):
            return IntentType.PREFERENCES
        if any(keyword in normalized for keyword in delete_keywords):
            return IntentType.DELETE
        if any(keyword in normalized for keyword in update_keywords):
            return IntentType.UPDATE
        if any(keyword in normalized for keyword in create_keywords):
            return IntentType.CREATE
        if any(keyword in normalized for keyword in read_keywords):
            return IntentType.READ
        return IntentType.UNKNOWN

    def _classify_with_llm(self, text: str) -> IntentType | None:
        if self.llm_client is None:
            return None
        raw_intent = self.llm_client.classify_intent(text)
        if raw_intent is None:
            return None

        mapping = {
            "create": IntentType.CREATE,
            "read": IntentType.READ,
            "update": IntentType.UPDATE,
            "delete": IntentType.DELETE,
            "preferences": IntentType.PREFERENCES,
        }
        resolved = mapping.get(raw_intent)
        if resolved == IntentType.UNKNOWN:
            return None
        return resolved

    def _build_default_llm_client(self) -> LocalOllamaClient | None:
        try:
            settings = load_settings()
        except Exception:
            return None

        if settings.llm_provider != "ollama":
            return None
        if not settings.ollama_model:
            return None
        return LocalOllamaClient(settings.ollama_base_url, settings.ollama_model)