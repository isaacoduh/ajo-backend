# Àjọ Build Sheet

This is the executable build order for the consultancy showcase. Work it top to
bottom unless a checkpoint explicitly changes scope.

## Decisions Assumed

- Work cadence is 2 focused hours per night, usually 5-7 nights per week.
- Size `S` means one night or less, `M` means 2-3 nights, and `L` means up to one
  focused week. Anything larger is split.
- The Prompt 1 harness is already built and is not repeated here as product work.
- Backend remains the critical path until the circle engine is complete.
- Existing frontend work is treated as a visual/mock prototype until M7.
- Calendar estimates are recalibrated from the original 25 hours/week plan to
  roughly 10-14 hours/week.
- Hurl is the default HTTP demo format unless a later ADR chooses Bruno.
- Admin UI is out of the protected path; admin workflows can remain API/Hurl
  unless time remains after M7.
- Observability is added in two passes: a minimal OpenTelemetry foundation during
  M1, then a polished dashboard and load-test evidence in M6.

## Milestone Table

| Milestone | Goal | Demoable artifact | Exit criteria | Calendar estimate |
| --- | --- | --- | --- | --- |
| M1 | Identity and wallet on FakeRail | `docs/api/demos/m1_wallet.hurl`: register, screened, top up, withdraw, statement | Wallet APIs work over HTTP, money postings go through ledger recipes, tests name the money path, one top-up emits correlated logs/traces/metrics, OpenAPI exported | 3-4 weeks |
| M2 | Circle engine | `docs/api/demos/m2_circle_lifetime.hurl`: compressed full circle lifecycle using a test clock | 8 members, 8 cycles, injected `FAILED_LATE`, shortfall and arrears recorded, invariants green | 6-8 weeks |
| M3 | StripeRail | Stripe sandbox rail doc, contract suite run, eval matrix row | Stripe rail passes shared contract suite where capabilities apply, webhooks/recon documented, no live keys accepted | 2-3 weeks |
| M4 | TrueLayerRail | TrueLayer sandbox rail doc plus mixed-rail Hurl story | TrueLayer top-up/account verification works or limitation is documented, mixed-rail config demonstrated | 2-3 weeks |
| M5 | GoCardlessRail, OpenSanctions, Griffin spike | GoCardless late-failure demo, OpenSanctions review demo, Griffin spike note | GC late failure feeds M2 shortfall machine, OpenSanctions persists review hits, Griffin stopped at timebox | 3-4 weeks |
| M6 | Pitch kit | Seeded Railway demo, walkthrough, eval matrix, load-test report | Demo reset verified, k6 graphs exported, repo presentable, all Hurl stories replay green | 2-3 weeks |
| M7 | Frontend | TanStack member journey screens 01-21 against demo API | Playwright walkthrough green, Lighthouse targets met, no mock-only critical path remains | 4-6 weeks |

## Task List

