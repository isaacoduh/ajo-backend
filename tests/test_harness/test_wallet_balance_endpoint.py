from collections.abc import AsyncIterator

import httpx
import pytest
from app.core.security import create_access_token
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import User
from app.modules.ledger.service import LedgerService
from app.modules.members.models import Member
from app.modules.wallets.repo import WalletsRepo
from app.modules.wallets.service import WalletService
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


@pytest.mark.asyncio
async def test_wallet_balance_requires_auth(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/balance")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_wallet_balance_returns_zero_for_new_member_wallet(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session, email="wallet-zero@example.com")
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/balance", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "currency": "GBP",
        "available_minor": 0,
        "pending_minor": 0,
    }


@pytest.mark.asyncio
async def test_wallet_balance_reads_ledger_account_snapshot(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session, email="wallet-balance@example.com")
    wallet_service = WalletService(WalletsRepo(db_session), LedgerService(db_session))
    wallet = await wallet_service.ensure_for_member(member_id=member.id)
    pending_account = await wallet_service.ledger_service.get_account_by_code(
        wallet.pending_account_code
    )
    available_account = await wallet_service.ledger_service.get_account_by_code(
        wallet.available_account_code
    )
    assert pending_account is not None
    assert available_account is not None
    pending_account.balance_minor = 2500
    available_account.balance_minor = 10000
    await db_session.flush()

    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/wallet/balance", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "currency": "GBP",
        "available_minor": 10000,
        "pending_minor": 2500,
    }
