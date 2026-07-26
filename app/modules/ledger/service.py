"""Ledger service boundary."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ledger import GBP, AccountType, PostedEntry, PostingInput, post_entry
from app.modules.ledger.models import LedgerAccount


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
