from uuid import UUID, uuid4

import pytest
from app.core.errors import AppError
from app.core.security import utc_now
from app.modules.identity.models import User
from app.modules.members.models import Member
from app.modules.members.repo import MembersRepo
from app.modules.members.service import MembersService
from sqlalchemy.ext.asyncio import AsyncSession


class FakeMembersRepo:
    def __init__(self, member: Member | None = None) -> None:
        self.member = member
        self.create_calls: list[dict[str, object]] = []
        self.updated_states: list[str] = []

    async def get_member_by_user_id(self, user_id: UUID) -> Member | None:
        if self.member is not None and self.member.user_id == user_id:
            return self.member
        return None

    async def create_member(
        self,
        *,
        user_id: UUID,
        display_name: str | None,
        country: str,
        screening_state: str,
    ) -> Member:
        self.create_calls.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "country": country,
                "screening_state": screening_state,
            }
        )
        self.member = make_member(user_id=user_id, screening_state=screening_state)
        return self.member

    async def update_screening_state(self, member: Member, screening_state: str) -> Member:
        self.updated_states.append(screening_state)
        member.screening_state = screening_state
        return member


def make_member(*, user_id: UUID, screening_state: str = "pending") -> Member:
    now = utc_now()
    return Member(
        id=uuid4(),
        user_id=user_id,
        display_name="member@example.com",
        country="GB",
        screening_state=screening_state,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_ensure_for_user_creates_member_once() -> None:
    user_id = uuid4()
    repo = FakeMembersRepo()
    service = MembersService(repo)  # type: ignore[arg-type]

    first = await service.ensure_for_user(
        user_id=user_id,
        display_name="member@example.com",
        screening_state="clear",
    )
    second = await service.ensure_for_user(
        user_id=user_id,
        display_name="member@example.com",
        screening_state="clear",
    )

    assert first is second
    assert len(repo.create_calls) == 1
    assert repo.create_calls[0]["user_id"] == user_id
    assert first.screening_state == "clear"


@pytest.mark.asyncio
async def test_ensure_for_user_updates_existing_screening_state_without_duplicate() -> None:
    user_id = uuid4()
    existing = make_member(user_id=user_id, screening_state="pending")
    repo = FakeMembersRepo(existing)
    service = MembersService(repo)  # type: ignore[arg-type]

    member = await service.ensure_for_user(user_id=user_id, screening_state="clear")

    assert member is existing
    assert repo.create_calls == []
    assert repo.updated_states == ["clear"]
    assert member.screening_state == "clear"


@pytest.mark.asyncio
async def test_ensure_for_user_rejects_invalid_screening_state() -> None:
    service = MembersService(FakeMembersRepo())  # type: ignore[arg-type]

    with pytest.raises(AppError):
        await service.ensure_for_user(user_id=uuid4(), screening_state="blocked")


@pytest.mark.asyncio
async def test_ensure_for_user_is_idempotent_against_database(db_session: AsyncSession) -> None:
    user = User(email="member-db@example.com", password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    service = MembersService(MembersRepo(db_session))

    first = await service.ensure_for_user(
        user_id=user.id,
        display_name=user.email,
        screening_state="clear",
    )
    second = await service.ensure_for_user(
        user_id=user.id,
        display_name=user.email,
        screening_state="clear",
    )

    assert first.id == second.id
    assert first.user_id == user.id
    assert second.screening_state == "clear"
