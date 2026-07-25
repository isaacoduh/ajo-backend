# API Conventions

## Errors

Errors use RFC 9457 `application/problem+json`.

- Validation errors include field-level details.
- Unexpected 500s are opaque and include a `trace_id`.
- Stack traces are never exposed to clients.

## Idempotency

Mutating routes require `Idempotency-Key`.

- First response is stored in Redis for 48 hours.
- Replays return byte-identical status, headers, and body.
- Concurrent duplicates return 409.

## Pagination

Collection endpoints use cursor pagination unless a later ADR approves a
different pattern for a specific endpoint.

## OpenAPI

`make openapi` exports the schema to `docs/api/openapi.json`.

