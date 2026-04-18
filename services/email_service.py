from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib


@dataclass(frozen=True)
class EmailSettings:
    host: str
    port: int
    username: str
    password: str
    from_email: str
    use_tls: bool = True


class EmailService:
    def __init__(self, settings: EmailSettings | None) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        if self.settings is None:
            return False
        return bool(self.settings.host and self.settings.port and self.settings.from_email)

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        if not self.is_configured() or not to_email:
            return False

        settings = self.settings
        if settings is None:
            return False

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.from_email
        message["To"] = to_email
        message.set_content(body)

        try:
            with smtplib.SMTP(settings.host, settings.port, timeout=15) as smtp:
                if settings.use_tls:
                    smtp.starttls()
                if settings.username:
                    smtp.login(settings.username, settings.password)
                smtp.send_message(message)
            return True
        except (smtplib.SMTPException, OSError):
            return False
