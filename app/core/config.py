"""Application configuration.

The live-secret guard is intentionally broad: this showcase must never boot with
credentials that look capable of touching real money.
"""

import os
import re
from enum import StrEnum
from functools import lru_cache
from typing import Any, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class RailName(StrEnum):
    FAKE = "fake"


LIVE_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk_live", re.IGNORECASE),
    re.compile(r"pk_live", re.IGNORECASE),
    re.compile(r"whsec_live", re.IGNORECASE),
    re.compile(r"\blive[_-]secret\b", re.IGNORECASE),
    re.compile(r"\blive[_-]key\b", re.IGNORECASE),
)

SECRET_NAME_HINTS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "WEBHOOK",
    "STRIPE",
    "TRUELAYER",
    "GOCARDLESS",
    "GRIFFIN",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    env: Environment = Field(default=Environment.LOCAL, alias="ENV")
    app_name: str = Field(default="ajo-backend", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")

    jwt_issuer: str = Field(default="ajo.local", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="ajo.api", alias="JWT_AUDIENCE")
    jwt_access_secret: SecretStr = Field(alias="JWT_ACCESS_SECRET", min_length=32)
    refresh_token_pepper: SecretStr = Field(alias="REFRESH_TOKEN_PEPPER", min_length=32)

    argon2_time_cost: int = Field(default=2, alias="ARGON2_TIME_COST", ge=1)
    argon2_memory_cost: int = Field(default=65536, alias="ARGON2_MEMORY_COST", ge=8192)
    argon2_parallelism: int = Field(default=2, alias="ARGON2_PARALLELISM", ge=1)

    rail_topup: RailName = Field(default=RailName.FAKE, alias="RAIL_TOPUP")
    rail_collection: RailName = Field(default=RailName.FAKE, alias="RAIL_COLLECTION")
    rail_payout: RailName = Field(default=RailName.FAKE, alias="RAIL_PAYOUT")

    smtp_host: str = Field(default="mailpit", alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, alias="SMTP_PORT")

    otel_service_name: str = Field(default="ajo-backend", alias="OTEL_SERVICE_NAME")
    otel_exporter_otlp_endpoint: str | None = Field(
        default=None,
        alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otel_enabled: bool = Field(default=True, alias="OTEL_ENABLED")

    @field_validator("otel_exporter_otlp_endpoint", mode="before")
    @classmethod
    def empty_otel_endpoint_is_unset(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def reject_live_money_credentials(self) -> Self:
        offenders = find_live_secret_offenders(os.environ)
        if offenders:
            names = ", ".join(sorted(offenders))
            raise ValueError(f"live-mode payment credentials are not allowed: {names}")
        return self

    def redacted_startup_summary(self) -> dict[str, Any]:
        return {
            "env": self.env.value,
            "app_name": self.app_name,
            "log_level": self.log_level,
            "database_url": redact_url(self.database_url),
            "redis_url": redact_url(self.redis_url),
            "jwt_issuer": self.jwt_issuer,
            "jwt_audience": self.jwt_audience,
            "rails": {
                "topup": self.rail_topup.value,
                "collection": self.rail_collection.value,
                "payout": self.rail_payout.value,
            },
            "smtp": {
                "host": self.smtp_host,
                "port": self.smtp_port,
            },
            "otel": {
                "enabled": self.otel_enabled,
                "service_name": self.otel_service_name,
                "otlp_configured": self.otel_exporter_otlp_endpoint is not None,
            },
        }


def find_live_secret_offenders(environ: os._Environ[str] | dict[str, str]) -> set[str]:
    offenders: set[str] = set()
    for name, value in environ.items():
        if not value:
            continue
        has_secret_name = any(hint in name.upper() for hint in SECRET_NAME_HINTS)
        if has_secret_name and any(pattern.search(value) for pattern in LIVE_SECRET_PATTERNS):
            offenders.add(name)
    return offenders


def redact_url(value: str) -> str:
    if "://" not in value or "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    _, host = rest.rsplit("@", 1)
    return f"{scheme}://***:***@{host}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
