# ADR 0004: Make the Internal Ledger Authoritative

Date: 2026-07-25

## Status

Accepted

## Context

External rails provide settlement records, webhooks, and reconciliation inputs,
but provider data can arrive late, out of order, or with rail-specific semantics.

## Decision

The internal append-only double-entry ledger is the authoritative financial
record. Provider records are reconciled against it rather than replacing it.

## Consequences

- Money movement is explained from one consistent ledger.
- Reconciliation breaks are visible instead of silently mutating balances.
- Payment integrations must map provider state into internal state machines.

