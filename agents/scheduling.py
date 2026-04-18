from __future__ import annotations

from db.repositories import EventRepository, ReminderRepository
from models.entities import Event, Reminder
from services.scheduler_service import ActionResult, SchedulerService

from .notification import NotificationAgent


class SchedulingAgent:
    name = "scheduling"

    def __init__(self, events: EventRepository, reminders: ReminderRepository, default_reminder_minutes: int = 15) -> None:
        self.notification = NotificationAgent()
        self.service = SchedulerService(
            events,
            reminders,
            self.notification,
            default_reminder_minutes=default_reminder_minutes,
        )

    def create_event(self, event: Event) -> ActionResult:
        return self.service.create_event(event)

    def update_event(self, event: Event) -> ActionResult:
        return self.service.update_event(event)

    def cancel_event(self, event_id: int) -> ActionResult:
        return self.service.cancel_event(event_id)

    def list_agenda(self, user_id: int) -> list[Event]:
        return self.service.list_agenda(user_id)