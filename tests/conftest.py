"""Shared test harness fixtures."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.model_registry import import_all_models
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests.factories import user_model


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        _ = ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.fixture
def test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setenv("ARGON2_MEMORY_COST", "8192")
    monkeypatch.setattr("app.core.idempotency.get_redis", lambda: InMemoryIdempotencyStore())
    get_settings.cache_clear()


@pytest.fixture
async def app_client(test_env: None) -> AsyncIterator[httpx.AsyncClient]:
    _ = test_env
    from app.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    pytest.importorskip("testcontainers.postgres")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator[Any]:
    pytest.importorskip("testcontainers.redis")
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7") as container:
        yield container


@pytest.fixture
def postgres_url(postgres_container: Any) -> str:
    return postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture
def redis_url(redis_container: Any) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture
async def db_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    import_all_models()
    engine = create_async_engine(postgres_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def user_factory(test_env: None) -> Any:
    _ = test_env
    return user_model


@pytest.fixture
def auth_header(test_env: None) -> dict[str, str]:
    _ = test_env
    user = user_model()
    token = create_access_token(user_id=user.id, token_version=user.token_version)
    return {"Authorization": f"Bearer {token}"}
