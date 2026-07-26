import pytest
from app.modules.ledger.models import JournalEntry
from app.modules.payments.models import PaymentObject
from app.modules.screening.models import ScreeningResult
from app.tools.seed import SEED_EMAIL, seed_m1
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_m1_seed_creates_rerunnable_verified_member_wallet_history(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env

    first = await seed_m1(db_session)
    second = await seed_m1(db_session)

    journal_count = await db_session.scalar(select(func.count()).select_from(JournalEntry))
    payment_count = await db_session.scalar(select(func.count()).select_from(PaymentObject))
    screening_count = await db_session.scalar(select(func.count()).select_from(ScreeningResult))

    assert second == first
    assert first.available_minor == 7_500
    assert first.pending_minor == 2_500
    assert journal_count == 3
    assert payment_count == 2
    assert screening_count == 1


@pytest.mark.asyncio
async def test_m1_seed_statement_and_activity_are_useful(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    summary = await seed_m1(db_session)

    from app.modules.ledger.service import LedgerService
    from app.modules.wallets.repo import WalletsRepo
    from app.modules.wallets.service import WalletService

    wallet_service = WalletService(WalletsRepo(db_session), LedgerService(db_session))
    balance = await wallet_service.balance_for_member(member_id=summary.member_id)
    activity = await wallet_service.activity_for_member(
        member_id=summary.member_id,
        cursor=None,
        limit=10,
    )

    assert balance.available_minor == 7_500
    assert balance.pending_minor == 2_500
    assert len(activity.items) == 5
    assert {item.description for item in activity.items} == {
        "Wallet top-up initiated",
        "Seed wallet top-up settled",
        "Wallet withdrawal initiated",
    }


@pytest.mark.asyncio
async def test_m1_seed_uses_expected_demo_login(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    await seed_m1(db_session)

    from app.modules.identity.models import User

    user = (
        await db_session.execute(
            select(User).where(User.email == SEED_EMAIL),
        )
    ).scalar_one()

    assert user.email == "m1.verified.member@example.com"
