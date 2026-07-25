"""Ledger persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class LedgerAccount(TimestampMixin, Base):
    __tablename__ = "ledger_account"
    __table_args__ = (
        CheckConstraint("currency = 'GBP'", name="ledger_account_currency_gbp"),
        CheckConstraint("account_type in ('asset', 'liability', 'income', 'expense', 'equity')", name="ledger_account_type_valid"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(24), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP", server_default="GBP")
    balance_minor: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    postings: Mapped[list["Posting"]] = relationship(back_populates="account")


class JournalEntry(Base):
    __tablename__ = "journal_entry"
    __table_args__ = (
        CheckConstraint("currency = 'GBP'", name="journal_entry_currency_gbp"),
        UniqueConstraint("idempotency_key", name="uq_journal_entry_idempotency_key"),
        UniqueConstraint("entry_hash", name="uq_journal_entry_entry_hash"),
        Index("ix_journal_entry_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP", server_default="GBP")
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reversed_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entry.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    postings: Mapped[list["Posting"]] = relationship(back_populates="journal_entry")


class Posting(Base):
    __tablename__ = "posting"
    __table_args__ = (
        CheckConstraint("side in ('debit', 'credit')", name="posting_side_valid"),
        CheckConstraint("amount_minor > 0", name="posting_amount_positive"),
        Index("ix_posting_journal_entry_id", "journal_entry_id"),
        Index("ix_posting_account_id", "account_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    journal_entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("journal_entry.id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("ledger_account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    journal_entry: Mapped[JournalEntry] = relationship(back_populates="postings")
    account: Mapped[LedgerAccount] = relationship(back_populates="postings")

