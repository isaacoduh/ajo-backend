"""Members repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.members.models import Member


class MembersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_member(
        self,
        *,
        user_id: UUID,
        display_name: str | None,
        country: str,
        screening_state: str,
    ) -> Member:
        member = Member(
            user_id=user_id,
            display_name=display_name,
            country=country,
            screening_state=screening_state,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_member_by_user_id(self, user_id: UUID) -> Member | None:
        result = await self.session.execute(select(Member).where(Member.user_id == user_id))
        return result.scalar_one_or_none()

    async def update_screening_state(self, member: Member, screening_state: str) -> Member:
        member.screening_state = screening_state
        await self.session.flush()
        return member

    async def update_profile(
        self,
        member: Member,
        *,
        display_name: str | None,
        country: str,
    ) -> Member:
        member.display_name = display_name
        member.country = country
        await self.session.flush()
        return member
