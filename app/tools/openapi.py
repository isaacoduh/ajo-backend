"""Export the FastAPI OpenAPI schema."""

import json
import os
from pathlib import Path


def main() -> None:
    configure_openapi_env()
    from app.main import create_app

    output_path = Path("docs/api/openapi.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")


def configure_openapi_env() -> None:
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ajo:ajo@localhost:5432/ajo")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("JWT_ACCESS_SECRET", "local-only-access-secret-32-bytes")
    os.environ.setdefault("REFRESH_TOKEN_PEPPER", "local-only-refresh-pepper-32-bytes")


if __name__ == "__main__":
    main()