### M1 - Identity and Wallet on FakeRail

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M1-01 | Define member and wallet domain model | BE/Docs | S | Harness | `docs/architecture.md` names `Member` ownership; model supports verified member state; no circle-specific fields leak into wallet | Keep `User` auth principal separate from domain member |
| M1-02 | Write wallet ledger recipes | Docs | S | M1-01 | `docs/ledger.md` covers top-up, withdrawal, pending settlement, reversal; recipes use integer minor units; no cross-circle accounts introduced | Money doc first reduces implementation drift |
| M1-03 | Add member and wallet migrations | BE | S | M1-01 | Alembic migration creates member/wallet tables; `make migration-drift` clean; model registry includes new models | Include indexes for owner and idempotency lookups |
| M1-04 | Implement member repo/service | BE | S | M1-03 | Registration can create/load member profile; screening result linked or queryable; tests cover duplicate user/member behavior | Avoid expanding auth service too much |
| M1-05 | Implement wallet account provisioning | BE/Test | S | M1-03 | New member gets wallet ledger accounts once; idempotent provisioning test passes; account codes are deterministic | Money-path test: wallet provisioning |
| M1-06 | Add wallet balance endpoint | BE/Test | S | M1-05 | `GET /wallet/balance` returns available/pending minor units; auth required; OpenAPI schema generated | Cursor pagination not needed for singleton balance |
| M1-07 | Add wallet activity endpoint | BE/Test | M | M1-05 | `GET /wallet/activity` returns cursor-paginated ledger-derived rows; no raw posting internals leaked; problem+json on invalid cursor | Use existing pagination conventions |
| M1-08 | Implement FakeRail top-up orchestration | BE/Test | M | M1-05 | Service creates payment object and ledger entry only through sanctioned recipe; idempotent retry returns same object; contract suite still green | Money-path test: wallet top-up |
| M1-09 | Add top-up endpoint | BE/Test | S | M1-08 | `POST /wallet/topups` requires `Idempotency-Key`; response exposes settlement state; missing key returns problem+json | Demo can stay synchronous-ish with FakeRail but state must remain honest |
| M1-10 | Implement withdrawal orchestration | BE/Test | M | M1-05 | Service rejects insufficient available balance; ledger posts withdrawal through recipe; payment object state tracked | Money-path test: wallet withdrawal |
| M1-11 | Add withdrawal endpoint | BE/Test | S | M1-10 | `POST /wallet/withdrawals` requires auth and idempotency; problem+json on insufficient funds; OpenAPI exported | Keep provider-specific details out of API |
| M1-12 | Add statement endpoint | BE/Test | M | M1-07 | `GET /statements/{period}` returns opening, movement, closing, and journal refs; tests cover empty and active periods | Money-path test: member statement |
| M1-13 | Add M1 seed data | BE/Infra | S | M1-12 | `make seed` creates one realistic verified member with wallet history; rerunnable without duplicate data | Existing target is placeholder |
| M1-14 | Add M1 Hurl demo | Test/Docs | S | M1-13 | `docs/api/demos/m1_wallet.hurl` replays register, top-up, withdraw, statement; README explains env vars | Use seeded or self-registering story |
| M1-15 | Add minimal OpenTelemetry foundation | BE/Infra/Docs | S | M1-09 | One wallet top-up emits a correlated request log, trace, and metric through OTLP when configured; disabled or stdout-safe when no exporter is configured; docs name the local collector path | Keep this thin; dashboard polish waits for M6 |
| M1-16 | CHECKPOINT: M1 hardening | Test/Docs/Infra | M | M1-15 | `make lint`, `make typecheck`, `make import-lint`, `make money-check`, `make test`, `make openapi` pass; Railway staging deploy attempted or documented; docs updated | Do not start M2 with flaky money tests |

### M2 - Circle Engine

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M2-01 | Define circle domain model and state machine ⚠ | BE/Docs | M | M1-16 | `docs/architecture.md` documents states; transitions cover draft, recruiting, agreement, locked, active, completed, cancelled; invalid transitions tested | Mitigation: model states before endpoints |
| M2-02 | Add circle/member/schedule migrations | BE | M | M2-01 | Tables support circle members, invites, agreements, cycles, contributions, payouts; constraints prevent duplicate membership | Avoid premature admin fields |
| M2-03 | Implement circle repo/service base | BE/Test | M | M2-02 | Service methods enforce owner/member permissions; import-linter still green; tests cover create/read/list | Cross-module access via services only |
| M2-04 | Add create and list circle endpoints | BE/Test | S | M2-03 | `POST /circles` and `GET /circles` work with auth; idempotency enforced on create; OpenAPI exported | Start replacing skeleton safely |
| M2-05 | Add invite and join flow | BE/Test | M | M2-04 | Invite token/code created; invited user joins once; expired/duplicate joins return problem+json | Demo needs this over HTTP |
| M2-06 | Add agreement capture | BE/Test | M | M2-05 | Each member accepts contribution amount, cadence, payout rules; circle cannot lock without unanimous agreement | Keep legal text simple for showcase |
| M2-07 | Lock circle and provision circle ledger accounts ⚠ | BE/Test | M | M2-06 | Lock freezes mutable terms; circle-level accounts created once; tests prove no cross-circle postings | Mitigation: deterministic account codes include circle ID |
| M2-08 | Implement commit-reveal draw design ⚠ | BE/Docs/Test | M | M2-07 | Published algorithm documented; commitments stored before reveals; deterministic order reproducible in tests | Mitigation: small pure function with fixtures |
| M2-09 | Add draw endpoints | BE/Test | S | M2-08 | Endpoints expose commitment, reveal, resulting order, verification data; invalid reveal fails safely | This is a signature demo moment |
| M2-10 | Add scheduler test clock | BE/Test/Docs | M | M2-07 | Clock can compress cycles in tests/demo; production path uses real time; docs explain usage | Do not let test clock leak into normal runtime |
| M2-11 | Implement contribution schedule generation | BE/Test | M | M2-10 | Locking creates expected cycles and contribution obligations; tests cover 8 members/8 cycles | Money-path prerequisite |
| M2-12 | Implement collection cron with FakeRail | BE/Test | M | M2-11 | Due contributions enqueue collections; idempotency keys stable; settlement states update payment objects | Money-path test: scheduled collection |
| M2-13 | Implement member contribution status endpoint | BE/Test | S | M2-12 | Circle detail can show due, processing, paid, failed, late; cursor or cycle filters documented | Needed later by frontend |
| M2-14 | Implement payout eligibility and payout execution ⚠ | BE/Test | M | M2-12 | Cycle recipient receives payout from collected funds; ledger recipes used; insufficient collected amount handled explicitly | Mitigation: payout service consumes contribution summary, not raw guesses |
| M2-15 | Implement shortfall and arrears recording ⚠ | BE/Test | M | M2-14 | Injected late failure reverses prior entry, records arrears, and keeps trial balance green | Mitigation: build from `FAILED_LATE` test first |
| M2-16 | Add circle ledger and statement endpoints | BE/Test | M | M2-15 | Member-facing circle ledger excludes other circles; statements include contributions, payouts, arrears | Money-path test: circle statement |
| M2-17 | Add completion flow | BE/Test | S | M2-16 | Final cycle completes circle when obligations resolved or arrears recorded; completion is idempotent | Be explicit about arrears not blocking historical completion |
| M2-18 | Add admin API trio | BE/Test | M | M2-16 | Member 360, ops queue, reversing-entry preview exist over HTTP; no admin UI required | Protect ledger guardrails |
| M2-19 | Add realistic 8-member seed | BE/Infra | M | M2-17 | `make seed` can create an 8-member circle at chosen state; rerunnable; demo-reset can rebuild it | This seed powers pitch and frontend |
| M2-20 | Add M2 Hurl lifetime demo | Test/Docs | M | M2-19 | Hurl story runs create, invite, agreement, lock, draw, collections, payout, late failure, completion | Keep output readable for a stranger |
| M2-21 | Add full-cycle simulation test | Test | M | M2-20 | 8 members, 8 cycles, injected `FAILED_LATE`, replay equals materialized balances, trial balance zero | Exit gate for M2 |
| M2-22 | CHECKPOINT: M2 hardening | Test/Docs/Infra | M | M2-21 | Full suite, import lint, money check, OpenAPI export, Railway staging deploy, M1/M2 Hurl replay, docs updated | No vendor rails until this is stable |

