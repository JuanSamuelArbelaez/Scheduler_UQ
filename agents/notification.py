from __future__ import annotations

from datetime import datetime

from models.entities import Event, Reminder


class NotificationAgent:
    name = "notification"

    def build_creation_message(self, event: Event, reminder: Reminder) -> str:
        return (
            f"Listo, agendé '{event.title}' para el {event.start_time:%d/%m/%Y a las %H:%M}. "
            f"Te enviaré un recordatorio el {reminder.remind_at:%d/%m/%Y a las %H:%M}."
        )

    def build_update_message(self, event: Event) -> str:
        return (
            f"Actualicé la cita '{event.title}'. Nueva fecha: {event.start_time:%d/%m/%Y a las %H:%M}."
        )

    def build_cancellation_message(self, event: Event) -> str:
        return f"Cancelé la cita '{event.title}' programada para el {event.start_time:%d/%m/%Y a las %H:%M}."

    def build_agenda_message(self, events: list[Event]) -> str:
        if not events:
            return "No encontré eventos en tu agenda."

        lines = ["Tu agenda actual es:"]
        for event in events:
            lines.append(f"- {event.title}: {event.start_time:%d/%m/%Y a las %H:%M}")
        return "\n".join(lines)