"""SMTP email implementation for Mailpit/local demos."""

import asyncio
import smtplib
from email.message import EmailMessage as SmtpEmailMessage

from app.core.config import Settings, get_settings
from app.modules.notifications.port import EmailMessage


class SmtpEmail:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings if settings is not None else get_settings()

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        smtp_message = SmtpEmailMessage()
        smtp_message["From"] = "noreply@ajo.local"
        smtp_message["To"] = message.to
        smtp_message["Subject"] = message.subject
        smtp_message.set_content(message.text)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=5) as client:
            client.send_message(smtp_message)

