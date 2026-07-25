"""ARQ settings entrypoint."""

from typing import ClassVar
from urllib.parse import urlparse

import structlog
from arq import cron
from arq.connections import RedisSettings, create_pool

from app.core.config import get_settings
from app.workers.jobs import heartbeat, persist_failed_job

logger = structlog.get_logger(__name__)


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    ctx["redis"] = await create_pool(redis_settings_from_url(settings.redis_url))


async def shutdown(ctx: dict[str, object]) -> None:
    redis = ctx.get("redis")
    if redis is not None:
        await redis.close()  # type: ignore[attr-defined]


async def on_job_start(ctx: dict[str, object]) -> None:
    logger.info(
        "job_started",
        job_id=ctx.get("job_id"),
        function=ctx.get("function"),
        job_try=ctx.get("job_try"),
    )


async def on_job_end(ctx: dict[str, object]) -> None:
    error = ctx.get("exception")
    if not isinstance(error, BaseException):
        logger.info(
            "job_finished",
            job_id=ctx.get("job_id"),
            function=ctx.get("function"),
            job_try=ctx.get("job_try"),
        )
        return
    await persist_failed_job(
        job_id=string_or_none(ctx.get("job_id")),
        function_name=string_or_default(ctx.get("function"), "unknown"),
        queue_name=string_or_none(ctx.get("queue_name")),
        try_number=int_or_none(ctx.get("job_try")),
        args={"ctx": scrub_job_context(ctx)},
        error=error,
    )


def redis_settings_from_url(redis_url: str) -> RedisSettings:
    parsed = urlparse(redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or "0"),
        username=parsed.username,
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


def string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def string_or_default(value: object, default: str) -> str:
    if value is None:
        return default
    return str(value)


def int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def scrub_job_context(ctx: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in ctx.items()
        if key not in {"redis", "settings", "exception"}
    }


class WorkerSettings:
    on_startup = startup
    on_shutdown = shutdown
    on_job_start = on_job_start
    on_job_end = on_job_end
    functions: ClassVar[list[object]] = [heartbeat]
    cron_jobs: ClassVar[list[object]] = [
        cron(heartbeat, name="heartbeat", second=0, max_tries=1),
    ]
    max_tries = 5

