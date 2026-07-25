"""Password, JWT, and refresh-token security helpers."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings, get_settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_BYTES = 32
REFRESH_TOKEN_TTL = timedelta(days=30)


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    token_version: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_password_hasher(settings: Settings | None = None) -> PasswordHasher:
    resolved_settings = settings if settings is not None else get_settings()
    return PasswordHasher(
        time_cost=resolved_settings.argon2_time_cost,
        memory_cost=resolved_settings.argon2_memory_cost,
        parallelism=resolved_settings.argon2_parallelism,
    )


def hash_password(password: str, settings: Settings | None = None) -> str:
    return build_password_hasher(settings).hash(password)


def verify_password(password: str, password_hash: str, settings: Settings | None = None) -> bool:
    try:
        return build_password_hasher(settings).verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(
    *,
    user_id: UUID,
    token_version: int,
    settings: Settings | None = None,
    issued_at: datetime | None = None,
) -> str:
    resolved_settings = settings if settings is not None else get_settings()
    now = issued_at if issued_at is not None else utc_now()
    payload = {
        "sub": str(user_id),
        "iss": resolved_settings.jwt_issuer,
        "aud": resolved_settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
        "token_version": token_version,
    }
    return jwt.encode(
        payload,
        resolved_settings.jwt_access_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings | None = None) -> AccessTokenClaims:
    resolved_settings = settings if settings is not None else get_settings()
    payload = jwt.decode(
        token,
        resolved_settings.jwt_access_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=resolved_settings.jwt_issuer,
        audience=resolved_settings.jwt_audience,
    )
    return AccessTokenClaims(
        user_id=UUID(str(payload["sub"])),
        token_version=int(payload["token_version"]),
    )


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str, settings: Settings | None = None) -> str:
    resolved_settings = settings if settings is not None else get_settings()
    pepper = resolved_settings.refresh_token_pepper.get_secret_value().encode()
    return hmac.new(pepper, token.encode(), hashlib.sha256).hexdigest()
