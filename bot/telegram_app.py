from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Final
import unicodedata

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from agents.history import HistoryAgent
from agents.intent import IntentType
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.scheduling import SchedulingAgent
from agents.notification import NotificationAgent
from models.entities import Event, User


USAGE_CREATE: Final[str] = "Uso: /create titulo | YYYY-MM-DDTHH:MM:SS | YYYY-MM-DDTHH:MM:SS | descripcion opcional"
USAGE_UPDATE: Final[str] = "Uso: /update id | titulo | YYYY-MM-DDTHH:MM:SS | YYYY-MM-DDTHH:MM:SS | descripcion opcional"
USAGE_CANCEL: Final[str] = "Uso: /cancel id"


@dataclass(slots=True)
class TelegramDependencies:
    orchestrator: OrchestratorAgent
    scheduling: SchedulingAgent
    preferences: UserPreferencesAgent
    notification: NotificationAgent
    history: HistoryAgent


def build_application(token: str, dependencies: TelegramDependencies) -> Application:
    application = ApplicationBuilder().token(token).concurrent_updates(False).build()
    application.bot_data["dependencies"] = dependencies

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("agenda", agenda_command))
    application.add_handler(CommandHandler("create", create_command))
    application.add_handler(CommandHandler("update", update_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    application.add_error_handler(error_handler)
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Scheduler listo. Puedes usar /agenda, /create, /update y /cancel. "
        "Si envias texto libre, intentare clasificarlo con el Orchestrator."
    )
    await update.effective_message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Comandos disponibles:\n"
        f"{USAGE_CREATE}\n"
        f"{USAGE_UPDATE}\n"
        f"{USAGE_CANCEL}\n"
        "/agenda"
    )


async def agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    events = dependencies.scheduling.list_agenda(user.id or 0)
    await update.effective_message.reply_text(dependencies.notification.build_agenda_message(events))


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    payload = " ".join(context.args)
    parts = _split_payload(payload, 4)
    if parts is None:
        await update.effective_message.reply_text(USAGE_CREATE)
        return

    try:
        title, start_raw, end_raw, description = parts
        event = Event(
            id=None,
            user_id=user.id or 0,
            title=title,
            description=description,
            location=None,
            start_time=_parse_datetime(start_raw),
            end_time=_parse_datetime(end_raw),
            priority=3,
        )
        result = dependencies.scheduling.create_event(event)
        dependencies.history.record(user.id or 0, "create", result.event.id if result.event else None, result.message)
        await update.effective_message.reply_text(result.message)
    except ValueError as error:
        await update.effective_message.reply_text(f"No pude crear la cita: {error}")


