from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

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
from app.modules.identity.models import User
from app.modules.identity.service import IdentityService


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
    revoked_at: object | None = None
    replaced_by_token_id: UUID | None = None


class FakeIdentityRepo:
    def __init__(self, user: User) -> None:
        self.user = user
        self.tokens_by_hash: dict[str, StoredRefreshToken] = {}
        self.revoked_families: list[UUID] = []
        self.created_user: User | None = None

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
    service = IdentityService(repo)
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
    service = IdentityService(repo)
    token_pair = await service._issue_pair(user=user, family_id=uuid4())
    await service.refresh(refresh_token=token_pair.refresh_token)
    old_family = repo.tokens_by_hash[hash_refresh_token(token_pair.refresh_token)].family_id

    with pytest.raises(AppError):
        await service.refresh(refresh_token=token_pair.refresh_token)

    assert old_family in repo.revoked_families


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
async def test_register_provisions_wallet_for_member(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    repo = FakeIdentityRepo(make_user())
    screening = FakeScreeningService()
    members = FakeMembersService()
    wallet = FakeWalletService()
    service = IdentityService(repo, screening, members, wallet)  # type: ignore[arg-type]

    await service.register(email="wallet@example.com", password="long-enough-password")

    assert wallet.calls == [{"member_id": members.member_id}]
