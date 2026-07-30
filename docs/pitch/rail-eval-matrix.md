# Rail Evaluation Matrix

| Rail | Implemented capabilities | Sandbox evidence | Webhook posture | Failure simulation | Go-live notes |
| --- | --- | --- | --- | --- | --- |
| Stripe | PaymentIntent top-ups, signature-verified webhooks, recent PaymentIntent reconciliation, optional Connect onboarding skeleton | Not yet run with real sandbox credentials; no object IDs claimed | `Stripe-Signature` HMAC verification, raw `partner_event` persistence, event ID dedupe | PaymentIntent failed/canceled states only; no `FAILED_LATE` claim | Live keys rejected by showcase config; payouts require recipient Connect account mapping before support can be claimed |
