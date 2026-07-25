"""Email notification port."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailPort(Protocol):
    async def send(self, message: EmailMessage) -> None: ...

