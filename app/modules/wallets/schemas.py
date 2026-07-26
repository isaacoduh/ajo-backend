"""Wallet API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WalletBalanceResponse(BaseModel):
    currency: str
    available_minor: int
    pending_minor: int


class WalletActivityItemResponse(BaseModel):
    id: UUID
    journal_entry_id: UUID
    created_at: datetime
    description: str
    currency: str
    amount_minor: int
    direction: str
    wallet_balance_bucket: str


class WalletActivityResponse(BaseModel):
    items: list[WalletActivityItemResponse]
    next_cursor: str | None
