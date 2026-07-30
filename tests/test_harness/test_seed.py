import pytest
from app.core.config import get_settings
from app.modules.circles.models import Circle
from app.modules.identity.models import User
from app.modules.ledger.models import JournalEntry
from app.modules.payments.models import PaymentObject
from app.modules.screening.models import ScreeningResult
from app.tools.demo_reset import CONFIRMATION, reset_and_seed
from app.tools.demo_reset import async_main as demo_reset_async_main
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


@pytest.mark.asyncio
async def test_demo_reset_rebuilds_seeded_product_data(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    db_session.add(User(email="throwaway@example.com", password_hash="hash"))
    await db_session.flush()

    first = await reset_and_seed(db_session)
    second = await reset_and_seed(db_session)

    user_count = await db_session.scalar(select(func.count()).select_from(User))
    circle_count = await db_session.scalar(select(func.count()).select_from(Circle))
    journal_count = await db_session.scalar(select(func.count()).select_from(JournalEntry))

    assert first != second
    assert user_count == 9
    assert circle_count == 1
    assert journal_count == 3


@pytest.mark.asyncio
async def test_demo_reset_refuses_production_before_database_work(
    test_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = test_env
    monkeypatch.setenv("DEMO_RESET_CONFIRM", CONFIRMATION)
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()

    try:
        with pytest.raises(SystemExit) as exc_info:
            await demo_reset_async_main()
    finally:
        get_settings.cache_clear()

    assert exc_info.value.code == 2
