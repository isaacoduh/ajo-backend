# ADR 0002: Use a Monolith-First Backend

Date: 2026-07-25

## Status

Accepted

## Context

The showcase targets a solo developer workflow, local Docker Compose, and a
Railway demo deploy. The design load is modest enough for one service, while the
correctness surface around money movement is high.

## Decision

Build a modular FastAPI monolith. Module boundaries are enforced in code, but
deployment remains one API service and one worker service.

## Consequences

- Transactions and ledger consistency stay straightforward.
- Local development remains fast and inspectable.
- Future extraction is possible if module boundaries stay clean.

