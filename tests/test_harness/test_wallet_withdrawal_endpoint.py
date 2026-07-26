from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.security import create_access_token
from app.db.ledger import PostingInput, PostingSide
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.ledger.models import JournalEntry
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import PLATFORM_SETTLEMENT_ACCOUNT_CODE, WalletService
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        _ = ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


def app_for_session(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


def auth_headers(user: User, *, idempotency_key: str | None = None) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


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


async def seed_available_balance(
    db_session: AsyncSession,
    *,
    member: Member,
    amount_minor: int,
) -> None:
    ledger_service = LedgerService(db_session)
    wallet_service = WalletService(WalletsRepo(db_session), ledger_service)
    wallet = await wallet_service.ensure_for_member(member_id=member.id)
    platform = await ledger_service.get_account_by_code(PLATFORM_SETTLEMENT_ACCOUNT_CODE)
    available = await ledger_service.get_account_by_code(wallet.available_account_code)
    assert platform is not None
    assert available is not None
    await ledger_service.post_entry(
        idempotency_key=f"endpoint-seed-available-{member.id}-{amount_minor}",
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
async def test_wallet_withdrawal_requires_idempotency_key(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="withdraw-key@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1000, "currency": "GBP"},
            headers=auth_headers(user),
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/idempotency-key-required"


@pytest.mark.asyncio
async def test_wallet_withdrawal_requires_auth(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1000, "currency": "GBP"},
            headers={"Idempotency-Key": "wallet-withdraw-auth"},
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_wallet_withdrawal_endpoint_creates_payout_and_reserves_balance(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-http@example.com")
    await seed_available_balance(db_session, member=member, amount_minor=5000)
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1500, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-withdraw-http"),
        )
        balance = await client.get("/wallet/balance", headers=auth_headers(user))

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["amount_minor"] == 1500
    assert body["currency"] == "GBP"
    assert body["state"] == "initiated"
    assert balance.status_code == 200
    assert balance.json() == {
        "currency": "GBP",
        "available_minor": 3500,
        "pending_minor": 1500,
    }


@pytest.mark.asyncio
async def test_wallet_withdrawal_insufficient_funds_returns_problem_json(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-low@example.com")
    await seed_available_balance(db_session, member=member, amount_minor=500)
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1500, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-withdraw-low"),
        )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/insufficient-wallet-funds"


@pytest.mark.asyncio
async def test_wallet_withdrawal_idempotency_replays_same_response_without_reposting(
    monkeypatch: pytest.MonkeyPatch,
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    store = InMemoryIdempotencyStore()
    monkeypatch.setattr("app.core.idempotency.get_redis", lambda: store)
    user, member = await create_member_user(db_session, email="withdraw-replay@example.com")
    await seed_available_balance(db_session, member=member, amount_minor=5000)
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1200, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-withdraw-replay"),
        )
        second = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1200, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-withdraw-replay"),
        )

    journal_count = await db_session.scalar(select(func.count()).select_from(JournalEntry))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.content == second.content
    assert journal_count == 2


@pytest.mark.asyncio
async def test_wallet_withdrawal_rejects_non_gbp_with_problem_json(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="withdraw-usd@example.com")
    await seed_available_balance(db_session, member=member, amount_minor=5000)
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/withdrawals",
            json={"amount_minor": 1000, "currency": "USD"},
            headers=auth_headers(user, idempotency_key="wallet-withdraw-usd"),
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/invalid-wallet-currency"
