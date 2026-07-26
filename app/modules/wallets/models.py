"""Wallet persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Wallet(TimestampMixin, Base):
    __tablename__ = "wallet"
    __table_args__ = (
        CheckConstraint("currency = 'GBP'", name="wallet_currency_gbp"),
        UniqueConstraint("member_id", name="uq_wallet_member_id"),
        UniqueConstraint("pending_account_code", name="uq_wallet_pending_account_code"),
        UniqueConstraint("available_account_code", name="uq_wallet_available_account_code"),
        Index("ix_wallet_provisioned_at", "provisioned_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="CASCADE"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP", server_default="GBP")
    pending_account_code: Mapped[str] = mapped_column(String(80), nullable=False)
    available_account_code: Mapped[str] = mapped_column(String(80), nullable=False)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
