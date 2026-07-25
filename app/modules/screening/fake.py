"""Fake screening implementation."""

from app.modules.screening.types import ScreeningHit


class AlwaysClearScreening:
    async def screen_person(
        self,
        *,
        name: str,
        dob: object | None,
        country: str,
    ) -> list[ScreeningHit]:
        _ = name, dob, country
        return []

