import importlib
from types import ModuleType

import httpx
import pytest
from app.core.config import get_settings
from app.core.health import DependencyStatus, ReadinessStatus, readiness_status
from pydantic import BaseModel


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


def set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setattr("app.core.idempotency.get_redis", lambda: InMemoryIdempotencyStore())
    get_settings.cache_clear()


def load_app_main() -> ModuleType:
    return importlib.import_module("app.main")


@pytest.mark.asyncio
async def test_healthz_echoes_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    app_main = load_app_main()
    transport = httpx.ASGITransport(app=app_main.create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz", headers={"X-Request-ID": "req-test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_validation_errors_are_problem_json(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    app_main = load_app_main()
    app = app_main.create_app()

    class Payload(BaseModel):
        amount: int

    @app.post("/validation-target")
    async def validation_target(payload: Payload) -> dict[str, int]:
        return {"amount": payload.amount}

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/validation-target",
            json={"amount": "not-an-int"},
            headers={"Idempotency-Key": "validation-key"},
        )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Unprocessable Content"
    assert body["trace_id"]
    assert body["errors"][0]["loc"] == ["body", "amount"]


@pytest.mark.asyncio
async def test_unhandled_errors_are_opaque_problem_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_required_env(monkeypatch)
    app_main = load_app_main()
    app = app_main.create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive internal detail")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={"X-Request-ID": "req-boom"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["detail"] == "An unexpected error occurred."
    assert body["trace_id"] == "req-boom"
    assert "sensitive internal detail" not in response.text


async def passing_check() -> DependencyStatus:
    return {"ok": True, "detail": "ok"}


async def failing_check() -> DependencyStatus:
    return {"ok": False, "detail": "ConnectionError"}


@pytest.mark.asyncio
async def test_readiness_status_reports_ok() -> None:
    status = await readiness_status(passing_check, passing_check)

    assert status["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_status_reports_degraded() -> None:
    status = await readiness_status(passing_check, failing_check)

    assert status["status"] == "degraded"
    assert status["checks"]["redis"] == {"ok": False, "detail": "ConnectionError"}


@pytest.mark.asyncio
async def test_readyz_failure_returns_problem_json(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required_env(monkeypatch)
    app_main = load_app_main()

    async def degraded_status() -> ReadinessStatus:
        return {
            "status": "degraded",
            "checks": {
                "database": {"ok": True, "detail": "ok"},
                "redis": {"ok": False, "detail": "ConnectionError"},
            },
        }

    monkeypatch.setattr(app_main, "readiness_status", degraded_status)
    transport = httpx.ASGITransport(app=app_main.create_app())

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz", headers={"X-Request-ID": "req-readyz"})

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["trace_id"] == "req-readyz"
    assert body["checks"]["redis"] == {"ok": False, "detail": "ConnectionError"}
