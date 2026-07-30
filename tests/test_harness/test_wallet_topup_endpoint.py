from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.ledger.models import JournalEntry
from app.modules.members.models import Member
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


@pytest.mark.asyncio
async def test_wallet_topup_requires_idempotency_key(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="topup-key@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/topups",
            json={"amount_minor": 2500, "currency": "GBP"},
            headers=auth_headers(user),
        )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/idempotency-key-required"


@pytest.mark.asyncio
async def test_wallet_topup_requires_auth(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/topups",
            json={"amount_minor": 2500, "currency": "GBP"},
            headers={"Idempotency-Key": "wallet-topup-auth"},
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_wallet_topup_endpoint_creates_payment_and_pending_balance(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="topup-http@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/topups",
            json={"amount_minor": 2500, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-topup-http"),
        )
        balance = await client.get("/wallet/balance", headers=auth_headers(user))

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["amount_minor"] == 2500
    assert body["currency"] == "GBP"
    assert body["state"] == "initiated"
    assert body["provider_action"] is None
    assert balance.status_code == 200
    assert balance.json() == {
        "currency": "GBP",
        "available_minor": 0,
        "pending_minor": 2500,
    }


@pytest.mark.asyncio
async def test_wallet_topup_idempotency_replays_same_response_without_reposting(
    monkeypatch: pytest.MonkeyPatch,
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    store = InMemoryIdempotencyStore()
    monkeypatch.setattr("app.core.idempotency.get_redis", lambda: store)
    user, _member = await create_member_user(db_session, email="topup-replay@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/wallet/topups",
            json={"amount_minor": 1200, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-topup-replay"),
        )
        second = await client.post(
            "/wallet/topups",
            json={"amount_minor": 1200, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="wallet-topup-replay"),
        )

    journal_count = await db_session.scalar(select(func.count()).select_from(JournalEntry))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.content == second.content
    assert journal_count == 1


@pytest.mark.asyncio
async def test_wallet_topup_rejects_non_gbp_with_problem_json(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="topup-usd@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/wallet/topups",
            json={"amount_minor": 2500, "currency": "USD"},
            headers=auth_headers(user, idempotency_key="wallet-topup-usd"),
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/invalid-wallet-currency"
