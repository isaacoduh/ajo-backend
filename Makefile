.PHONY: help lint typecheck test import-lint money-check openapi migration migrate migration-drift up seed stripe-listen

help:
	@echo "Available targets: lint typecheck test import-lint money-check openapi migration migrate migration-drift up seed stripe-listen"

lint:
	uv run ruff check app tests

typecheck:
	uv run mypy

test:
	uv run pytest

import-lint:
	uv run lint-imports

money-check:
	@if rg -n "\b(float|Decimal)\b" app/db app/modules/ledger; then exit 1; fi

openapi:
	uv run python -m app.tools.openapi

migration:
	uv run alembic revision --autogenerate -m "$(message)"

migrate:
	uv run alembic upgrade head

migration-drift:
	uv run alembic check

up:
	docker compose up --build

seed:
	@echo "Seed command will be implemented with the data model."

stripe-listen:
	@echo "Stripe listener placeholder; real rail integration lands in a later pass."
