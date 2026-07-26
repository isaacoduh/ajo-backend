import pytest
from app.core.config import Environment, Settings, find_live_secret_offenders, redact_url
from pydantic import ValidationError


def test_redacts_urls_with_credentials() -> None:
    assert (
        redact_url("postgresql+asyncpg://ajo:secret@localhost:5432/ajo")
        == "postgresql+asyncpg://***:***@localhost:5432/ajo"
    )


def test_finds_live_payment_secret_values() -> None:
    offenders = find_live_secret_offenders(
        {
            "STRIPE_SECRET_KEY": "sk_live_123",
            "NORMAL_VALUE": "sk_live_not_scanned_without_secret_name",
        }
    )

    assert offenders == {"STRIPE_SECRET_KEY"}


def test_environment_accepts_deploy_stages() -> None:
    assert {environment.value for environment in Environment} == {
        "local",
        "development",
        "staging",
        "production",
        "test",
    }


def test_settings_reject_live_payment_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_123")

    with pytest.raises(ValidationError, match="live-mode payment credentials"):
        Settings()


def test_settings_startup_summary_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://:redis-password@localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")

    summary = Settings().redacted_startup_summary()

    assert summary["database_url"] == "postgresql+asyncpg://***:***@localhost:5432/ajo"
    assert summary["redis_url"] == "redis://***:***@localhost:6379/0"
    assert summary["rails"] == {"topup": "fake", "collection": "fake", "payout": "fake"}
    assert summary["otel"] == {
        "enabled": True,
        "service_name": "ajo-backend",
        "otlp_configured": False,
    }


def test_settings_treats_blank_otel_endpoint_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    monkeypatch.setenv("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    settings = Settings()

    assert settings.otel_exporter_otlp_endpoint is None
