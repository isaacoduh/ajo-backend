# PM Tracking

## Backend Done

- FastAPI application chassis.
- Health endpoint: `GET /healthz`.
- Readiness endpoint: `GET /readyz`.
- Structured request logging.
- Request ID propagation.
- RFC 9457 `application/problem+json` error responses.
- Redis-backed rate limiting.
- Redis-backed idempotency middleware.
- Async SQLAlchemy database setup.
- Alembic migration setup.
- Initial schema migrations.
- Identity user model.
- Registration endpoint: `POST /auth/register`.
- Login endpoint: `POST /auth/login`.
- Refresh endpoint: `POST /auth/refresh`.
- Logout endpoint: `POST /auth/logout`.
- Logout-all endpoint: `POST /auth/logout-all`.
- JWT access-token foundation.
- Refresh-token family rotation.
- Refresh-token replay protection.
- Password hashing.
- Screening port.
- Always-clear screening implementation.
- Screening result persistence.
- Notification email port.
- Console email implementation.
- SMTP email implementation.
- Append-only ledger tables.
- Double-entry ledger posting primitive.
- Ledger hash-chain primitive.
- Ledger replay checks.
- Integer minor-unit money discipline.
- Payment rail port.
- Fake payment rail implementation.
- Payment rail registry.
- Payment object persistence.
- Provider event persistence.
- Reconciliation break persistence.
- Webhook verification/persistence skeleton.
- Payment settlement state machine.
- ARQ worker harness.
- Job enqueue-after-commit pattern.
- Failed job persistence.
- Circle module skeleton.
- Circle ping endpoint: `GET /circles/ping`.
- Generated OpenAPI export.
- Local Docker Compose workflow.
- Railway deployment runbook.
- Backend harness tests.
- Payment rail contract tests.
- Architecture decision records.

## Backend Remaining

- Real circle lifecycle endpoints.
- Circle member onboarding workflows.
- Circle invite and join flows.
- Circle contribution schedule logic.
- Circle payout order and draw workflow.
- Wallet balance endpoint.
- Wallet activity endpoint.
- Wallet top-up endpoint.
- Wallet withdrawal endpoint.
- Contribution collection endpoints.
- Payout endpoints.
- Member-facing ledger endpoints.
- Statement endpoints.
- Real KYC provider integration.
- Real payment provider integrations.
- Provider-specific webhook routes.
- Production deployment automation.
- Seed/demo data command.
- Full demo reset implementation tied to product data.
- Frontend-specific API coverage for all PM screens.

## Frontend Dependency Notes

- Frontend can currently use auth endpoints only.
- Frontend cannot yet build the full wallet journey from backend APIs.
- Frontend cannot yet build the full circle journey from backend APIs.
- Frontend cannot yet build ledger or statement screens from backend APIs.
- Frontend can use `/healthz`, `/readyz`, `/auth/*`, and `/circles/ping`.

## Deployment Readiness

- Backend foundation is deployable as a demo harness.
- Backend is not yet deployable as the full PM product API.
- Deploy target is Railway.
- Required managed services are Postgres and Redis.
- Required runtime services are API and worker.
- Required release command is `uv run alembic upgrade head`.
- Required API command is `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Required worker command is `uv run arq app.workers.main.WorkerSettings`.
- Required healthcheck path is `/readyz`.
- Required Railway showcase environment is `ENV=staging`.
- Required fake rail settings are `RAIL_TOPUP=fake`, `RAIL_COLLECTION=fake`, and `RAIL_PAYOUT=fake`.
- Live payment credentials must not be set.
