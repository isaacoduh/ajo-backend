.PHONY: help lint typecheck test test-containers test-stripe import-lint money-check openapi migration migrate migration-drift up seed demo-reset stripe-listen

help:
	@echo "Available targets: lint typecheck test test-containers test-stripe import-lint money-check openapi migration migrate migration-drift up seed demo-reset stripe-listen"

lint:
	uv run ruff check app tests

typecheck:
	uv run mypy

test:
	uv run pytest -m "not containers"

test-containers:
	uv run pytest -m containers

test-stripe:
	uv run pytest -m stripe tests/test_harness/test_stripe_rail.py

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
	uv run python -m app.tools.seed

demo-reset:
	uv run python -m app.tools.demo_reset

stripe-listen:
	stripe listen --forward-to localhost:8000/payments/webhooks/stripe
