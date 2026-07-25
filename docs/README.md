# Àjọ Backend Docs

This directory is part of the product, not a side channel. A change that alters
architecture, a contract, or a money flow is not done until the relevant document
is updated in the same commit.

## Reading Order

1. `prd.md` - showcase scope and PRD deltas.
2. `architecture.md` - system context, module map, and cross-cutting flows.
3. `ledger.md` - ledger account taxonomy, invariants, posting recipes, replay.
4. `payments.md` - rail port contract, webhook discipline, reconciliation.
5. `api/conventions.md` - API error, idempotency, pagination, and schema rules.
6. `runbooks/local-dev.md` - local Docker Compose workflow.
7. `runbooks/deploy.md` - Railway demo deployment workflow.
8. `adr/` - decision history and deviations from the prompt.

## Directory Map

- `adr/` - architecture decision records.
- `api/` - API conventions and generated OpenAPI export.
- `pitch/` - future evaluation matrix and load-test evidence.
- `rails/` - one provider note per future rail integration.
- `runbooks/` - operational procedures for local, demo, and reset workflows.

## Existing References

The prompt and design artifacts in this directory are preserved as source
material for the build:

- `prompt-1-backend-harness-v2.md`
- `prompt-2-build-sheet-v2.md`
- `prompt-3-rail-integrations.md`
- `prompt-4-frontend-tanstack.md`
- `ajo-wireframes.pdf`
- `ajo-wireframes-v2.pdf`

