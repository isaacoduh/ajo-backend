"""Screening service."""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.screening.fake import AlwaysClearScreening
from app.modules.screening.port import ScreeningPort
from app.modules.screening.repo import ScreeningRepo
from app.modules.screening.types import ScreeningHit


class ScreeningService:
    def __init__(
        self,
        repo: ScreeningRepo,
        port: ScreeningPort | None = None,
    ) -> None:
        self.repo = repo
        self.port = port if port is not None else AlwaysClearScreening()

    async def screen_person(
        self,
        *,
        user_id: UUID,
        name: str,
        dob: date | None,
        country: str,
    ) -> list[ScreeningHit]:
        hits = await self.port.screen_person(name=name, dob=dob, country=country)
        await self.repo.persist_result(
            user_id=user_id,
            provider=self.port.__class__.__name__,
            subject_name=name,
            subject_country=country,
            hits=hits,
        )
        return hits


def get_screening_service(session: AsyncSession) -> ScreeningService:
    return ScreeningService(ScreeningRepo(session))
