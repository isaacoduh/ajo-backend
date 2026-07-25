# ADR 0003: Store Money as Integer Minor Units

Date: 2026-07-25

## Status

Accepted

## Context

The ledger must be deterministic, replayable, and easy to reason about under
property tests. Floating point and ad hoc decimal handling create avoidable
rounding risks.

## Decision

Store all money amounts as integer minor units. This showcase supports GBP only.

## Consequences

- Ledger arithmetic is exact.
- Tests can grep money paths for banned numeric types.
- Multi-currency support requires a later explicit design decision.

