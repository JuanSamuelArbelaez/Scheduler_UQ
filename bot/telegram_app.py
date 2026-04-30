from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
import re
from typing import Final
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
import html
import json
import logging
import traceback
from telegram.constants import ParseMode

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
    default_timezone: str = "America/Bogota"


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


logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Determine chat_id: use update's chat if available, otherwise use bot owner's chat
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id = update.effective_chat.id
    else:
        # For jobs or other contexts without update, send to bot owner
        # This assumes we have a way to get the bot owner's chat_id
        # For now, we'll skip sending the message if no chat_id is available
        logger.warning("Cannot send error message: no valid chat_id available")
        return

    # Finally, send the message
    await context.bot.send_message(
        chat_id=chat_id, text=message, parse_mode=ParseMode.HTML
    )


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
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    application.add_error_handler(error_handler)
    if application.job_queue is not None:
        application.job_queue.run_repeating(_email_reminder_job, interval=60, first=20)
    return application


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    onboarding_hint = "Te voy a pedir tu email y zona horaria para activar recordatorios por correo."
    if user.email and dependencies.preferences.has_configured_timezone(user):
        onboarding_hint = "Tus preferencias ya están configuradas."

    keyboard = [
        [InlineKeyboardButton("📅 Ver Agenda", callback_data="menu_agenda")],
        [InlineKeyboardButton("➕ Crear Cita", callback_data="menu_create")],
        [InlineKeyboardButton("✏️ Modificar Cita", callback_data="menu_update")],
        [InlineKeyboardButton("❌ Cancelar Cita", callback_data="menu_cancel")],
        [InlineKeyboardButton("⚙️ Preferencias", callback_data="menu_preferences")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "Scheduler listo. Elige una opción del menú o escribe texto libre.\n"
        f"{onboarding_hint}"
    )
    await update.effective_message.reply_text(message, reply_markup=reply_markup)


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
    if await _handle_onboarding(update, context, dependencies, user):
        return

    timezone_name = dependencies.preferences.get_timezone(user)
    events = dependencies.scheduling.list_agenda(user.id or 0)
    await update.effective_message.reply_text(dependencies.notification.build_agenda_message(events, timezone_name))


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    if await _handle_onboarding(update, context, dependencies, user):
        return

    payload = " ".join(context.args)
    parts = _split_payload(payload, 4)
    if parts is None:
        await update.effective_message.reply_text(USAGE_CREATE)
        return

    try:
        title, start_raw, end_raw, description = parts
        user_timezone = dependencies.preferences.get_timezone(user)
        start_local = _parse_datetime(start_raw)
        end_local = _parse_datetime(end_raw)
        event = Event(
            id=None,
            user_id=user.id or 0,
            title=title,
            description=description,
            location=None,
            start_time=_to_utc_datetime(start_local, user_timezone),
            end_time=_to_utc_datetime(end_local, user_timezone),
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
    if await _handle_onboarding(update, context, dependencies, user):
        return

    payload = " ".join(context.args)
    parts = _split_payload(payload, 5)
    if parts is None:
        await update.effective_message.reply_text(USAGE_UPDATE)
        return

    try:
        event_id_raw, title, start_raw, end_raw, description = parts
        user_timezone = dependencies.preferences.get_timezone(user)
        start_local = _parse_datetime(start_raw)
        end_local = _parse_datetime(end_raw)
        event = Event(
            id=int(event_id_raw),
            user_id=user.id or 0,
            title=title,
            description=description,
            location=None,
            start_time=_to_utc_datetime(start_local, user_timezone),
            end_time=_to_utc_datetime(end_local, user_timezone),
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
    if await _handle_onboarding(update, context, dependencies, user):
        return

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

    if await _handle_onboarding(update, context, dependencies, user):
        return

    user_timezone = dependencies.preferences.get_timezone(user)

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
        await message.reply_text(dependencies.notification.build_agenda_message(events, user_timezone))
        return

    if orchestration.intent == IntentType.PREFERENCES:
        if _apply_preference_updates(text, dependencies, user):
            updated_user = dependencies.preferences.get_user(user.telegram_chat_id)
            updated_timezone = dependencies.preferences.get_timezone(updated_user)
            await message.reply_text(
                f"Preferencias actualizadas. Email: {updated_user.email or 'sin configurar'}. UTC/Zona horaria: {updated_timezone}."
            )
            return
        await message.reply_text(
            "Puedo actualizar tus preferencias. Ejemplos: 'mi correo es nombre@dominio.com' o 'mi zona horaria es America/Bogota'."
        )
        return

    if orchestration.intent == IntentType.CREATE:
        parsed_create = _parse_natural_create(text, reference_now=_now_in_timezone(user_timezone))
        if parsed_create is None:
            await message.reply_text(
                "Puedo crearla si me indicas fecha y hora validas. Ejemplo: Programa reunion con Ana manana a las 15:30"
            )
            return

        start_utc = _to_utc_datetime(parsed_create.start_time, user_timezone)
        end_utc = _to_utc_datetime(parsed_create.end_time, user_timezone)
        pending = {
            "type": "create",
            "title": parsed_create.title,
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
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
        local_start = _to_user_timezone(selected_event.start_time, user_timezone)
        await message.reply_text(
            f"¿Confirmas cancelar la cita '{selected_event.title}' del {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return

    if orchestration.intent == IntentType.UPDATE:
        parsed_update = _parse_natural_update(text, reference_now=_now_in_timezone(user_timezone))
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

        _prepare_pending_update(context, selected_event, _to_utc_datetime(parsed_update.new_start, user_timezone))
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


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    data = query.data

    if data == "menu_agenda":
        timezone_name = dependencies.preferences.get_timezone(user)
        events = dependencies.scheduling.list_agenda(user.id or 0)
        message = dependencies.notification.build_agenda_message(events, timezone_name)
        await query.edit_message_text(message)

    elif data == "menu_create":
        await query.edit_message_text(
            "Para crear una cita, dime algo como:\n"
            "• 'Reunión mañana a las 3pm'\n"
            "• 'Cena con Ana el viernes 8pm'\n"
            "• 'Dentista 20/04/2026 10:30'"
        )

    elif data == "menu_update":
        events = dependencies.scheduling.list_agenda(user.id or 0)
        if not events:
            await query.edit_message_text("No tienes citas para modificar.")
            return

        keyboard = []
        for event in events[:5]:  # Máximo 5 opciones
            local_start = _to_user_timezone(event.start_time, dependencies.preferences.get_timezone(user))
            button_text = f"{event.title} - {local_start:%d/%m %H:%M}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"update_{event.id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Selecciona la cita a modificar:", reply_markup=reply_markup)

    elif data == "menu_cancel":
        events = dependencies.scheduling.list_agenda(user.id or 0)
        if not events:
            await query.edit_message_text("No tienes citas para cancelar.")
            return

        keyboard = []
        for event in events[:5]:  # Máximo 5 opciones
            local_start = _to_user_timezone(event.start_time, dependencies.preferences.get_timezone(user))
            button_text = f"{event.title} - {local_start:%d/%m %H:%M}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cancel_{event.id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Selecciona la cita a cancelar:", reply_markup=reply_markup)

    elif data == "menu_preferences":
        user_prefs = dependencies.preferences.get_user(user.telegram_chat_id)
        timezone_name = dependencies.preferences.get_timezone(user_prefs)
        message = (
            f"📧 Email: {user_prefs.email or 'no configurado'}\n"
            f"🕐 Zona horaria: {timezone_name}\n\n"
            "Para cambiar, dime:\n"
            "• 'mi email es nombre@dominio.com'\n"
            "• 'mi zona horaria es America/Bogota'"
        )
        await query.edit_message_text(message)

    elif data.startswith("update_"):
        event_id = int(data.split("_")[1])
        context.user_data["pending_update_selection"] = event_id
        await query.edit_message_text(
            "Ahora dime la nueva fecha/hora. Ejemplos:\n"
            "• 'mañana a las 5pm'\n"
            "• 'el lunes 10:30'\n"
            "• '2026-04-25 14:00'"
        )

    elif data.startswith("cancel_"):
        event_id = int(data.split("_")[1])
        try:
            event = dependencies.scheduling.service.events.get_by_id(event_id)
            context.user_data["pending_action"] = {"type": "cancel", "event_id": event_id}
            local_start = _to_user_timezone(event.start_time, dependencies.preferences.get_timezone(user))

            keyboard = [
                [InlineKeyboardButton("✅ Sí, cancelar", callback_data="confirm_cancel")],
                [InlineKeyboardButton("❌ No, mantener", callback_data="cancel_operation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"¿Confirmas cancelar '{event.title}' del {local_start:%d/%m/%Y a las %H:%M}?",
                reply_markup=reply_markup
            )
        except LookupError:
            await query.edit_message_text("Cita no encontrada.")

    elif data == "confirm_cancel":
        pending = context.user_data.get("pending_action")
        if pending and pending.get("type") == "cancel":
            try:
                result = dependencies.scheduling.cancel_event(pending["event_id"])
                dependencies.history.record(user.id or 0, "cancel", result.event.id if result.event else None, result.message)
                await query.edit_message_text(f"✅ {result.message}")
            except (ValueError, LookupError) as error:
                await query.edit_message_text(f"❌ Error: {error}")
        else:
            await query.edit_message_text("❌ No hay acción pendiente.")
        context.user_data.pop("pending_action", None)

    elif data == "cancel_operation":
        context.user_data.pop("pending_action", None)
        await query.edit_message_text("❌ Operación cancelada.")

    else:
        await query.edit_message_text("Opción no reconocida.")


async def _email_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    dependencies = _dependencies(context)
    dependencies.scheduling.dispatch_due_reminders()


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


async def _handle_onboarding(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    dependencies: TelegramDependencies,
    user: User,
) -> bool:
    message = update.effective_message
    if message is None:
        return False

    text = (message.text or "").strip()
    pending = context.user_data.get("pending_onboarding")

    if pending is None and user.email and dependencies.preferences.has_configured_timezone(user):
        return False

    if pending is None:
        initial_step = "email" if not user.email else "timezone"
        context.user_data["pending_onboarding"] = {"step": initial_step}
        if initial_step == "email" and not _extract_email(text):
            await message.reply_text(
                "Antes de continuar, configura tu correo para notificaciones. Escribe algo como: mi correo es nombre@dominio.com"
            )
            return True
        if initial_step == "timezone" and _extract_timezone(text, dependencies.default_timezone) is None:
            await message.reply_text(
                "Antes de continuar, configura tu zona horaria. Ejemplo: America/Bogota o UTC-5"
            )
            return True
        pending = context.user_data.get("pending_onboarding")

    step = str(pending.get("step") or "")
    if step == "email":
        extracted_email = _extract_email(text)
        if not extracted_email:
            await message.reply_text("No detecté un correo válido. Ejemplo: mi correo es nombre@dominio.com")
            return True

        updated_user = dependencies.preferences.update_email(user, extracted_email)
        timezone_name = _extract_timezone(text, dependencies.default_timezone)
        if timezone_name is not None:
            updated_user = dependencies.preferences.update_timezone(updated_user, timezone_name)
            context.user_data.pop("pending_onboarding", None)
            await message.reply_text(
                f"Configuración completada. Email: {updated_user.email or 'sin email'}. Zona horaria: {dependencies.preferences.get_timezone(updated_user)}."
            )
            return True

        context.user_data["pending_onboarding"] = {"step": "timezone"}
        await message.reply_text(
            f"Correo guardado: {updated_user.email}. Ahora configura tu zona horaria (ejemplo: America/Bogota o UTC-5)."
        )
        return True

    if step == "timezone":
        timezone_name = _extract_timezone(text, dependencies.default_timezone)
        if timezone_name is None:
            await message.reply_text(
                "No reconocí la zona horaria. Usa formato IANA (America/Bogota) o UTC±N (UTC-5)."
            )
            return True

        updated_user = dependencies.preferences.update_timezone(user, timezone_name)
        context.user_data.pop("pending_onboarding", None)
        await message.reply_text(
            f"Configuración completada. Email: {updated_user.email or 'sin email'}. Zona horaria: {dependencies.preferences.get_timezone(updated_user)}."
        )
        return True

    context.user_data.pop("pending_onboarding", None)
    return False


def _apply_preference_updates(text: str, dependencies: TelegramDependencies, user: User) -> bool:
    changed = False
    email = _extract_email(text)
    if email:
        user = dependencies.preferences.update_email(user, email)
        changed = True

    timezone_name = _extract_timezone(text, dependencies.default_timezone)
    if timezone_name:
        dependencies.preferences.update_timezone(user, timezone_name)
        changed = True

    return changed


def _extract_email(text: str) -> str | None:
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    if match is None:
        return None
    return match.group(0).strip()


def _extract_timezone(text: str, default_timezone: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    utc_match = re.search(r"\butc\s*([+-])\s*(\d{1,2})\b", normalized, flags=re.IGNORECASE)
    if utc_match:
        sign = -1 if utc_match.group(1) == "-" else 1
        hours = int(utc_match.group(2))
        offset = sign * hours
        mapping = {
            -5: "America/Bogota",
            -6: "America/Guatemala",
            -4: "America/La_Paz",
            0: "UTC",
            1: "Europe/Madrid",
        }
        return mapping.get(offset, default_timezone)

    lowered = _normalize_text(normalized)
    if "colombia" in lowered or "bogota" in lowered:
        return "America/Bogota"

    match = re.search(r"\b([A-Za-z_]+/[A-Za-z_]+)\b", normalized)
    if match:
        candidate = match.group(1)
        return candidate
    return None


def _to_utc_datetime(value: datetime, timezone_name: str) -> datetime:
    user_zone = _resolve_timezone(timezone_name)

    if value.tzinfo is None:
        localized = value.replace(tzinfo=user_zone)
    else:
        localized = value.astimezone(user_zone)
    return localized.astimezone(UTC)


def _to_user_timezone(value: datetime, timezone_name: str) -> datetime:
    user_zone = _resolve_timezone(timezone_name)

    source = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return source.astimezone(user_zone)


def _now_in_timezone(timezone_name: str) -> datetime:
    zone = _resolve_timezone(timezone_name)
    return datetime.now(zone)


def _resolve_timezone(timezone_name: str) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        lowered = _normalize_text(timezone_name)
        if lowered in {"america/bogota", "bogota", "colombia", "utc-5"}:
            return timezone(timedelta(hours=-5))
        if lowered in {"utc", "etc/utc", "utc+0", "gmt"}:
            return timezone.utc
        utc_match = re.match(r"^utc([+-])(\d{1,2})$", lowered)
        if utc_match:
            sign = -1 if utc_match.group(1) == "-" else 1
            hours = int(utc_match.group(2))
            return timezone(timedelta(hours=sign * hours))
        return timezone(timedelta(hours=-5))


def _split_payload(payload: str, expected_parts: int) -> list[str] | None:
    parts = [part.strip() for part in payload.split("|")]
    if len(parts) != expected_parts or any(not part for part in parts[: expected_parts - 1]):
        return None
    return parts


def _parse_datetime(value: str) -> datetime:
    """Parse datetime with enhanced Spanish expressions support"""
    normalized = _normalize_text(value.strip())

    # Handle Spanish time expressions
    if normalized in ["mediodia", "mediodía"]:
        return datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    elif normalized in ["medianoche"]:
        return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized == "ahora":
        return datetime.now()

    # Handle relative dates
    now = datetime.now()
    if normalized == "hoy":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized in ["manana", "mañana"]:
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif normalized == "pasado":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Handle day names
    day_names = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6
    }
    if normalized in day_names:
        target_weekday = day_names[normalized]
        current_weekday = now.weekday()
        days_ahead = (target_weekday - current_weekday) % 7
        if days_ahead == 0:  # Today
            days_ahead = 7  # Next week
        return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Try ISO format first
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    # Try common formats
    for fmt in ["%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(f"No se pudo parsear la fecha/hora: {value}")


def _parse_natural_create(text: str, reference_now: datetime | None = None) -> ParsedCreateRequest | None:
    normalized = _normalize_text(text)

    # Enhanced patterns with more Spanish expressions
    patterns = [
        # Pattern 1: "agendar reunión mañana a las 3pm"
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|pasado)\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        # Pattern 2: "reunión el 2024-04-25 a las 15:30"
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<date>\d{4}-\d{2}-\d{2})\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        # Pattern 3: "dentista el 25 de abril de 2024 a las 10:30"
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?:(?:lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\s+)?(?P<day_num>\d{1,2})\s+de\s+(?P<month_name>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+(?:de\s+)?(?P<year>\d{4})(?P<between>.*?)\s*(?:a\s+las?\s+|a\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?",
        # Pattern 4: "reunión mañana al mediodía"
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana|lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|pasado)\s+(?:a\s+|al\s+)(?P<time>mediodia|mediodía|medianoche)",
        # Pattern 5: "cita hoy a las 14:00"
        r"(?:agenda|agendar|programa|crear|crea|agrega|anade|añade|haz)\s+(?P<title>.+?)\s+(?:el\s+)?(?P<day>hoy|manana|mañana)\s+(?:a\s+las?\s+|a\s+)(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|de la manana|de la mañana|de la tarde|de la noche)?"
    ]

    for pattern in patterns:
        day_match = re.search(pattern, normalized, re.IGNORECASE)
        if day_match:
            break
    else:
        return None

    title = day_match.group("title").strip(" .,")
    between = (day_match.groupdict().get("between") or "").strip(" .,")
    if between:
        title = f"{title} {between}".strip()
    title = _clean_create_title(title)
    if not title:
        return None

    try:
        # Handle special time expressions
        if "time" in day_match.groupdict() and day_match.group("time"):
            time_expr = day_match.group("time").lower()
            if time_expr in ["mediodia", "mediodía"]:
                event_time = time(12, 0)
            elif time_expr == "medianoche":
                event_time = time(0, 0)
            else:
                event_time = time(9, 0)  # Default fallback
        else:
            event_time = _resolve_time(day_match.group("hour"), day_match.group("minute"), day_match.group("ampm"))

        event_date = _resolve_date(day_match.groupdict(), reference_now=reference_now)
    except ValueError:
        return None

    start_time = datetime.combine(event_date, event_time)
    # Default duration: 1 hour, but can be smarter based on context
    duration = timedelta(hours=1)
    if "reunion" in title.lower() or "meeting" in title.lower():
        duration = timedelta(hours=1)
    elif "cita" in title.lower() or "consulta" in title.lower():
        duration = timedelta(minutes=30)

    return ParsedCreateRequest(title=title, start_time=start_time, end_time=start_time + duration, description=None)


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


def _parse_natural_update(text: str, reference_now: datetime | None = None) -> ParsedUpdateRequest | None:
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
        event_date = _resolve_date(timing_match.groupdict(), reference_now=reference_now)
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
    user_timezone = dependencies.preferences.get_timezone(user)
    decision = llm_client.analyze(text, _build_llm_context(events, context.user_data))
    if decision is None:
        return False

    if decision.needs_clarification and decision.clarification:
        await message.reply_text(decision.clarification)
        return True

    action = _normalize_text(decision.action)
    if action == "read":
        if _looks_like_explicit_create(text):
            return False
        await message.reply_text(dependencies.notification.build_agenda_message(events, user_timezone))
        return True

    if action == "create":
        parsed_event = _build_event_from_llm(decision, user.id or 0)
        if parsed_event is None:
            return False

        parsed_event.start_time = _to_utc_datetime(parsed_event.start_time, user_timezone)
        parsed_event.end_time = _to_utc_datetime(parsed_event.end_time, user_timezone)
        local_start = _to_user_timezone(parsed_event.start_time, user_timezone)

        context.user_data["pending_action"] = {
            "type": "create",
            "title": parsed_event.title,
            "start": parsed_event.start_time.isoformat(),
            "end": parsed_event.end_time.isoformat(),
            "description": parsed_event.description,
        }
        await message.reply_text(
            f"¿Confirmas crear la cita '{parsed_event.title}' para el {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    if action in {"update", "cancel"}:
        selected_event = _select_event_with_llm(decision, events)
        if selected_event is None:
            return False

        if isinstance(selected_event, list):
            pending_new_start = None
            if decision.start:
                try:
                    pending_new_start = _to_utc_datetime(datetime.fromisoformat(decision.start), user_timezone).isoformat()
                except ValueError:
                    pending_new_start = None
            context.user_data["pending_disambiguation"] = {
                "type": action,
                "event_ids": [event.id for event in selected_event if event.id is not None],
                "new_start": pending_new_start,
            }
            await message.reply_text(_build_disambiguation_prompt("modificar" if action == "update" else "cancelar", selected_event))
            return True

        if action == "cancel":
            context.user_data["pending_action"] = {"type": "cancel", "event_id": selected_event.id}
            local_start = _to_user_timezone(selected_event.start_time, user_timezone)
            await message.reply_text(
                f"¿Confirmas cancelar la cita '{selected_event.title}' del {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
            )
            return True

        if not decision.start:
            return False

        try:
            new_start = datetime.fromisoformat(decision.start)
        except ValueError:
            return False

        new_start_utc = _to_utc_datetime(new_start, user_timezone)
        _prepare_pending_update(context, selected_event, new_start_utc)
        local_start = _to_user_timezone(new_start_utc, user_timezone)
        await message.reply_text(
            f"¿Confirmas mover la cita '{selected_event.title}' al {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
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
    user_timezone = dependencies.preferences.get_timezone(user)

    if pending_type == "cancel":
        context.user_data["pending_action"] = {"type": "cancel", "event_id": selected_event.id}
        context.user_data.pop("pending_disambiguation", None)
        local_start = _to_user_timezone(selected_event.start_time, user_timezone)
        await message.reply_text(
            f"¿Confirmas cancelar la cita '{selected_event.title}' del {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
        )
        return True

    if pending_type == "update":
        new_start_raw = pending.get("new_start")
        if not new_start_raw:
            context.user_data.pop("pending_disambiguation", None)
            await message.reply_text("Me falta la nueva fecha/hora para completar la modificación.")
            return True
        new_start = datetime.fromisoformat(str(new_start_raw))
        _prepare_pending_update(context, selected_event, new_start)
        context.user_data.pop("pending_disambiguation", None)
        local_start = _to_user_timezone(new_start, user_timezone)
        await message.reply_text(
            f"¿Confirmas mover la cita '{selected_event.title}' al {local_start:%d/%m/%Y a las %H:%M}? Responde si o no."
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


def _resolve_date(values: dict[str, str | None], reference_now: datetime | None = None) -> date:
    """Resolve date with enhanced Spanish expressions support"""
    today = (reference_now or datetime.now()).date()

    # Handle ISO date
    if values.get("date"):
        return date.fromisoformat(values["date"] or "")

    # Handle full date with month name
    if values.get("day_num") and values.get("month_name") and values.get("year"):
        month_map = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12,
        }
        month_value = month_map.get(_normalize_text(values["month_name"] or ""))
        if month_value is None:
            raise ValueError("Mes inválido")
        return date(year=int(values["year"] or "0"), month=month_value, day=int(values["day_num"] or "0"))

    # Handle relative dates
    day_name = _normalize_text(values.get("day") or "")
    if day_name == "hoy":
        return today
    elif day_name in ["manana", "mañana"]:
        return today + timedelta(days=1)
    elif day_name == "pasado":
        return today - timedelta(days=1)
    elif day_name == "anteayer":
        return today - timedelta(days=2)

    # Handle weekdays
    weekday_map = {
        "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2,
        "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
    }
    if day_name in weekday_map:
        target_weekday = weekday_map[day_name]
        current_weekday = today.weekday()
        delta = (target_weekday - current_weekday) % 7
        if delta == 0:  # Same day this week
            return today + timedelta(days=7)  # Next week
        return today + timedelta(days=delta)

    # Default to today if nothing matches
    return today


def _resolve_time(hour_raw: str | None, minute_raw: str | None, ampm_raw: str | None) -> time:
    """Resolve time with enhanced Spanish expressions support"""
    hour = int(hour_raw or "0")
    minute = int(minute_raw or "0")
    ampm = _normalize_text(ampm_raw or "")

    # Handle Spanish time expressions
    if ampm in ["de la manana", "de la mañana"]:
        if hour < 12:
            pass  # Keep as is
    elif ampm in ["de la tarde", "de la noche"]:
        if hour < 12:
            hour += 12
    elif ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif ampm == "pm" and hour == 12:
        pass  # Keep as 12 PM

    # Validate hour range
    if not (0 <= hour <= 23):
        raise ValueError(f"Hora inválida: {hour}")
    if not (0 <= minute <= 59):
        raise ValueError(f"Minutos inválidos: {minute}")

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


def _clean_create_title(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"^(una\s+)?cita\s+para\s+", "", cleaned).strip()
    cleaned = re.sub(r"^(un\s+)?evento\s+para\s+", "", cleaned).strip()
    cleaned = re.sub(r"^para\s+", "", cleaned).strip()
    cleaned = re.sub(r"\b(voy\s+a\s+ir|ire|ir)\b", "", cleaned).strip(" .,")
    return " ".join(cleaned.split())


def _looks_like_explicit_create(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(re.search(r"\b(crea|crear|programa|agenda|agendar|agrega|anade|anadir|añade|cita)\b", normalized))


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_marks = "".join(character for character in normalized if not unicodedata.combining(character))
    return " ".join(without_marks.split())
