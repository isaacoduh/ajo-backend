"""Circle engine service."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import utc_now
from app.db.ledger import GBP, AccountType, PostingInput, PostingSide
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
from app.modules.circles.repo import CirclesRepo
from app.modules.circles.schemas import (
    CircleContributionResponse,
    CircleDetailResponse,
    CircleLedgerItemResponse,
    CircleMemberResponse,
    CirclePayoutResponse,
    CircleRecordsResponse,
    CircleResponse,
    CircleStatementResponse,
    PingResponse,
)
from app.modules.ledger.service import LedgerService
from app.modules.payments.registry import PaymentRailRegistry, default_registry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService
from app.modules.payments.types import CollectionRequest, PaymentFlow, PayoutRequest

CIRCLE_STATES = frozenset(
    {
        "draft",
        "recruiting",
        "agreement_pending",
        "locked",
        "draw_pending",
        "active",
        "completed",
        "cancelled",
    }
)
PLATFORM_SETTLEMENT_ACCOUNT_CODE = "platform:settlement:gbp"
STATE_TRANSITIONS = {
    "draft": {"recruiting", "cancelled"},
    "recruiting": {"agreement_pending", "cancelled"},
    "agreement_pending": {"locked", "cancelled"},
    "locked": {"draw_pending", "cancelled"},
    "draw_pending": {"active", "cancelled"},
    "active": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}


@dataclass(frozen=True)
class CircleAccountCodes:
    collected: str
    arrears: str
    shortfall: str


@dataclass(frozen=True)
class CircleLedgerAccounts:
    collected_id: UUID
    arrears_id: UUID


class CirclesService:
    def __init__(
        self,
        repo: CirclesRepo,
        ledger_service: LedgerService | None = None,
        payments_service: PaymentsService | None = None,
        rail_registry: PaymentRailRegistry | None = None,
    ) -> None:
        self.repo = repo
        self.ledger_service = ledger_service
        self.payments_service = payments_service
        self.rail_registry = rail_registry

    async def ping(self) -> PingResponse:
        return PingResponse(module="circles", status=await self.repo.ping())

    async def create_circle(
        self,
        *,
        owner_member_id: UUID,
        name: str,
        contribution_amount_minor: int,
        member_count_target: int,
        cycle_count: int,
        cadence: str,
        start_date: date,
    ) -> CircleDetailResponse:
        validate_money(amount_minor=contribution_amount_minor, currency=GBP)
        if cycle_count != member_count_target:
            raise circle_error(
                422,
                "Invalid Circle Terms",
                "M2 requires cycle count to match target member count.",
                "invalid-cycle-count",
            )
        circle = Circle(
            owner_member_id=owner_member_id,
            name=name,
            state="recruiting",
            currency=GBP,
            contribution_amount_minor=contribution_amount_minor,
            member_count_target=member_count_target,
            cycle_count=cycle_count,
            cadence=cadence,
            start_date=start_date,
            terms={"payout_rule": "commit_reveal_order"},
        )
        membership = CircleMember(
            circle_id=circle.id,
            member_id=owner_member_id,
            role="owner",
            status="active",
            joined_at=utc_now(),
        )
        await self.repo.create_circle(circle, membership)
        return await self.detail_for_member(circle_id=circle.id, member_id=owner_member_id)

    async def list_for_member(self, *, member_id: UUID) -> list[CircleResponse]:
        circles = await self.repo.list_circles_for_member(member_id)
        return [await self.response(circle) for circle in circles]

    async def detail_for_member(self, *, circle_id: UUID, member_id: UUID) -> CircleDetailResponse:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        members = await self.repo.list_memberships(circle.id)
        base = await self.response(circle)
        return CircleDetailResponse(
            **base.model_dump(),
            members=[
                CircleMemberResponse(
                    member_id=membership.member_id,
                    role=membership.role,
                    status=membership.status,
                    joined_at=membership.joined_at,
                )
                for membership in members
            ],
        )

    async def create_invite(
        self,
        *,
        circle_id: UUID,
        member_id: UUID,
        email: str | None,
        expires_in_days: int,
    ) -> CircleInvite:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"recruiting", "agreement_pending"})
        invite = CircleInvite(
            circle_id=circle.id,
            invited_by_member_id=member_id,
            token=secrets.token_urlsafe(32),
            email=email,
            status="pending",
            expires_at=utc_now() + timedelta(days=expires_in_days),
        )
        return await self.repo.create_invite(invite)

    async def join(self, *, token: str, member_id: UUID) -> CircleDetailResponse:
        invite = await self.repo.get_invite_by_token(token)
        if invite is None or invite.status != "pending":
            raise circle_error(404, "Not Found", "Circle invite was not found.", "invite-not-found")
        if invite.expires_at < utc_now():
            invite.status = "expired"
            raise circle_error(410, "Invite Expired", "Circle invite has expired.", "invite-expired")
        circle = await self.require_circle(invite.circle_id)
        ensure_state(circle, {"recruiting", "agreement_pending"})
        existing = await self.repo.get_membership(circle_id=circle.id, member_id=member_id)
        if existing is None:
            if await self.repo.count_members(circle.id) >= circle.member_count_target:
                raise circle_error(409, "Circle Full", "Circle already has the target member count.", "circle-full")
            await self.repo.add_member(
                CircleMember(
                    circle_id=circle.id,
                    member_id=member_id,
                    role="member",
                    status="active",
                    joined_at=utc_now(),
                )
            )
        invite.status = "accepted"
        invite.accepted_by_member_id = member_id
        invite.accepted_at = utc_now()
        if await self.repo.count_members(circle.id) >= circle.member_count_target:
            transition(circle, "agreement_pending")
        return await self.detail_for_member(circle_id=circle.id, member_id=member_id)

    async def agree(
        self,
        *,
        circle_id: UUID,
        member_id: UUID,
        contribution_amount_minor: int,
        cadence: str,
        start_date: date,
        payout_rules: dict[str, object],
    ) -> CircleAgreement:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"recruiting", "agreement_pending"})
        if contribution_amount_minor != circle.contribution_amount_minor:
            raise circle_error(422, "Terms Mismatch", "Agreement contribution amount must match circle terms.", "terms-mismatch")
        if cadence != circle.cadence or start_date != circle.start_date:
            raise circle_error(422, "Terms Mismatch", "Agreement cadence and start date must match circle terms.", "terms-mismatch")
        existing = await self.repo.get_agreement(circle_id=circle.id, member_id=member_id)
        if existing is not None:
            return existing
        agreement = CircleAgreement(
            circle_id=circle.id,
            member_id=member_id,
            contribution_amount_minor=contribution_amount_minor,
            cadence=cadence,
            start_date=start_date,
            payout_rules=payout_rules,
            accepted_at=utc_now(),
        )
        return await self.repo.save_agreement(agreement)

    async def list_agreements(self, *, circle_id: UUID, member_id: UUID) -> list[CircleAgreement]:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        return await self.repo.list_agreements(circle.id)

    async def lock(self, *, circle_id: UUID, member_id: UUID) -> CircleDetailResponse:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"agreement_pending"})
        member_count = await self.repo.count_members(circle.id)
        agreement_count = await self.repo.count_agreements(circle.id)
        if member_count != circle.member_count_target or agreement_count != member_count:
            raise circle_error(409, "Circle Not Ready", "All target members must join and agree before lock.", "circle-not-ready")
        await self.ensure_circle_accounts(circle.id)
        transition(circle, "locked")
        circle.locked_at = utc_now()
        transition(circle, "draw_pending")
        return await self.detail_for_member(circle_id=circle.id, member_id=member_id)

    async def commit_draw(self, *, circle_id: UUID, member_id: UUID, commitment_hash: str) -> CircleDraw:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"draw_pending"})
        existing = await self.repo.get_draw(circle.id)
        if existing is not None:
            return existing
        return await self.repo.save_draw(CircleDraw(circle_id=circle.id, commitment_hash=commitment_hash))

    async def reveal_draw(self, *, circle_id: UUID, member_id: UUID, salt: str) -> CircleDraw:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"draw_pending"})
        draw = await self.repo.get_draw(circle.id)
        if draw is None:
            raise circle_error(409, "Draw Not Committed", "Commit draw before reveal.", "draw-not-committed")
        memberships = await self.repo.list_memberships(circle.id)
        member_ids = [membership.member_id for membership in memberships]
        expected_hash = draw_commitment_hash(circle_id=circle.id, member_ids=member_ids, salt=salt)
        if expected_hash != draw.commitment_hash:
            raise circle_error(422, "Invalid Draw Reveal", "Reveal salt does not match draw commitment.", "invalid-draw-reveal")
        payout_order = deterministic_payout_order(circle_id=circle.id, member_ids=member_ids, salt=salt)
        draw.salt = salt
        draw.payout_order = [str(member_id) for member_id in payout_order]
        draw.revealed_at = utc_now()
        await self.generate_schedule(circle=circle, payout_order=payout_order)
        transition(circle, "active")
        return draw

    async def get_draw_for_member(self, *, circle_id: UUID, member_id: UUID) -> CircleDraw | None:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        return await self.repo.get_draw(circle.id)

    async def collect_due(self, *, circle_id: UUID, member_id: UUID, now: datetime | None = None) -> list[CircleContribution]:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"active"})
        due = await self.repo.list_due_contributions(circle_id=circle.id, now=now or utc_now())
        for contribution in due:
            await self.collect_contribution(contribution)
        return due

    async def list_contributions(self, *, circle_id: UUID, member_id: UUID) -> list[CircleContributionResponse]:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        contributions = await self.repo.list_contributions(circle.id)
        return [
            CircleContributionResponse(
                id=item.id,
                cycle_id=item.cycle_id,
                member_id=item.member_id,
                amount_minor=item.amount_minor,
                status=item.status,
                due_date=item.due_date,
                payment_object_id=item.payment_object_id,
            )
            for item in contributions
        ]

    async def execute_payout(self, *, circle_id: UUID, cycle_id: UUID, member_id: UUID) -> CirclePayoutResponse:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        ensure_state(circle, {"active"})
        cycle = await self.repo.get_cycle(circle_id=circle.id, cycle_id=cycle_id)
        if cycle is None:
            raise circle_error(404, "Not Found", "Circle cycle was not found.", "cycle-not-found")
        existing = await self.repo.get_payout_for_cycle(cycle.id)
        if existing is not None:
            return payout_response(existing)
        contributions = [item for item in await self.repo.list_contributions(circle.id) if item.cycle_id == cycle.id]
        collected_minor = sum(item.amount_minor for item in contributions if item.status == "paid")
        expected_minor = circle.contribution_amount_minor * len(contributions)
        shortfall_minor = max(expected_minor - collected_minor, 0)
        if collected_minor <= 0:
            raise circle_error(409, "No Collected Funds", "Cycle has no collected funds to pay out.", "no-collected-funds")
        payment_object = await self.require_payments_service().create_payout_object(
            self.require_registry().for_flow(PaymentFlow.PAYOUT),
            PayoutRequest(
                idempotency_key=f"circle:{circle.id}:cycle:{cycle.id}:payout",
                user_id=str(cycle.recipient_member_id),
                amount_minor=collected_minor,
                currency=GBP,
            ),
        )
        if payment_object.provider != "fake":
            payout = await self.repo.save_payout(
                CirclePayout(
                    circle_id=circle.id,
                    cycle_id=cycle.id,
                    recipient_member_id=cycle.recipient_member_id,
                    amount_minor=collected_minor,
                    shortfall_minor=shortfall_minor,
                    status="processing",
                    payment_object_id=payment_object.id,
                )
            )
            return payout_response(payout)
        accounts = await self.ensure_circle_accounts(circle.id)
        platform = await self.require_ledger_service().get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
        if platform is None:
            raise circle_error(500, "Ledger Account Missing", "Platform settlement account is missing.", "ledger-account-missing")
        posted = await self.require_ledger_service().post_entry(
            idempotency_key=f"circle:{circle.id}:cycle:{cycle.id}:payout:ledger",
            description=f"Circle payout cycle {cycle.position}",
            postings=[
                PostingInput(account_id=accounts.collected_id, side=PostingSide.DEBIT, amount_minor=collected_minor),
                PostingInput(account_id=platform.id, side=PostingSide.CREDIT, amount_minor=collected_minor),
            ],
        )
        await self.require_payments_service().attach_journal_entry(
            payment_object=payment_object,
            journal_entry_id=posted.journal_entry.id,
        )
        payout = await self.repo.save_payout(
            CirclePayout(
                circle_id=circle.id,
                cycle_id=cycle.id,
                recipient_member_id=cycle.recipient_member_id,
                amount_minor=collected_minor,
                shortfall_minor=shortfall_minor,
                status="paid",
                payment_object_id=payment_object.id,
                journal_entry_id=posted.journal_entry.id,
            )
        )
        if shortfall_minor > 0:
            await self.repo.save_shortfall(
                CircleShortfallRecord(
                    circle_id=circle.id,
                    cycle_id=cycle.id,
                    payout_id=payout.id,
                    amount_minor=shortfall_minor,
                    reason="cycle_payout_shortfall",
                )
            )
        cycle.status = "paid_out"
        return payout_response(payout)

    async def settle_payout_if_ready(
        self,
        *,
        provider: str,
        provider_object_id: str,
    ) -> CirclePayout | None:
        payment_object = await PaymentsRepo(self.repo.require_session()).get_payment_object(
            provider=provider,
            provider_object_id=provider_object_id,
        )
        if payment_object is None or payment_object.flow != PaymentFlow.PAYOUT.value:
            return None
        payout = await self.repo.get_payout_by_payment_object_id(payment_object.id)
        if payout is None:
            return None
        if payment_object.state == "settled":
            await self._settle_circle_payout(payout=payout)
            if payout.journal_entry_id is not None and payment_object.journal_entry_id is None:
                await self.require_payments_service().attach_journal_entry(
                    payment_object=payment_object,
                    journal_entry_id=payout.journal_entry_id,
                )
            return payout
        if payment_object.state == "failed":
            payout.status = "failed"
            return payout
        return None

    async def _settle_circle_payout(
        self,
        *,
        payout: CirclePayout,
    ) -> None:
        if payout.status == "paid" and payout.journal_entry_id is not None:
            return
        cycle = await self.repo.get_cycle(circle_id=payout.circle_id, cycle_id=payout.cycle_id)
        if cycle is None:
            return
        accounts = await self.ensure_circle_accounts(payout.circle_id)
        platform = await self.require_ledger_service().get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
        if platform is None:
            raise circle_error(500, "Ledger Account Missing", "Platform settlement account is missing.", "ledger-account-missing")
        posted = await self.require_ledger_service().post_entry(
            idempotency_key=f"circle:{payout.circle_id}:cycle:{payout.cycle_id}:payout:ledger",
            description=f"Circle payout cycle {cycle.position}",
            postings=[
                PostingInput(account_id=accounts.collected_id, side=PostingSide.DEBIT, amount_minor=payout.amount_minor),
                PostingInput(account_id=platform.id, side=PostingSide.CREDIT, amount_minor=payout.amount_minor),
            ],
        )
        payout.journal_entry_id = posted.journal_entry.id
        payout.status = "paid"
        cycle.status = "paid_out"
        if payout.shortfall_minor > 0:
            await self.repo.save_shortfall(
                CircleShortfallRecord(
                    circle_id=payout.circle_id,
                    cycle_id=payout.cycle_id,
                    payout_id=payout.id,
                    amount_minor=payout.shortfall_minor,
                    reason="cycle_payout_shortfall",
                )
            )

    async def inject_late_failure(self, *, circle_id: UUID, contribution_id: UUID, member_id: UUID) -> CircleContributionResponse:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        contribution = await self.repo.get_contribution(contribution_id)
        if contribution is None or contribution.circle_id != circle.id:
            raise circle_error(404, "Not Found", "Circle contribution was not found.", "contribution-not-found")
        if contribution.status != "paid":
            raise circle_error(409, "Invalid Contribution State", "Only paid contributions can fail late.", "invalid-contribution-state")
        accounts = await self.ensure_circle_accounts(circle.id)
        platform = await self.require_ledger_service().get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
        if platform is None:
            raise circle_error(500, "Ledger Account Missing", "Platform settlement account is missing.", "ledger-account-missing")
        posted = await self.require_ledger_service().post_entry(
            idempotency_key=f"circle:{circle.id}:contribution:{contribution.id}:failed-late",
            description="Circle contribution failed late",
            postings=[
                PostingInput(account_id=accounts.arrears_id, side=PostingSide.DEBIT, amount_minor=contribution.amount_minor),
                PostingInput(account_id=platform.id, side=PostingSide.CREDIT, amount_minor=contribution.amount_minor),
            ],
        )
        contribution.status = "late_failed"
        contribution.late_failure_journal_entry_id = posted.journal_entry.id
        await self.repo.save_arrears(
            CircleArrearsRecord(
                circle_id=circle.id,
                cycle_id=contribution.cycle_id,
                contribution_id=contribution.id,
                member_id=contribution.member_id,
                amount_minor=contribution.amount_minor,
                reason="failed_late",
            )
        )
        await self.repo.save_shortfall(
            CircleShortfallRecord(
                circle_id=circle.id,
                cycle_id=contribution.cycle_id,
                amount_minor=contribution.amount_minor,
                reason="failed_late",
            )
        )
        return CircleContributionResponse(
            id=contribution.id,
            cycle_id=contribution.cycle_id,
            member_id=contribution.member_id,
            amount_minor=contribution.amount_minor,
            status=contribution.status,
            due_date=contribution.due_date,
            payment_object_id=contribution.payment_object_id,
        )

    async def ledger_for_member(self, *, circle_id: UUID, member_id: UUID) -> list[CircleLedgerItemResponse]:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        codes = circle_account_codes(circle.id)
        rows = await self.require_ledger_service().list_account_activity(
            account_codes=[codes.collected, codes.arrears, codes.shortfall],
            limit=100,
        )
        return [
            CircleLedgerItemResponse(
                posting_id=row.posting_id,
                journal_entry_id=row.journal_entry_id,
                created_at=row.journal_created_at,
                account_code=row.account_code,
                description=row.journal_description,
                amount_minor=row.amount_minor,
                side=row.side,
            )
            for row in rows
        ]

    async def statement_for_member(self, *, circle_id: UUID, member_id: UUID, period: str) -> CircleStatementResponse:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        start, end = parse_period(period)
        codes = circle_account_codes(circle.id)
        statement = await self.require_ledger_service().account_statement(
            account_codes=[codes.collected, codes.arrears, codes.shortfall],
            period_start=start,
            period_end=end,
        )
        return CircleStatementResponse(
            period=period,
            currency=GBP,
            opening_balance_minor=statement.opening_balance_minor,
            movement_minor=statement.movement_minor,
            closing_balance_minor=statement.closing_balance_minor,
            journal_entry_ids=statement.journal_entry_ids,
        )

    async def records_for_member(self, *, circle_id: UUID, member_id: UUID) -> CircleRecordsResponse:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        arrears_count, shortfall_count, arrears_minor, shortfall_minor = await self.repo.records_summary(circle.id)
        return CircleRecordsResponse(
            arrears_count=arrears_count,
            shortfall_count=shortfall_count,
            arrears_minor=arrears_minor,
            shortfall_minor=shortfall_minor,
        )

    async def complete(self, *, circle_id: UUID, member_id: UUID) -> CircleDetailResponse:
        circle = await self.require_owner_circle(circle_id=circle_id, member_id=member_id)
        if circle.state == "completed":
            return await self.detail_for_member(circle_id=circle.id, member_id=member_id)
        ensure_state(circle, {"active"})
        cycles = await self.repo.list_cycles(circle.id)
        if any(cycle.status not in {"paid_out", "completed"} for cycle in cycles):
            raise circle_error(409, "Circle Not Complete", "Every cycle must be paid out before completion.", "circle-not-complete")
        transition(circle, "completed")
        circle.completed_at = utc_now()
        return await self.detail_for_member(circle_id=circle.id, member_id=member_id)

    async def response(self, circle: Circle) -> CircleResponse:
        return CircleResponse(
            id=circle.id,
            name=circle.name,
            state=circle.state,
            currency=circle.currency,
            contribution_amount_minor=circle.contribution_amount_minor,
            member_count_target=circle.member_count_target,
            cycle_count=circle.cycle_count,
            cadence=circle.cadence,
            start_date=circle.start_date,
            owner_member_id=circle.owner_member_id,
            member_count=await self.repo.count_members(circle.id),
            agreed_count=await self.repo.count_agreements(circle.id),
            created_at=circle.created_at,
            locked_at=circle.locked_at,
            completed_at=circle.completed_at,
        )

    async def collect_contribution(self, contribution: CircleContribution) -> None:
        payment_object = await self.require_payments_service().create_collection_object(
            self.require_registry().for_flow(PaymentFlow.COLLECTION),
            CollectionRequest(
                idempotency_key=f"circle:{contribution.circle_id}:contribution:{contribution.id}:collection",
                mandate_id=f"fake_mandate:{contribution.member_id}",
                amount_minor=contribution.amount_minor,
                currency=GBP,
            ),
        )
        accounts = await self.ensure_circle_accounts(contribution.circle_id)
        platform = await self.require_ledger_service().get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
        if platform is None:
            raise circle_error(500, "Ledger Account Missing", "Platform settlement account is missing.", "ledger-account-missing")
        posted = await self.require_ledger_service().post_entry(
            idempotency_key=f"circle:{contribution.circle_id}:contribution:{contribution.id}:collection:ledger",
            description="Circle contribution collected",
            postings=[
                PostingInput(account_id=platform.id, side=PostingSide.DEBIT, amount_minor=contribution.amount_minor),
                PostingInput(account_id=accounts.collected_id, side=PostingSide.CREDIT, amount_minor=contribution.amount_minor),
            ],
        )
        await self.require_payments_service().attach_journal_entry(
            payment_object=payment_object,
            journal_entry_id=posted.journal_entry.id,
        )
        contribution.payment_object_id = payment_object.id
        contribution.collected_journal_entry_id = posted.journal_entry.id
        contribution.status = "paid"

    async def generate_schedule(self, *, circle: Circle, payout_order: list[UUID]) -> None:
        if await self.repo.list_cycles(circle.id):
            return
        for index, recipient_member_id in enumerate(payout_order, start=1):
            due_date = add_months(circle.start_date, index - 1)
            cycle = await self.repo.save_cycle(
                CircleCycle(
                    circle_id=circle.id,
                    position=index,
                    recipient_member_id=recipient_member_id,
                    due_date=due_date,
                    status="scheduled",
                )
            )
            for membership in await self.repo.list_memberships(circle.id):
                await self.repo.save_contribution(
                    CircleContribution(
                        circle_id=circle.id,
                        cycle_id=cycle.id,
                        member_id=membership.member_id,
                        amount_minor=circle.contribution_amount_minor,
                        status="due",
                        due_date=due_date,
                    )
                )

    async def ensure_circle_accounts(self, circle_id: UUID) -> CircleLedgerAccounts:
        ledger = self.require_ledger_service()
        codes = circle_account_codes(circle_id)
        platform = await ledger.ensure_account(
            code=PLATFORM_SETTLEMENT_ACCOUNT_CODE,
            name="Platform settlement GBP",
            account_type=AccountType.ASSET,
        )
        collected = await ledger.ensure_account(
            code=codes.collected,
            name=f"Circle {circle_id} collected funds GBP",
            account_type=AccountType.LIABILITY,
        )
        arrears = await ledger.ensure_account(
            code=codes.arrears,
            name=f"Circle {circle_id} arrears GBP",
            account_type=AccountType.ASSET,
        )
        shortfall = await ledger.ensure_account(
            code=codes.shortfall,
            name=f"Circle {circle_id} shortfall GBP",
            account_type=AccountType.EXPENSE,
        )
        _ = platform, shortfall

        return CircleLedgerAccounts(collected_id=collected.id, arrears_id=arrears.id)

    async def require_circle(self, circle_id: UUID) -> Circle:
        circle = await self.repo.get_circle(circle_id)
        if circle is None:
            raise circle_error(404, "Not Found", "Circle was not found.", "circle-not-found")
        return circle

    async def require_member_circle(self, *, circle_id: UUID, member_id: UUID) -> Circle:
        circle = await self.require_circle(circle_id)
        membership = await self.repo.get_membership(circle_id=circle_id, member_id=member_id)
        if membership is None:
            raise circle_error(403, "Forbidden", "You are not a member of this circle.", "circle-forbidden")
        return circle

    async def require_owner_circle(self, *, circle_id: UUID, member_id: UUID) -> Circle:
        circle = await self.require_member_circle(circle_id=circle_id, member_id=member_id)
        membership = await self.repo.get_membership(circle_id=circle_id, member_id=member_id)
        if membership is None or membership.role != "owner":
            raise circle_error(403, "Forbidden", "Only the circle owner can perform this action.", "circle-owner-required")
        return circle

    def require_ledger_service(self) -> LedgerService:
        if self.ledger_service is None:
            raise RuntimeError("LedgerService is required.")
        return self.ledger_service

    def require_payments_service(self) -> PaymentsService:
        if self.payments_service is None:
            raise RuntimeError("PaymentsService is required.")
        return self.payments_service

    def require_registry(self) -> PaymentRailRegistry:
        if self.rail_registry is None:
            self.rail_registry = default_registry()
        return self.rail_registry


def get_circles_service(session: AsyncSession) -> CirclesService:
    return CirclesService(
        CirclesRepo(session),
        LedgerService(session),
        PaymentsService(PaymentsRepo(session)),
        default_registry(),
    )


def circle_account_codes(circle_id: UUID) -> CircleAccountCodes:
    return CircleAccountCodes(
        collected=f"circle:{circle_id}:collected:gbp",
        arrears=f"circle:{circle_id}:arrears:gbp",
        shortfall=f"circle:{circle_id}:shortfall:gbp",
    )


def transition(circle: Circle, next_state: str) -> None:
    if next_state not in STATE_TRANSITIONS[circle.state]:
        raise circle_error(
            409,
            "Invalid Circle State Transition",
            f"Cannot transition circle from {circle.state} to {next_state}.",
            "invalid-state-transition",
        )
    circle.state = next_state


def ensure_state(circle: Circle, allowed: set[str]) -> None:
    if circle.state not in allowed:
        raise circle_error(
            409,
            "Invalid Circle State",
            f"Circle state {circle.state} does not allow this action.",
            "invalid-circle-state",
        )


def validate_money(*, amount_minor: int, currency: str) -> None:
    if currency != GBP or amount_minor <= 0:
        raise circle_error(422, "Invalid Money", "Circle money paths support positive GBP minor units only.", "invalid-money")


def draw_commitment_hash(*, circle_id: UUID, member_ids: list[UUID], salt: str) -> str:
    canonical_members = ",".join(sorted(str(member_id) for member_id in member_ids))
    payload = f"{circle_id}:{canonical_members}:{salt}"
    return hashlib.sha256(payload.encode()).hexdigest()


def deterministic_payout_order(*, circle_id: UUID, member_ids: list[UUID], salt: str) -> list[UUID]:
    return sorted(
        member_ids,
        key=lambda member_id: hashlib.sha256(f"{circle_id}:{member_id}:{salt}".encode()).hexdigest(),
    )


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, month_lengths[month - 1])
    return date(year, month, day)


def parse_period(period: str) -> tuple[datetime, datetime]:
    try:
        year_text, month_text = period.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        start = datetime(year, month, 1, tzinfo=UTC)
    except ValueError as exc:
        raise circle_error(422, "Invalid Period", "Period must use YYYY-MM format.", "invalid-period") from exc
    end_date = add_months(start.date(), 1)
    return start, datetime(end_date.year, end_date.month, end_date.day, tzinfo=UTC)


def payout_response(payout: CirclePayout) -> CirclePayoutResponse:
    return CirclePayoutResponse(
        id=payout.id,
        circle_id=payout.circle_id,
        cycle_id=payout.cycle_id,
        recipient_member_id=payout.recipient_member_id,
        amount_minor=payout.amount_minor,
        shortfall_minor=payout.shortfall_minor,
        status=payout.status,
        payment_object_id=payout.payment_object_id,
        journal_entry_id=payout.journal_entry_id,
    )


def circle_error(status_code: int, title: str, detail: str, code: str) -> AppError:
    return AppError(
        status_code=status_code,
        title=title,
        detail=detail,
        type_=f"https://ajo.dev/problems/circle-{code}",
    )
