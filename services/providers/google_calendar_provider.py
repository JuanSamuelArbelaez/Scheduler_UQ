from __future__ import annotations

from datetime import UTC
import logging
from typing import Any

from models.entities import Event, User
from services.google_calendar_service import GoogleCalendarService

from .calendar_provider import CalendarCapabilitySnapshot, CalendarProvider, CalendarSyncResult


logger = logging.getLogger(__name__)


class GoogleCalendarProvider(CalendarProvider):
    name = "google-calendar-direct"

    def __init__(
        self,
        calendar_service: GoogleCalendarService,
        default_calendar_id: str = "primary",
    ) -> None:
        self.calendar_service = calendar_service
        self.default_calendar_id = (default_calendar_id or "primary").strip() or "primary"

    def is_available(self) -> bool:
        # Disponible si existe service account o si habrá OAuth por usuario en runtime.
        return True

    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        return CalendarCapabilitySnapshot(
            tools=[
                "google_calendar.create_event",
                "google_calendar.update_event",
                "google_calendar.delete_event",
            ],
            templates=["calendar-event-template"],
            data_sources=["google-calendar://primary"],
        )

    def create_event(self, event: Event, user: User) -> CalendarSyncResult:
        payload = self._build_payload("create", event, user)
        try:
            response = self.calendar_service.create_event(
                calendar_id=str(payload["calendar_id"]),
                title=str(payload["title"]),
                start_time_utc=str(payload["start_time_utc"]),
                end_time_utc=str(payload["end_time_utc"]),
                description=payload.get("description"),
                location=payload.get("location"),
                oauth_credentials=payload.get("oauth_credentials") if isinstance(payload.get("oauth_credentials"), dict) else None,
            )
            external_id = self._extract_external_id(response)
            return CalendarSyncResult(
                success=True,
                provider_name=self.name,
                action="create",
                message=f"Evento creado en Google Calendar ({external_id or 'sin id'})",
                external_id=external_id,
                payload=payload,
                capabilities=self.describe_capabilities(),
            )
        except Exception as error:
            logger.warning("Google calendar create falló: %s", error)
            return self._fallback_result("create", payload, str(error))

    def update_event(self, event: Event, user: User) -> CalendarSyncResult:
        payload = self._build_payload("update", event, user)
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            return self._fallback_result(
                "update",
                payload,
                "event_id de Google no disponible; crea el evento primero para enlazarlo",
            )

        try:
            response = self.calendar_service.update_event(
                calendar_id=str(payload["calendar_id"]),
                event_id=event_id,
                title=str(payload["title"]),
                start_time_utc=str(payload["start_time_utc"]),
                end_time_utc=str(payload["end_time_utc"]),
                description=payload.get("description"),
                location=payload.get("location"),
                oauth_credentials=payload.get("oauth_credentials") if isinstance(payload.get("oauth_credentials"), dict) else None,
            )
            external_id = self._extract_external_id(response) or event_id
            return CalendarSyncResult(
                success=True,
                provider_name=self.name,
                action="update",
                message=f"Evento actualizado en Google Calendar ({external_id})",
                external_id=external_id,
                payload=payload,
                capabilities=self.describe_capabilities(),
            )
        except Exception as error:
            logger.warning("Google calendar update falló: %s", error)
            return self._fallback_result("update", payload, str(error))

    def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
        payload = self._build_payload("delete", event, user)
        event_id = payload.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            return self._fallback_result(
                "delete",
                payload,
                "event_id de Google no disponible; no hay recurso remoto para eliminar",
            )

        try:
            self.calendar_service.delete_event(
                calendar_id=str(payload["calendar_id"]),
                event_id=event_id,
                oauth_credentials=payload.get("oauth_credentials") if isinstance(payload.get("oauth_credentials"), dict) else None,
            )
            return CalendarSyncResult(
                success=True,
                provider_name=self.name,
                action="delete",
                message=f"Evento eliminado en Google Calendar ({event_id})",
                external_id=event_id,
                payload=payload,
                capabilities=self.describe_capabilities(),
            )
        except Exception as error:
            logger.warning("Google calendar delete falló: %s", error)
            return self._fallback_result("delete", payload, str(error))

    def _build_payload(self, action: str, event: Event, user: User) -> dict[str, Any]:
        start_dt = event.start_time if event.start_time.tzinfo is not None else event.start_time.replace(tzinfo=UTC)
        end_dt = event.end_time if event.end_time.tzinfo is not None else event.end_time.replace(tzinfo=UTC)

        payload: dict[str, Any] = {
            "calendar_id": self.default_calendar_id,
            "title": event.title,
            "start_time_utc": start_dt.astimezone(UTC).isoformat(),
            "end_time_utc": end_dt.astimezone(UTC).isoformat(),
            "description": event.description,
            "location": event.location,
        }

        oauth_credentials = None
        if isinstance(user.preferences, dict):
            raw_credentials = user.preferences.get("google_calendar_oauth")
            if isinstance(raw_credentials, dict) and raw_credentials:
                oauth_credentials = raw_credentials
        if oauth_credentials is not None:
            payload["oauth_credentials"] = oauth_credentials

        if action in {"update", "delete"}:
            payload["event_id"] = self._resolve_external_event_id(event)

        if action == "delete":
            return {
                "calendar_id": payload["calendar_id"],
                "event_id": payload.get("event_id"),
                "oauth_credentials": payload.get("oauth_credentials"),
            }

        return payload

    def _resolve_external_event_id(self, event: Event) -> str | None:
        metadata = event.metadata if isinstance(event.metadata, dict) else {}
        for key in ("google_calendar_event_id", "external_id", "event_id", "calendar_event_id"):
            raw_value = metadata.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                return raw_value.strip()
            if isinstance(raw_value, int):
                return str(raw_value)
        return None

    def _extract_external_id(self, response: dict[str, Any]) -> str | None:
        for key in ("id", "event_id", "calendar_event_id", "external_id"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return None

    def _fallback_result(self, action: str, payload: dict[str, Any], reason: str) -> CalendarSyncResult:
        return CalendarSyncResult(
            success=False,
            provider_name=self.name,
            action=action,
            message=f"Sincronización Google Calendar no disponible: {reason}",
            fallback_used=True,
            payload=payload,
            capabilities=self.describe_capabilities(),
        )
