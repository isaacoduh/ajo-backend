.PHONY: help lint typecheck test import-lint openapi up seed stripe-listen

help:
	@echo "Available targets: lint typecheck test import-lint openapi up seed stripe-listen"

lint:
	uv run ruff check app tests

typecheck:
	uv run mypy

test:
	uv run pytest

import-lint:
	uv run lint-imports

openapi:
	uv run python -m app.tools.openapi

up:
	docker compose up --build

seed:
	@echo "Seed command will be implemented with the data model."

stripe-listen:
	@echo "Stripe listener placeholder; real rail integration lands in a later pass."

