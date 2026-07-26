from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.members.models import Member
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession


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


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


@pytest.mark.asyncio
async def test_statement_requires_auth(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/statements/{current_period()}")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_statement_returns_empty_period(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="statement-empty@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/statements/2099-01", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "period": "2099-01",
        "currency": "GBP",
        "opening_balance_minor": 0,
        "movement_minor": 0,
        "closing_balance_minor": 0,
        "journal_entry_ids": [],
    }


@pytest.mark.asyncio
async def test_statement_returns_active_period_movement_and_journal_refs(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="statement-active@example.com")
    period = current_period()
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        topup = await client.post(
            "/wallet/topups",
            json={"amount_minor": 2500, "currency": "GBP"},
            headers=auth_headers(user, idempotency_key="statement-topup"),
        )
        response = await client.get(f"/statements/{period}", headers=auth_headers(user))

    assert topup.status_code == 201
    assert response.status_code == 200
    body = response.json()
    assert body["period"] == period
    assert body["currency"] == "GBP"
    assert body["opening_balance_minor"] == 0
    assert body["movement_minor"] == 2500
    assert body["closing_balance_minor"] == 2500
    assert len(body["journal_entry_ids"]) == 1


@pytest.mark.asyncio
async def test_statement_invalid_period_returns_problem_json(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="statement-invalid@example.com")
    transport = httpx.ASGITransport(app=app_for_session(db_session))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/statements/2026-13", headers=auth_headers(user))

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"] == "https://ajo.dev/problems/invalid-statement-period"