### M3 - StripeRail

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M3-01 | Prepare Stripe sandbox config | BE/Docs | S | M2-22 | Settings reject live Stripe keys; `.env.example` updated; `docs/rails/stripe.md` stub created | Sandbox only |
| M3-02 | Implement Stripe rail skeleton | BE/Test | M | M3-01 | Rail lives under payments Stripe package; unsupported capabilities return `NotSupported`; registry selects it | No SDK imports outside provider package |
| M3-03 | Implement Connect/Identity onboarding | BE/Test | M | M3-02 | `onboard_member` creates sandbox objects or documents gated behavior; webhook mirrors status | Keep Identity vs Connect recommendation in rail doc |
| M3-04 | Implement PaymentIntent top-ups | BE/Test | M | M3-02 | Top-up uses Stripe idempotency key and metadata; maps states into unified state machine | Contract suite applies where possible |
| M3-05 | Implement transfers/payouts | BE/Test | M | M3-03 | Payout path handles transfer then payout; state changes are webhook-confirmed | Two-step ledger posting may need ADR |
| M3-06 | Implement Stripe webhooks and recon | BE/Test | M | M3-04 | Signature verification, raw event persistence, dedupe, balance-transaction reconciliation mismatch test | Keep process async after persist |
| M3-07 | Add Stripe eval row and Hurl demo | Docs/Test | S | M3-06 | `docs/pitch/rail-eval-matrix.md` has Stripe row; demo records real sandbox object IDs | Include hours spent |
| M3-08 | CHECKPOINT: M3 hardening | Test/Docs/Infra | M | M3-07 | Default suite green; `make test-stripe` green or limitations documented; staging config tested | Do not let Stripe shape the port alone |

