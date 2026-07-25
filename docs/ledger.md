# Ledger

The ledger is the deepest credential in the showcase: append-only,
double-entry, integer minor units, GBP only.

## Tables

- `ledger_account` - account identity, taxonomy, currency, materialized balance.
- `journal_entry` - immutable business event, idempotency key, hash-chain fields.
- `posting` - immutable debit/credit lines linked to one journal entry.

Implemented fields:

- `ledger_account`: `id`, `code`, `name`, `account_type`, `currency`,
  `balance_minor`, timestamps.
- `journal_entry`: `id`, `idempotency_key`, `description`, `currency`,
  `previous_hash`, `entry_hash`, optional `reversed_entry_id`, `created_at`.
- `posting`: `id`, `journal_entry_id`, `account_id`, `side`, `amount_minor`,
  `created_at`.

The only sanctioned journal write path is `app/db/ledger.py::post_entry()`.

## Account Taxonomy

Initial taxonomy:

- Asset
- Liability
- Income
- Expense
- Equity

Balance semantics:

- Asset and expense accounts are debit-normal.
- Liability, income, and equity accounts are credit-normal.
- `balance_minor` is stored in each account's normal-balance direction.

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

Canonicalization is JSON with sorted keys and compact separators over:

- `currency`
- `description`
- `idempotency_key`
- sorted postings
- `previous_hash`
- `reversed_entry_id`

`post_entry()` takes a Postgres advisory transaction lock before reading the
latest hash, making the hash chain single-writer within a transaction.

## Append-Only Posture

The migration revokes `UPDATE` and `DELETE` on `journal_entry` and `posting` from
`PUBLIC`, and from the local app role `ajo` when present. Corrections must be new
reversing entries.

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

`make money-check` rejects `float` and `Decimal` references in `app/db` and
`app/modules/ledger`.
