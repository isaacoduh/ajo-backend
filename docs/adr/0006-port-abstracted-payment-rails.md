# ADR 0006: Abstract Payment Rails Behind a Port

Date: 2026-07-25

## Status

Accepted

## Context

The showcase must later demonstrate Stripe, TrueLayer, GoCardless, and Griffin
plugging into the same backend without rewriting money-flow code.

## Decision

Define a `PaymentRailPort` with capability flags and per-flow rail selection.
Implement `FakeRail` first and require future rails to pass the shared contract
test suite unmodified.

## Consequences

- Rails can differ by capability without forcing a lowest-common-denominator API.
- Mixed-rail flows are supported structurally.
- Contract tests become the evidence that integrations are interchangeable.

