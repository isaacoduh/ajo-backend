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
- Authenticated profile endpoint: `GET /auth/me`.
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
- Member domain profile.
- Wallet provisioning.
- Wallet balance endpoint: `GET /wallet/balance`.
- Wallet activity endpoint: `GET /wallet/activity`.
- Wallet top-up endpoint: `POST /wallet/topups`.
- Wallet withdrawal endpoint: `POST /wallet/withdrawals`.
- Statement endpoint: `GET /statements/{period}`.
- M1 seed/demo flow.
- Minimal OpenTelemetry foundation.
- M2 circle models and migrations.
- Circle create/list/detail endpoints.
- Circle invite and join endpoints.
- Circle agreement and lock flow.
- Circle commit-reveal draw and schedule generation.
- FakeRail-backed circle collection and payout endpoints.
- Circle late-failure, arrears, shortfall, ledger, statement, and completion endpoints.
- Generated OpenAPI export.
- Local Docker Compose workflow.
- Railway deployment runbook.
- Standard runtime stages: `local`, `development`, `staging`, `production`, plus internal `test`.
- Alembic reads the app settings database URL, so local `.env` and Railway env vars drive migrations.
- Backend harness tests.
- Payment rail contract tests.
- Architecture decision records.

## Backend Remaining

- Realistic 8-member circle seed/reset command.
- Real KYC provider integration.
- Real payment provider integrations.
- Provider-specific webhook routes.
- Production deployment automation.
- Full seeded reset implementation tied to product data.
- Full M7 frontend coverage for all PM screens.

## Frontend Dependency Notes

- Frontend can use `/healthz`, `/readyz`, `/auth/*`, wallet M1 endpoints, and core `/circles/*` M2 endpoints.
- Frontend currently implements a minimal authenticated dashboard, create-circle flow, and circle detail shell.
- Full M7 circle operations UI remains out of scope.

## Deployment Readiness

- Backend foundation is deployable as a demo harness.
- Backend is not yet deployable as the full PM product API.
- Deploy target is Railway.
- Required managed services are Postgres and Redis.
- Required runtime services are API and worker.
- Required release command is `uv run alembic upgrade head`.
- Alembic uses `DATABASE_URL` from the process environment or the app settings `.env` fallback.
- Required API command is `uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- Required worker command is `uv run arq app.workers.main.WorkerSettings`.
- Required healthcheck path is `/readyz`.
- Required Railway showcase environment is `ENV=staging`.
- Required fake rail settings are `RAIL_TOPUP=fake`, `RAIL_COLLECTION=fake`, and `RAIL_PAYOUT=fake`.
- Live payment credentials must not be set.
