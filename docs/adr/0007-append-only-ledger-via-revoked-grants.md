# ADR 0007: Enforce Append-Only Ledger with Revoked Grants

Date: 2026-07-25

## Status

Accepted

## Context

Application-level conventions are not enough for the showcase ledger claim. The
database must make mutation of journal history structurally difficult.

## Decision

Ledger journal tables are append-only. Corrections use reversing entries, and
the application database role has `UPDATE` and `DELETE` revoked on journal
tables.

## Consequences

- Accidental mutation of ledger history is blocked below application code.
- Migrations need a privileged role or controlled migration context.
- Tests must verify correction behavior through new entries, not updates.

