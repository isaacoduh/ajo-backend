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
        "user": {
            "id": str(user.id),
            "email": "me@example.com",
        },
        "member": {
            "id": str(member.id),
            "display_name": "Ada Adebayo",
            "country": "GB",
            "screening_state": "clear",
        },
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
        "user": {
            "id": str(user.id),
            "email": "no-idempotency@example.com",
        },
        "member": {
            "id": str(member.id),
            "display_name": None,
            "country": "GB",
            "screening_state": "pending",
        },
    }


@pytest.mark.asyncio
async def test_update_auth_me_updates_display_name(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/auth/me",
            headers={**auth_headers(user), "Idempotency-Key": "update-me-display-name"},
            json={"display_name": "  Ada   Lovelace  "},
        )

    assert response.status_code == 200
    assert response.json()["member"] == {
        "id": str(member.id),
        "display_name": "Ada Lovelace",
        "country": "GB",
        "screening_state": "clear",
    }


@pytest.mark.asyncio
async def test_update_auth_me_updates_supported_country(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/auth/me",
            headers={**auth_headers(user), "Idempotency-Key": "update-me-country"},
            json={"country": "gb"},
        )

    assert response.status_code == 200
    assert response.json()["member"] == {
        "id": str(member.id),
        "display_name": "Ada Adebayo",
        "country": "GB",
        "screening_state": "clear",
    }


@pytest.mark.asyncio
async def test_update_auth_me_rejects_unauthenticated_request(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/auth/me",
            headers={"Idempotency-Key": "update-me-unauthenticated"},
            json={"display_name": "Ada Lovelace"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_auth_me_rejects_forbidden_fields(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            "/auth/me",
            headers={**auth_headers(user), "Idempotency-Key": "update-me-forbidden"},
            json={
                "email": "new@example.com",
                "screening_state": "clear",
                "wallet_id": "not-allowed",
            },
        )

    assert response.status_code == 422
