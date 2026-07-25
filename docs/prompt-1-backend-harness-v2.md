# PROMPT 1 (v2) — Backend Harness & Structure — consultancy showcase edition

Paste into a fresh Claude Code session in an empty repo. Supersedes v1 and the Stripe patch.

---

You are a **staff-level backend engineer** scaffolding **Àjọ**, a digital esusu (rotating savings circle) platform. Context that shapes every decision: this is a **consultancy showcase, never going live**. That raises the bar rather than lowering it — the codebase is the pitch. Every pattern must be the one you would defend in front of a client's CTO: production-pattern, sandbox-proven. No shortcuts justified by "it's just a demo", and equally no ops theatre that only matters for live operation (no on-call tooling, no status page).

This pass builds the chassis only: structure, plumbing, cross-cutting harnesses, ledger primitives, and the multi-rail payment port. **No product features, no real payment providers yet** — rails are integrated later via a separate prompt, one per vendor, against the same port.

## Context

- Solo developer. Local dev = Docker Compose. Deployed demo = **Railway** (managed Postgres, managed Redis, Dockerfile services).
- Design load: 500 concurrent-ish users, payday-burst collection pattern. Correctness > simplicity > performance.
- The showcase's centrepiece claims: (1) append-only double-entry ledger with enforced invariants, (2) a `PaymentRailPort` that four real vendors (Stripe, TrueLayer, GoCardless, Griffin) plug into interchangeably, (3) bank-grade webhook + reconciliation discipline. Build the chassis so those claims are structurally true.

## Stack (fixed — do not substitute)

Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, PostgreSQL 16, Redis 7, **ARQ** (jobs + cron), `uv`, ruff, `mypy --strict` on `core/`, `db/`, `modules/ledger`, `modules/payments`, pytest + pytest-asyncio + testcontainers + hypothesis, structlog, argon2-cffi, PyJWT.

## `/docs` — first-class, created in this pass

Create this structure and maintain it in every subsequent pass. Rule for you and every future session: **a change that alters architecture, a contract, or a money flow is not done until its doc is updated in the same commit.**

```
docs/
  README.md            # doc map + reading order for a new engineer (or client)
  prd.md               # placeholder: "see AJO-PRD-001" + scope deltas from PRD to showcase build
  architecture.md      # living TAD-lite: context diagram, module map, key flows (mermaid)
  ledger.md            # account taxonomy, posting recipes, invariants I1–I6, hash chain, replay
  payments.md          # PaymentRailPort contract, rail lifecycle states, webhook rules, recon design
  adr/                 # 0001-record-architecture-decisions.md + one ADR per significant decision
  rails/               # one file per provider, written during rail integration passes
  runbooks/            # deploy.md (Railway), local-dev.md, demo-reset.md
  api/                 # export of OpenAPI schema (make openapi) + conventions.md (errors, idempotency, pagination)
  pitch/               # empty for now; eval matrix + load test results land here later
```

Seed `adr/` with ADRs for the decisions in this prompt (monolith-first, integer minor units, internal ledger authoritative, ARQ over Celery, port-abstracted rails, append-only via revoked grants). Any deviation you make from this spec = an ADR with the reason.

## Repository layout

```
app/
  main.py                  # app factory, middleware stack, router mounting
  core/                    # config, logging, errors, security, idempotency, pagination, deps
  db/                      # engine/session/base + ledger primitives (db/ledger.py)
  modules/
    identity/              # implemented this pass: router/service/repo/models/schemas
    circles/               # skeleton only (/ping)
    ledger/                # service over db/ledger.py
    payments/              # port + FakeRail + webhook harness (provider-agnostic core)
    screening/             # ScreeningPort protocol + AlwaysClear fake (OpenSanctions later)
    notifications/         # EmailPort + console impl + Mailpit SMTP impl
  workers/main.py          # ARQ settings, cron + job registries
tests/                     # conftest (testcontainers), test_harness/, contract/ (see port contract tests)
alembic/  docs/  docker-compose.yml  Dockerfile  Makefile
```

Module rule: routers → services → repos; cross-module access only via another module's `service.py`; enforced with import-linter.

## Harnesses (each with tests — unchanged in substance from v1)

