from dataclasses import dataclass, field

import pytest
from app.workers.jobs import (
    discard_after_commit_jobs,
    enqueue_after_commit,
    flush_after_commit_jobs,
    has_after_commit_jobs,
    heartbeat,
    retry_defer_seconds,
)
from app.workers.main import on_job_end, redis_settings_from_url, scrub_job_context


@dataclass
class FakeSession:
    info: dict[str, object] = field(default_factory=dict)


class FakeArqRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(
        self,
        function_name: str,
        *args: object,
        _job_id: str | None = None,
        **kwargs: object,
    ) -> None:
        kwargs["_job_id"] = _job_id
        self.enqueued.append((function_name, args, kwargs))


def test_retry_defer_seconds_is_exponential_and_capped() -> None:
    assert retry_defer_seconds(1) == 1
    assert retry_defer_seconds(2) == 2
    assert retry_defer_seconds(3) == 4
    assert retry_defer_seconds(10) == 60


@pytest.mark.asyncio
async def test_enqueue_after_commit_flushes_jobs() -> None:
    session = FakeSession()
    redis = FakeArqRedis()

    enqueue_after_commit(session, "send_email", "user-id", job_id="job-1", template="welcome")

    assert has_after_commit_jobs(session)
    await flush_after_commit_jobs(session, redis)  # type: ignore[arg-type]

    assert not has_after_commit_jobs(session)
    assert redis.enqueued == [
        ("send_email", ("user-id",), {"template": "welcome", "_job_id": "job-1"})
    ]


@pytest.mark.asyncio
async def test_discard_after_commit_jobs_clears_pending_jobs() -> None:
    session = FakeSession()

    enqueue_after_commit(session, "send_email")
    await discard_after_commit_jobs(session)  # type: ignore[arg-type]

    assert not has_after_commit_jobs(session)


@pytest.mark.asyncio
async def test_heartbeat_returns_ok() -> None:
    assert await heartbeat({}) == {"status": "ok"}


def test_redis_settings_from_url_parses_local_url() -> None:
    settings = redis_settings_from_url("redis://user:pass@redis:6380/2")

    assert settings.host == "redis"
    assert settings.port == 6380
    assert settings.database == 2
    assert settings.username == "user"
    assert settings.password == "pass"


def test_scrub_job_context_removes_runtime_objects() -> None:
    assert scrub_job_context(
        {
            "redis": object(),
            "settings": object(),
            "exception": RuntimeError("boom"),
            "job_id": "job-1",
        }
    ) == {"job_id": "job-1"}


@pytest.mark.asyncio
async def test_on_job_end_persists_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_persist_failed_job(**kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("app.workers.main.persist_failed_job", fake_persist_failed_job)

    await on_job_end(
        {
            "exception": RuntimeError("boom"),
            "job_id": "job-1",
            "function": "send_email",
            "queue_name": "arq:queue",
            "job_try": 5,
            "redis": object(),
        }
    )

    assert calls[0]["job_id"] == "job-1"
    assert calls[0]["function_name"] == "send_email"
    assert calls[0]["try_number"] == 5
    assert isinstance(calls[0]["error"], RuntimeError)

