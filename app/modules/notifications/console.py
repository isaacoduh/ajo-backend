"""Console email implementation."""

import structlog

from app.modules.notifications.port import EmailMessage

logger = structlog.get_logger(__name__)


class ConsoleEmail:
    async def send(self, message: EmailMessage) -> None:
        logger.info("email_sent_console", to=message.to, subject=message.subject)

