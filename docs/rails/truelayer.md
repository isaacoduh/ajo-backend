# TrueLayerRail

TrueLayer integration currently supports sandbox wallet top-ups through hosted
Payments v3 bank transfers and a narrow payout path through Payments v3
business-account payouts.

When `RAIL_TOPUP=truelayer`, `POST /wallet/topups` creates a TrueLayer hosted
payment and returns:

```json
{
  "state": "initiated",
  "provider_action": {
    "type": "truelayer_hosted_payment",
    "redirect_url": "https://payment.truelayer-sandbox.com/..."
  }
}
```

The frontend should redirect the member to `provider_action.redirect_url`.
TrueLayer webhooks update the internal payment state and settle wallet top-ups
when the payment status becomes `settled` or `payment_creditable`.

When `RAIL_PAYOUT=truelayer`, wallet withdrawals and circle payouts create a
TrueLayer `POST /v3/payouts` object through the existing payment service flow.
The implemented demo payout type is `business_account`; `external_account` and
`payment_source` remain unsupported because the current request shape does not
carry bank account details or a reusable TrueLayer payment source ID.

Required sandbox env:

```text
RAIL_TOPUP=truelayer
RAIL_PAYOUT=truelayer
TRUELAYER_CLIENT_ID=...
TRUELAYER_CLIENT_SECRET=...
TRUELAYER_KEY_ID=...
TRUELAYER_PRIVATE_KEY_PEM_B64=...
TRUELAYER_MERCHANT_ACCOUNT_ID=...
TRUELAYER_REDIRECT_URI=...
TRUELAYER_API_BASE_URL=https://api.truelayer-sandbox.com
TRUELAYER_AUTH_BASE_URL=https://auth.truelayer-sandbox.com
```

## Webhook Setup

In TrueLayer Console, open the app, then go to Payments > Settings > Webhook URI.
Set the URI to:

```text
https://ajo-backend-production.up.railway.app/payments/webhooks/truelayer
```

TrueLayer allows one webhook URI per app. The backend verifies the `Tl-Signature`
header against TrueLayer's allowed webhook JWKS URLs:

```text
https://webhooks.truelayer-sandbox.com/.well-known/jwks
https://webhooks.truelayer.com/.well-known/jwks
```

The webhook path is part of the signature. If the configured URI changes, keep
the backend route path as `/payments/webhooks/truelayer` or update
`TRUE_LAYER_WEBHOOK_PATH` to match.

## Request Signing

The backend uses TrueLayer's Python signing library through
`app.modules.payments.truelayer_signing.build_signed_json_request`.

Rules:

- Sign the request path only, for example `/v3/payments` or `/v3/payouts`, not
  the full URL.
- Serialize JSON exactly once:

```python
body = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()
```

- Pass those exact `body` bytes to both the signer and `httpx.post(content=body)`.
- If `Idempotency-Key` is signed, send the exact same header value with the
  request.
- Do not add trailing newlines or reformat JSON after signing.
- `TRUELAYER_KEY_ID` must match the public key uploaded in Console, and the
  private key used by the backend must be the matching private key.

The resulting request headers include:

```text
Content-Type: application/json
Idempotency-Key: ...
Tl-Signature: ...
```

## Sandbox Keys

Public keys belong in TrueLayer Console. Private keys remain backend-only and
should be supplied through sandbox environment variables only.

## Demo Evidence

TrueLayer sandbox acceptance is materially proven for the supported wallet
top-up path.

Observed 3000 minor-unit top-up:

- Top-up initiation posted funds into the wallet pending bucket.
- Verified TrueLayer webhook/status processing landed.
- Settlement journal moved 3000 minor units out of pending.
- Settlement journal moved 3000 minor units into available.

This proves the hosted payment top-up, webhook verification/status processing,
and internal wallet settlement recipe in sandbox.

Business-account payout support is also materially proven in sandbox:

- Payout creation uses `POST /v3/payouts`.
- Payout status fetch uses `GET /v3/payouts/{id}` after webhook receipt or
  status polling.
- `payout_executed` maps to internal `settled`.
- `payout_failed` maps to internal `failed`.
- Wallet withdrawal settlement/release is applied by wallet ledger recipes after
  fetched provider state, not by the TrueLayer rail.

Observed 1500 minor-unit payout:

- `RAIL_PAYOUT=truelayer` was enabled in the Railway environment.
- Wallet withdrawal returned `processing`, proving the request used the
  TrueLayer rail rather than the fake rail.
- Withdrawal initiation decreased available funds by 1500 minor units.
- Verified provider webhook/status processing landed.
- Settlement journal moved 1500 minor units out of the wallet pending bucket.

This proves the supported business-account payout creation, webhook/status
processing, and internal wallet settlement recipe in sandbox. It does not claim
production readiness, AIS account verification, `external_account` payouts, or
`payment_source` payouts.
