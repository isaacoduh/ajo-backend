# Product Requirements

Canonical PRD: see `AJO-PRD-001`.

This backend pass implements the showcase chassis only:

- Python/FastAPI backend harness.
- Local Docker Compose and Railway-compatible runtime posture.
- Cross-cutting reliability harnesses.
- Identity/authentication foundation.
- Append-only double-entry ledger primitives.
- Provider-plural payment rail port with `FakeRail`.
- Screening and notification ports.

Out of scope for this pass:

- Real payment provider integrations.
- Circle product workflows beyond the skeleton module.
- Frontend implementation.
- Live operation tooling such as on-call rotations or public status pages.

## Showcase Deltas

- The system is structurally incapable of booting with live-mode payment
  credentials.
- The internal ledger is authoritative even when provider journals disagree.
- Payment rails are configured per flow rather than globally.
- Documentation is delivery criteria for architecture, contract, and money-flow
  changes.

