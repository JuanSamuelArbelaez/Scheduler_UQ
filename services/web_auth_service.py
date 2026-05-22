from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import re
import secrets

from db.repositories import OTPRepository, UserRepository
from models.entities import User
from services.email_service import EmailService


@dataclass(slots=True)
class AuthResult:
    ok: bool
    message: str
    user: User | None = None


class WebAuthService:
    def __init__(
        self,
        users: UserRepository,
        otp_repository: OTPRepository,
        email_service: EmailService,
        default_timezone: str,
        otp_expiration_minutes: int = 10,
    ) -> None:
        self.users = users
        self.otp_repository = otp_repository
        self.email_service = email_service
        self.default_timezone = default_timezone
        self.otp_expiration_minutes = otp_expiration_minutes

    def register(self, username: str, email: str, password: str) -> AuthResult:
        username = username.strip()
        email = email.strip().lower()
        if not re.fullmatch(r"[a-zA-Z0-9_]{3,32}", username):
            return AuthResult(False, "El usuario debe tener 3-32 caracteres alfanuméricos o guion bajo.")
        if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
            return AuthResult(False, "Correo inválido.")
        if len(password) < 8:
            return AuthResult(False, "La contraseña debe tener al menos 8 caracteres.")

        try:
            self.users.get_by_username(username)
            return AuthResult(False, "Ese nombre de usuario ya existe.")
        except LookupError:
            pass

        try:
            self.users.get_by_email(email)
            return AuthResult(False, "Ese correo ya está registrado.")
        except LookupError:
            pass

        password_hash = self._hash_password(password)
        user = self.users.create_web_user(username, email, password_hash, default_timezone=self.default_timezone)
        code = self._issue_otp(user.id or 0)
        self._send_otp_email(email, code)
        return AuthResult(True, "Te envié un código OTP al correo para validar tu cuenta.", user=user)

    def verify_otp(self, user_id: int, otp_code: str) -> AuthResult:
        row = self.otp_repository.get_latest_active(user_id)
        if row is None:
            return AuthResult(False, "No hay un OTP activo. Solicita uno nuevo.")

        expires_at = datetime.fromisoformat(row["expires_at"])
        now_utc = datetime.now(UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now_utc:
            return AuthResult(False, "El OTP expiró. Solicita uno nuevo.")

        expected = row["otp_hash"]
        if not hmac.compare_digest(expected, self._hash_otp(otp_code.strip())):
            return AuthResult(False, "OTP inválido.")

        self.otp_repository.mark_used(int(row["id"]))
        user = self.users.verify_email(user_id)
        return AuthResult(True, "Correo verificado correctamente.", user=user)

    def resend_otp(self, user_id: int) -> AuthResult:
        user = self.users.get_by_id(user_id)
        if not user.email:
            return AuthResult(False, "No hay correo asociado para reenviar OTP.")
        code = self._issue_otp(user_id)
        self._send_otp_email(user.email, code)
        return AuthResult(True, "Se envió un nuevo OTP.")

    def login(self, username: str, password: str) -> AuthResult:
        username = username.strip()
        password_hash = self.users.get_password_hash_by_username(username)
        if not password_hash:
            return AuthResult(False, "Credenciales inválidas.")
        if not self._verify_password(password, password_hash):
            return AuthResult(False, "Credenciales inválidas.")

        user = self.users.get_by_username(username)
        if not bool(user.preferences.get("email_verified")):
            return AuthResult(False, "Debes verificar tu correo antes de iniciar sesión.", user=user)
        return AuthResult(True, "Inicio de sesión correcto.", user=user)

    def _issue_otp(self, user_id: int) -> str:
        code = f"{secrets.randbelow(10**6):06d}"
        expires_at = datetime.now(UTC) + timedelta(minutes=self.otp_expiration_minutes)
        self.otp_repository.create_code(user_id, self._hash_otp(code), expires_at)
        return code

    def _send_otp_email(self, to_email: str, code: str) -> None:
        subject = "Tu código OTP de Scheduler"
        body = (
            "Hola,\n\n"
            f"Tu código OTP es: {code}\n"
            f"Este código expira en {self.otp_expiration_minutes} minutos.\n\n"
            "Si no solicitaste este registro, ignora este correo."
        )
        self.email_service.send_email(to_email, subject, body)

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
        return f"{salt}${digest.hex()}"

    def _verify_password(self, candidate: str, password_hash: str) -> bool:
        try:
            salt, digest_hex = password_hash.split("$", 1)
        except ValueError:
            return False
        expected = hashlib.pbkdf2_hmac("sha256", candidate.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
        return hmac.compare_digest(expected, digest_hex)

    def _hash_otp(self, otp_code: str) -> str:
        return hashlib.sha256(otp_code.encode("utf-8")).hexdigest()
