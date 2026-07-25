# ADR 0005: Use ARQ for Jobs and Cron

Date: 2026-07-25

## Status

Accepted

## Context

The stack is async Python with FastAPI, SQLAlchemy async, Redis, and Railway.
The worker needs jobs, cron, retries, and a small operational surface.

## Decision

Use ARQ instead of Celery.

## Consequences

- The worker model fits the async application stack.
- Redis remains the only queue dependency.
- The codebase avoids Celery's larger configuration and broker/result-backend
  surface.

