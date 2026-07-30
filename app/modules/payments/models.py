"""Payments persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentObject(Base):
    __tablename__ = "payment_object"
    __table_args__ = (
        UniqueConstraint("provider", "provider_object_id", name="uq_payment_object_provider_object"),
        UniqueConstraint("idempotency_key", name="uq_payment_object_idempotency_key"),
        Index("ix_payment_object_flow", "flow"),
        Index("ix_payment_object_state", "state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_object_id: Mapped[str] = mapped_column(String(200), nullable=False)
    flow: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    amount_minor: Mapped[int | None] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP", server_default="GBP")
    provider_metadata: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    journal_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entry.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PartnerEvent(Base):
    __tablename__ = "partner_event"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_partner_event_provider_event"),
        Index("ix_partner_event_provider_object_id", "provider_object_id"),
        Index("ix_partner_event_processed_at", "processed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_object_id: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ReconBreak(Base):
    __tablename__ = "recon_break"
    __table_args__ = (
        Index("ix_recon_break_provider", "provider"),
        Index("ix_recon_break_resolved_at", "resolved_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_object_id: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
