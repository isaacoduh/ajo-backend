# API Conventions

## Errors

Errors use RFC 9457 `application/problem+json`.

- Validation errors include field-level details.
- Unexpected 500s are opaque and include a `trace_id`.
- Stack traces are never exposed to clients.

Problem responses include:

- `type`
- `title`
- `status`
- `detail`
- `instance`
- `trace_id` when request context exists

Validation errors add `errors`, using FastAPI/Pydantic field locations and
messages.

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

## Request IDs

Clients may send `X-Request-ID`. If omitted, the API generates one. The same
value is returned in the response header, included as `trace_id` in problem
responses, and bound into structured request logs.
