# Ledger

The ledger is the deepest credential in the showcase: append-only,
double-entry, integer minor units, GBP only.

## Tables

- `ledger_account` - account identity, taxonomy, currency, materialized balance.
- `journal_entry` - immutable business event, idempotency key, hash-chain fields.
- `posting` - immutable debit/credit lines linked to one journal entry.

## Account Taxonomy

Initial taxonomy:

- Asset
- Liability
- Income
- Expense
- Equity

Concrete accounts are added by the ledger implementation pass.

## Invariants

- I1: Money is stored only as integer minor units.
- I2: Currency is GBP only for this showcase.
- I3: Every journal entry balances: total debits equal total credits.
- I4: Journal tables are append-only; corrections use reversing entries.
- I5: Liability accounts cannot be driven negative by `post_entry()`.
- I6: Replaying postings from genesis produces the materialized balances.

## Hash Chain

Each journal entry stores a SHA-256 hash over deterministic entry content and the
previous journal hash. This provides tamper evidence and supports replay checks.

The exact canonicalization format lands with `app/db/ledger.py`.

## Posting Recipes

### Contribution

Member contribution collected into the platform settlement account:

- Debit: cash or settlement asset account.
- Credit: member contribution liability account.

### Payout + Fee

Circle payout with a platform fee:

- Debit: member contribution liability account.
- Credit: cash or settlement asset account for payout amount.
- Credit: platform fee income account for fee amount.

### Top-Up

Member ad-hoc top-up:

- Debit: cash or settlement asset account.
- Credit: member wallet or contribution liability account.

### Reversal

Correction for a prior entry:

- Create a new journal entry with postings exactly inverted from the original.
- Link the reversing entry to the original entry.
- Never update or delete the original entry.

## Replay

Replay starts from genesis, applies postings in journal order, and compares the
computed balances with materialized balances. Property tests generate valid
batches and assert trial balance zero plus replay equality.

