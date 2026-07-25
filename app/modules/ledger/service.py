"""Ledger service boundary."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ledger import PostedEntry, PostingInput, post_entry


class LedgerService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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

