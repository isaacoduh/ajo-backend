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
- StripeRail sandbox implementation for PaymentIntent wallet top-ups.
- TrueLayerRail sandbox implementation for hosted payment wallet top-ups and
  signed business-account payout creation.
- Payment rail registry.
- Payment object persistence.
- Provider event persistence.
- Reconciliation break persistence.
- Provider webhook routes for Stripe and TrueLayer.
- Stripe webhook verification, raw event persistence, event dedupe, state fetch,
  and wallet settlement orchestration.
- TrueLayer webhook verification, raw event persistence, event dedupe, payment
  or payout status processing, and wallet settlement orchestration.
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
- M2 full-cycle harness coverage: 8 members, 8 cycles, 64 contribution obligations, all payouts, late failure, completion idempotency, ledger replay, and balanced debits/credits.
- M2 lifetime Hurl story enumerates all 8 registrations, joins, agreements, collections, payouts, late failure, records, ledger, statement, and completion; commit hash still requires the documented helper calculation because Hurl cannot compute SHA-256 from captured IDs.
- Guarded demo reset command for local/development/staging/test that requires `DEMO_RESET_CONFIRM=destroy-and-reseed`, refuses production, clears product tables, and reseeds M1/M2 demo data.
- Stripe sandbox payment path materially proven for supported top-up flows.
- TrueLayer sandbox top-up flow materially proven end-to-end: top-up initiation
  posts pending funds, verified webhook/status processing posts settlement,
  pending decreases, and available balance increases.
- TrueLayer sandbox business-account payout flow materially proven end-to-end:
  `RAIL_PAYOUT=truelayer` withdrawal returned `processing`, provider
  webhook/status processing posted settlement, pending decreased, and the
  wallet withdrawal settled.
- Generated OpenAPI export.
- Local Docker Compose workflow.
- Railway deployment runbook.
- Standard runtime stages: `local`, `development`, `staging`, `production`, plus internal `test`.
- Alembic reads the app settings database URL, so local `.env` and Railway env vars drive migrations.
- Backend harness tests.
- Payment rail contract tests.
- Architecture decision records.

## Backend Remaining

- Real KYC provider integration.
- GoCardless payment provider integration.
- OpenSanctions screening provider integration.
- Griffin BaaS spike documentation.
- Stripe Connect payout execution and Stripe Identity evidence model, if kept in
  scope beyond the currently proven PaymentIntent top-up path.
- TrueLayer AIS account verification, `external_account` payouts, and
  `payment_source` payouts remain gated unless sandbox/account access supports
  them.
- Production deployment automation.
- Railway-verified seeded reset drill.
- M1/M2 Hurl replay evidence from a fresh local or staging environment.
- Reproducible integrated rail demo evidence for Stripe and TrueLayer should be
  kept current with provider object IDs or redacted run notes suitable for the
  pitch kit.
- Full M7 frontend coverage for all PM screens.

## Frontend Dependency Notes

- Frontend can use `/healthz`, `/readyz`, `/auth/*`, wallet M1 endpoints, and core `/circles/*` M2 endpoints.
- Frontend currently implements a minimal authenticated dashboard, create-circle flow, and circle detail shell.
- Full M7 circle operations UI remains out of scope.

## Deployment Readiness

- Backend foundation is deployable as a demo harness.
- Backend now has sandbox-proven Stripe and TrueLayer wallet top-up settlement
  paths for supported capabilities.
- Backend now has sandbox-proven TrueLayer business-account payout settlement
  for the supported withdrawal path.
- Backend is not yet production-ready as the full PM product API.
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
- Stripe/TrueLayer sandbox credentials may be set only for sandbox rail demos;
  live credentials remain rejected by configuration safeguards.
