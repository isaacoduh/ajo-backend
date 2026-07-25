# Harness Summary

| Harness | Test file | Doc section |
| --- | --- | --- |
| Config/live-key guard | `tests/test_harness/test_config.py` | `docs/README.md`, `docs/api/conventions.md` |
| RFC 9457 errors/request logging/health | `tests/test_harness/test_errors_logging_health.py` | `docs/api/conventions.md`, `docs/architecture.md` |
| Async DB/Alembic metadata | `tests/test_harness/test_db_metadata.py` | `docs/architecture.md` |
| Identity/auth refresh rotation | `tests/test_harness/test_identity_auth.py` | `docs/api/conventions.md`, `docs/architecture.md` |
| Rate limiting/idempotency | `tests/test_harness/test_rate_limit_idempotency.py` | `docs/api/conventions.md`, `docs/architecture.md` |
| Ledger primitives | `tests/test_harness/test_ledger_primitives.py` | `docs/ledger.md` |
| ARQ jobs harness | `tests/test_harness/test_jobs_harness.py` | `docs/architecture.md` |
| Payments rail port/FakeRail | `tests/contract/test_payment_rail_contract.py`, `tests/test_harness/test_payments_harness.py` | `docs/payments.md` |
| Screening/notifications | `tests/test_harness/test_screening_notifications.py` | `docs/architecture.md`, `docs/api/conventions.md` |
| Circles skeleton | `tests/test_harness/test_circles_skeleton.py` | `docs/architecture.md` |
| Shared test harness | `tests/test_harness/test_testing_harness.py` | `docs/runbooks/local-dev.md` |

## ADRs

- `0001-record-architecture-decisions.md`
- `0002-monolith-first.md`
- `0003-integer-minor-units.md`
- `0004-internal-ledger-authoritative.md`
- `0005-arq-over-celery.md`
- `0006-port-abstracted-payment-rails.md`
- `0007-append-only-ledger-via-revoked-grants.md`

