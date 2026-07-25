from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from app.modules.notifications.console import ConsoleEmail
from app.modules.notifications.port import EmailMessage
from app.modules.screening.fake import AlwaysClearScreening
from app.modules.screening.service import ScreeningService
from app.modules.screening.types import ScreeningHit


@dataclass
class PersistedScreening:
    user_id: UUID
    provider: str
    subject_name: str
    subject_country: str
    hits: list[ScreeningHit]


class FakeScreeningRepo:
    def __init__(self) -> None:
        self.persisted: list[PersistedScreening] = []

    async def persist_result(
        self,
        *,
        user_id: UUID,
        provider: str,
        subject_name: str,
        subject_country: str,
        hits: list[ScreeningHit],
    ) -> PersistedScreening:
        result = PersistedScreening(
            user_id=user_id,
            provider=provider,
            subject_name=subject_name,
            subject_country=subject_country,
            hits=hits,
        )
        self.persisted.append(result)
        return result


@pytest.mark.asyncio
async def test_always_clear_screening_returns_no_hits() -> None:
    hits = await AlwaysClearScreening().screen_person(name="Ada", dob=None, country="GB")

    assert hits == []


@pytest.mark.asyncio
async def test_screening_service_persists_result() -> None:
    repo = FakeScreeningRepo()
    service = ScreeningService(repo)  # type: ignore[arg-type]
    user_id = uuid4()

    hits = await service.screen_person(user_id=user_id, name="Ada", dob=None, country="GB")

    assert hits == []
    assert repo.persisted == [
        PersistedScreening(
            user_id=user_id,
            provider="AlwaysClearScreening",
            subject_name="Ada",
            subject_country="GB",
            hits=[],
        )
    ]


@pytest.mark.asyncio
async def test_console_email_accepts_message() -> None:
    await ConsoleEmail().send(
        EmailMessage(
            to="user@example.com",
            subject="Welcome",
            text="Hello",
        )
    )

