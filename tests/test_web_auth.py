from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from db.database import Database
from db.repositories import OTPRepository, UserRepository
from services.email_service import EmailService
from services.web_auth_service import WebAuthService


class _DummyEmailService(EmailService):
    def __init__(self) -> None:
        super().__init__(None)
        self.sent = []

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        self.sent.append({"to": to_email, "subject": subject, "body": body})
        return True


class WebAuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.database = Database(self.db_path)
        self.database.initialize()
        self.connection = self.database.connect()
        self.users = UserRepository(self.connection)
        self.otps = OTPRepository(self.connection)
        self.email = _DummyEmailService()
        self.service = WebAuthService(
            users=self.users,
            otp_repository=self.otps,
            email_service=self.email,
            default_timezone="America/Bogota",
            otp_expiration_minutes=10,
        )

    def tearDown(self) -> None:
        self.connection.close()
        del self.service
        del self.email
        del self.otps
        del self.users
        del self.connection
        del self.database

    def test_register_creates_user_and_sends_otp(self) -> None:
        result = self.service.register("user_test", "user@test.com", "strongpass")

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.user)
        self.assertEqual(len(self.email.sent), 1)
        self.assertIn("OTP", self.email.sent[0]["subject"])

    def test_verify_otp_marks_email_verified(self) -> None:
        register = self.service.register("user_otp", "otp@test.com", "strongpass")
        self.assertTrue(register.ok)
        user = register.user
        self.assertIsNotNone(user)

        otp_row = self.otps.get_latest_active(user.id or 0)
        self.assertIsNotNone(otp_row)

        # Extract OTP from sent email body for test usage.
        body = self.email.sent[-1]["body"]
        otp_code = body.split("Tu código OTP es:")[1].split("\n")[0].strip()

        verify = self.service.verify_otp(user.id or 0, otp_code)
        self.assertTrue(verify.ok)

        updated = self.users.get_by_id(user.id or 0)
        self.assertTrue(updated.preferences.get("email_verified"))

    def test_login_requires_verified_email(self) -> None:
        register = self.service.register("user_login", "login@test.com", "strongpass")
        self.assertTrue(register.ok)

        login = self.service.login("user_login", "strongpass")
        self.assertFalse(login.ok)
        self.assertIn("verificar", login.message.lower())


if __name__ == "__main__":
    unittest.main()
