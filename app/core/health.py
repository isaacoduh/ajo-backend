"""Health and readiness checks."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypedDict

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.db.engine import get_engine


class DependencyStatus(TypedDict):
    ok: bool
    detail: str


class ReadinessStatus(TypedDict):
    status: str
    checks: dict[str, DependencyStatus]


async def check_database(engine: AsyncEngine | None = None) -> DependencyStatus:
    database_engine = engine if engine is not None else get_engine()
    try:
        async with database_engine.connect() as connection:
            await connection.execute(text("select 1"))
    except Exception as exc:
        return {"ok": False, "detail": exc.__class__.__name__}
    return {"ok": True, "detail": "ok"}


async def check_redis(settings: Settings | None = None) -> DependencyStatus:
    resolved_settings = settings if settings is not None else get_settings()
    client = Redis.from_url(resolved_settings.redis_url, socket_timeout=1)
    try:
        await client.ping()
    except Exception as exc:
        return {"ok": False, "detail": exc.__class__.__name__}
    finally:
        await client.aclose()
    return {"ok": True, "detail": "ok"}


async def run_with_timeout(
    check: Callable[[], Awaitable[DependencyStatus]],
    timeout_seconds: float = 1.0,
) -> DependencyStatus:
    try:
        return await asyncio.wait_for(check(), timeout=timeout_seconds)
    except TimeoutError:
        return {"ok": False, "detail": "timeout"}


async def readiness_status(
    database_check: Callable[[], Awaitable[DependencyStatus]] | None = None,
    redis_check: Callable[[], Awaitable[DependencyStatus]] | None = None,
) -> ReadinessStatus:
    resolved_database_check = database_check if database_check is not None else check_database
    resolved_redis_check = redis_check if redis_check is not None else check_redis
    database, redis = await asyncio.gather(
        run_with_timeout(resolved_database_check),
        run_with_timeout(resolved_redis_check),
    )
    checks = {"database": database, "redis": redis}
    status = "ok" if all(check["ok"] for check in checks.values()) else "degraded"
    return {"status": status, "checks": checks}

