from __future__ import annotations

from dataclasses import dataclass
import re

from agents.intent import IntentType
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.scheduling import SchedulingAgent
from models.entities import Event, User
from services.calendar_text_parsing import (
    ParsedCancelRequest,
    _extract_timezone,
    _now_in_timezone,
    _parse_natural_cancel_request,
    _parse_natural_create,
    _parse_natural_update,
    _resolve_event_selection,
    _to_utc_datetime,
)
from services.google_calendar_oauth import GoogleCalendarOAuthManager


@dataclass(slots=True)
class ChatOutcome:
    reply_text: str


class WebChatService:
    def __init__(
        self,
        orchestrator: OrchestratorAgent,
        scheduling: SchedulingAgent,
        preferences: UserPreferencesAgent,
        notification: NotificationAgent,
        oauth_manager: GoogleCalendarOAuthManager | None,
        default_timezone: str,
    ) -> None:
        self.orchestrator = orchestrator
        self.scheduling = scheduling
        self.preferences = preferences
        self.notification = notification
        self.oauth_manager = oauth_manager
        self.default_timezone = default_timezone

    def onboarding_missing_message(self, user: User) -> str | None:
        timezone_configured = self.preferences.has_configured_timezone(user)
        if not timezone_configured:
            return "Debes completar onboarding: configura tu zona horaria (ej: America/Bogota) en tu perfil."
        if self.oauth_manager is not None:
            if not self.oauth_manager.is_configured():
                return "Google OAuth aún no está configurado en el entorno."
            if not self.oauth_manager.has_connection(user):
                return "Conecta Google Calendar para continuar usando la agenda sincronizada."
        return None

    def apply_preference_text(self, user: User, text: str) -> User | None:
        timezone_name = _extract_timezone(text, self.default_timezone)
        if not timezone_name:
            return None
        return self.preferences.update_timezone(user, timezone_name)

    def process_text(self, user: User, text: str) -> ChatOutcome:
        normalized = (text or "").strip()
        if not normalized:
            return ChatOutcome("Escribe un mensaje para que pueda ayudarte.")

        user_timezone = self.preferences.get_timezone(user)
        if self._contains_harmful_prompt(normalized):
            return ChatOutcome("No voy a ejecutar instrucciones peligrosas. Solo puedo ayudarte con agenda.")

        orchestration = self.orchestrator.handle(normalized)

        if orchestration.intent == IntentType.READ:
            events = self.scheduling.list_agenda(user.id or 0)
            return ChatOutcome(self.notification.build_agenda_message(events, user_timezone))

        if orchestration.intent == IntentType.CREATE:
            parsed = _parse_natural_create(normalized, reference_now=_now_in_timezone(user_timezone))
            if parsed is None:
                return ChatOutcome("No entendí la fecha/hora. Ejemplo: Agenda comité mañana a las 3pm")

            event = Event(
                id=None,
                user_id=user.id or 0,
                title=parsed.title,
                description=parsed.description,
                location=None,
                start_time=_to_utc_datetime(parsed.start_time, user_timezone),
                end_time=_to_utc_datetime(parsed.end_time, user_timezone),
                priority=orchestration.priority,
                source="web",
                timezone=user_timezone,
            )
            result = self.scheduling.create_event(event)
            return ChatOutcome(result.message)

        if orchestration.intent == IntentType.DELETE:
            events = self.scheduling.list_agenda(user.id or 0)
            request = _parse_natural_cancel_request(normalized)
            selected = _resolve_event_selection(request, events)
            if selected is None or isinstance(selected, list):
                return ChatOutcome("No pude identificar una cita única para cancelar. Incluye id o título más específico.")
            result = self.scheduling.cancel_event(selected.id or 0)
            return ChatOutcome(result.message)

        if orchestration.intent == IntentType.UPDATE:
            events = self.scheduling.list_agenda(user.id or 0)
            parsed = _parse_natural_update(normalized, reference_now=_now_in_timezone(user_timezone))
            if parsed is None:
                return ChatOutcome("No entendí el cambio. Ejemplo: mueve comité a mañana 18:00")
            selected = _resolve_event_selection(
                ParsedCancelRequest(event_id=parsed.event_id, title_query=parsed.title_query),
                events,
            )
            if selected is None or isinstance(selected, list):
                return ChatOutcome("No pude identificar una cita única para modificar.")
            updated = Event(
                id=selected.id,
                user_id=selected.user_id,
                title=selected.title,
                description=selected.description,
                location=selected.location,
                start_time=_to_utc_datetime(parsed.new_start, user_timezone),
                end_time=_to_utc_datetime(parsed.new_start, user_timezone) + (selected.end_time - selected.start_time),
                priority=selected.priority,
                status=selected.status,
                source="web",
                timezone=user_timezone,
                metadata=dict(selected.metadata),
            )
            result = self.scheduling.update_event(updated)
            return ChatOutcome(result.message)

        if orchestration.intent == IntentType.PREFERENCES:
            updated = self.apply_preference_text(user, normalized)
            if updated is None:
                return ChatOutcome("Para preferencias indícame una zona horaria válida, por ejemplo: America/Bogota")
            return ChatOutcome(f"Preferencias actualizadas. Zona horaria: {self.preferences.get_timezone(updated)}")

        return ChatOutcome("No entendí una acción concreta. Puedes pedirme crear, ver, modificar o cancelar citas.")

    def _contains_harmful_prompt(self, text: str) -> bool:
        patterns = [
            r"\brm\s+-rf\b",
            r"\bdrop\s+table\b",
            r"\battach\b",
            r"\bpragma\b",
            r"\bcmd\.exe\b",
            r"\bpowershell\b",
        ]
        lowered = text.lower()
        return any(re.search(pattern, lowered) for pattern in patterns)