### M4 - TrueLayerRail

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M4-01 | Prepare TrueLayer sandbox config | BE/Docs | S | M3-08 | Settings reject live credentials; rail doc stub includes sandbox setup notes | JWS verification differs from Stripe |
| M4-02 | Implement TrueLayer rail skeleton | BE/Test | M | M4-01 | Capability flags reflect PIS/AIS/payout access; registry selects rail per flow | Avoid fake support for gated payouts |
| M4-03 | Implement PIS top-up flow | BE/Test | M | M4-02 | Redirect/return flow works; executed vs settled nuance documented; state mapping tested | Treat executed as not necessarily settled |
| M4-04 | Implement AIS account verification | BE/Test | M | M4-02 | Account holder name match persisted with provenance; withdrawal gate can consume result | Good CoP-adjacent demo |
| M4-05 | Implement TrueLayer webhook/recon | BE/Test | M | M4-03 | JWS verification, raw event persistence, dedupe, mismatch writes `recon_break` | Add provider gap cron slot |
| M4-06 | Add mixed-rail demo config | Test/Docs | S | M4-05 | Hurl story proves TrueLayer top-up, Fake or Stripe collection/payout, one ledger | Update Railway env notes |
| M4-07 | CHECKPOINT: M4 hardening | Test/Docs/Infra | M | M4-06 | Default suite green; TrueLayer marked tests pass or gated behavior documented; eval matrix row added | Keep limitations explicit |

### M5 - GoCardlessRail, OpenSanctions, Griffin Spike

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M5-01 | Prepare GoCardless sandbox config | BE/Docs | S | M4-07 | Settings reject live credentials; rail doc stub includes mandate lead-time table | Lead times affect scheduler offsets |
| M5-02 | Implement mandate creation | BE/Test | M | M5-01 | Customer, bank account, mandate redirect flow represented; mandate state mirrored from webhooks | Capability belongs to collection rail |
| M5-03 | Implement recurring collection | BE/Test | M | M5-02 | `collect` maps GC payment states into unified machine; scheduler reads per-rail offset | Money-path test: GC collection |
| M5-04 | Implement GC late-failure flagship test | BE/Test | M | M5-03 | Simulated late failure triggers shortfall, reversing entry, arrears, invariants green | Reuses M2 shortfall machinery |
| M5-05 | Implement GC webhook/recon | BE/Test | M | M5-03 | Signature verification, dedupe retry test, mismatch writes `recon_break` | Document webhook retry behavior |
| M5-06 | Implement OpenSanctions screening port | BE/Test/Docs | M | M5-05 | Matching API behind `ScreeningPort`; hits persist with dataset provenance; review state reaches ops queue | Use fixture/test entity where possible |
| M5-07 | Add screening re-check cron | BE/Test | S | M5-06 | Existing members can be re-screened; review transitions tested; cron registered | Keep alerting simple |
| M5-08 | Griffin 2-day spike | BE/Docs | L | M5-07 | `docs/rails/griffin.md` explains BaaS fit, sandbox progress, go-live requirements; matrix row added | Cut first if behind schedule |
| M5-09 | CHECKPOINT: M5 hardening | Test/Docs/Infra | M | M5-08 | Default suite green; GC/OpenSanctions tests pass or limitations documented; eval matrix current | Protect Stripe plus one other rail if cutting |

### M6 - Pitch Kit

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M6-01 | Wire showcase observability dashboard | Infra/Docs | M | M5-09 | OpenTelemetry Collector plus Grafana/Tempo/Prometheus or Jaeger runs locally; Sentry/log-based checks documented for demo; walkthrough can show one trace from contribution collection to ledger posting | Keep within showcase scope; no on-call theatre |
| M6-02 | Finalize Railway staging environment | Infra/Docs | M | M6-01 | API and worker services deployed; Postgres/Redis managed services attached; `/readyz` green | Record exact env vars |
| M6-03 | Implement full demo reset | BE/Infra/Test | M | M6-02 | `make demo-reset` destroys/reseeds showcase data; reset verified against staging | Must not need manual database poking |
| M6-04 | Write walkthrough script | Docs | S | M6-03 | `docs/pitch/walkthrough.md` fits 10 minutes; timing notes included after rehearsal | Script the failure moments deliberately |
| M6-05 | Finalize rail evaluation matrix | Docs | S | M5-09 | Matrix covers capabilities, sandbox quality, hours, webhooks, failure simulation, pricing, go-live requirements | Use actual experience, not marketing copy |
| M6-06 | Build k6 payday-burst test | Test/Infra | M | M6-03 | Scenario models 1k circles collecting in one hour; output saved reproducibly | Load test should exercise critical API paths |
| M6-07 | Write load-test report | Docs | S | M6-06 | `docs/pitch/load-test.md` includes graphs, bottlenecks, and interpretation | Include methodology before charts |
| M6-08 | Draft three write-up outlines | Docs | S | M6-07 | Ledger, multi-rail port, and late-failure state-machine outlines exist | Third outline is cuttable |
| M6-09 | CHECKPOINT: Pitch rehearsal | Test/Docs/Infra | M | M6-08 | Fresh reset, all Hurl stories replay green, walkthrough timed, repo README presentable | This is the client-facing gate |

