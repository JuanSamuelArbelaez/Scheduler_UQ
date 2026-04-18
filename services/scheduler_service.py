from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from db.repositories import EventRepository, ReminderRepository
from models.entities import Event, Reminder
from agents.notification import NotificationAgent


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
        notification: NotificationAgent,
        default_reminder_minutes: int = 15,
    ) -> None:
        self.events = events
        self.reminders = reminders
        self.notification = notification
        self.default_reminder_minutes = default_reminder_minutes

    def create_event(self, event: Event) -> ActionResult:
        self._validate_event_text(event)
        self._validate_event_window(event.start_time, event.end_time)
        self._validate_not_in_past(event.start_time)
        self._validate_no_overlap(event.user_id, event.start_time, event.end_time)

        created_event = self.events.create(event)
        reminder = self._build_default_reminder(created_event)
        created_reminder = self.reminders.create(reminder)
        message = self.notification.build_creation_message(created_event, created_reminder)
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
        message = self.notification.build_update_message(updated_event)
        return ActionResult(updated_event, None, message)

    def cancel_event(self, event_id: int) -> ActionResult:
        existing_event = self.events.get_by_id(event_id)
        self._validate_not_in_past(existing_event.start_time)
        self.events.cancel(event_id)
        message = self.notification.build_cancellation_message(existing_event)
        return ActionResult(existing_event, None, message)

    def list_agenda(self, user_id: int) -> list[Event]:
        return self.events.list_by_user(user_id)

    def _build_default_reminder(self, event: Event) -> Reminder:
        remind_at = event.start_time - timedelta(minutes=self.default_reminder_minutes)
        return Reminder(id=None, event_id=event.id or 0, remind_at=remind_at)

    def _validate_event_window(self, start_time: datetime, end_time: datetime) -> None:
        if end_time <= start_time:
            raise ValueError("Event end_time must be after start_time")

    def _validate_not_in_past(self, start_time: datetime) -> None:
        now = datetime.now(start_time.tzinfo) if start_time.tzinfo is not None else datetime.now()
        if start_time < now:
            raise ValueError("Past events cannot be modified or created")

    def _validate_no_overlap(self, user_id: int, start_time: datetime, end_time: datetime, exclude_event_id: int | None = None) -> None:
        if self.events.has_overlap(user_id, start_time, end_time, exclude_event_id=exclude_event_id):
            raise ValueError("The event overlaps with an existing event")

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