async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    payload = " ".join(context.args)
    parts = _split_payload(payload, 5)
    if parts is None:
        await update.effective_message.reply_text(USAGE_UPDATE)
        return

    try:
        event_id_raw, title, start_raw, end_raw, description = parts
        event = Event(
            id=int(event_id_raw),
            user_id=user.id or 0,
            title=title,
            description=description,
            location=None,
            start_time=_parse_datetime(start_raw),
            end_time=_parse_datetime(end_raw),
            priority=3,
        )
        result = dependencies.scheduling.update_event(event)
        dependencies.history.record(user.id or 0, "update", result.event.id if result.event else None, result.message)
        await update.effective_message.reply_text(result.message)
    except ValueError as error:
        await update.effective_message.reply_text(f"No pude actualizar la cita: {error}")
    except LookupError as error:
        await update.effective_message.reply_text(f"No pude actualizar la cita: {error}")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    payload = " ".join(context.args).strip()
    if not payload.isdigit():
        await update.effective_message.reply_text(USAGE_CANCEL)
        return

    try:
        result = dependencies.scheduling.cancel_event(int(payload))
        dependencies.history.record(user.id or 0, "cancel", result.event.id if result.event else None, result.message)
        await update.effective_message.reply_text(result.message)
    except ValueError as error:
        await update.effective_message.reply_text(f"No pude cancelar la cita: {error}")
    except LookupError as error:
        await update.effective_message.reply_text(f"No pude cancelar la cita: {error}")


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return

    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    text = message.text or ""

    if _looks_like_confirmation(text):
        if await _handle_confirmation(update, context, dependencies, user):
            return

    orchestration = dependencies.orchestrator.handle(text)

    if orchestration.intent == IntentType.READ:
        events = dependencies.scheduling.list_agenda(user.id or 0)
        await message.reply_text(dependencies.notification.build_agenda_message(events))
        return

    if orchestration.intent == IntentType.CREATE:
        parsed_create = _parse_natural_create(text)
        if parsed_create is None:
            await message.reply_text(
                "Puedo crearla si me indicas fecha y hora. Ejemplo: Agenda reunion con Ana mañana a las 15:30"
            )
            return

        pending = {
            "type": "create",
            "title": parsed_create.title,
            "start": parsed_create.start_time.isoformat(),
            "end": parsed_create.end_time.isoformat(),
            "description": parsed_create.description,
        }
        context.user_data["pending_action"] = pending
        await message.reply_text(
            f"¿Confirmas crear la cita '{parsed_create.title}' para el {parsed_create.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.intent == IntentType.DELETE:
        parsed_cancel = _parse_natural_cancel(text, dependencies.scheduling.list_agenda(user.id or 0))
        if parsed_cancel is None:
            await message.reply_text(
                "Para cancelar por texto libre, indica el id o el titulo aproximado de la cita."
            )
            return

        context.user_data["pending_action"] = {"type": "cancel", "event_id": parsed_cancel.id}
        await message.reply_text(
            f"¿Confirmas cancelar la cita '{parsed_cancel.title}' del {parsed_cancel.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.intent == IntentType.UPDATE:
        parsed_update = _parse_natural_update(text)
        if parsed_update is None:
            await message.reply_text(
                "Para modificar por texto libre necesito el id y la nueva fecha/hora. Ejemplo: mueve la cita 3 a mañana 18:00"
            )
            return

        event = dependencies.scheduling.service.events.get_by_id(parsed_update.event_id)
        duration = event.end_time - event.start_time
        new_start = parsed_update.new_start
        new_end = new_start + duration
        context.user_data["pending_action"] = {
            "type": "update",
            "event_id": event.id,
            "title": event.title,
            "description": event.description,
            "location": event.location,
            "start": new_start.isoformat(),
            "end": new_end.isoformat(),
            "priority": event.priority,
        }
        await message.reply_text(
            f"¿Confirmas mover la cita '{event.title}' al {new_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.requires_confirmation:
        await message.reply_text(
            "Entendí tu solicitud. Puedo procesarla en lenguaje natural si incluye fecha y hora. "
            "Si prefieres, usa /help para el formato guiado."
        )
        return

    await message.reply_text(
        "Recibi tu mensaje, pero aun no tengo suficientes datos para ejecutar una accion concreta."
    )


def _dependencies(context: ContextTypes.DEFAULT_TYPE) -> TelegramDependencies:
    return context.application.bot_data["dependencies"]


def _ensure_user(update: Update, dependencies: TelegramDependencies) -> User:
    chat = update.effective_chat
    if chat is None:
        raise ValueError("Chat not available")

    telegram_chat_id = str(chat.id)
    try:
        user = dependencies.preferences.get_user(telegram_chat_id)
    except LookupError:
        user = dependencies.preferences.upsert_user(User(id=None, telegram_chat_id=telegram_chat_id))

    if user.id is None:
        raise ValueError("User persistence failed")
    return user


def _split_payload(payload: str, expected_parts: int) -> list[str] | None:
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) != expected_parts or any(not part for part in parts[:expected_parts - 1]):
        return None
    return parts


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = "Ocurrió un error inesperado procesando tu solicitud. Inténtalo de nuevo."
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text(message)


@dataclass(slots=True)
class ParsedCreateRequest:
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None


@dataclass(slots=True)
class ParsedUpdateRequest:
    event_id: int
    new_start: datetime


def _parse_natural_create(text: str) -> ParsedCreateRequest | None:
    normalized = _normalize_text(text)
    day_match = re.search(
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+(?:a\s+las\s+|a\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
        normalized,
    )
    if day_match is None:
        day_match = re.search(
            r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<date>\d{4}-\d{2}-\d{2})\s+(?:a\s+las\s+|a\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
            normalized,
        )

    if day_match is None:
        return None

    title = day_match.group("title").strip(" .,")
    if not title:
        return None

    event_date = _resolve_date(day_match.groupdict())
    event_time = _resolve_time(day_match.group("hour"), day_match.group("minute"), day_match.group("ampm"))
    start_time = datetime.combine(event_date, event_time)
    return ParsedCreateRequest(title=title, start_time=start_time, end_time=start_time + timedelta(hours=1), description=None)


def _parse_natural_cancel(text: str, events: list[Event]) -> Event | None:
    id_match = re.search(r"\b(\d+)\b", text)
    if id_match is not None:
        event_id = int(id_match.group(1))
        for event in events:
            if event.id == event_id and event.status != "cancelled":
                return event

    normalized = _normalize_text(text)
    keywords = {"cancela", "cancelar", "elimina", "borrar", "borra", "anula", "la", "el", "mi", "cita", "evento"}
    candidate_tokens = [token for token in re.split(r"\W+", normalized) if token and token not in keywords]
    if not candidate_tokens:
        return None

    best_event: Event | None = None
    best_score = 0
    for event in events:
        if event.status == "cancelled":
            continue
        title_tokens = set(re.split(r"\W+", _normalize_text(event.title)))
        score = sum(1 for token in candidate_tokens if token in title_tokens)
        if score > best_score:
            best_score = score
            best_event = event
    return best_event if best_score > 0 else None


def _parse_natural_update(text: str) -> ParsedUpdateRequest | None:
    normalized = _normalize_text(text)
    id_match = re.search(r"\b(\d+)\b", normalized)
    if id_match is None:
        return None

    timing_matches = list(re.finditer(
        r"(?:a|para)\s+(?:(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
        normalized,
    ))
    if not timing_matches:
        return None
    timing_match = timing_matches[-1]

    event_date = _resolve_date(timing_match.groupdict())
    event_time = _resolve_time(timing_match.group("hour"), timing_match.group("minute"), timing_match.group("ampm"))
    return ParsedUpdateRequest(event_id=int(id_match.group(1)), new_start=datetime.combine(event_date, event_time))


def _resolve_date(values: dict[str, str | None]) -> date:
    today = datetime.now().date()
    if values.get("date"):
        return date.fromisoformat(values["date"] or "")

    day_name = _normalize_text(values.get("day") or "")
    if day_name in {"hoy"}:
        return today
    if day_name in {"manana", "mañana"}:
        return today + timedelta(days=1)

    weekday_map = {
        "lunes": 0,
        "martes": 1,
        "miercoles": 2,
        "miércoles": 2,
        "jueves": 3,
        "viernes": 4,
        "sabado": 5,
        "sábado": 5,
        "domingo": 6,
    }
    if day_name not in weekday_map:
        return today

    target_weekday = weekday_map[day_name]
    current_weekday = today.weekday()
    delta = (target_weekday - current_weekday) % 7
    return today + timedelta(days=delta)


def _resolve_time(hour_raw: str | None, minute_raw: str | None, ampm_raw: str | None) -> time:
    hour = int(hour_raw or "0")
    minute = int(minute_raw or "0")
    ampm = (ampm_raw or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return time(hour=hour, minute=minute)


def _looks_like_confirmation(text: str) -> bool:
    normalized = _normalize_text(text)
    return normalized in {"si", "sí", "s", "ok", "confirmo", "dale", "yes", "no", "cancelar"}


def _is_positive_confirmation(text: str) -> bool:
    return _normalize_text(text) in {"si", "sí", "s", "ok", "confirmo", "dale", "yes"}


async def _handle_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    dependencies: TelegramDependencies,
    user: User,
) -> bool:
    pending = context.user_data.get("pending_action")
    if pending is None:
        return False

    message = update.effective_message
    if message is None:
        return True

    if not _is_positive_confirmation(message.text or ""):
        context.user_data.pop("pending_action", None)
        await message.reply_text("Acción cancelada. No se realizaron cambios.")
        return True

    action_type = pending.get("type")
    try:
        if action_type == "create":
            event = Event(
                id=None,
                user_id=user.id or 0,
                title=str(pending["title"]),
                description=str(pending.get("description") or "") or None,
                location=None,
                start_time=datetime.fromisoformat(str(pending["start"])),
                end_time=datetime.fromisoformat(str(pending["end"])),
                priority=3,
            )
            result = dependencies.scheduling.create_event(event)
            dependencies.history.record(user.id or 0, "create", result.event.id if result.event else None, result.message)
            await message.reply_text(result.message)
        elif action_type == "cancel":
            result = dependencies.scheduling.cancel_event(int(pending["event_id"]))
            dependencies.history.record(user.id or 0, "cancel", result.event.id if result.event else None, result.message)
            await message.reply_text(result.message)
        elif action_type == "update":
            event = Event(
                id=int(pending["event_id"]),
                user_id=user.id or 0,
                title=str(pending["title"]),
                description=str(pending.get("description") or "") or None,
                location=str(pending.get("location") or "") or None,
                start_time=datetime.fromisoformat(str(pending["start"])),
                end_time=datetime.fromisoformat(str(pending["end"])),
                priority=int(pending.get("priority") or 3),
            )
            result = dependencies.scheduling.update_event(event)
            dependencies.history.record(user.id or 0, "update", result.event.id if result.event else None, result.message)
            await message.reply_text(result.message)
        else:
            await message.reply_text("No encontré una acción pendiente válida.")
    except (ValueError, LookupError) as error:
        await message.reply_text(f"No pude completar la acción: {error}")
    finally:
        context.user_data.pop("pending_action", None)
    return True


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(without_marks.split())