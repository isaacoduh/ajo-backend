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

General account types:

- Asset
- Liability
- Income
- Expense
- Equity

Balance semantics:

- Asset and expense accounts are debit-normal.
- Liability, income, and equity accounts are credit-normal.
- `balance_minor` is stored in each account's normal-balance direction.

M1 wallet accounts:

- `platform:settlement:gbp` - asset account for FakeRail/provider settlement
  cash used by wallet top-ups and withdrawals.
- `member:{member_id}:wallet:pending:gbp` - liability account for member wallet
  money in flight. Pending money is not available to spend or withdraw.
- `member:{member_id}:wallet:available:gbp` - liability account for member
  wallet money available for withdrawal or future circle use.

The member wallet balance is ledger-derived:

- pending balance = `member:{member_id}:wallet:pending:gbp.balance_minor`.
- available balance = `member:{member_id}:wallet:available:gbp.balance_minor`.

No circle, contribution, arrears, or cross-circle accounts are introduced in M1.

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

### Wallet Account Provisioning

Wallet provisioning creates ledger accounts idempotently by deterministic code:

- `platform:settlement:gbp` as an asset account.
- `member:{member_id}:wallet:pending:gbp` as a liability account.
- `member:{member_id}:wallet:available:gbp` as a liability account.

Provisioning does not post a journal entry and does not change balances.

### Wallet Top-Up Initiated

When FakeRail accepts a member top-up for processing:

- Debit: `platform:settlement:gbp`.
- Credit: `member:{member_id}:wallet:pending:gbp`.

The amount remains pending until settlement is confirmed. The journal entry uses
integer `amount_minor` in GBP and a stable idempotency key derived from the
wallet top-up command.

### Wallet Top-Up Settled

When the provider top-up reaches `SETTLED`:

- Debit: `member:{member_id}:wallet:pending:gbp`.
- Credit: `member:{member_id}:wallet:available:gbp`.

This moves the member wallet liability from pending to available without changing
the total member wallet liability.

### Wallet Withdrawal Initiated

When a member withdrawal is accepted for processing, reserve available funds:

- Debit: `member:{member_id}:wallet:available:gbp`.
- Credit: `member:{member_id}:wallet:pending:gbp`.

The wallet service must reject the command before posting if available balance is
less than `amount_minor`.

### Wallet Withdrawal Settled

When the provider payout reaches `SETTLED`:

- Debit: `member:{member_id}:wallet:pending:gbp`.
- Credit: `platform:settlement:gbp`.

This removes the pending wallet liability and reduces platform settlement cash.

### Failed Payment

If a pending top-up fails before settlement:

- Debit: `member:{member_id}:wallet:pending:gbp`.
- Credit: `platform:settlement:gbp`.

If a pending withdrawal fails before settlement:

- Debit: `member:{member_id}:wallet:pending:gbp`.
- Credit: `member:{member_id}:wallet:available:gbp`.

Failures after settlement use a reversal entry linked to the original settled
journal entry.

### Reversal

Corrections and late failures are new journal entries with postings exactly
inverted from the original entry. The reversing entry links to the original via
`reversed_entry_id`.

Never update or delete journal entries or postings.

### Future Circle Recipes

Circle contribution, payout, fee, arrears, and shortfall recipes are intentionally
left for M2. They must use circle-scoped account codes and must not reuse member
wallet pending or available accounts as hidden circle balances.

## Replay

Replay starts from genesis, applies postings in journal order, and compares the
computed balances with materialized balances. Property tests generate valid
batches and assert trial balance zero plus replay equality.

`make money-check` rejects `float` and `Decimal` references in `app/db` and
`app/modules/ledger`.
