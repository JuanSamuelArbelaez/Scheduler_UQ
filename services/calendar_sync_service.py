from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging

from agents.history import HistoryAgent
from models.entities import Event, User

from .providers.calendar_provider import CalendarCapabilitySnapshot, CalendarProvider, CalendarSyncResult, NoopCalendarProvider


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CalendarSyncOutcome:
    result: CalendarSyncResult
    retries: int = 0

    @property
    def success(self) -> bool:
        return self.result.success

    @property
    def fallback_used(self) -> bool:
        return self.result.fallback_used

    @property
    def message(self) -> str:
        return self.result.message


class CalendarSyncService:
    def __init__(
        self,
        provider: CalendarProvider | None,
        history: HistoryAgent | None = None,
        retry_count: int = 2,
    ) -> None:
        self.provider = provider or NoopCalendarProvider()
        self.history = history
        self.retry_count = max(0, retry_count)

    def describe_capabilities(self) -> CalendarCapabilitySnapshot:
        try:
            return self.provider.describe_capabilities()
        except Exception as error:
            logger.warning("No se pudieron obtener capacidades de calendario: %s", error)
            return CalendarCapabilitySnapshot()

    def sync_create(self, event: Event, user: User) -> CalendarSyncOutcome:
        return self._sync("create", event, user)

    def sync_update(self, event: Event, user: User) -> CalendarSyncOutcome:
        return self._sync("update", event, user)

    def sync_delete(self, event: Event, user: User) -> CalendarSyncOutcome:
        return self._sync("delete", event, user)

    def _sync(self, action: str, event: Event, user: User) -> CalendarSyncOutcome:
        if not self.provider.is_available():
            result = self._fallback_result(action, event, user, "sincronización externa deshabilitada")
            self._record_history(action, event, user, result)
            return CalendarSyncOutcome(result=result, retries=0)

        last_error: Exception | None = None
        for attempt in range(self.retry_count + 1):
            try:
                result = self._call_provider(action, event, user)
                if result.success:
                    self._record_history(action, event, user, result)
                    return CalendarSyncOutcome(result=result, retries=attempt)
                last_error = RuntimeError(result.message)
                logger.warning("Sync intento %s falló para %s: %s", attempt + 1, action, result.message)
            except Exception as error:
                last_error = error
                logger.warning("Sync intento %s lanzó error para %s: %s", attempt + 1, action, error)

        result = self._fallback_result(action, event, user, str(last_error) if last_error else "sincronización externa no disponible")
        self._record_history(action, event, user, result)
        return CalendarSyncOutcome(result=result, retries=self.retry_count)

    def _call_provider(self, action: str, event: Event, user: User) -> CalendarSyncResult:
        if action == "create":
            return self.provider.create_event(event, user)
        if action == "update":
            return self.provider.update_event(event, user)
        if action == "delete":
            return self.provider.delete_event(event, user)
        raise ValueError(f"Acción de calendario no soportada: {action}")

    def _fallback_result(self, action: str, event: Event, user: User, reason: str) -> CalendarSyncResult:
        return CalendarSyncResult(
            success=False,
            provider_name=self.provider.name,
            action=action,
            message=f"Sincronización externa omitida; se mantuvo el flujo local ({reason}).",
            fallback_used=True,
            payload=self._build_payload(action, event, user),
            capabilities=self.describe_capabilities(),
        )

    def _build_payload(self, action: str, event: Event, user: User) -> dict[str, object]:
        return {
            "action": action,
            "event_id": event.id,
            "user_id": user.id,
            "email": user.email,
            "timezone": str(user.preferences.get("timezone") or event.timezone),
        }

    def _record_history(self, action: str, event: Event, user: User, result: CalendarSyncResult) -> None:
        if self.history is None:
            return

        history_action = f"calendar_sync_{action}" if result.success else f"calendar_sync_{action}_failed"
        details = {
            "provider": result.provider_name,
            "fallback_used": result.fallback_used,
            "message": result.message,
            "external_id": result.external_id,
            "payload": self._redact_sensitive_payload(result.payload),
            "capabilities": asdict(result.capabilities),
        }
        try:
            self.history.record(user.id or 0, history_action, event.id, json.dumps(details, ensure_ascii=False))
        except Exception as error:
            logger.warning("No se pudo registrar historial de sincronización de calendario: %s", error)

    def _redact_sensitive_payload(self, payload: dict[str, object]) -> dict[str, object]:
        def scrub(value: object) -> object:
            if isinstance(value, dict):
                redacted: dict[str, object] = {}
                for key, nested_value in value.items():
                    if key in {"oauth_credentials", "google_calendar_oauth"}:
                        redacted[key] = "[redacted]"
                    else:
                        redacted[key] = scrub(nested_value)
                return redacted
            if isinstance(value, list):
                return [scrub(item) for item in value]
            return value

        return scrub(payload) if isinstance(payload, dict) else {}