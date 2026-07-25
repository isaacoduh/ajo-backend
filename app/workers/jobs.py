"""Shared worker job primitives."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from arq import Retry
from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.models import FailedJob

JobFunction = Callable[..., Awaitable[object]]


@dataclass(frozen=True)
class PendingJob:
    function_name: str
    args: Sequence[object] = field(default_factory=tuple)
    kwargs: dict[str, object] = field(default_factory=dict)
    job_id: str | None = None


def retry_defer_seconds(job_try: int) -> int:
    return min(2 ** max(job_try - 1, 0), 60)


def retry_later(job_try: int) -> Retry:
    return Retry(defer=retry_defer_seconds(job_try))


def enqueue_after_commit(
    session: AsyncSession,
    function_name: str,
    *args: object,
    job_id: str | None = None,
    **kwargs: object,
) -> None:
    pending = session.info.setdefault("jobs_after_commit", [])
    pending.append(PendingJob(function_name=function_name, args=args, kwargs=kwargs, job_id=job_id))


def has_after_commit_jobs(session: AsyncSession) -> bool:
    return bool(session.info.get("jobs_after_commit"))


async def flush_after_commit_jobs(session: AsyncSession, redis: ArqRedis) -> None:
    pending = session.info.pop("jobs_after_commit", [])
    for job in pending:
        await redis.enqueue_job(
            job.function_name,
            *job.args,
            _job_id=job.job_id,
            **job.kwargs,
        )


async def discard_after_commit_jobs(session: AsyncSession) -> None:
    session.info.pop("jobs_after_commit", None)


async def heartbeat(ctx: dict[object, object]) -> dict[str, str]:
    _ = ctx
    return {"status": "ok"}


async def persist_failed_job(
    *,
    function_name: str,
    error: BaseException,
    job_id: str | None = None,
    queue_name: str | None = None,
    try_number: int | None = None,
    args: dict[str, object] | None = None,
) -> None:
    from app.db.engine import get_session_maker

    async with get_session_maker()() as session:
        session.add(
            FailedJob(
                job_id=job_id,
                function_name=function_name,
                queue_name=queue_name,
                try_number=try_number,
                args=args,
                error_type=error.__class__.__name__,
                error_message=str(error),
            )
        )
        await session.commit()
