from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Wrapper para Google Calendar API con soporte para OAuth por usuario."""

    def __init__(self, service_account_file: str | None = None) -> None:
        self.service = None
        service_file = (service_account_file or "").strip()
        if service_file and Path(service_file).is_file():
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    service_file,
                    scopes=["https://www.googleapis.com/auth/calendar"],
                )
                self.service = build("calendar", "v3", credentials=credentials)
                logger.info("Google Calendar service inicializado con service account")
            except Exception as error:
                logger.warning("No se pudo inicializar Google Calendar con service account: %s", error)

    def is_available(self) -> bool:
        return self.service is not None

    def create_event(
        self,
        calendar_id: str,
        title: str,
        start_time_utc: str,
        end_time_utc: str,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        oauth_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        service = self._resolve_service(oauth_credentials)
        if service is None:
            raise RuntimeError("Google Calendar no disponible: faltan credenciales OAuth o service account")

        body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_time_utc},
            "end": {"dateTime": end_time_utc},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        event = service.events().insert(calendarId=calendar_id, body=body).execute()
        logger.info("Google Calendar create_event OK: %s", event.get("id"))
        return event

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        title: str | None = None,
        start_time_utc: str | None = None,
        end_time_utc: str | None = None,
        description: str | None = None,
        location: str | None = None,
        oauth_credentials: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        service = self._resolve_service(oauth_credentials)
        if service is None:
            raise RuntimeError("Google Calendar no disponible: faltan credenciales OAuth o service account")

        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        if title:
            event["summary"] = title
        if start_time_utc:
            event["start"] = {"dateTime": start_time_utc}
        if end_time_utc:
            event["end"] = {"dateTime": end_time_utc}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location

        updated = service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
        logger.info("Google Calendar update_event OK: %s", event_id)
        return updated

    def delete_event(
        self,
        calendar_id: str,
        event_id: str,
        oauth_credentials: dict[str, Any] | None = None,
    ) -> bool:
        service = self._resolve_service(oauth_credentials)
        if service is None:
            raise RuntimeError("Google Calendar no disponible: faltan credenciales OAuth o service account")

        try:
            service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info("Google Calendar delete_event OK: %s", event_id)
            return True
        except HttpError as error:
            status = getattr(getattr(error, "resp", None), "status", None)
            if status == 404:
                logger.info("Google Calendar event %s ya no existe; delete se considera exitoso", event_id)
                return True
            raise

    def _resolve_service(self, oauth_credentials: dict[str, Any] | None = None):
        if oauth_credentials:
            try:
                credentials = UserCredentials.from_authorized_user_info(
                    oauth_credentials,
                    scopes=["https://www.googleapis.com/auth/calendar"],
                )
                if credentials.expired:
                    if credentials.refresh_token:
                        credentials.refresh(Request())
                    else:
                        logger.warning("OAuth expirado sin refresh_token")
                        return None
                return build("calendar", "v3", credentials=credentials)
            except Exception as error:
                logger.warning("OAuth de usuario inválido para Google Calendar: %s", error)
                return None

        return self.service
