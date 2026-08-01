# StripeRail

StripeRail integrates Stripe sandbox objects behind `PaymentRailPort`. Wallet,
circle, ledger, and member services continue to call the payment service and rail
registry only; they do not import Stripe code or SDK types.

## Sandbox Setup

1. Create or use a Stripe test-mode account.
2. Copy a test secret key beginning with `sk_test_`.
3. For local webhooks, install the Stripe CLI and run:

```bash
make stripe-listen
```

4. Copy the emitted `whsec_...` value into `STRIPE_WEBHOOK_SECRET`.
5. Set `RAIL_TOPUP=stripe` to use Stripe for wallet top-ups. Leave collection
   and payout rails as `fake` unless a later pass implements those capabilities.

## Required Environment

```bash
RAIL_TOPUP=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_API_BASE_URL=https://api.stripe.com
```

Optional Connect onboarding sandbox settings:

```bash
STRIPE_CONNECT_ENABLED=true
STRIPE_CONNECT_REFRESH_URL=http://localhost:3000/stripe/refresh
STRIPE_CONNECT_RETURN_URL=http://localhost:3000/stripe/return
```

`STRIPE_PUBLISHABLE_KEY` may be set for frontend use, but backend rail calls only
require the secret key and webhook signing secret.

## Live-Key Rejection

This showcase rejects live-mode payment credentials. Any environment variable
whose name looks like a payment secret and whose value contains patterns such as
`sk_live`, `pk_live`, or `whsec_live` fails configuration validation. This is
intentionally stricter than production-ready behavior because the project is a
showcase and must not accidentally touch real money.

If any flow is configured as `stripe`, `STRIPE_SECRET_KEY` is required. Connect
onboarding also requires both Connect return URLs.

## Supported Flows

- Top-up: creates a Stripe PaymentIntent using the internal idempotency key as
  Stripe's `Idempotency-Key`.
- Frontend handoff: wallet top-up responses include
  `provider_action.type=stripe_payment_intent` and the PaymentIntent
  `client_secret` so the frontend can mount Stripe Elements without exposing
  provider details elsewhere.
- Webhooks: verifies Stripe HMAC signatures, persists raw events, dedupes by
  event ID, then mirrors current provider state.
- Wallet settlement: when a top-up PaymentIntent reaches `succeeded`, the
  provider webhook orchestration asks the wallet service to post the internal
  pending-to-available settlement recipe.
- Reconciliation: lists recent PaymentIntents and compares provider state against
  internal `payment_object` rows.
- Connect onboarding: creates an Express account and account-link when
  `STRIPE_CONNECT_ENABLED=true`.

## Unsupported Flows

- Mandates and scheduled collections are not claimed for StripeRail in this pass.
- Payout execution is not claimed because the current `PayoutRequest` has no
  provider-account mapping for a recipient Connect account. `send_payout`
  returns `NotSupported`.
- Stripe Identity is not implemented in this pass. It belongs beside the
  screening/member boundary and should not be squeezed into the payment rail
  without a separate evidence model.

## Webhook Events Consumed

The route is:

```text
POST /payments/webhooks/stripe
```

The route verifies `Stripe-Signature`, stores the raw event in `partner_event`,
and fetches the current PaymentIntent before applying state.

Relevant events:

- `payment_intent.processing`
- `payment_intent.succeeded`
- `payment_intent.payment_failed`
- `payment_intent.canceled`

The implementation does not trust event deltas alone. It uses the event only to
identify the provider object, then calls Stripe for the current state.

When the fetched state maps to `settled`, wallet top-ups move funds with an
idempotent ledger entry:

```text
debit  member:{id}:wallet:pending:gbp
credit member:{id}:wallet:available:gbp
```

The journal idempotency key is `wallet-topup:{idempotency_key}:settled`, so
duplicate Stripe deliveries do not double-credit the wallet.

## State Mapping

| Stripe PaymentIntent status | Internal settlement state |
| --- | --- |
| `requires_payment_method` | `initiated` |
| `requires_confirmation` | `initiated` |
| `requires_action` | `initiated` |
| `processing` | `processing` |
| `requires_capture` | `processing` |
| `succeeded` | `settled` |
| `canceled` | `failed` |
| unknown status | `processing` |

The backend creates new PaymentIntents with
`automatic_payment_methods[allow_redirects]=never` for the current frontend
handoff path. If redirect-based methods are added later, the frontend must own a
real return URL and the rail docs should be updated with that redirect flow.

Stripe PaymentIntents do not map to `failed_late` in this pass. Bacs-style late
failure behavior remains represented by FakeRail and future debit rails.

## Reconciliation

StripeRail's reconciliation source is the PaymentIntent list endpoint. The
payment service compares each provider line against `payment_object` by
idempotency key and writes `recon_break` rows for missing internal objects or
state mismatches.

Webhook processing also records reconciliation breaks when a Stripe event points
to a missing internal payment object or attempts a conflicting state move, such
as moving an already settled internal object back to processing.

## Demo Evidence

Stripe sandbox acceptance is materially proven for the supported wallet top-up
path. A sandbox PaymentIntent run created a provider object, replayed a signed
webhook through `/payments/webhooks/stripe`, processed the fetched provider
state, and settled the internal wallet top-up without provider code posting
ledger entries directly.

This evidence proves the supported PaymentIntent top-up/webhook settlement path
in sandbox. It does not claim production readiness, Stripe Identity, mandates,
or payout execution.
