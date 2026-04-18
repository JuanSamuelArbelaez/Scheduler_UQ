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
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.scheduling import SchedulingAgent
from models.entities import Event, User
from services.local_llm import LocalLlmDecision, LocalOllamaClient


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
    llm_client: LocalOllamaClient | None = None


@dataclass(slots=True)
class ParsedCreateRequest:
    title: str
    start_time: datetime
    end_time: datetime
    description: str | None


@dataclass(slots=True)
class ParsedUpdateRequest:
    event_id: int | None
    title_query: str | None
    new_start: datetime


@dataclass(slots=True)
class ParsedCancelRequest:
    event_id: int | None
    title_query: str | None


def build_application(token: str, dependencies: TelegramDependencies) -> Application:
    application = ApplicationBuilder().token(token).concurrent_updates(False).build()
    application.bot_data["dependencies"] = dependencies

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("agenda", agenda_command))
    application.add_handler(CommandHandler("create", create_command))
    application.add_handler(CommandHandler("update", update_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    application.add_error_handler(error_handler)
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Scheduler listo. Puedes usar /agenda, /create, /update, /cancel y /health. "
        "Si envias texto libre, intentare clasificarlo con el Orchestrator."
    )
    await update.effective_message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Comandos disponibles:\n"
        f"{USAGE_CREATE}\n"
        f"{USAGE_UPDATE}\n"
        f"{USAGE_CANCEL}\n"
        "/agenda\n"
        "/health"
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    db_status = "ok"
    try:
        dependencies.scheduling.service.events.connection.execute("SELECT 1").fetchone()
    except Exception:
        db_status = "error"

    await update.effective_message.reply_text(
        f"Health check interno:\n- db: {db_status}\n- bot: running"
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

    if await _handle_disambiguation_selection(update, context, dependencies, user):
        return

    if _looks_like_confirmation(text):
        if await _handle_confirmation(update, context, dependencies, user):
            return

    if _contains_harmful_prompt(text):
        await message.reply_text(
            "No voy a ejecutar instrucciones peligrosas. Puedo ayudarte con operaciones de agenda y recordatorios."
        )
        return

    if await _attempt_llm_assisted_flow(update, context, dependencies, user, text):
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
                "Puedo crearla si me indicas fecha y hora validas. Ejemplo: Programa reunion con Ana manana a las 15:30"
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

    events = dependencies.scheduling.list_agenda(user.id or 0)

    if orchestration.intent == IntentType.DELETE:
        parsed_cancel = _parse_natural_cancel_request(text)
        selected_event = _resolve_event_selection(parsed_cancel, events)
        if selected_event is None:
            await message.reply_text(
                "Para cancelar por texto libre, indica el id o un titulo aproximado de la cita."
            )
            return
        if isinstance(selected_event, list):
            context.user_data["pending_disambiguation"] = {
                "type": "cancel",
                "event_ids": [event.id for event in selected_event if event.id is not None],
            }
            await message.reply_text(_build_disambiguation_prompt("cancelar", selected_event))
            return

        context.user_data["pending_action"] = {"type": "cancel", "event_id": selected_event.id}
        await message.reply_text(
            f"¿Confirmas cancelar la cita '{selected_event.title}' del {selected_event.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.intent == IntentType.UPDATE:
        parsed_update = _parse_natural_update(text)
        if parsed_update is None:
            await message.reply_text(
                "Para modificar por texto libre necesito fecha/hora y el id o titulo de la cita. Ejemplo: mueve reunion equipo a manana 18:00"
            )
            return

        selected_event = _resolve_event_selection(
            ParsedCancelRequest(event_id=parsed_update.event_id, title_query=parsed_update.title_query),
            events,
        )
        if selected_event is None:
            await message.reply_text("No encontré una cita para modificar con esos datos.")
            return
        if isinstance(selected_event, list):
            context.user_data["pending_disambiguation"] = {
                "type": "update",
                "event_ids": [event.id for event in selected_event if event.id is not None],
                "new_start": parsed_update.new_start.isoformat(),
            }
            await message.reply_text(_build_disambiguation_prompt("modificar", selected_event))
            return

        _prepare_pending_update(context, selected_event, parsed_update.new_start)
        await message.reply_text(
            f"¿Confirmas mover la cita '{selected_event.title}' al {parsed_update.new_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.requires_confirmation:
        await message.reply_text(
            "Entendí tu solicitud. Puedo procesarla en lenguaje natural si incluye fecha y hora. "
            "Si prefieres, usa /help para el formato guiado."
        )
        return

    await message.reply_text(
        "Recibí tu mensaje, pero aún no tengo suficientes datos para ejecutar una acción concreta."
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = "Ocurrió un error inesperado procesando tu solicitud. Inténtalo de nuevo."
    if isinstance(update, Update) and update.effective_message is not None:
        await update.effective_message.reply_text(message)


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
    if len(parts) != expected_parts or any(not part for part in parts[: expected_parts - 1]):
        return None
    return parts


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


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

    try:
        event_date = _resolve_date(day_match.groupdict())
        event_time = _resolve_time(day_match.group("hour"), day_match.group("minute"), day_match.group("ampm"))
    except ValueError:
        return None

    start_time = datetime.combine(event_date, event_time)
    return ParsedCreateRequest(title=title, start_time=start_time, end_time=start_time + timedelta(hours=1), description=None)


def _parse_natural_cancel_request(text: str) -> ParsedCancelRequest | None:
    normalized = _normalize_text(text)
    id_match = re.search(r"\b(\d+)\b", normalized)
    if id_match is not None:
        return ParsedCancelRequest(event_id=int(id_match.group(1)), title_query=None)

    title_match = re.search(r"(?:cancela|cancelar|elimina|borra|anula)\s+(?P<title>.+)$", normalized)
    if title_match is None:
        return None

    title_query = _clean_title_query(title_match.group("title"))
    if not title_query:
        return None
    return ParsedCancelRequest(event_id=None, title_query=title_query)


def _parse_natural_update(text: str) -> ParsedUpdateRequest | None:
    normalized = _normalize_text(text)
    timing_matches = list(
        re.finditer(
            r"(?:a|para)\s+(?:(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?",
            normalized,
        )
    )
    if not timing_matches:
        return None

    timing_match = timing_matches[-1]
    try:
        event_date = _resolve_date(timing_match.groupdict())
        event_time = _resolve_time(timing_match.group("hour"), timing_match.group("minute"), timing_match.group("ampm"))
    except ValueError:
        return None

    before_timing = normalized[: timing_match.start()].strip()
    id_match = re.search(r"\b(\d+)\b", before_timing)
    if id_match is not None:
        return ParsedUpdateRequest(
            event_id=int(id_match.group(1)),
            title_query=None,
            new_start=datetime.combine(event_date, event_time),
        )

    title_match = re.search(r"(?:mueve|cambia|modifica|reprograma|actualiza)\s+(?P<title>.+)$", before_timing)
    if title_match is None:
        return None

    title_query = _clean_title_query(title_match.group("title"))
    if not title_query:
        return None
    return ParsedUpdateRequest(
        event_id=None,
        title_query=title_query,
        new_start=datetime.combine(event_date, event_time),
    )


def _resolve_event_selection(request: ParsedCancelRequest | None, events: list[Event]) -> Event | list[Event] | None:
    if request is None:
        return None

    if request.event_id is not None:
        for event in events:
            if event.id == request.event_id and event.status != "cancelled":
                return event
        return None

    if not request.title_query:
        return None

    candidates = _find_event_candidates(request.title_query, events)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return candidates[:5]


def _find_event_candidates(query: str, events: list[Event]) -> list[Event]:
    query_tokens = [token for token in re.split(r"\W+", _normalize_text(query)) if token]
    if not query_tokens:
        return []

    scored: list[tuple[int, Event]] = []
    for event in events:
        if event.status == "cancelled":
            continue
        title_tokens = set(re.split(r"\W+", _normalize_text(event.title)))
        score = sum(1 for token in query_tokens if token in title_tokens)
        if score > 0:
            scored.append((score, event))

    scored.sort(key=lambda item: (-item[0], item[1].start_time))
    return [event for _, event in scored]


def _clean_title_query(text: str) -> str:
    normalized = _normalize_text(text)
    cleaned = re.sub(r"\b(la|el|mi|cita|evento|de|del)\b", " ", normalized)
    return " ".join(cleaned.split())


def _build_disambiguation_prompt(action: str, events: list[Event]) -> str:
    lines = [f"Encontré varias citas para {action}. Responde con el número de la opción:"]
    for index, event in enumerate(events, start=1):
        lines.append(f"{index}. [{event.id}] {event.title} - {event.start_time:%d/%m/%Y %H:%M}")
    return "\n".join(lines)


def _build_llm_context(events: list[Event], user_data: dict[str, object]) -> dict[str, object]:
    return {
        "pending_action": user_data.get("pending_action"),
        "pending_disambiguation": user_data.get("pending_disambiguation"),
        "events": [
            {
                "id": event.id,
                "title": event.title,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
                "status": event.status,
            }
            for event in events
        ],
    }


def _build_event_from_llm(decision: LocalLlmDecision, user_id: int) -> Event | None:
    if not decision.title or not decision.start or not decision.end:
        return None

    try:
        start_time = datetime.fromisoformat(decision.start)
        end_time = datetime.fromisoformat(decision.end)
    except ValueError:
        return None

    return Event(
        id=None,
        user_id=user_id,
        title=decision.title,
        description=decision.description,
        location=None,
        start_time=start_time,
        end_time=end_time,
        priority=3,
    )


def _select_event_with_llm(decision: LocalLlmDecision, events: list[Event]) -> Event | list[Event] | None:
    if decision.event_id is not None:
        for event in events:
            if event.id == decision.event_id and event.status != "cancelled":
                return event
        return None

    query = decision.title_query or decision.title
    if not query:
        return None

    return _resolve_event_selection(ParsedCancelRequest(event_id=None, title_query=query), events)


async def _attempt_llm_assisted_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    dependencies: TelegramDependencies,
    user: User,
    text: str,
) -> bool:
    llm_client = dependencies.llm_client
    message = update.effective_message
    if llm_client is None or message is None or not llm_client.is_configured():
        return False

    events = dependencies.scheduling.list_agenda(user.id or 0)
    decision = llm_client.analyze(text, _build_llm_context(events, context.user_data))
    if decision is None:
        return False

    if decision.needs_clarification and decision.clarification:
        await message.reply_text(decision.clarification)
        return True

    action = _normalize_text(decision.action)
    if action == "read":
        await message.reply_text(dependencies.notification.build_agenda_message(events))
        return True

    if action == "create":
        parsed_event = _build_event_from_llm(decision, user.id or 0)
        if parsed_event is None:
            return False

        context.user_data["pending_action"] = {
            "type": "create",
            "title": parsed_event.title,
            "start": parsed_event.start_time.isoformat(),
            "end": parsed_event.end_time.isoformat(),
            "description": parsed_event.description,
        }
        await message.reply_text(
            f"¿Confirmas crear la cita '{parsed_event.title}' para el {parsed_event.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    if action in {"update", "cancel"}:
        selected_event = _select_event_with_llm(decision, events)
        if selected_event is None:
            return False

        if isinstance(selected_event, list):
            context.user_data["pending_disambiguation"] = {
                "type": action,
                "event_ids": [event.id for event in selected_event if event.id is not None],
                "new_start": decision.start,
            }
            await message.reply_text(_build_disambiguation_prompt("modificar" if action == "update" else "cancelar", selected_event))
            return True

        if action == "cancel":
            context.user_data["pending_action"] = {"type": "cancel", "event_id": selected_event.id}
            await message.reply_text(
                f"¿Confirmas cancelar la cita '{selected_event.title}' del {selected_event.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
            )
            return True

        if not decision.start:
            return False

        try:
            new_start = datetime.fromisoformat(decision.start)
        except ValueError:
            return False

        _prepare_pending_update(context, selected_event, new_start)
        await message.reply_text(
            f"¿Confirmas mover la cita '{selected_event.title}' al {new_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    if decision.action == "unknown" and decision.clarification:
        await message.reply_text(decision.clarification)
        return True

    return False


async def _handle_disambiguation_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    dependencies: TelegramDependencies,
    user: User,
) -> bool:
    pending = context.user_data.get("pending_disambiguation")
    message = update.effective_message
    if pending is None or message is None:
        return False

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.reply_text("Responde con el número de la opción para continuar.")
        return True

    event_ids = pending.get("event_ids") or []
    selection = int(text)
    if selection < 1 or selection > len(event_ids):
        await message.reply_text(f"La opción debe estar entre 1 y {len(event_ids)}.")
        return True

    selected_id = int(event_ids[selection - 1])
    selected_event = dependencies.scheduling.service.events.get_by_id(selected_id)
    pending_type = pending.get("type")

    if pending_type == "cancel":
        context.user_data["pending_action"] = {"type": "cancel", "event_id": selected_event.id}
        context.user_data.pop("pending_disambiguation", None)
        await message.reply_text(
            f"¿Confirmas cancelar la cita '{selected_event.title}' del {selected_event.start_time:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    if pending_type == "update":
        new_start = datetime.fromisoformat(str(pending["new_start"]))
        _prepare_pending_update(context, selected_event, new_start)
        context.user_data.pop("pending_disambiguation", None)
        await message.reply_text(
            f"¿Confirmas mover la cita '{selected_event.title}' al {new_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    context.user_data.pop("pending_disambiguation", None)
    await message.reply_text("No encontré una acción pendiente válida.")
    return True


def _prepare_pending_update(context: ContextTypes.DEFAULT_TYPE, event: Event, new_start: datetime) -> None:
    duration = event.end_time - event.start_time
    context.user_data["pending_action"] = {
        "type": "update",
        "event_id": event.id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "start": new_start.isoformat(),
        "end": (new_start + duration).isoformat(),
        "priority": event.priority,
    }


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


def _contains_harmful_prompt(text: str) -> bool:
    normalized = _normalize_text(text)
    harmful_patterns = (
        "rm -rf",
        "powershell",
        "cmd.exe",
        "drop table",
        "delete from",
        "attach database",
        "pragma",
    )
    return any(pattern in normalized for pattern in harmful_patterns)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(without_marks.split())