### M7 - Frontend

| ID | Title | Layer | Size | Depends on | Acceptance criteria | Notes/risks |
| --- | --- | --- | --- | --- | --- | --- |
| M7-01 | Reconcile frontend prototype with Prompt 4 | FE/Docs | S | M6-09 | Existing routes audited; mock-only pieces listed; `docs/frontend.md` created | Keep useful visual work, replace fake flows |
| M7-02 | Generate typed API client | FE/Test | S | M7-01 | OpenAPI types generated; API wrapper sends `Idempotency-Key` on mutations; auth retry shape decided | Never hand-write API object types |
| M7-03 | Implement real auth flow | FE/Test | M | M7-02 | Register/login/refresh/logout use API; access token stays in memory; no localStorage tokens | Replace `mock-auth.ts` |
| M7-04 | Implement KYC/pending/home states | FE/Test | M | M7-03 | Screens 04-06 covered with loading/empty/error states; polling honest for async status | Backend may still use fake screening in demo |
| M7-05 | Implement wallet flow | FE/Test | M | M7-04 | Balance, activity, top-up, withdrawal screens work against API; payment status polls to terminal state | Money rendered through one component |
| M7-06 | Implement circle creation and invite flow | FE/Test | M | M7-05 | Screens 10-13 covered; form validation clear; mutation invalidation works | Use TanStack Form for money/setup forms |
| M7-07 | Implement draw verification UI | FE/Test | M | M7-06 | Client recomputes order from reveal and published algorithm; verification unit test passes | Signature frontend moment |
| M7-08 | Implement active circle, pay, ledger, statement | FE/Test | M | M7-07 | Screens 16-21 covered; status pills consistent; ledger/statement paths work | Preserve mobile-first layout |
| M7-09 | Add Playwright walkthrough smoke | FE/Test | M | M7-08 | Full scripted walkthrough runs against demo env; no blank screens; keyboard focus visible | Use `docs/pitch/walkthrough.md` |
| M7-10 | CHECKPOINT: Frontend hardening | FE/Test/Docs | M | M7-09 | Build passes; Lighthouse mobile target met on home and circle detail; route-to-wireframe table complete | Admin UI remains cuttable |

## Five Riskiest Tasks

| Task | Risk | Mitigation |
| --- | --- | --- |
| M2-01 | Circle state machine becomes ambiguous and infects every endpoint | Model states/transitions in docs before migrations; keep transition tests small |
| M2-07 | Ledger account design allows cross-circle or duplicated postings | Deterministic account codes and tests that attempt cross-circle misuse |
| M2-08 | Commit-reveal draw is hard to explain or verify | Pure deterministic function, published algorithm, fixed fixtures, frontend recomputation later |
| M2-14/M2-15 | Late failures and shortfalls break ledger invariants | Build from failing `FAILED_LATE` simulation test and only post via ledger recipes |
| M3-06 | Vendor webhooks/recon force port drift | Extend shared contract suite before provider-specific behavior leaks into services |

## Cut List

Protect, in order:

1. Ledger correctness and append-only invariants.
2. Circle engine with full-cycle simulation.
3. Stripe plus one additional real rail.
4. Provider evaluation matrix based on hands-on work.
5. Seeded Railway demo and reset.

Cut first if behind:

1. Griffin spike.
2. Admin UI polish or any admin frontend.
3. Third technical write-up.
4. Frontend admin screens.
5. Non-essential visual polish after Lighthouse/accessibility targets are met.
6. Third real payment rail if Stripe plus one other rail are already strong.

Do not cut:

- Money-path tests.
- Hurl demos for completed milestones.
- OpenAPI export after API changes.
- Docs updates for architecture, contracts, and money flows.

## Pitch-Day Checklist

- Railway staging API and worker are deployed and healthy.
- Managed Postgres and Redis are attached.
- Demo reset has been run from scratch and verified.
- Seeded 8-member circle exists in the expected state.
- M1-M2 Hurl stories replay green.
- Integrated rail Hurl stories replay green or documented sandbox gates are ready to show.
- Walkthrough script is rehearsed and timing noted.
- Load-test graphs are exported and linked from `docs/pitch/load-test.md`.
- Observability dashboard can show traces, metrics, and correlated logs for at
  least one wallet or circle money flow.
- Rail evaluation matrix is current with every attempted rail.
- OpenAPI schema is current.
- Repo README and docs reading order are presentable.
- Live-mode credentials are absent and config still rejects them.
- Final full suite, import lint, typecheck, money check, and migration drift check have been run or any exception is documented.
