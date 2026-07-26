"""Ledger service boundary."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ledger import GBP, AccountType, PostedEntry, PostingInput, post_entry
from app.modules.ledger.models import JournalEntry, LedgerAccount, Posting


@dataclass(frozen=True)
class AccountActivityRow:
    posting_id: UUID
    journal_entry_id: UUID
    account_code: str
    side: str
    amount_minor: int
    journal_created_at: datetime
    journal_description: str
    currency: str


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_account(
        self,
        *,
        code: str,
        name: str,
        account_type: AccountType,
    ) -> LedgerAccount:
        result = await self.session.execute(select(LedgerAccount).where(LedgerAccount.code == code))
        account = result.scalar_one_or_none()
        if account is not None:
            return account
        account = LedgerAccount(
            code=code,
            name=name,
            account_type=account_type.value,
            currency=GBP,
        )
        self.session.add(account)
        await self.session.flush()
        return account

    async def get_account_by_code(self, code: str) -> LedgerAccount | None:
        result = await self.session.execute(select(LedgerAccount).where(LedgerAccount.code == code))
        return result.scalar_one_or_none()

    async def list_account_activity(
        self,
        *,
        account_codes: Sequence[str],
        limit: int,
        before_created_at: datetime | None = None,
        before_posting_id: UUID | None = None,
    ) -> list[AccountActivityRow]:
        statement = (
            select(
                Posting.id,
                JournalEntry.id,
                LedgerAccount.code,
                Posting.side,
                Posting.amount_minor,
                JournalEntry.created_at,
                JournalEntry.description,
                JournalEntry.currency,
            )
            .join(JournalEntry, Posting.journal_entry_id == JournalEntry.id)
            .join(LedgerAccount, Posting.account_id == LedgerAccount.id)
            .where(LedgerAccount.code.in_(account_codes))
            .order_by(JournalEntry.created_at.desc(), Posting.id.desc())
            .limit(limit)
        )
        if before_created_at is not None and before_posting_id is not None:
            statement = statement.where(
                or_(
                    JournalEntry.created_at < before_created_at,
                    (
                        (JournalEntry.created_at == before_created_at)
                        & (Posting.id < before_posting_id)
                    ),
                )
            )
        result = await self.session.execute(statement)
        return [
            AccountActivityRow(
                posting_id=posting_id,
                journal_entry_id=journal_entry_id,
                account_code=account_code,
                side=side,
                amount_minor=amount_minor,
                journal_created_at=journal_created_at,
                journal_description=journal_description,
                currency=currency,
            )
            for (
                posting_id,
                journal_entry_id,
                account_code,
                side,
                amount_minor,
                journal_created_at,
                journal_description,
                currency,
            ) in result.all()
        ]

    async def post_entry(
        self,
        *,
        idempotency_key: str,
        description: str,
        postings: Sequence[PostingInput],
        reversed_entry_id: UUID | None = None,
    ) -> PostedEntry:
        return await post_entry(
            self.session,
            idempotency_key=idempotency_key,
            description=description,
            postings=postings,
            reversed_entry_id=reversed_entry_id,
        )
