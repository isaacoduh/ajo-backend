from collections.abc import AsyncIterator

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


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


async def create_member_user(
    db_session: AsyncSession,
    *,
    email: str = "me@example.com",
    display_name: str | None = "Ada Adebayo",
    screening_state: str = "clear",
) -> tuple[User, Member]:
    user = User(email=email, password_hash="hash")
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name=display_name,
        country="GB",
        screening_state=screening_state,
    )
    db_session.add(member)
    await db_session.flush()
    return user, member


@pytest.mark.asyncio
async def test_auth_me_requires_bearer_access_token(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_auth_me_returns_user_and_member_profile(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/me", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "email": "me@example.com",
        "member_id": str(member.id),
        "display_name": "Ada Adebayo",
        "screening_state": "clear",
    }


@pytest.mark.asyncio
async def test_auth_me_does_not_require_idempotency_key(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(
        db_session,
        email="no-idempotency@example.com",
        display_name=None,
        screening_state="pending",
    )
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/me", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == {
        "email": "no-idempotency@example.com",
        "member_id": str(member.id),
        "display_name": None,
        "screening_state": "pending",
    }
