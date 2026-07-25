"""Redis-backed fixed-window rate limiting."""

from dataclasses import dataclass
from typing import Protocol, cast

import structlog
from fastapi import Request
from redis.exceptions import RedisError

from app.core.errors import AppError
from app.core.redis import get_redis

logger = structlog.get_logger(__name__)


class FixedWindowStore(Protocol):
    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> object: ...

    async def ttl(self, key: str) -> int: ...


@dataclass(frozen=True)
class RateLimit:
    name: str
    limit: int
    window_seconds: int


AUTH_RATE_LIMIT = RateLimit(name="auth", limit=5, window_seconds=60)
USER_WRITE_RATE_LIMIT = RateLimit(name="user_write", limit=60, window_seconds=60)


class FixedWindowRateLimiter:
    def __init__(self, store: FixedWindowStore) -> None:
        self.store = store

    async def check(self, *, identity: str, rate_limit: RateLimit) -> int | None:
        key = f"rate_limit:{rate_limit.name}:{identity}"
        count = await self.store.incr(key)
        if count == 1:
            await self.store.expire(key, rate_limit.window_seconds)
        if count <= rate_limit.limit:
            return None
        ttl = await self.store.ttl(key)
        return ttl if ttl > 0 else rate_limit.window_seconds


async def enforce_rate_limit(
    *,
    identity: str,
    rate_limit: RateLimit,
    store: FixedWindowStore | None = None,
) -> None:
    resolved_store = store if store is not None else cast(FixedWindowStore, get_redis())
    try:
        retry_after = await FixedWindowRateLimiter(resolved_store).check(
            identity=identity,
            rate_limit=rate_limit,
        )
    except RedisError:
        logger.exception(
            "rate_limit_failed_open",
            identity=identity,
            rate_limit=rate_limit.name,
        )
        return
    if retry_after is not None:
        raise AppError(
            status_code=429,
            title="Too Many Requests",
            detail="Rate limit exceeded.",
            type_="https://ajo.dev/problems/rate-limit-exceeded",
            extra={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


async def rate_limit_auth(request: Request) -> None:
    await enforce_rate_limit(identity=client_ip(request), rate_limit=AUTH_RATE_LIMIT)


async def rate_limit_user_writes(user_id: str) -> None:
    await enforce_rate_limit(identity=user_id, rate_limit=USER_WRITE_RATE_LIMIT)
