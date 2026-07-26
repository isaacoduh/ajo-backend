"""Seed local M1 demo data."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.ledger import PostingInput, PostingSide
from app.db.session import session_scope
from app.modules.identity.models import User
from app.modules.ledger.models import JournalEntry
from app.modules.ledger.service import LedgerService
from app.modules.members.repo import MembersRepo
from app.modules.members.service import MembersService
from app.modules.payments.models import PaymentObject
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService
from app.modules.payments.types import SettlementState
from app.modules.screening.models import ScreeningResult
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import WalletService

SEED_EMAIL = "m1.verified.member@example.com"
SEED_PASSWORD = "correct horse battery staple"
SEED_TOPUP_KEY = "seed:m1:wallet:topup"
SEED_TOPUP_SETTLED_KEY = "seed:m1:wallet:topup:settled"
SEED_WITHDRAWAL_KEY = "seed:m1:wallet:withdrawal"


@dataclass(frozen=True)
class SeedSummary:
    user_id: UUID
    member_id: UUID
    available_minor: int
    pending_minor: int


async def seed_m1(session: AsyncSession) -> SeedSummary:
    user = await ensure_seed_user(session)
    await ensure_clear_screening_result(session, user=user)
    members_service = MembersService(MembersRepo(session))
    member = await members_service.ensure_for_user(
        user_id=user.id,
        display_name="M1 Verified Member",
        country="GB",
        screening_state="clear",
    )
    ledger_service = LedgerService(session)
    wallet_service = WalletService(
        WalletsRepo(session),
        ledger_service,
        PaymentsService(PaymentsRepo(session)),
    )

    topup = await wallet_service.create_topup(
        member_id=member.id,
        user_id=user.id,
        amount_minor=10_000,
        currency="GBP",
        idempotency_key=SEED_TOPUP_KEY,
    )
    await ensure_topup_settled(
        session,
        wallet_service=wallet_service,
        member_id=member.id,
        topup_payment_object_id=topup.id,
    )
    await wallet_service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=2_500,
        currency="GBP",
        idempotency_key=SEED_WITHDRAWAL_KEY,
    )
    balance = await wallet_service.balance_for_member(member_id=member.id)
    return SeedSummary(
        user_id=user.id,
        member_id=member.id,
        available_minor=balance.available_minor,
        pending_minor=balance.pending_minor,
    )


async def ensure_seed_user(session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.email == SEED_EMAIL))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email=SEED_EMAIL,
        password_hash=hash_password(SEED_PASSWORD),
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_clear_screening_result(session: AsyncSession, *, user: User) -> None:
    result = await session.execute(
        select(ScreeningResult).where(
            ScreeningResult.user_id == user.id,
            ScreeningResult.status == "clear",
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    session.add(
        ScreeningResult(
            user_id=user.id,
            provider="AlwaysClearScreening",
            subject_name=user.email,
            subject_country="GB",
            status="clear",
            hits=[],
        )
    )
    await session.flush()


async def ensure_topup_settled(
    session: AsyncSession,
    *,
    wallet_service: WalletService,
    member_id: UUID,
    topup_payment_object_id: UUID,
) -> None:
    if await journal_exists(session, idempotency_key=SEED_TOPUP_SETTLED_KEY):
        await mark_payment_settled(session, payment_object_id=topup_payment_object_id)
        return

    wallet = await wallet_service.ensure_for_member(member_id=member_id)
    pending_account = await wallet_service.ledger_service.get_account_by_code(
        wallet.pending_account_code
    )
    available_account = await wallet_service.ledger_service.get_account_by_code(
        wallet.available_account_code
    )
    if pending_account is None or available_account is None:
        raise RuntimeError("Seed wallet accounts were not provisioned.")

    await wallet_service.ledger_service.post_entry(
        idempotency_key=SEED_TOPUP_SETTLED_KEY,
        description="Seed wallet top-up settled",
        postings=[
            PostingInput(
                account_id=pending_account.id,
                side=PostingSide.DEBIT,
                amount_minor=10_000,
            ),
            PostingInput(
                account_id=available_account.id,
                side=PostingSide.CREDIT,
                amount_minor=10_000,
            ),
        ],
    )
    await mark_payment_settled(session, payment_object_id=topup_payment_object_id)


async def journal_exists(session: AsyncSession, *, idempotency_key: str) -> bool:
    result = await session.execute(
        select(JournalEntry.id).where(JournalEntry.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none() is not None


async def mark_payment_settled(session: AsyncSession, *, payment_object_id: UUID) -> None:
    payment_object = await session.get(PaymentObject, payment_object_id)
    if payment_object is None:
        return
    payment_object.state = SettlementState.SETTLED.value
    await session.flush()


async def async_main() -> None:
    async for session in session_scope():
        summary = await seed_m1(session)
        print(
            "Seeded M1 wallet demo: "
            f"user={summary.user_id} member={summary.member_id} "
            f"available_minor={summary.available_minor} pending_minor={summary.pending_minor}"
        )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
