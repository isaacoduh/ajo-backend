"""Redis client construction."""

from functools import lru_cache
from typing import cast

from redis.asyncio import Redis

from app.core.config import Settings, get_settings


@lru_cache(maxsize=1)
def get_redis(settings: Settings | None = None) -> Redis:
    resolved_settings = settings if settings is not None else get_settings()
    return cast(Redis, Redis.from_url(resolved_settings.redis_url, decode_responses=True))
