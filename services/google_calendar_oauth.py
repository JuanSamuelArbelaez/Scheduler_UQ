from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import secrets
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from google_auth_oauthlib.flow import Flow

from agents.preferences import UserPreferencesAgent
from models.entities import User


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GoogleOAuthResult:
    success: bool
    message: str
    user_chat_id: str | None = None


@dataclass(slots=True)
class _PendingOAuthSession:
    chat_id: str
    code_verifier: str | None = None


class GoogleCalendarOAuthManager:
    def __init__(
        self,
        preferences: UserPreferencesAgent,
        client_secrets_file: str,
        redirect_host: str = "127.0.0.1",
        redirect_port: int = 8765,
        scopes: str = "https://www.googleapis.com/auth/calendar",
        telegram_bot_token: str | None = None,
    ) -> None:
        self.preferences = preferences
        self.client_secrets_file = Path(client_secrets_file)
        self.redirect_host = redirect_host
        self.redirect_port = redirect_port
        self.scopes = [scope.strip() for scope in scopes.split() if scope.strip()]
        self.telegram_bot_token = telegram_bot_token
        self._pending_states: dict[str, _PendingOAuthSession] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://{self.redirect_host}:{self.redirect_port}/oauth/google/callback"

    def is_configured(self) -> bool:
        return self.client_secrets_file.is_file() and bool(self.scopes)

    def has_connection(self, user: User) -> bool:
        return self.preferences.is_google_calendar_connected(user)

    def build_authorization_url(self, user: User) -> str:
        if not self.is_configured():
            raise RuntimeError("Google OAuth no está configurado")

        state = secrets.token_urlsafe(24)
        flow = self._build_flow(state)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
            state=state,
        )
        self._pending_states[state] = _PendingOAuthSession(
            chat_id=user.telegram_chat_id,
            code_verifier=getattr(flow, "code_verifier", None),
        )
        return authorization_url

    def start_callback_server(self) -> None:
        if self._server is not None:
            return

        manager = self

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                logger.info("%s - %s", self.client_address[0], format % args)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path != "/oauth/google/callback":
                    self.send_response(404)
                    self.end_headers()
                    return

                query = parse_qs(parsed.query)
                code = (query.get("code") or [""])[0].strip()
                state = (query.get("state") or [""])[0].strip()
                error = (query.get("error") or [""])[0].strip()

                if error:
                    result = GoogleOAuthResult(False, f"Google devolvió un error: {error}")
                else:
                    result = manager.complete_authorization(state, code)

                body = manager._render_html_result(result)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer((self.redirect_host, self.redirect_port), OAuthCallbackHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Google OAuth callback server listening on http://%s:%s", self.redirect_host, self.redirect_port)

    def complete_authorization(self, state: str, code: str) -> GoogleOAuthResult:
        session = self._pending_states.pop(state, None)
        if not session:
            return GoogleOAuthResult(False, "La sesión OAuth expiró o no es válida.")

        if not code:
            return GoogleOAuthResult(False, "No se recibió el código de autorización.")

        try:
            flow = self._build_flow(state)
            if session.code_verifier:
                flow.code_verifier = session.code_verifier
            flow.fetch_token(code=code)
            credentials = json.loads(flow.credentials.to_json())
            user = self.preferences.get_user(session.chat_id)
            self.preferences.update_google_calendar_credentials(user, credentials)
            self._notify_telegram(session.chat_id, "Google Calendar quedó vinculado a tu calendario personal.")
            return GoogleOAuthResult(True, "Google Calendar conectado correctamente.", user_chat_id=session.chat_id)
        except Exception as error:
            logger.exception("No se pudo completar OAuth de Google Calendar")
            return GoogleOAuthResult(False, f"No se pudo completar la conexión: {error}", user_chat_id=session.chat_id)

    def build_status_text(self, user: User) -> str:
        if self.has_connection(user):
            return "✅ Google Calendar vinculado a tu calendario personal."
        if not self.is_configured():
            return "⚠️ Aún no configuré el flujo de Google Calendar."
        return "🔗 Conecta Google Calendar una sola vez para usar tu calendario personal."

    def _build_flow(self, state: str) -> Flow:
        flow = Flow.from_client_secrets_file(str(self.client_secrets_file), scopes=self.scopes, state=state)
        flow.redirect_uri = self.redirect_uri
        flow.autogenerate_code_verifier = True
        return flow

    def _notify_telegram(self, chat_id: str, message: str) -> None:
        if not self.telegram_bot_token:
            return

        body = urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
        request = Request(
            f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10):
                return
        except Exception:
            logger.warning("No se pudo enviar notificación Telegram de OAuth")

    def _render_html_result(self, result: GoogleOAuthResult) -> bytes:
        title = "Conexión de Google Calendar"
        if result.success:
            message = "La conexión quedó lista. Ya puedes volver a Telegram."
        else:
            message = result.message
        html = f"""
        <html>
          <head><title>{title}</title></head>
          <body style=\"font-family: sans-serif; padding: 24px;\">
            <h2>{title}</h2>
            <p>{message}</p>
            <p>Puedes cerrar esta pestaña y volver a Telegram.</p>
          </body>
        </html>
        """.strip()
        return html.encode("utf-8")