1. **Config** — pydantic-settings, `ENV=local|test|demo`, fail-fast, redacted startup summary. Config hard-fails if any live-mode vendor key is ever present (`sk_live`, etc.) — this repo must be structurally incapable of touching real money.
2. **Auth** — access JWT 15 min; refresh = opaque 256-bit, hashed at rest, rotating, **family revocation on reuse**; register/login/refresh/logout/logout-all; `token_version` bump on password change.
3. **Errors** — RFC 9457 problem+json everywhere; field-level validation details; opaque 500 + trace_id; no leaked stacks.
4. **Rate limiting** — Redis fixed-window; auth 5/min/IP, writes 60/min/member; 429 + Retry-After; fails open with loud logging.
5. **Idempotency** — `Idempotency-Key` on mutating routes; Redis-stored first response replayed byte-identical 48 h; concurrent duplicate → 409; race-tested.
6. **Request logging** — request_id in/out, bound through logs and ARQ job context.
7. **Health** — `/healthz`, `/readyz` (DB + Redis, 1 s timeouts); Railway healthcheck on `/readyz`.
8. **Jobs** — ARQ base with log binding, max_tries=5 exp backoff, `failed_jobs` dead-letter table, heartbeat cron, **enqueue-after-commit** hook (documented in `docs/architecture.md`).
9. **Migrations** — Alembic async, autogenerate, drift check in CI.
10. **Testing** — testcontainers Postgres+Redis, member factories, auth client fixture, `make test` < 90 s.

## Ledger primitives (the deepest credential — build with care)

As v1, verbatim: `ledger_account` / `journal_entry` / `posting`; integer minor units GBP only (CI greps money path for `float|Decimal`); single `post_entry()` in one DB transaction with deterministic lock ordering, Σ D == Σ C, no negative liabilities, materialised balances, SHA-256 hash chain; **UPDATE/DELETE revoked at the DB role level** on journal tables; corrections are reversing entries only; hypothesis property tests (random valid batches → trial balance zero, replay == materialised). Document all of it in `docs/ledger.md` with worked posting-recipe examples (contribution, payout+fee, top-up, reversal).

## Payments — multi-rail port (the showcase's second centrepiece)

Design the port for **four** upcoming implementations, integrated later one prompt at a time: `StripeRail`, `TrueLayerRail`, `GoCardlessRail`, `GriffinRail` (spike). This pass implements **`FakeRail` only**, but the abstractions must already be provider-plural:

- `PaymentRailPort` protocol covering: `onboard_member` (KYC/account-holder creation where the rail supports it), `create_topup` , `create_mandate` + `collect` (DD-style rails), `send_payout`, `get_settlement_status`, `verify_webhook`. Rails may return `NotSupported` for capabilities they lack — the port models a **capability matrix**, not a lowest common denominator. Capability flags live on the rail class and are queryable (`rail.supports(Capability.MANDATES)`).
- **Rail selection is per-flow config**, not one global provider: e.g. `RAIL_TOPUP=fake`, `RAIL_COLLECTION=fake`, `RAIL_PAYOUT=fake` — because the demo's killer move is mixing rails (TrueLayer pay-ins + GoCardless collections + Stripe payouts) over one ledger.
- Unified settlement state machine every rail maps into: `INITIATED → PROCESSING → SETTLED | FAILED | FAILED_LATE` (late failure after reported success — the Bacs truth — is first-class, with `FakeRail.fail_late()` hook for tests).
- `partner_event` table (append-only, `provider` column) + provider-agnostic webhook pipeline: verify (per-provider strategy) → persist raw → 200 → async process → dedupe on provider event id → drive state machine from fetched object state, never event deltas. Per-provider gap-detection cron slot.
- Nightly reconciliation job skeleton: per-provider statement/balance-transaction fetch (FakeRail returns its own journal) → match to `journal_entry` by idempotency key → `recon_break` rows → ERROR log + email on breaks.
- **Port contract test suite** (`tests/contract/test_payment_rail_contract.py`): a single parametrised suite asserting lifecycle behaviour, idempotency, late-failure handling, and webhook round-trip for *any* rail implementation. FakeRail passes it now; every future rail must pass it unmodified. This suite is a headline artifact — mention it in `docs/payments.md`.

## Screening port

`ScreeningPort` (`screen_person(name, dob, country) -> hits[]`) with `AlwaysClearScreening` fake; called during identity onboarding; results persisted. OpenSanctions implementation comes in the rails pass.

## Docker & Railway

Compose: api (reload), worker, postgres, redis, mailpit; `make up`, `make seed`, `make stripe-listen` placeholder targets. One Dockerfile, two Railway services (api / worker CMDs), migrations in release phase, healthcheck `/readyz`. Write `docs/runbooks/deploy.md` and `docs/runbooks/local-dev.md`, plus `demo-reset.md` (destroy + reseed the demo environment in one command — a pitch essential).

## Definition of done

`make up && make test` green; `docs/` populated as specified; new module addable by copying the circles skeleton; contract suite green against FakeRail. Finish with a summary table: harness → test file → doc section, plus any ADRs you added.

Build order: layout + config + compose → docs scaffold + seed ADRs → DB/migrations → errors/logging → auth → rate-limit/idempotency → ledger (+ docs/ledger.md) → jobs → payments port + FakeRail + contract suite (+ docs/payments.md) → screening port → runbooks → final sweep. Conventional commit at each arrow.
