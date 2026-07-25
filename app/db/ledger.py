"""Append-only double-entry ledger primitive."""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting

GBP = "GBP"


class AccountType(StrEnum):
    ASSET = "asset"
    LIABILITY = "liability"
    INCOME = "income"
    EXPENSE = "expense"
    EQUITY = "equity"


class PostingSide(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


@dataclass(frozen=True)
class PostingInput:
    account_id: UUID
    side: PostingSide
    amount_minor: int


@dataclass(frozen=True)
class PostedEntry:
    journal_entry: JournalEntry
    postings: Sequence[Posting]


async def post_entry(
    session: AsyncSession,
    *,
    idempotency_key: str,
    description: str,
    postings: Sequence[PostingInput],
    reversed_entry_id: UUID | None = None,
) -> PostedEntry:
    validate_postings(postings)
    await lock_ledger_hash_chain(session)
    account_ids = sorted({posting.account_id for posting in postings}, key=str)
    accounts = await locked_accounts(session, account_ids)
    if len(accounts) != len(account_ids):
        raise ledger_error("Unknown ledger account.", "unknown-account")

    previous_hash = await latest_entry_hash(session)
    entry_hash = compute_entry_hash(
        idempotency_key=idempotency_key,
        description=description,
        previous_hash=previous_hash,
        postings=postings,
        reversed_entry_id=reversed_entry_id,
    )
    journal_entry = JournalEntry(
        idempotency_key=idempotency_key,
        description=description,
        currency=GBP,
        previous_hash=previous_hash,
        entry_hash=entry_hash,
        reversed_entry_id=reversed_entry_id,
    )
    session.add(journal_entry)
    await session.flush()

    accounts_by_id = {account.id: account for account in accounts}
    stored_postings: list[Posting] = []
    for posting in postings:
        account = accounts_by_id[posting.account_id]
        account.balance_minor += account_delta(
            account_type=AccountType(account.account_type),
            side=posting.side,
            amount_minor=posting.amount_minor,
        )
        if account.account_type == AccountType.LIABILITY and account.balance_minor < 0:
            raise ledger_error("Liability accounts cannot be negative.", "negative-liability")
        stored_posting = Posting(
            journal_entry_id=journal_entry.id,
            account_id=posting.account_id,
            side=posting.side.value,
            amount_minor=posting.amount_minor,
        )
        session.add(stored_posting)
        stored_postings.append(stored_posting)

    await session.flush()
    return PostedEntry(journal_entry=journal_entry, postings=stored_postings)


def validate_postings(postings: Sequence[PostingInput]) -> None:
    if len(postings) < 2:
        raise ledger_error("A journal entry requires at least two postings.", "too-few-postings")
    debit_total = 0
    credit_total = 0
    for posting in postings:
        if posting.amount_minor <= 0:
            raise ledger_error("Posting amounts must be positive.", "non-positive-posting")
        if posting.side == PostingSide.DEBIT:
            debit_total += posting.amount_minor
        else:
            credit_total += posting.amount_minor
    if debit_total != credit_total:
        raise ledger_error("Journal entry is unbalanced.", "unbalanced-entry")


def account_delta(*, account_type: AccountType, side: PostingSide, amount_minor: int) -> int:
    debit_normal = account_type in {AccountType.ASSET, AccountType.EXPENSE}
    if side == PostingSide.DEBIT:
        return amount_minor if debit_normal else -amount_minor
    return -amount_minor if debit_normal else amount_minor


def compute_entry_hash(
    *,
    idempotency_key: str,
    description: str,
    previous_hash: str | None,
    postings: Sequence[PostingInput],
    reversed_entry_id: UUID | None,
) -> str:
    payload = {
        "currency": GBP,
        "description": description,
        "idempotency_key": idempotency_key,
        "postings": [
            {
                "account_id": str(posting.account_id),
                "amount_minor": posting.amount_minor,
                "side": posting.side.value,
            }
            for posting in sorted(postings, key=lambda item: (str(item.account_id), item.side.value))
        ],
        "previous_hash": previous_hash,
        "reversed_entry_id": str(reversed_entry_id) if reversed_entry_id is not None else None,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def replay_balances(
    postings: Iterable[tuple[UUID, AccountType, PostingSide, int]],
) -> dict[UUID, int]:
    balances: dict[UUID, int] = {}
    for account_id, account_type, side, amount_minor in postings:
        balances[account_id] = balances.get(account_id, 0) + account_delta(
            account_type=account_type,
            side=side,
            amount_minor=amount_minor,
        )
    return balances


async def lock_ledger_hash_chain(session: AsyncSession) -> None:
    await session.execute(text("select pg_advisory_xact_lock(2701001)"))


async def latest_entry_hash(session: AsyncSession) -> str | None:
    result = await session.execute(
        select(JournalEntry.entry_hash).order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def locked_accounts(session: AsyncSession, account_ids: Sequence[UUID]) -> list[LedgerAccount]:
    result = await session.execute(
        select(LedgerAccount)
        .where(LedgerAccount.id.in_(account_ids))
        .order_by(LedgerAccount.id)
        .with_for_update()
    )
    return list(result.scalars())


def ledger_error(detail: str, code: str) -> AppError:
    return AppError(
        status_code=422,
        title="Ledger Entry Rejected",
        detail=detail,
        type_=f"https://ajo.dev/problems/ledger-{code}",
    )

