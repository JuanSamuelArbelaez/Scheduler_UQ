from __future__ import annotations

from typing import Any
import logging
import asyncio

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TelegramService:
    """Servicio para enviar mensajes de Telegram fuera del contexto del bot"""

    def __init__(self, token: str) -> None:
        self.bot = Bot(token=token)

    async def send_message(self, chat_id: str, text: str, **kwargs: Any) -> bool:
        """Envía un mensaje a un chat específico"""
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return True
        except TelegramError as e:
            logger.error(f"Error sending Telegram message to {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False

    def send_message_sync(self, chat_id: str, text: str, **kwargs: Any) -> bool:
        """Versión síncrona de send_message"""
        try:
            # Crear un nuevo loop de eventos si no hay uno
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.send_message(chat_id, text, **kwargs))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Error in send_message_sync: {e}")
            return False

    async def send_reminder(self, chat_id: str, event_title: str, event_time: str, timezone: str) -> bool:
        """Envía un recordatorio específico para un evento"""
        message = (
            f"🔔 **Recordatorio**\n\n"
            f"📅 **{event_title}**\n"
            f"🕐 {event_time}\n"
            f"🌍 Zona horaria: {timezone}\n\n"
            f"_Este evento está por comenzar_"
        )

        return await self.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )

    def send_reminder_sync(self, chat_id: str, event_title: str, event_time: str, timezone: str) -> bool:
        """Versión síncrona de send_reminder"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.send_reminder(chat_id, event_title, event_time, timezone))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Error in send_reminder_sync: {e}")
            return False