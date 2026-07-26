"""Wallet API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


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


class WalletTopupRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    currency: str


class WalletTopupResponse(BaseModel):
    id: UUID
    amount_minor: int
    currency: str
    state: str


class WalletWithdrawalRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    currency: str


class WalletWithdrawalResponse(BaseModel):
    id: UUID
    amount_minor: int
    currency: str
    state: str


class WalletStatementResponse(BaseModel):
    period: str
    currency: str
    opening_balance_minor: int
    movement_minor: int
    closing_balance_minor: int
    journal_entry_ids: list[UUID]
