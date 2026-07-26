from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.security import create_access_token
from app.db.ledger import AccountType, PostingInput, PostingSide
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import (
    PLATFORM_SETTLEMENT_ACCOUNT_CODE,
    WalletService,
)
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession


def app_for_session(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


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


async def post_wallet_topup_pending(
    db_session: AsyncSession,
    *,
    member: Member,
    amount_minor: int,
    idempotency_key: str,
) -> None:
    ledger_service = LedgerService(db_session)
    wallet_service = WalletService(WalletsRepo(db_session), ledger_service)
    wallet = await wallet_service.ensure_for_member(member_id=member.id)
    platform = await ledger_service.get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
    pending = await ledger_service.get_account_by_code(wallet.pending_account_code)
    assert platform is not None
    assert pending is not None
    await ledger_service.post_entry(
        idempotency_key=idempotency_key,
        description=f"Wallet top-up pending {amount_minor}",
        postings=[
            PostingInput(
                account_id=platform.id,
                side=PostingSide.DEBIT,
                amount_minor=amount_minor,
            ),
            PostingInput(
                account_id=pending.id,
                side=PostingSide.CREDIT,
                amount_minor=amount_minor,
            ),
        ],
    )


async def post_non_wallet_activity(
    db_session: AsyncSession,
    *,
    amount_minor: int,
) -> None:
    ledger_service = LedgerService(db_session)
    platform = await ledger_service.ensure_account(
        code=PLATFORM_SETTLEMENT_ACCOUNT_CODE,
        name="Platform settlement GBP",
        account_type=AccountType.ASSET,
    )
    other = await ledger_service.ensure_account(
        code="test:other:liability:gbp",
        name="Other liability GBP",
        account_type=AccountType.LIABILITY,
    )
    await ledger_service.post_entry(
        idempotency_key="non-wallet-activity",
        description="Non-wallet activity",
        postings=[
            PostingInput(
                account_id=platform.id,
                side=PostingSide.DEBIT,
                amount_minor=amount_minor,
            ),
            PostingInput(
                account_id=other.id,
                side=PostingSide.CREDIT,
                amount_minor=amount_minor,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_wallet_activity_requires_auth(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/activity")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_wallet_activity_empty_for_new_wallet(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="activity-empty@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/activity", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None}


@pytest.mark.asyncio
async def test_wallet_activity_returns_wallet_journal_rows_only(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="activity-wallet@example.com")
    await post_wallet_topup_pending(
        db_session,
        member=member,
        amount_minor=2500,
        idempotency_key="wallet-activity-1",
    )
    await post_non_wallet_activity(db_session, amount_minor=9999)
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/activity", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["next_cursor"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["description"] == "Wallet top-up pending 2500"
    assert item["currency"] == "GBP"
    assert item["amount_minor"] == 2500
    assert item["direction"] == "increase"
    assert item["wallet_balance_bucket"] == "pending"
    assert item["journal_entry_id"]


@pytest.mark.asyncio
async def test_wallet_activity_invalid_cursor_returns_problem_json(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="activity-cursor@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/wallet/activity?cursor=not-a-cursor",
            headers=auth_headers(user),
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/invalid-wallet-activity-cursor"


@pytest.mark.asyncio
async def test_wallet_activity_paginates_with_cursor(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="activity-pages@example.com")
    await post_wallet_topup_pending(
        db_session,
        member=member,
        amount_minor=1000,
        idempotency_key="wallet-activity-page-1",
    )
    await post_wallet_topup_pending(
        db_session,
        member=member,
        amount_minor=2000,
        idempotency_key="wallet-activity-page-2",
    )
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.get("/wallet/activity?limit=1", headers=auth_headers(user))
        cursor = first.json()["next_cursor"]
        second = await client.get(f"/wallet/activity?limit=1&cursor={cursor}", headers=auth_headers(user))

    assert first.status_code == 200
    assert cursor
    assert second.status_code == 200
    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert len(first_ids) == 1
    assert len(second_ids) == 1
    assert first_ids.isdisjoint(second_ids)
