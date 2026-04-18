from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

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
    dependencies = _dependencies(context)
    user = _ensure_user(update, dependencies)
    orchestration = dependencies.orchestrator.handle(update.effective_message.text or "")

    if orchestration.intent == IntentType.READ:
        events = dependencies.scheduling.list_agenda(user.id or 0)
        await update.effective_message.reply_text(dependencies.notification.build_agenda_message(events))
        return

    if orchestration.requires_confirmation:
        await update.effective_message.reply_text(
            "Entendi la solicitud, pero necesito un formato estructurado para ejecutar la accion. "
            "Usa /help para ver ejemplos."
        )
        return

    await update.effective_message.reply_text(
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