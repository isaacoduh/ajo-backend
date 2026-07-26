import asyncio

import httpx
import pytest
from app.core.errors import AppError
from app.core.idempotency import IdempotencyMiddleware, configure_idempotency_openapi
from app.core.rate_limit import RateLimit, enforce_rate_limit
from fastapi import FastAPI, Header
from redis.exceptions import RedisError


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


class InMemoryRateLimitStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)


class FailingRateLimitStore:
    async def incr(self, key: str) -> int:
        _ = key
        raise RedisError("redis unavailable")

    async def expire(self, key: str, seconds: int) -> None:
        _ = key, seconds

    async def ttl(self, key: str) -> int:
        _ = key
        return -1


def idempotency_test_app(store: InMemoryIdempotencyStore) -> FastAPI:
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, store=store)
    calls = {"count": 0}

    @app.post("/target")
    async def target() -> dict[str, int]:
        calls["count"] += 1
        return {"count": calls["count"]}

    return app


def test_openapi_documents_idempotency_header_on_mutations() -> None:
    app = FastAPI()

    @app.post("/target")
    async def target() -> dict[str, str]:
        return {"status": "ok"}

    configure_idempotency_openapi(app)

    operation = app.openapi()["paths"]["/target"]["post"]
    parameters = operation["parameters"]

    assert parameters == [
        {
            "name": "Idempotency-Key",
            "in": "header",
            "required": True,
            "description": (
                "Unique key for this mutation. Reuse it only when retrying the same request."
            ),
            "schema": {"type": "string", "minLength": 1},
        }
    ]
    assert operation["responses"]["400"]["description"] == (
        "Idempotency-Key header is required."
    )
    assert operation["responses"]["409"]["description"] == (
        "A request with this Idempotency-Key is already in progress."
    )


def test_openapi_does_not_duplicate_declared_idempotency_header() -> None:
    app = FastAPI()

    @app.post("/target")
    async def target(idempotency_key: str = Header(alias="Idempotency-Key")) -> None:
        _ = idempotency_key

    configure_idempotency_openapi(app)

    parameters = app.openapi()["paths"]["/target"]["post"]["parameters"]

    assert len(parameters) == 1


@pytest.mark.asyncio
async def test_idempotency_replays_first_response() -> None:
    transport = httpx.ASGITransport(app=idempotency_test_app(InMemoryIdempotencyStore()))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/target", headers={"Idempotency-Key": "same-key"})
        second = await client.post("/target", headers={"Idempotency-Key": "same-key"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert first.json() == {"count": 1}


@pytest.mark.asyncio
async def test_idempotency_requires_key_for_mutating_requests() -> None:
    transport = httpx.ASGITransport(app=idempotency_test_app(InMemoryIdempotencyStore()))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/target")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.asyncio
async def test_idempotency_concurrent_duplicate_returns_conflict() -> None:
    store = InMemoryIdempotencyStore()
    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware, store=store)
    started = asyncio.Event()
    release = asyncio.Event()

    @app.post("/slow")
    async def slow() -> dict[str, str]:
        started.set()
        await release.wait()
        return {"status": "done"}

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_task = asyncio.create_task(
            client.post("/slow", headers={"Idempotency-Key": "same-key"})
        )
        await started.wait()
        duplicate = await client.post("/slow", headers={"Idempotency-Key": "same-key"})
        release.set()
        first = await first_task

    assert duplicate.status_code == 409
    assert duplicate.headers["content-type"].startswith("application/problem+json")
    assert first.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_returns_retry_after() -> None:
    store = InMemoryRateLimitStore()
    rate_limit = RateLimit(name="test", limit=2, window_seconds=60)

    await enforce_rate_limit(identity="ip", rate_limit=rate_limit, store=store)
    await enforce_rate_limit(identity="ip", rate_limit=rate_limit, store=store)

    with pytest.raises(AppError) as exc_info:
        await enforce_rate_limit(identity="ip", rate_limit=rate_limit, store=store)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "60"}
    assert exc_info.value.extra == {"retry_after": 60}


@pytest.mark.asyncio
async def test_rate_limit_fails_open_on_redis_error() -> None:
    await enforce_rate_limit(
        identity="ip",
        rate_limit=RateLimit(name="test", limit=1, window_seconds=60),
        store=FailingRateLimitStore(),
    )
