"""Screening port."""

from typing import Protocol

from app.modules.screening.types import ScreeningHit


class ScreeningPort(Protocol):
    async def screen_person(
        self,
        *,
        name: str,
        dob: object | None,
        country: str,
    ) -> list[ScreeningHit]: ...

