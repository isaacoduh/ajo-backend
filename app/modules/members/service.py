"""Members service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.members.models import Member
from app.modules.members.repo import MembersRepo

SCREENING_PENDING = "pending"
SCREENING_CLEAR = "clear"
SCREENING_REVIEW = "review"
SCREENING_STATES = frozenset({SCREENING_PENDING, SCREENING_CLEAR, SCREENING_REVIEW})


class MembersService:
    def __init__(self, repo: MembersRepo) -> None:
        self.repo = repo

    async def ensure_for_user(
        self,
        *,
        user_id: UUID,
        display_name: str | None = None,
        country: str = "GB",
        screening_state: str = SCREENING_PENDING,
    ) -> Member:
        validate_screening_state(screening_state)
        member = await self.repo.get_member_by_user_id(user_id)
        if member is not None:
            if member.screening_state != screening_state:
                return await self.repo.update_screening_state(member, screening_state)
            return member
        return await self.repo.create_member(
            user_id=user_id,
            display_name=display_name,
            country=country,
            screening_state=screening_state,
        )

    async def get_current_member(self, *, user_id: UUID) -> Member:
        member = await self.repo.get_member_by_user_id(user_id)
        if member is None:
            raise member_not_found_error()
        return member

    async def screening_state_for_user(self, *, user_id: UUID) -> str:
        return (await self.get_current_member(user_id=user_id)).screening_state


def get_members_service(session: AsyncSession) -> MembersService:
    return MembersService(MembersRepo(session))


def validate_screening_state(screening_state: str) -> None:
    if screening_state not in SCREENING_STATES:
        raise AppError(
            status_code=422,
            title="Invalid Member State",
            detail="Member screening state is invalid.",
            type_="https://ajo.dev/problems/invalid-member-screening-state",
        )


def member_not_found_error() -> AppError:
    return AppError(
        status_code=404,
        title="Not Found",
        detail="Member profile was not found for this user.",
        type_="https://ajo.dev/problems/member-not-found",
    )
