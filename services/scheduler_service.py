from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from db.repositories import EventRepository, ReminderRepository, UserRepository
from models.entities import Event, Reminder
from agents.notification import NotificationAgent
from services.email_service import EmailService
from services.calendar_sync_service import CalendarSyncService
from agents.history import HistoryAgent


@dataclass(slots=True)
class ActionResult:
    event: Event | None
    reminder: Reminder | None
    message: str


class SchedulerService:
    def __init__(
        self,
        events: EventRepository,
        reminders: ReminderRepository,
        users: UserRepository,
        notification: NotificationAgent,
        email_service: EmailService,
        history: HistoryAgent | None = None,
        calendar_sync: CalendarSyncService | None = None,
        default_timezone: str = "America/Bogota",
        default_reminder_minutes: int = 15,
    ) -> None:
        self.events = events
        self.reminders = reminders
        self.users = users
        self.notification = notification
        self.email_service = email_service
        self.history = history
        self.calendar_sync = calendar_sync
        self.default_timezone = default_timezone
        self.default_reminder_minutes = default_reminder_minutes

    def create_event_with_conflict_resolution(self, event: Event) -> ActionResult:
        """Crea evento manejando conflictos automáticamente"""
        self._validate_event_text(event)
        self._validate_event_window(event.start_time, event.end_time)
        self._validate_not_in_past(event.start_time)

        # Verificar conflictos
        overlapping_events = self.events.get_overlapping(event.user_id, event.start_time, event.end_time)

        if overlapping_events:
            # Encontrar el primer espacio libre después del conflicto
            duration = event.end_time - event.start_time
            free_slots = self.find_conflict_free_slots(
                event.user_id,
                duration_hours=duration.total_seconds() / 3600,
                preferred_start=event.start_time
            )

            if free_slots:
                # Mover automáticamente al primer espacio libre
                new_start = free_slots[0]
                new_end = new_start + duration
                event.start_time = new_start
                event.end_time = new_end

                # Crear el evento movido
                created_event = self.events.create(event)
                reminder = self._build_default_reminder(created_event)
                created_reminder = self.reminders.create(reminder)
                timezone_name = self._get_user_timezone(created_event.user_id)

                conflict_titles = [f"'{e.title}'" for e in overlapping_events]
                message = (
                    f"⚠️ Conflicto detectado con {', '.join(conflict_titles)}. "
                    f"Agendé '{created_event.title}' en el siguiente espacio disponible: "
                    f"{self._to_user_timezone(new_start, timezone_name):%d/%m %H:%M}."
                )

                sync_message = self._sync_calendar_message("create", created_event)
                if sync_message:
                    message = f"{message} {sync_message}"

                self._notify_action_email("create", created_event, timezone_name)
                return ActionResult(created_event, created_reminder, message)
            else:
                # No hay espacios libres
                conflict_titles = [f"'{e.title}'" for e in overlapping_events]
                raise ValueError(f"No se puede agendar: conflicto con {', '.join(conflict_titles)} y no hay espacios libres")

        # Sin conflictos, crear normalmente
        created_event = self.events.create(event)
        reminder = self._build_default_reminder(created_event)
        created_reminder = self.reminders.create(reminder)
        timezone_name = self._get_user_timezone(created_event.user_id)
        message = self.notification.build_creation_message(created_event, created_reminder, timezone_name)
        sync_message = self._sync_calendar_message("create", created_event)
        if sync_message:
            message = f"{message} {sync_message}"
        self._notify_action_email("create", created_event, timezone_name)
        return ActionResult(created_event, created_reminder, message)

    def update_event(self, event: Event) -> ActionResult:
        if event.id is None:
            raise ValueError("Event id is required")

        self._validate_event_text(event)
        existing_event = self.events.get_by_id(event.id)
        self._validate_not_in_past(existing_event.start_time)
        self._validate_event_window(event.start_time, event.end_time)
        self._validate_no_overlap(event.user_id, event.start_time, event.end_time, exclude_event_id=event.id)
        updated_event = self.events.update(event)
        timezone_name = self._get_user_timezone(updated_event.user_id)
        message = self.notification.build_update_message(updated_event, timezone_name)
        sync_message = self._sync_calendar_message("update", updated_event)
        if sync_message:
            message = f"{message} {sync_message}"
        self._notify_action_email("update", updated_event, timezone_name)
        return ActionResult(updated_event, None, message)

    def cancel_event(self, event_id: int) -> ActionResult:
        existing_event = self.events.get_by_id(event_id)
        self._validate_not_in_past(existing_event.start_time)
        self.events.cancel(event_id)
        timezone_name = self._get_user_timezone(existing_event.user_id)
        message = self.notification.build_cancellation_message(existing_event, timezone_name)
        sync_message = self._sync_calendar_message("delete", existing_event)
        if sync_message:
            message = f"{message} {sync_message}"
        self._notify_action_email("cancel", existing_event, timezone_name)
        return ActionResult(existing_event, None, message)

    def list_agenda(self, user_id: int) -> list[Event]:
        return self.events.list_by_user(user_id)

    def _build_default_reminder(self, event: Event) -> Reminder:
        remind_at = event.start_time - timedelta(minutes=self.default_reminder_minutes)
        return Reminder(id=None, event_id=event.id or 0, remind_at=remind_at, channel="both")

    def dispatch_due_reminders(self, now_utc: datetime | None = None) -> int:
        current_time = now_utc or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)

        due_reminders = self.reminders.list_due_unsent(current_time)
        sent_count = 0

        for row in due_reminders:
            reminder_id = int(row["reminder_id"])
            channel = str(row.get("reminder_channel") or "email")  # Default to email for backwards compatibility
            event_title = str(row["event_title"])
            event_start_time = row["event_start_time"]
            user_email = str(row.get("user_email") or "").strip()
            user_preferences = row.get("user_preferences") or {}
            timezone_name = str(user_preferences.get("timezone") or self.default_timezone)

            # Formatear la hora del evento en la zona horaria del usuario
            if event_start_time.tzinfo is None:
                event_start_time = event_start_time.replace(tzinfo=UTC)

            try:
                user_tz = ZoneInfo(timezone_name)
                local_time = event_start_time.astimezone(user_tz)
                time_str = local_time.strftime("%d/%m/%Y %H:%M")
            except (ZoneInfoNotFoundError, Exception):
                # Fallback si la zona horaria no es válida
                time_str = event_start_time.strftime("%d/%m/%Y %H:%M UTC")

            sent = False

            # Enviar por email si el canal lo requiere
            if channel in ["email", "both"] and user_email:
                subject = self.notification.build_reminder_email_subject(
                    Event(id=0, user_id=0, title=event_title, start_time=event_start_time, end_time=event_start_time)
                )
                body = self.notification.build_reminder_email_body(
                    Event(id=0, user_id=0, title=event_title, start_time=event_start_time, end_time=event_start_time),
                    timezone_name
                )
                sent = self.email_service.send_email(user_email, subject, body) or sent

            # Marcar como enviado si al menos un canal tuvo éxito
            delivery_status = "sent" if sent else "failed"
            self.reminders.mark_delivery(reminder_id, delivery_status)
            if sent:
                sent_count += 1

        return sent_count

    def _validate_event_window(self, start_time: datetime, end_time: datetime) -> None:
        if end_time <= start_time:
            raise ValueError("Event end_time must be after start_time")

    def _validate_not_in_past(self, start_time: datetime) -> None:
        if start_time.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(start_time.tzinfo)
        if start_time < now:
            raise ValueError("Past events cannot be modified or created")

    def _validate_no_overlap(self, user_id: int, start_time: datetime, end_time: datetime, exclude_event_id: int | None = None) -> None:
        """Valida que no haya solapamiento con eventos existentes"""
        overlapping_events = self.events.get_overlapping(user_id, start_time, end_time, exclude_event_id)

        if not overlapping_events:
            return

        # Si hay solapamiento, construir mensaje inteligente
        conflict_messages = []
        for event in overlapping_events:
            local_start = self._to_user_timezone(event.start_time, self._get_user_timezone(user_id))
            local_end = self._to_user_timezone(event.end_time, self._get_user_timezone(user_id))
            conflict_messages.append(
                f"'{event.title}' ({local_start:%d/%m %H:%M}-{local_end:%H:%M})"
            )

        conflict_text = ", ".join(conflict_messages)
        raise ValueError(f"Conflicto con evento(s) existente(s): {conflict_text}")

    def find_conflict_free_slots(self, user_id: int, duration_hours: int = 1, preferred_start: datetime | None = None) -> list[datetime]:
        """Encuentra espacios libres para un evento de duración específica"""
        if preferred_start is None:
            preferred_start = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)

        # Buscar en las próximas 24 horas
        slots = []
        current = preferred_start

        for _ in range(24):  # Máximo 24 slots
            end_time = current + timedelta(hours=duration_hours)
            if not self.events.has_overlap(user_id, current, end_time):
                slots.append(current)
                if len(slots) >= 3:  # Máximo 3 sugerencias
                    break
            current += timedelta(hours=1)

        return slots

    def _to_user_timezone(self, dt: datetime, timezone_name: str) -> datetime:
        """Convierte datetime a zona horaria del usuario"""
        from agents.notification import NotificationAgent
        notification = NotificationAgent()
        return notification._to_timezone(dt, timezone_name)

    def _validate_event_text(self, event: Event) -> None:
        self._validate_text_field("title", event.title, max_length=120)
        self._validate_text_field("description", event.description, max_length=500)
        self._validate_text_field("location", event.location, max_length=180)

    def _validate_text_field(self, field_name: str, value: str | None, max_length: int) -> None:
        if value is None:
            return

        clean_value = value.strip()
        if not clean_value:
            if field_name == "title":
                raise ValueError("Event title cannot be empty")
            return

        if len(clean_value) > max_length:
            raise ValueError(f"{field_name} exceeds maximum length")

        suspicious_pattern = re.compile(
            r"(;|--|/\*|\*/|\bdrop\b|\battach\b|\bpragma\b|\bdelete\s+from\b|\brm\s+-rf\b|\bpowershell\b|\bcmd\.exe\b)",
            flags=re.IGNORECASE,
        )
        if suspicious_pattern.search(clean_value):
            raise ValueError(f"{field_name} contains disallowed content")

    def _get_user_timezone(self, user_id: int) -> str:
        try:
            user = self.users.get_by_id(user_id)
        except LookupError:
            return self.default_timezone
        timezone_name = str(user.preferences.get("timezone") or "").strip()
        return timezone_name or self.default_timezone

    def _notify_action_email(self, action: str, event: Event, timezone_name: str) -> None:
        try:
            user = self.users.get_by_id(event.user_id)
        except LookupError:
            return

        email = (user.email or "").strip()
        if not email:
            return

        subject = self.notification.build_action_email_subject(action, event)
        body = self.notification.build_action_email_body(action, event, timezone_name)
        self.email_service.send_email(email, subject, body)

    def _sync_calendar_message(self, action: str, event: Event) -> str:
        if self.calendar_sync is None:
            return ""

        try:
            user = self.users.get_by_id(event.user_id)
        except LookupError:
            return ""

        if action == "create":
            outcome = self.calendar_sync.sync_create(event, user)
        elif action == "update":
            outcome = self.calendar_sync.sync_update(event, user)
        elif action == "delete":
            outcome = self.calendar_sync.sync_delete(event, user)
        else:
            return ""

        if outcome.success:
            if action in {"create", "update"}:
                self._attach_external_calendar_id(event, outcome.result.external_id)
            return "Sincronización Google Calendar aplicada correctamente."
        return "Sincronización Google Calendar no disponible; mantuve el guardado local."

    def _attach_external_calendar_id(self, event: Event, external_id: str | None) -> None:
        if not external_id or event.id is None:
            return

        metadata = dict(event.metadata or {})
        if metadata.get("google_calendar_event_id") == external_id:
            return

        metadata["google_calendar_event_id"] = external_id
        event.metadata = metadata
        self.events.update(event)