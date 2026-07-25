"""Export the FastAPI OpenAPI schema."""

import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    output_path = Path("docs/api/openapi.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()

