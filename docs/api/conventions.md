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
- Missing keys return `400 application/problem+json`.
- The in-flight lock expires after 60 seconds if a worker dies mid-request.

## Pagination

Collection endpoints use cursor pagination unless a later ADR approves a
different pattern for a specific endpoint.

## OpenAPI

`make openapi` exports the schema to `docs/api/openapi.json`.

## Request IDs

Clients may send `X-Request-ID`. If omitted, the API generates one. The same
value is returned in the response header, included as `trace_id` in problem
responses, and bound into structured request logs.

## Authentication

Identity routes live under `/auth`:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/logout-all`

Access tokens are JWT bearer tokens with a 15-minute lifetime. Refresh tokens are
opaque 256-bit random values, stored only as HMAC-SHA-256 hashes with the
deployment pepper.

Refresh tokens rotate on every refresh. Reusing a token that was already rotated
or revoked revokes the entire refresh-token family. Password changes bump
`user.token_version`, invalidating older access tokens.

## Rate Limits

Rate limits use Redis fixed windows:

- Auth routes: 5 requests per minute per client IP.
- Authenticated writes: 60 requests per minute per user.

Exceeded limits return `429 application/problem+json` with `Retry-After`.
If Redis is unavailable, rate limiting fails open and emits an ERROR log.
