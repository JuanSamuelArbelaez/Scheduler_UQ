from __future__ import annotations

from enum import StrEnum


class IntentType(StrEnum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    PREFERENCES = "preferences"
    UNKNOWN = "unknown"


class IntentAgent:
    name = "intent"

    def classify(self, text: str) -> IntentType:
        normalized = text.lower()
        create_keywords = ("agrega", "crear", "añade", "programa", "cita")
        read_keywords = ("que tengo", "agenda", "ver", "consultar", "mañana", "hoy")
        update_keywords = ("mueve", "cambia", "modifica", "reprograma", "actualiza")
        delete_keywords = ("cancela", "elimina", "borra", "anula")
        preferences_keywords = ("preferencia", "preferencias", "idioma", "recordatorio")

        if any(keyword in normalized for keyword in delete_keywords):
            return IntentType.DELETE
        if any(keyword in normalized for keyword in update_keywords):
            return IntentType.UPDATE
        if any(keyword in normalized for keyword in preferences_keywords):
            return IntentType.PREFERENCES
        if any(keyword in normalized for keyword in read_keywords):
            return IntentType.READ
        if any(keyword in normalized for keyword in create_keywords):
            return IntentType.CREATE
        return IntentType.UNKNOWN