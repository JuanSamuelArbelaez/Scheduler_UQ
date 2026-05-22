from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException

from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.preferences import UserPreferencesAgent
from agents.scheduling import SchedulingAgent
from db.repositories import ChatRepository, UserRepository
from models.entities import User
from services.google_calendar_oauth import GoogleCalendarOAuthManager
from services.speech_to_text_service import SpeechToTextService
from services.text_to_speech_service import TextToSpeechService
from services.web_auth_service import WebAuthService
from services.web_chat_service import WebChatService


@dataclass(slots=True)
class WebDependencies:
    users: UserRepository
    preferences: UserPreferencesAgent
    orchestrator: OrchestratorAgent
    scheduling: SchedulingAgent
    notification: NotificationAgent
    oauth_manager: GoogleCalendarOAuthManager | None
    auth_service: WebAuthService
    chat_repository: ChatRepository
    stt_service: SpeechToTextService
    tts_service: TextToSpeechService
    default_timezone: str


def create_web_app(settings: Any, dependencies: WebDependencies) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = settings.flask_secret_key or "dev-secret-change-me"

    chat_service = WebChatService(
        orchestrator=dependencies.orchestrator,
        scheduling=dependencies.scheduling,
        preferences=dependencies.preferences,
        notification=dependencies.notification,
        oauth_manager=dependencies.oauth_manager,
        default_timezone=dependencies.default_timezone,
    )

    def _current_user() -> User | None:
        user_id = session.get("user_id")
        if not user_id:
            return None
        try:
            return dependencies.users.get_by_id(int(user_id))
        except LookupError:
            session.clear()
            return None

    def _require_auth() -> User:
        user = _current_user()
        if user is None:
            raise PermissionError("not authenticated")
        return user

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException) -> Any:
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": error.description or "Error HTTP"}), error.code
        return error

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception) -> Any:
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "message": f"Error interno del servidor: {error}"}), 500
        raise error

    @app.get("/")
    def index() -> Any:
        user = _current_user()
        if user is None:
            return redirect(url_for("login"))

        messages = dependencies.chat_repository.list_messages(user.id or 0, limit=100)
        onboarding_missing = chat_service.onboarding_missing_message(user)
        google_connected = bool(user.preferences.get("google_calendar_connected"))
        return render_template(
            "index.html",
            user=user,
            messages=messages,
            onboarding_missing=onboarding_missing,
            google_connected=google_connected,
            oauth_configured=dependencies.oauth_manager.is_configured() if dependencies.oauth_manager else False,
            timezone=dependencies.preferences.get_timezone(user),
        )

    @app.route("/register", methods=["GET", "POST"])
    def register() -> Any:
        if request.method == "POST":
            username = request.form.get("username", "")
            email = request.form.get("email", "")
            password = request.form.get("password", "")
            result = dependencies.auth_service.register(username, email, password)
            if result.ok and result.user is not None:
                session["pending_user_id"] = result.user.id
                flash(result.message, "success")
                return redirect(url_for("verify_otp"))
            flash(result.message, "error")
        return render_template("register.html")

    @app.route("/verify-otp", methods=["GET", "POST"])
    def verify_otp() -> Any:
        pending_user_id = session.get("pending_user_id")
        if not pending_user_id:
            return redirect(url_for("register"))

        if request.method == "POST":
            otp_code = request.form.get("otp", "")
            result = dependencies.auth_service.verify_otp(int(pending_user_id), otp_code)
            if result.ok and result.user is not None:
                session.pop("pending_user_id", None)
                session["user_id"] = result.user.id
                flash(result.message, "success")
                return redirect(url_for("index"))
            flash(result.message, "error")
        return render_template("verify_otp.html")

    @app.post("/resend-otp")
    def resend_otp() -> Any:
        pending_user_id = session.get("pending_user_id")
        if not pending_user_id:
            return redirect(url_for("register"))
        result = dependencies.auth_service.resend_otp(int(pending_user_id))
        flash(result.message, "success" if result.ok else "error")
        return redirect(url_for("verify_otp"))

    @app.route("/login", methods=["GET", "POST"])
    def login() -> Any:
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            result = dependencies.auth_service.login(username, password)
            if result.ok and result.user is not None:
                session["user_id"] = result.user.id
                flash(result.message, "success")
                return redirect(url_for("index"))
            if result.user is not None:
                session["pending_user_id"] = result.user.id
                flash("Debes verificar tu correo con OTP.", "error")
                return redirect(url_for("verify_otp"))
            flash(result.message, "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login"))

    @app.post("/profile/timezone")
    def update_timezone() -> Any:
        try:
            user = _require_auth()
        except PermissionError:
            return redirect(url_for("login"))

        timezone_name = request.form.get("timezone", "")
        updated = dependencies.preferences.update_timezone(user, timezone_name)
        flash(f"Zona horaria actualizada a {dependencies.preferences.get_timezone(updated)}", "success")
        return redirect(url_for("index"))

    @app.get("/connect-google")
    def connect_google() -> Any:
        try:
            user = _require_auth()
        except PermissionError:
            return redirect(url_for("login"))

        manager = dependencies.oauth_manager
        if manager is None or not manager.is_configured():
            flash("Google OAuth no está configurado en este entorno.", "error")
            return redirect(url_for("index"))

        auth_url = manager.build_authorization_url(user, force_account_selection=True)
        return redirect(auth_url)

    @app.post("/disconnect-google")
    def disconnect_google() -> Any:
        try:
            user = _require_auth()
        except PermissionError:
            return redirect(url_for("login"))

        manager = dependencies.oauth_manager
        if manager is None:
            flash("OAuth manager no disponible.", "error")
            return redirect(url_for("index"))

        manager.disconnect(user)
        flash("Google Calendar desvinculado. Puedes vincular otra cuenta.", "success")
        return redirect(url_for("index"))

    @app.get("/oauth/google/callback")
    def oauth_google_callback() -> Any:
        manager = dependencies.oauth_manager
        if manager is None:
            flash("OAuth manager no disponible.", "error")
            return redirect(url_for("index"))

        state = request.args.get("state", "")
        code = request.args.get("code", "")
        error = request.args.get("error", "")
        if error:
            flash(f"Google devolvió error: {error}", "error")
            return redirect(url_for("index"))

        result = manager.complete_authorization(state=state, code=code)
        flash(result.message, "success" if result.success else "error")
        return redirect(url_for("index"))

    @app.post("/api/chat")
    def chat() -> Any:
        try:
            user = _require_auth()
        except PermissionError:
            return jsonify({"ok": False, "message": "No autenticado"}), 401

        payload = request.get_json(silent=True) or {}
        text = str(payload.get("message") or "").strip()
        if not text:
            return jsonify({"ok": False, "message": "Mensaje vacío"}), 400

        onboarding_missing = chat_service.onboarding_missing_message(user)
        if onboarding_missing:
            return jsonify({"ok": False, "message": onboarding_missing, "onboarding_required": True}), 400

        outcome = chat_service.process_text(user, text)
        dependencies.chat_repository.append_message(user.id or 0, "user", text)
        dependencies.chat_repository.append_message(user.id or 0, "assistant", outcome.reply_text)
        return jsonify({"ok": True, "reply": outcome.reply_text})

    @app.post("/api/stt")
    def speech_to_text() -> Any:
        try:
            _ = _require_auth()
        except PermissionError:
            return jsonify({"ok": False, "message": "No autenticado"}), 401

        audio = request.files.get("audio")
        if audio is None:
            return jsonify({"ok": False, "message": "No se recibió audio"}), 400

        suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
        temp_path = ""
        with NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            audio.save(temp_path)
            try:
                text = dependencies.stt_service.transcribe(Path(temp_path))
            except Exception as error:
                return jsonify({"ok": False, "message": str(error)}), 500
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        return jsonify({"ok": True, "text": text})

    @app.post("/api/tts")
    def text_to_speech() -> Any:
        try:
            _ = _require_auth()
        except PermissionError:
            return jsonify({"ok": False, "message": "No autenticado"}), 401

        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "message": "Texto vacío"}), 400

        try:
            audio_bytes = dependencies.tts_service.synthesize(text)
        except Exception as error:
            return jsonify({"ok": False, "message": str(error)}), 500

        return send_file(BytesIO(audio_bytes), mimetype="audio/wav", as_attachment=False, download_name="reply.wav")

    return app
