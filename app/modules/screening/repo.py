"""Screening repository."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.screening.models import ScreeningResult
from app.modules.screening.types import ScreeningHit


class ScreeningRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def persist_result(
        self,
        *,
        user_id: UUID,
        provider: str,
        subject_name: str,
        subject_country: str,
        hits: list[ScreeningHit],
    ) -> ScreeningResult:
        status = "clear" if not hits else "review"
        result = ScreeningResult(
            user_id=user_id,
            provider=provider,
            subject_name=subject_name,
            subject_country=subject_country,
            status=status,
            hits=[{"source": hit.source, "score": hit.score, "reason": hit.reason} for hit in hits],
        )
        self.session.add(result)
        await self.session.flush()
        return result

