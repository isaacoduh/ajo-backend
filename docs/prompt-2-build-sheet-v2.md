# PROMPT 2 (v2) — Consolidated Build Sheet — consultancy showcase edition

Paste after the v2 harness exists. Give the session repo access. Supersedes v1.

---

You are a staff engineer planning the build of **Àjọ**, a digital esusu platform that is a **consultancy showcase — it will never go live**. One developer (me): backend built at staff level first, frontend built later at pragmatic mid/senior level with TanStack. Budget ~25 focused hrs/week, target ~8–9 weeks.

The harness exists (FastAPI modular monolith, ARQ, append-only hash-chained ledger, JWT with rotating refresh + family revocation, idempotency, multi-rail `PaymentRailPort` with FakeRail + a parametrised rail contract test suite, ScreeningPort, `/docs` folder conventions, Docker local / Railway demo).

Produce `docs/BUILD_SHEET.md`: a single consolidated build order I execute top to bottom.

## What "done" means for this project

Not launch. The finish line is a **pitch kit**: a seeded live demo on Railway, four sandbox-proven vendor rails behind one port, a provider evaluation matrix written from hands-on use, a payday-burst load test with graphs, and 2–3 publishable technical write-ups. Every milestone should move toward an artifact I can show a client.

## Scope

**In:** auth + verified member; screening via OpenSanctions; wallet; full circle lifecycle (create → invite → agreement → lock → commit-reveal draw → collection cron → payout → shortfall "pay what's collected" → completion + arrears recording); circle ledger + statements; admin trio (member 360, ops queue, reversing entry with posting preview); **four rails**: StripeRail (Connect + Identity + PaymentIntents + transfers/payouts), TrueLayerRail (PIS top-ups + AIS account verification + sandbox payout), GoCardlessRail (mandates + recurring collection + simulated late failures), GriffinRail (2-day spike, documented not completed); pitch assets (below); TanStack frontend covering the member journey per wireframes AJO-WIRE-001.

**Out — do not create tasks for:** live-mode anything, Stripe platform-approval outreach, pilot programme, on-call/alerting beyond Sentry + log-based checks, complaints/support tooling, credit reporting, trust-profile page, i18n, native apps.

**Non-negotiables:** ledger invariants + property tests stay green; every rail passes the contract suite unmodified; no cross-circle postings; append-only journal; problem+json everywhere; `/docs` updated in the same commit as the change it describes.

## Sequencing rules (replaces v1's vertical-slice rule)

Backend-first is deliberate. Instead of UI slices, **every backend milestone must end demoable over HTTP**: a Hurl (or Bruno) collection in `docs/api/demos/` that a stranger can replay against a seeded environment, telling the milestone's story end-to-end. The frontend is its own milestone group at the end, executed with the frontend prompt (Prompt 4) against a finished API.

## Milestone arc (refine if you see better, and say why)

- **M1 — Identity & wallet on FakeRail** (auth, screening, wallet, top-up/withdraw, statements). Demo: Hurl story "register → screened → top up → withdraw".
- **M2 — Circle engine** (the heart — largest allocation). Create/invite/agreement/lock/draw/collection cron/payout/shortfall/completion, circle ledger. Exit criterion: the full-cycle simulation test — 8 members, 8 cycles, injected `FAILED_LATE` mid-cycle — passes with invariants green. Demo: scripted circle lifetime compressed via a time-travel test clock on the scheduler (build one; document it — clients love seeing a 10-month circle run in 90 seconds).
- **M3 — StripeRail** (via Prompt 3, Stripe section). Contract suite green; `docs/rails/stripe.md`; eval-matrix row.
- **M4 — TrueLayerRail** (Prompt 3). Same exit shape. Include the mixed-rail demo config here (TL top-ups + Fake collections).
- **M5 — GoCardlessRail + Griffin spike + OpenSanctions live impl** (Prompt 3). GC late-failure feeding the shortfall machine is the flagship test. Griffin: timeboxed spike, output is `docs/rails/griffin.md` + matrix row, not a full rail.
- **M6 — Pitch kit**: seeded Railway demo env + `demo-reset` verified; 10-minute scripted walkthrough (write the script into `docs/pitch/walkthrough.md`); provider evaluation matrix (`docs/pitch/rail-eval-matrix.md`) — criteria: capabilities, sandbox quality, integration effort (actual hours from my commits), webhook ergonomics, failure-simulation support, pricing model, go-live requirements; k6 payday-burst load test (1k circles collecting in one hour) with results + graphs in `docs/pitch/load-test.md`; outlines for 3 write-ups (ledger design, multi-rail port, Bacs late-failure state machine).
- **M7 — Frontend (TanStack, via Prompt 4)**: member journey screens 01–21 from AJO-WIRE-001 against the demo API; admin stays API/Hurl-only unless time allows.

## Output format

`docs/BUILD_SHEET.md` containing:

1. **Milestone table** — goal, demoable artifact (one sentence), exit criteria, calendar estimate.
2. **Task list** — grouped by milestone, execution order: `ID | Title | Layer (BE/FE/Infra/Docs/Test) | Size (S≤2h / M≤half-day / L≤2 days, split larger) | Depends on | Acceptance criteria (1–3 testable bullets; money-path tasks name their test) | Notes/risks`. Include the forgettables: seed script with a realistic 8-member circle, scheduler test clock, Hurl collections per milestone, Sentry wiring, Railway env promotion, OpenAPI export, demo-reset drill, eval-matrix row per rail, ADRs. Flag the 5 riskiest tasks ⚠ with one-line mitigations. End each milestone with a `CHECKPOINT` task: full suite green, deploy to Railway, replay the milestone's Hurl story, update `/docs`.
3. **Cut list** — ordered cuts if behind schedule (protect: ledger, circle engine, Stripe + one other rail, eval matrix; cut first: Griffin spike, admin UI polish, third write-up, frontend admin screens).
4. **Pitch-day checklist** — demo env seeded and reset-tested, walkthrough rehearsed timing noted, load-test graphs exported, matrix current with all integrated rails, repo README presentable, all Hurl stories replay green.

Before writing, read the repo and `/docs` to confirm what exists — **no tasks for built things**. Align IDs/terminology with the PRD if present. At most 3 clarifying questions, only if sequencing is genuinely blocked; otherwise decide and record in a "Decisions assumed" section at the top.
