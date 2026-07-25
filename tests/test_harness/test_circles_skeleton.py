import importlib

import httpx
import pytest
from app.core.config import get_settings


class InMemoryIdempotencyStore:
    async def get(self, key: str) -> str | None:
        _ = key
        return None

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        _ = key, value, ex, nx
        return True

    async def delete(self, key: str) -> None:
        _ = key


def set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setattr("app.core.idempotency.get_redis", lambda: InMemoryIdempotencyStore())
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_circles_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    app_main = importlib.import_module("app.main")
    transport = httpx.ASGITransport(app=app_main.create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/circles/ping")

    assert response.status_code == 200
    assert response.json() == {"module": "circles", "status": "ok"}

