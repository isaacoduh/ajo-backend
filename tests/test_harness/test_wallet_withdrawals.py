from uuid import UUID, uuid4

import pytest
from app.core.errors import AppError
from app.db.ledger import PostingInput, PostingSide
from app.modules.identity.models import User
from app.modules.ledger.models import JournalEntry
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.payments.fake_rail import FakeRail
from app.modules.payments.models import PaymentObject
from app.modules.payments.registry import PaymentRailRegistry
from app.modules.payments.repo import PaymentsRepo
from app.modules.payments.service import PaymentsService
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import (
    PLATFORM_SETTLEMENT_ACCOUNT_CODE,
    WalletService,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_member_user(db_session: AsyncSession, *, email: str) -> tuple[User, Member]:
    user = User(email=email, password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name=email,
        country="GB",
        screening_state="clear",
    )
    db_session.add(member)
    await db_session.flush()
    return user, member


def wallet_service(db_session: AsyncSession) -> WalletService:
    return WalletService(
        WalletsRepo(db_session),
        LedgerService(db_session),
        PaymentsService(PaymentsRepo(db_session)),
        PaymentRailRegistry({"fake": FakeRail()}),
    )


async def seed_available_balance(
    service: WalletService,
    *,
    member_id: UUID,
    amount_minor: int,
) -> None:
    wallet = await service.ensure_for_member(member_id=member_id)
    platform = await service.ledger_service.get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
    available = await service.ledger_service.get_account_by_code(wallet.available_account_code)
    assert platform is not None
    assert available is not None
    await service.ledger_service.post_entry(
        idempotency_key=f"seed-available-{member_id}-{amount_minor}",
        description="Seed available wallet balance",
        postings=[
            PostingInput(
                account_id=platform.id,
                side=PostingSide.DEBIT,
                amount_minor=amount_minor,
            ),
            PostingInput(
                account_id=available.id,
                side=PostingSide.CREDIT,
                amount_minor=amount_minor,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_wallet_withdrawal_moves_available_to_pending(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw@example.com")
    service = wallet_service(db_session)
    await seed_available_balance(service, member_id=member.id, amount_minor=5000)

    result = await service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1500,
        currency="GBP",
        idempotency_key="wallet-withdrawal-1",
    )

    wallet = await service.ensure_for_member(member_id=member.id)
    pending = await service.ledger_service.get_account_by_code(wallet.pending_account_code)
    available = await service.ledger_service.get_account_by_code(wallet.available_account_code)
    payment_object = await db_session.get(PaymentObject, result.id)

    assert result.amount_minor == 1500
    assert result.currency == "GBP"
    assert result.state == "initiated"
    assert result.journal_entry_id is not None
    assert payment_object is not None
    assert payment_object.flow == "payout"
    assert payment_object.journal_entry_id == result.journal_entry_id
    assert pending is not None
    assert available is not None
    assert available.balance_minor == 3500
    assert pending.balance_minor == 1500


@pytest.mark.asyncio
async def test_wallet_withdrawal_rejects_insufficient_available_balance(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-insufficient@example.com")
    service = wallet_service(db_session)
    await seed_available_balance(service, member_id=member.id, amount_minor=500)

    with pytest.raises(AppError) as exc_info:
        await service.create_withdrawal(
            member_id=member.id,
            user_id=user.id,
            amount_minor=1500,
            currency="GBP",
            idempotency_key="wallet-withdrawal-insufficient",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.type == "https://ajo.dev/problems/insufficient-wallet-funds"


@pytest.mark.asyncio
async def test_wallet_withdrawal_retry_returns_same_payment_object_without_reposting(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-retry@example.com")
    service = wallet_service(db_session)
    await seed_available_balance(service, member_id=member.id, amount_minor=5000)

    first = await service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1200,
        currency="GBP",
        idempotency_key="wallet-withdrawal-retry",
    )
    second = await service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1200,
        currency="GBP",
        idempotency_key="wallet-withdrawal-retry",
    )

    journal_count = await db_session.scalar(select(func.count()).select_from(JournalEntry))

    assert second.id == first.id
    assert second.journal_entry_id == first.journal_entry_id
    assert journal_count == 2


@pytest.mark.asyncio
async def test_wallet_withdrawal_rejects_idempotency_key_reuse_with_different_amount(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-conflict@example.com")
    service = wallet_service(db_session)
    await seed_available_balance(service, member_id=member.id, amount_minor=5000)

    await service.create_withdrawal(
        member_id=member.id,
        user_id=user.id,
        amount_minor=1200,
        currency="GBP",
        idempotency_key="wallet-withdrawal-conflict",
    )

    with pytest.raises(AppError) as exc_info:
        await service.create_withdrawal(
            member_id=member.id,
            user_id=user.id,
            amount_minor=1300,
            currency="GBP",
            idempotency_key="wallet-withdrawal-conflict",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_wallet_withdrawal_rejects_non_gbp_currency(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-currency@example.com")
    service = wallet_service(db_session)

    with pytest.raises(AppError) as exc_info:
        await service.create_withdrawal(
            member_id=member.id,
            user_id=user.id,
            amount_minor=1200,
            currency="USD",
            idempotency_key=str(uuid4()),
        )

    assert exc_info.value.status_code == 422
