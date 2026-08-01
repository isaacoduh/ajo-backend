"""Circles repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.circles.models import (
    Circle,
    CircleAgreement,
    CircleArrearsRecord,
    CircleContribution,
    CircleCycle,
    CircleDraw,
    CircleInvite,
    CircleMember,
    CirclePayout,
    CircleShortfallRecord,
)


class CirclesRepo:
    def __init__(self, session: AsyncSession | None = None) -> None:
        self.session = session

    async def ping(self) -> str:
        return "ok"

    def require_session(self) -> AsyncSession:
        if self.session is None:
            raise RuntimeError("CirclesRepo requires a database session for this operation.")
        return self.session

    async def create_circle(self, circle: Circle, owner_membership: CircleMember) -> Circle:
        session = self.require_session()
        session.add(circle)
        await session.flush()
        owner_membership.circle_id = circle.id
        session.add(owner_membership)
        await session.flush()
        return circle

    async def get_circle(self, circle_id: UUID) -> Circle | None:
        result = await self.require_session().execute(select(Circle).where(Circle.id == circle_id))
        return result.scalar_one_or_none()

    async def list_circles_for_member(self, member_id: UUID) -> list[Circle]:
        result = await self.require_session().execute(
            select(Circle)
            .join(CircleMember, CircleMember.circle_id == Circle.id)
            .where(CircleMember.member_id == member_id, CircleMember.status == "active")
            .order_by(Circle.created_at.desc(), Circle.id.desc())
        )
        return list(result.scalars())

    async def get_membership(self, *, circle_id: UUID, member_id: UUID) -> CircleMember | None:
        result = await self.require_session().execute(
            select(CircleMember).where(
                CircleMember.circle_id == circle_id,
                CircleMember.member_id == member_id,
                CircleMember.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_memberships(self, circle_id: UUID) -> list[CircleMember]:
        result = await self.require_session().execute(
            select(CircleMember)
            .where(CircleMember.circle_id == circle_id, CircleMember.status == "active")
            .order_by(CircleMember.created_at.asc(), CircleMember.id.asc())
        )
        return list(result.scalars())

    async def count_members(self, circle_id: UUID) -> int:
        result = await self.require_session().execute(
            select(func.count()).select_from(CircleMember).where(
                CircleMember.circle_id == circle_id,
                CircleMember.status == "active",
            )
        )
        return int(result.scalar_one())

    async def create_invite(self, invite: CircleInvite) -> CircleInvite:
        self.require_session().add(invite)
        await self.require_session().flush()
        return invite

    async def get_invite_by_token(self, token: str) -> CircleInvite | None:
        result = await self.require_session().execute(select(CircleInvite).where(CircleInvite.token == token))
        return result.scalar_one_or_none()

    async def add_member(self, membership: CircleMember) -> CircleMember:
        self.require_session().add(membership)
        await self.require_session().flush()
        return membership

    async def get_agreement(self, *, circle_id: UUID, member_id: UUID) -> CircleAgreement | None:
        result = await self.require_session().execute(
            select(CircleAgreement).where(
                CircleAgreement.circle_id == circle_id,
                CircleAgreement.member_id == member_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_agreements(self, circle_id: UUID) -> list[CircleAgreement]:
        result = await self.require_session().execute(
            select(CircleAgreement)
            .where(CircleAgreement.circle_id == circle_id)
            .order_by(CircleAgreement.accepted_at.asc(), CircleAgreement.id.asc())
        )
        return list(result.scalars())

    async def count_agreements(self, circle_id: UUID) -> int:
        result = await self.require_session().execute(
            select(func.count()).select_from(CircleAgreement).where(CircleAgreement.circle_id == circle_id)
        )
        return int(result.scalar_one())

    async def save_agreement(self, agreement: CircleAgreement) -> CircleAgreement:
        self.require_session().add(agreement)
        await self.require_session().flush()
        return agreement

    async def get_draw(self, circle_id: UUID) -> CircleDraw | None:
        result = await self.require_session().execute(select(CircleDraw).where(CircleDraw.circle_id == circle_id))
        return result.scalar_one_or_none()

    async def save_draw(self, draw: CircleDraw) -> CircleDraw:
        self.require_session().add(draw)
        await self.require_session().flush()
        return draw

    async def list_cycles(self, circle_id: UUID) -> list[CircleCycle]:
        result = await self.require_session().execute(
            select(CircleCycle)
            .where(CircleCycle.circle_id == circle_id)
            .order_by(CircleCycle.position.asc())
        )
        return list(result.scalars())

    async def get_cycle(self, *, circle_id: UUID, cycle_id: UUID) -> CircleCycle | None:
        result = await self.require_session().execute(
            select(CircleCycle).where(CircleCycle.circle_id == circle_id, CircleCycle.id == cycle_id)
        )
        return result.scalar_one_or_none()

    async def save_cycle(self, cycle: CircleCycle) -> CircleCycle:
        self.require_session().add(cycle)
        await self.require_session().flush()
        return cycle

    async def save_contribution(self, contribution: CircleContribution) -> CircleContribution:
        self.require_session().add(contribution)
        await self.require_session().flush()
        return contribution

    async def list_contributions(self, circle_id: UUID) -> list[CircleContribution]:
        result = await self.require_session().execute(
            select(CircleContribution)
            .where(CircleContribution.circle_id == circle_id)
            .order_by(CircleContribution.due_date.asc(), CircleContribution.id.asc())
        )
        return list(result.scalars())

    async def list_due_contributions(self, *, circle_id: UUID, now: datetime) -> list[CircleContribution]:
        result = await self.require_session().execute(
            select(CircleContribution)
            .where(
                CircleContribution.circle_id == circle_id,
                CircleContribution.status == "due",
                CircleContribution.due_date <= now.date(),
            )
            .order_by(CircleContribution.due_date.asc(), CircleContribution.id.asc())
        )
        return list(result.scalars())

    async def get_contribution(self, contribution_id: UUID) -> CircleContribution | None:
        result = await self.require_session().execute(
            select(CircleContribution).where(CircleContribution.id == contribution_id)
        )
        return result.scalar_one_or_none()

    async def get_payout_for_cycle(self, cycle_id: UUID) -> CirclePayout | None:
        result = await self.require_session().execute(select(CirclePayout).where(CirclePayout.cycle_id == cycle_id))
        return result.scalar_one_or_none()

    async def get_payout_by_payment_object_id(self, payment_object_id: UUID) -> CirclePayout | None:
        result = await self.require_session().execute(select(CirclePayout).where(CirclePayout.payment_object_id == payment_object_id))
        return result.scalar_one_or_none()

    async def save_payout(self, payout: CirclePayout) -> CirclePayout:
        self.require_session().add(payout)
        await self.require_session().flush()
        return payout

    async def save_arrears(self, record: CircleArrearsRecord) -> CircleArrearsRecord:
        self.require_session().add(record)
        await self.require_session().flush()
        return record

    async def save_shortfall(self, record: CircleShortfallRecord) -> CircleShortfallRecord:
        self.require_session().add(record)
        await self.require_session().flush()
        return record

    async def records_summary(self, circle_id: UUID) -> tuple[int, int, int, int]:
        session = self.require_session()
        arrears = await session.execute(
            select(func.count(), func.coalesce(func.sum(CircleArrearsRecord.amount_minor), 0)).where(
                CircleArrearsRecord.circle_id == circle_id
            )
        )
        shortfalls = await session.execute(
            select(func.count(), func.coalesce(func.sum(CircleShortfallRecord.amount_minor), 0)).where(
                CircleShortfallRecord.circle_id == circle_id
            )
        )
        arrears_count, arrears_minor = arrears.one()
        shortfall_count, shortfall_minor = shortfalls.one()
        return int(arrears_count), int(shortfall_count), int(arrears_minor), int(shortfall_minor)
