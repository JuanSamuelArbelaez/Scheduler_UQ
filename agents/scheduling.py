from __future__ import annotations

from db.repositories import EventRepository, ReminderRepository, UserRepository
from models.entities import Event, Reminder
from services.scheduler_service import ActionResult, SchedulerService
from services.email_service import EmailService
from services.telegram_service import TelegramService

from .notification import NotificationAgent


class SchedulingAgent:
    name = "scheduling"

    def __init__(
        self,
        events: EventRepository,
        reminders: ReminderRepository,
        users: UserRepository,
        email_service: EmailService,
        telegram_service: TelegramService | None = None,
        default_timezone: str = "America/Bogota",
        default_reminder_minutes: int = 15,
    ) -> None:
        self.notification = NotificationAgent()
        self.default_timezone = default_timezone
        self.service = SchedulerService(
            events,
            reminders,
            users,
            self.notification,
            email_service,
            telegram_service,
            default_timezone=default_timezone,
            default_reminder_minutes=default_reminder_minutes,
        )

    def create_event(self, event: Event) -> ActionResult:
        return self.service.create_event_with_conflict_resolution(event)

    def update_event(self, event: Event) -> ActionResult:
        return self.service.update_event(event)

    def cancel_event(self, event_id: int) -> ActionResult:
        return self.service.cancel_event(event_id)

    def list_agenda(self, user_id: int) -> list[Event]:
        return self.service.list_agenda(user_id)

    def dispatch_due_reminders(self) -> int:
        return self.service.dispatch_due_reminders()