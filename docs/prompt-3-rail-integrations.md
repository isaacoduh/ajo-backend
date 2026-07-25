# PROMPT 3 — Rail Integration (reusable: run once per vendor, in milestone order)

Usage: paste the **Common contract** section plus exactly ONE vendor section per session (M3 Stripe → M4 TrueLayer → M5 GoCardless, Griffin, OpenSanctions). Requires the v2 harness and M2 circle engine.

---

## Common contract (include every time)

You are a staff engineer integrating a real payment vendor's **sandbox** into Àjọ's multi-rail architecture. Rules that apply to every vendor:

1. **The port is law.** Implement the vendor behind `PaymentRailPort`. No vendor SDK import outside `modules/payments/{vendor}/`. Unsupported capabilities return `NotSupported` and set capability flags — never fake a capability.
2. **The contract suite is the exit gate.** `tests/contract/test_payment_rail_contract.py` must pass against this rail **unmodified**. If the suite can't express a vendor behaviour, extend the suite (all rails re-run) — never special-case one rail.
3. **Sandbox only, structurally.** Config validation rejects live credentials for this vendor. `.env.example` updated with sandbox key names.
4. Webhooks follow the harness pipeline: signature verify (implement this vendor's scheme) → persist raw to `partner_event` with `provider` set → 200 → async process → dedupe on vendor event id → state driven by fetched object state. Register the vendor's gap-detection cron.
5. Map vendor states into the unified settlement machine `INITIATED → PROCESSING → SETTLED | FAILED | FAILED_LATE`; document the mapping table in the rail doc.
6. Reconciliation: implement this vendor's statement/transaction fetch in the nightly recon job; write one test seeding a deliberate mismatch and asserting the `recon_break`.
7. Ledger postings go through existing recipes — a rail never invents postings.
8. Integration tests marked `@pytest.mark.{vendor}`, excluded from default suite, run via `make test-{vendor}`; record real sandbox object IDs in test fixtures docs.
9. **Deliverables beyond code**, same commit series: `docs/rails/{vendor}.md` (what was integrated, state-mapping table, webhook events handled, sandbox tricks/gotchas discovered, capability matrix row, integration hours actually spent — check git log) and a new row appended to `docs/pitch/rail-eval-matrix.md`. Add an ADR if the vendor forced a port change.
10. Timebox honesty: if something is sales-gated or sandbox-broken, document the wall in the rail doc and stop — a documented limitation is a consultancy asset; a hacked workaround is a liability.

---

## Vendor section — STRIPE (run for M3)

Scope: Stripe Connect Express + Payment Intents + Transfers/Payouts + Stripe Identity, test mode.

- `onboard_member` → create Connect Express account, generate onboarding link, mirror `charges_enabled`/`payouts_enabled` from `account.updated` webhooks into `rail_status`. KYC leg: Stripe Identity verification session as the `ScreeningPort`-adjacent identity evidence (document how Identity vs Connect onboarding overlap and which you'd recommend to a client).
- `create_topup` → PaymentIntent, methods = Bacs DD + Pay by Bank (no cards), `transfer_group=circle:{id}:cycle:{n}`, our idempotency key as Stripe's, metadata carries member/circle/cycle.
- `send_payout` → Transfer (platform → connected account) then Payout to external account; two webhook-confirmed steps, two ledger postings.
- **Bacs late-failure is the flagship**: use Stripe's Bacs test bank numbers to drive a real `payment_intent.succeeded` → later failure sequence in an integration test; assert the shortfall/arrears flow and reversing entry fire correctly.
- Webhooks minimum: `account.updated`, `payment_intent.processing|succeeded|payment_failed`, `charge.dispute.created`, `transfer.created`, `payout.paid|failed`, `charge.refunded`. `make stripe-listen` wired for local forwarding.
- Recon source: Balance Transactions API.
- Rail doc extras: Express vs Custom recommendation; test-clock usage notes; fee model summary for the eval matrix.

## Vendor section — TRUELAYER (run for M4)

Scope: sandbox console app; Payments API (PIS) for top-ups; Data API (AIS) for account ownership verification; sandbox payouts if the sandbox tier allows (document if gated).

- `create_topup` → PIS single immediate payment via TrueLayer's mock bank; handle the redirect/HPP flow server-side with a return endpoint; map `executed/settled/failed` into the settlement machine (note: PIS "executed" ≠ funds received — treat settlement confirmation as the SETTLED trigger and document the nuance; it is the Open Banking equivalent of the Bacs truth).
- AIS: fetch account + holder name, implement name-match against the member's verified legal name → this is our CoP-equivalent for withdrawals; store the verification result with provenance.
- `send_payout` → Payouts API against sandbox if available; else `NotSupported` + documented gating.
- Webhooks: payment status events with TrueLayer's signing scheme (JWS) — implement verification properly, it differs from Stripe's HMAC and the difference is a good rail-doc paragraph.
- After this rail: add the **mixed-rail demo config** (`RAIL_TOPUP=truelayer`, `RAIL_COLLECTION=fake`, `RAIL_PAYOUT=stripe`) and a Hurl story proving one ledger across three rails.

## Vendor section — GOCARDLESS (run for M5)

Scope: sandbox; Bacs DD mandates + recurring collections; the deepest DD lifecycle available self-serve.

- `create_mandate` → customer + bank account + mandate via redirect flow; mandate states mirrored from webhooks (`pending_submission → submitted → active | failed | cancelled`).
- `collect` → payment against mandate for the contribution amount; map GC payment states incl. `charged_back` and `late_failure` — **GC lets you simulate late failures and chargebacks by magic bank-account numbers in sandbox: use them.** The flagship test: circle collection succeeds → GC late-failure fires days later (simulated) → shortfall machine + reversing entry + arrears, invariants green. This proves the state machine is not Stripe-shaped.
- Webhooks: GC's signature scheme; events for mandates + payments; their webhook retries are aggressive — dedupe test required.
- Recon source: GC payouts/events API reports.
- Rail doc extras: mandate lead times table (why collection cron needs N-day offsets per rail — make the offset a per-rail config the scheduler reads), pricing capped-percentage note for the matrix.

## Vendor section — GRIFFIN (run for M5, strict 2-day timebox)

Scope: spike, not a full rail. Goal is credible BaaS/safeguarding fluency, not completeness.

- Sandbox: create an organisation, a customer with onboarding/verification workflow, open an account, execute an internal sandbox payment. Wrap only what fits naturally in a `GriffinRail` with most capabilities `NotSupported`.
- Output weighted toward the doc: `docs/rails/griffin.md` — how a real bank BaaS differs from PSP-style rails (safeguarded accounts, verification workflows, FPS access), what Àjọ's "proper" Phase-1 architecture would look like on Griffin, and what go-live onboarding requires. Matrix row included. Stop at the timebox even if incomplete; write down where you stopped and why.

## Vendor section — OPENSANCTIONS (run for M5)

Scope: implement `ScreeningPort` against the OpenSanctions matching API (free/self-serve tier).

- `screen_person` → match endpoint with name/DOB/country; parse scores; threshold config; persist hits with dataset provenance; onboarding flow routes hits to a `COMPLIANCE_REVIEW` member state surfaced in the admin ops queue.
- Delta re-screening cron for existing members.
- Tests: fixture a known sanctioned name (OpenSanctions publishes test entities) end-to-end into review state; a clear name passes.
- Doc: `docs/rails/opensanctions.md` — matching-quality notes, threshold rationale, what a production fincrime stack adds beyond this (name-check ComplyAdvantage/vendor tier for the matrix).
