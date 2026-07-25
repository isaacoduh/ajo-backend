"""Test factories."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.core.security import hash_password
from app.modules.identity.models import User


@dataclass(frozen=True)
class UserFactoryData:
    id: UUID
    email: str
    password: str
    password_hash: str
    token_version: int


def user_factory_data(
    *,
    email: str = "user@example.com",
    password: str = "correct horse battery staple",
) -> UserFactoryData:
    return UserFactoryData(
        id=uuid4(),
        email=email,
        password=password,
        password_hash=hash_password(password),
        token_version=1,
    )


def user_model(
    *,
    email: str = "user@example.com",
    password_hash: str = "hash",
    token_version: int = 1,
) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid4(),
        email=email,
        password_hash=password_hash,
        token_version=token_version,
        created_at=now,
        updated_at=now,
    )

