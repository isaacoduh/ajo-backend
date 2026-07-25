"""Async SQLAlchemy engine construction."""

from collections.abc import AsyncIterator
from functools import lru_cache

from arq.connections import create_pool
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings
from app.workers.jobs import (
    discard_after_commit_jobs,
    flush_after_commit_jobs,
    has_after_commit_jobs,
)
from app.workers.main import redis_settings_from_url


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    resolved_settings = settings if settings is not None else get_settings()
    return create_async_engine(
        resolved_settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def create_session_maker(database_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=database_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    return create_engine()


@lru_cache(maxsize=1)
def get_session_maker() -> async_sessionmaker[AsyncSession]:
    return create_session_maker(get_engine())


async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
            if has_after_commit_jobs(session):
                redis = await create_pool(redis_settings_from_url(get_settings().redis_url))
                try:
                    await flush_after_commit_jobs(session, redis)
                finally:
                    await redis.close()
        except Exception:
            await session.rollback()
            await discard_after_commit_jobs(session)
            raise
