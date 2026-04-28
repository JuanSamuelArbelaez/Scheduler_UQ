from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models.entities import Event, Reminder


class NotificationAgent:
    name = "notification"

    def build_creation_message(self, event: Event, reminder: Reminder, timezone_name: str = "America/Bogota") -> str:
        local_start = self._to_timezone(event.start_time, timezone_name)
        local_remind = self._to_timezone(reminder.remind_at, timezone_name)
        return (
            f"Listo, agendé '{event.title}' para el {local_start:%d/%m/%Y a las %H:%M}. "
            f"Te enviaré un recordatorio el {local_remind:%d/%m/%Y a las %H:%M}."
        )

    def build_update_message(self, event: Event, timezone_name: str = "America/Bogota") -> str:
        local_start = self._to_timezone(event.start_time, timezone_name)
        return (
            f"Actualicé la cita '{event.title}'. Nueva fecha: {local_start:%d/%m/%Y a las %H:%M}."
        )

    def build_cancellation_message(self, event: Event, timezone_name: str = "America/Bogota") -> str:
        local_start = self._to_timezone(event.start_time, timezone_name)
        return f"Cancelé la cita '{event.title}' programada para el {local_start:%d/%m/%Y a las %H:%M}."

    def build_agenda_message(self, events: list[Event], timezone_name: str = "America/Bogota") -> str:
        if not events:
            return "📅 No tienes eventos programados."

        # Agrupar eventos por día
        from collections import defaultdict
        from datetime import date

        events_by_date = defaultdict(list)
        for event in events:
            local_start = self._to_timezone(event.start_time, timezone_name)
            event_date = local_start.date()
            events_by_date[event_date].append((local_start, event))

        # Ordenar fechas
        sorted_dates = sorted(events_by_date.keys())

        lines = ["📅 Tu agenda:"]
        for event_date in sorted_dates:
            day_events = events_by_date[event_date]
            day_events.sort(key=lambda x: x[0])  # Ordenar por hora

            # Nombre del día
            today = date.today()
            if event_date == today:
                day_name = "Hoy"
            elif event_date == today + timedelta(days=1):
                day_name = "Mañana"
            else:
                day_name = event_date.strftime("%A %d/%m")

            lines.append(f"\n🗓️ {day_name}:")

            for local_start, event in day_events:
                lines.append(f"⏰ {local_start:%H:%M}  {event.title}")

        return "\n".join(lines)

    def build_action_email_subject(self, action: str, event: Event) -> str:
        action_label = {
            "create": "Cita agendada",
            "update": "Cita actualizada",
            "cancel": "Cita cancelada",
        }.get(action, "Actualización de cita")
        return f"{action_label}: {event.title}"

    def build_action_email_body(self, action: str, event: Event, timezone_name: str) -> str:
        local_start = self._to_timezone(event.start_time, timezone_name)
        local_end = self._to_timezone(event.end_time, timezone_name)
        action_line = {
            "create": "Se agendó una nueva cita.",
            "update": "Se actualizó una cita.",
            "cancel": "Se canceló una cita.",
        }.get(action, "Hubo una actualización en tu agenda.")
        return (
            f"{action_line}\n\n"
            f"Título: {event.title}\n"
            f"Inicio: {local_start:%Y-%m-%d %H:%M}\n"
            f"Fin: {local_end:%Y-%m-%d %H:%M}\n"
            f"Zona horaria: {timezone_name}\n"
        )

    def build_reminder_email_subject(self, event: Event) -> str:
        return f"Recordatorio: {event.title}"

    def build_reminder_email_body(self, event: Event, timezone_name: str) -> str:
        local_start = self._to_timezone(event.start_time, timezone_name)
        return (
            "Este es un recordatorio de tu cita.\n\n"
            f"Título: {event.title}\n"
            f"Inicio: {local_start:%Y-%m-%d %H:%M}\n"
            f"Zona horaria: {timezone_name}\n"
        )

    def _to_timezone(self, dt: datetime, timezone_name: str) -> datetime:
        target_tz = self._safe_timezone(timezone_name)
        source_dt = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        return source_dt.astimezone(target_tz)

    def _safe_timezone(self, timezone_name: str) -> ZoneInfo | timezone:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            offset_map = {
                "America/Bogota": -5,
                "UTC": 0,
                "Europe/Madrid": 1,
            }
            offset_hours = offset_map.get(timezone_name, -5)
            return timezone(timedelta(hours=offset_hours))