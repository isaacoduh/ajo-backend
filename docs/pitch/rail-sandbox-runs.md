# Rail Sandbox Runs

This file keeps redacted provider-run evidence for the pitch kit. It should not
contain bearer tokens, provider secrets, private keys, account numbers, or
unredacted personally identifiable information.

## TrueLayer Top-Up Settlement

- Environment: Railway showcase backend.
- Rail config: `RAIL_TOPUP=truelayer`.
- Amount: 3000 minor units GBP.
- Observed sequence:
  - Wallet top-up initiated at 00:25:58 local operator time.
  - Pending balance increased by 3000 minor units.
  - TrueLayer webhook/status processing landed at 00:28:20 local operator time.
  - Pending balance decreased by 3000 minor units.
  - Available balance increased by 3000 minor units.
- Result: sandbox top-up settlement path proven end-to-end.

## TrueLayer Business-Account Payout Settlement

- Environment: Railway showcase backend.
- Rail config: `RAIL_PAYOUT=truelayer`.
- Internal payment object: `5ce8c1a2-42f3-49cd-b280-ae6a5be2ee13`.
- Amount: 1500 minor units GBP.
- Initial API response state: `processing`.
- Initiation journal: `96bde666-8de4-45a3-9f35-6afaffd703bb`.
- Settlement journal: `6dca62d1-fc54-4068-b5eb-4c725640f8e6`.
- Observed sequence:
  - `2026-08-01T12:54:26.345282Z`: wallet withdrawal initiated; available
    balance decreased by 1500 minor units.
  - `2026-08-01T12:54:28.817010Z`: wallet withdrawal settled; pending balance
    decreased by 1500 minor units.
- Result: sandbox business-account payout settlement path proven end-to-end.

Provider object IDs may be added in redacted form if needed for a live pitch
walkthrough. Do not add access tokens, webhook signatures, secrets, account
numbers, or private key material.
