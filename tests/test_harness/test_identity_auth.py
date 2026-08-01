from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    utc_now,
    verify_password,
)
from app.db.session import get_session
from app.main import create_app
from app.modules.identity.models import RefreshToken, User
from app.modules.identity.service import IdentityService
from app.modules.members.models import Member
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setenv("ARGON2_MEMORY_COST", "8192")
    get_settings.cache_clear()


@dataclass
class StoredRefreshToken:
    id: UUID
    user_id: UUID
    family_id: UUID
    token_hash: str
    expires_at: object
    used_at: object | None = None
    revoked_at: object | None = None
    replaced_by_token_id: UUID | None = None


class FakeIdentityRepo:
    def __init__(self, user: User) -> None:
        self.user = user
        self.tokens_by_hash: dict[str, StoredRefreshToken] = {}
        self.revoked_families: list[UUID] = []
        self.created_user: User | None = None
        self.revoked_user_tokens: list[UUID] = []

    async def create_user(self, *, email: str, password_hash: str) -> User:
        user = User(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            token_version=1,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.created_user = user
        self.user = user
        return user

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        if user_id == self.user.id:
            return self.user
        return None

    async def create_refresh_token(
        self,
        *,
        user_id: UUID,
        family_id: UUID,
        token_hash: str,
        expires_at: object,
    ) -> StoredRefreshToken:
        token = StoredRefreshToken(
            id=uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.tokens_by_hash[token_hash] = token
        return token

    async def get_refresh_token_by_hash(self, token_hash: str) -> StoredRefreshToken | None:
        return self.tokens_by_hash.get(token_hash)

    async def mark_refresh_token_used(
        self,
        *,
        token_id: UUID,
        used_at: object,
        replaced_by_token_id: UUID,
    ) -> None:
        _ = used_at
        for token in self.tokens_by_hash.values():
            if token.id == token_id:
                token.replaced_by_token_id = replaced_by_token_id

    async def revoke_refresh_family(self, *, family_id: UUID, revoked_at: object) -> None:
        self.revoked_families.append(family_id)
        for token in self.tokens_by_hash.values():
            if token.family_id == family_id:
                token.revoked_at = revoked_at

    async def revoke_user_refresh_tokens(self, *, user_id: UUID, revoked_at: object) -> None:
        self.revoked_user_tokens.append(user_id)
        for token in self.tokens_by_hash.values():
            if token.user_id == user_id:
                token.revoked_at = revoked_at

    async def bump_token_version(self, *, user_id: UUID, password_hash: str) -> User | None:
        if user_id != self.user.id:
            return None
        self.user.password_hash = password_hash
        self.user.token_version += 1
        self.user.password_changed_at = utc_now()
        return self.user


def app_for_session(db_session: AsyncSession) -> FastAPI:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}


class FakeScreeningService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def screen_person(
        self,
        *,
        user_id: UUID,
        name: str,
        dob: object | None,
        country: str,
    ) -> list[object]:
        self.calls.append({"user_id": user_id, "name": name, "dob": dob, "country": country})
        return []


class FakeMembersService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.member_id = uuid4()

    async def ensure_for_user(
        self,
        *,
        user_id: UUID,
        display_name: str | None = None,
        country: str = "GB",
        screening_state: str = "pending",
    ) -> object:
        self.calls.append(
            {
                "user_id": user_id,
                "display_name": display_name,
                "country": country,
                "screening_state": screening_state,
            }
        )
        return SimpleNamespace(id=self.member_id)


class FakeWalletService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def ensure_for_member(self, *, member_id: UUID) -> object:
        self.calls.append({"member_id": member_id})
        return object()


def make_user() -> User:
    return User(
        id=uuid4(),
        email="user@example.com",
        password_hash="hash",
        token_version=1,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


async def create_member_user(
    db_session: AsyncSession,
    *,
    email: str = "user@example.com",
    password: str = "correct horse battery staple",
) -> tuple[User, Member]:
    user = User(email=email, password_hash=hash_password(password))
    db_session.add(user)
    await db_session.flush()
    member = Member(
        user_id=user.id,
        display_name="Ada Adebayo",
        country="GB",
        screening_state="clear",
    )
    db_session.add(member)
    await db_session.flush()
    return user, member


def test_password_hash_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_refresh_token_hash_is_peppered(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)

    first = hash_refresh_token("refresh-token")
    second = hash_refresh_token("refresh-token")

    assert first == second
    assert first != "refresh-token"
    assert len(first) == 64


def test_access_token_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    user_id = uuid4()

    token = create_access_token(user_id=user_id, token_version=7)
    claims = decode_access_token(token)

    assert claims.user_id == user_id
    assert claims.token_version == 7


@pytest.mark.asyncio
async def test_refresh_rotates_token(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    user = make_user()
    repo = FakeIdentityRepo(user)
    service = IdentityService(repo)  # type: ignore[arg-type]
    token_pair = await service._issue_pair(user=user, family_id=uuid4())

    rotated = await service.refresh(refresh_token=token_pair.refresh_token)

    assert rotated.refresh_token != token_pair.refresh_token
    old_stored = repo.tokens_by_hash[hash_refresh_token(token_pair.refresh_token)]
    assert old_stored.replaced_by_token_id is not None
    assert repo.tokens_by_hash[hash_refresh_token(rotated.refresh_token)].family_id == old_stored.family_id


@pytest.mark.asyncio
async def test_refresh_reuse_revokes_family(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    user = make_user()
    repo = FakeIdentityRepo(user)
    service = IdentityService(repo)  # type: ignore[arg-type]
    token_pair = await service._issue_pair(user=user, family_id=uuid4())
    await service.refresh(refresh_token=token_pair.refresh_token)
    old_family = repo.tokens_by_hash[hash_refresh_token(token_pair.refresh_token)].family_id

    with pytest.raises(AppError):
        await service.refresh(refresh_token=token_pair.refresh_token)

    assert old_family in repo.revoked_families


@pytest.mark.asyncio
async def test_change_password_invalidates_old_tokens_and_allows_new_login(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    old_access_headers = auth_headers(user)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "change-password-login"},
            json={"email": user.email, "password": "correct horse battery staple"},
        )
        old_refresh_token = login_response.json()["refresh_token"]

        response = await client.post(
            "/auth/change-password",
            headers={**old_access_headers, "Idempotency-Key": "change-password"},
            json={
                "current_password": "correct horse battery staple",
                "new_password": "new correct horse battery staple",
            },
        )

        old_access_response = await client.get("/auth/me", headers=old_access_headers)
        old_refresh_response = await client.post(
            "/auth/refresh",
            headers={"Idempotency-Key": "change-password-refresh"},
            json={"refresh_token": old_refresh_token},
        )
        new_login_response = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "change-password-new-login"},
            json={"email": user.email, "password": "new correct horse battery staple"},
        )

    assert response.status_code == 204
    assert user.password_changed_at is not None
    assert user.token_version == 2
    assert old_access_response.status_code == 401
    assert old_refresh_response.status_code == 401
    assert new_login_response.status_code == 200


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_current_password(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/change-password",
            headers={**auth_headers(user), "Idempotency-Key": "change-password-wrong"},
            json={"current_password": "wrong password", "new_password": "long enough password"},
        )

    assert response.status_code == 401
    assert user.token_version == 1


@pytest.mark.asyncio
async def test_change_password_rejects_unauthenticated_request(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/change-password",
            headers={"Idempotency-Key": "change-password-unauthenticated"},
            json={
                "current_password": "correct horse battery staple",
                "new_password": "new correct horse battery staple",
            },
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_short_new_password(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/auth/change-password",
            headers={**auth_headers(user), "Idempotency-Key": "change-password-short"},
            json={"current_password": "correct horse battery staple", "new_password": "short"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sessions_list_current_user_sessions_without_token_hash(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    other_user, _other_member = await create_member_user(
        db_session,
        email="other@example.com",
        password="other correct horse battery staple",
    )
    now = utc_now()
    active = RefreshToken(
        user_id=user.id,
        family_id=uuid4(),
        token_hash="a" * 64,
        expires_at=now + timedelta(days=1),
    )
    used = RefreshToken(
        user_id=user.id,
        family_id=uuid4(),
        token_hash="b" * 64,
        expires_at=now + timedelta(days=1),
        used_at=now,
    )
    revoked = RefreshToken(
        user_id=user.id,
        family_id=uuid4(),
        token_hash="c" * 64,
        expires_at=now + timedelta(days=1),
        revoked_at=now,
    )
    expired = RefreshToken(
        user_id=user.id,
        family_id=uuid4(),
        token_hash="d" * 64,
        expires_at=now - timedelta(seconds=1),
    )
    other = RefreshToken(
        user_id=other_user.id,
        family_id=uuid4(),
        token_hash="e" * 64,
        expires_at=now + timedelta(days=1),
    )
    db_session.add_all([active, used, revoked, expired, other])
    await db_session.flush()
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/sessions", headers=auth_headers(user))

    assert response.status_code == 200
    sessions = response.json()["sessions"]
    sessions_by_id = {session["id"]: session for session in sessions}
    assert set(sessions_by_id) == {str(active.id), str(used.id), str(revoked.id), str(expired.id)}
    assert all("token_hash" not in session for session in sessions)
    assert sessions_by_id[str(active.id)]["active"] is True
    assert sessions_by_id[str(used.id)]["active"] is False
    assert sessions_by_id[str(revoked.id)]["active"] is False
    assert sessions_by_id[str(expired.id)]["active"] is False


@pytest.mark.asyncio
async def test_sessions_list_rejects_unauthenticated_request(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth/sessions")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_revoke_revokes_own_refresh_token(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_response = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "session-revoke-login"},
            json={"email": user.email, "password": "correct horse battery staple"},
        )
        refresh_token = login_response.json()["refresh_token"]
        sessions_response = await client.get("/auth/sessions", headers=auth_headers(user))
        session_id = sessions_response.json()["sessions"][0]["id"]

        response = await client.delete(
            f"/auth/sessions/{session_id}",
            headers={**auth_headers(user), "Idempotency-Key": "session-revoke"},
        )
        second_response = await client.delete(
            f"/auth/sessions/{session_id}",
            headers={**auth_headers(user), "Idempotency-Key": "session-revoke-again"},
        )
        refresh_response = await client.post(
            "/auth/refresh",
            headers={"Idempotency-Key": "session-revoke-refresh"},
            json={"refresh_token": refresh_token},
        )

    assert response.status_code == 204
    assert second_response.status_code == 204
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_session_revoke_rejects_unauthenticated_request(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            f"/auth/sessions/{uuid4()}",
            headers={"Idempotency-Key": "session-revoke-unauthenticated"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_revoke_does_not_revoke_another_users_session(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    other_user, _other_member = await create_member_user(
        db_session,
        email="other-session@example.com",
        password="other correct horse battery staple",
    )
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        other_login = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "other-session-login"},
            json={"email": other_user.email, "password": "other correct horse battery staple"},
        )
        other_refresh_token = other_login.json()["refresh_token"]
        token_hash = hash_refresh_token(other_refresh_token)
        token = (
            await db_session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        ).scalar_one()

        response = await client.delete(
            f"/auth/sessions/{token.id}",
            headers={**auth_headers(user), "Idempotency-Key": "other-session-delete"},
        )
        refresh_response = await client.post(
            "/auth/refresh",
            headers={"Idempotency-Key": "other-session-refresh"},
            json={"refresh_token": other_refresh_token},
        )

    assert response.status_code == 204
    assert refresh_response.status_code == 200


@pytest.mark.asyncio
async def test_session_revoke_keeps_logout_all_working(
    test_env: None,
    db_session: AsyncSession,
) -> None:
    _ = test_env
    user, _member = await create_member_user(db_session)
    app = app_for_session(db_session)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_login = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "logout-all-first-login"},
            json={"email": user.email, "password": "correct horse battery staple"},
        )
        second_login = await client.post(
            "/auth/login",
            headers={"Idempotency-Key": "logout-all-second-login"},
            json={"email": user.email, "password": "correct horse battery staple"},
        )
        first_refresh_token = first_login.json()["refresh_token"]
        second_refresh_token = second_login.json()["refresh_token"]
        sessions_response = await client.get("/auth/sessions", headers=auth_headers(user))
        session_id = sessions_response.json()["sessions"][0]["id"]

        revoke_response = await client.delete(
            f"/auth/sessions/{session_id}",
            headers={**auth_headers(user), "Idempotency-Key": "logout-all-delete-one"},
        )
        logout_all_response = await client.post(
            "/auth/logout-all",
            headers={**auth_headers(user), "Idempotency-Key": "logout-all"},
        )
        first_refresh_response = await client.post(
            "/auth/refresh",
            headers={"Idempotency-Key": "logout-all-first-refresh"},
            json={"refresh_token": first_refresh_token},
        )
        second_refresh_response = await client.post(
            "/auth/refresh",
            headers={"Idempotency-Key": "logout-all-second-refresh"},
            json={"refresh_token": second_refresh_token},
        )

    assert revoke_response.status_code == 204
    assert logout_all_response.status_code == 204
    assert first_refresh_response.status_code == 401
    assert second_refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_register_calls_screening(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    repo = FakeIdentityRepo(make_user())
    screening = FakeScreeningService()
    service = IdentityService(repo, screening)  # type: ignore[arg-type]

    token_pair = await service.register(email="new@example.com", password="long-enough-password")

    assert token_pair.user.email == "new@example.com"
    assert screening.calls == [
        {
            "user_id": token_pair.user.id,
            "name": "new@example.com",
            "dob": None,
            "country": "GB",
        }
    ]


@pytest.mark.asyncio
async def test_register_ensures_clear_member_after_screening(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    repo = FakeIdentityRepo(make_user())
    screening = FakeScreeningService()
    members = FakeMembersService()
    service = IdentityService(repo, screening, members)  # type: ignore[arg-type]

    token_pair = await service.register(email="member@example.com", password="long-enough-password")

    assert members.calls == [
        {
            "user_id": token_pair.user.id,
            "display_name": "member@example.com",
            "country": "GB",
            "screening_state": "clear",
        }
    ]


@pytest.mark.asyncio
async def test_register_uses_display_name_for_member(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    repo = FakeIdentityRepo(make_user())
    screening = FakeScreeningService()
    members = FakeMembersService()
    service = IdentityService(repo, screening, members)  # type: ignore[arg-type]

    token_pair = await service.register(
        email="named@example.com",
        password="long-enough-password",
        display_name="Ada Adebayo",
    )

    assert members.calls == [
        {
            "user_id": token_pair.user.id,
            "display_name": "Ada Adebayo",
            "country": "GB",
            "screening_state": "clear",
        }
    ]


@pytest.mark.asyncio
async def test_register_provisions_wallet_for_member(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    repo = FakeIdentityRepo(make_user())
    screening = FakeScreeningService()
    members = FakeMembersService()
    wallet = FakeWalletService()
    service = IdentityService(repo, screening, members, wallet)  # type: ignore[arg-type]

    await service.register(email="wallet@example.com", password="long-enough-password")

    assert wallet.calls == [{"member_id": members.member_id}]
