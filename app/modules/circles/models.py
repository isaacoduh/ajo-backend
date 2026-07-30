"""Circle persistence models."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Circle(TimestampMixin, Base):
    __tablename__ = "circle"
    __table_args__ = (
        CheckConstraint("currency = 'GBP'", name="circle_currency_gbp"),
        CheckConstraint(
            "state in ('draft', 'recruiting', 'agreement_pending', 'locked', 'draw_pending', 'active', 'completed', 'cancelled')",
            name="circle_state_valid",
        ),
        CheckConstraint("contribution_amount_minor > 0", name="circle_contribution_positive"),
        CheckConstraint("member_count_target >= 2", name="circle_member_count_target_min"),
        CheckConstraint("cycle_count >= 1", name="circle_cycle_count_positive"),
        Index("ix_circle_owner_member_id", "owner_member_id"),
        Index("ix_circle_state", "state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", server_default="draft")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="GBP", server_default="GBP")
    contribution_amount_minor: Mapped[int] = mapped_column(nullable=False)
    member_count_target: Mapped[int] = mapped_column(nullable=False)
    cycle_count: Mapped[int] = mapped_column(nullable=False)
    cadence: Mapped[str] = mapped_column(String(24), nullable=False, default="monthly", server_default="monthly")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    terms: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CircleMember(TimestampMixin, Base):
    __tablename__ = "circle_member"
    __table_args__ = (
        CheckConstraint("role in ('owner', 'member')", name="circle_member_role_valid"),
        CheckConstraint("status in ('active', 'removed')", name="circle_member_status_valid"),
        UniqueConstraint("circle_id", "member_id", name="uq_circle_member_circle_member"),
        Index("ix_circle_member_member_id", "member_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", server_default="active")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CircleInvite(TimestampMixin, Base):
    __tablename__ = "circle_invite"
    __table_args__ = (
        CheckConstraint("status in ('pending', 'accepted', 'expired', 'revoked')", name="circle_invite_status_valid"),
        UniqueConstraint("token", name="uq_circle_invite_token"),
        Index("ix_circle_invite_circle_id", "circle_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    invited_by_member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    token: Mapped[str] = mapped_column(String(80), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by_member_id: Mapped[UUID | None] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CircleAgreement(TimestampMixin, Base):
    __tablename__ = "circle_agreement"
    __table_args__ = (
        UniqueConstraint("circle_id", "member_id", name="uq_circle_agreement_circle_member"),
        Index("ix_circle_agreement_circle_id", "circle_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    contribution_amount_minor: Mapped[int] = mapped_column(nullable=False)
    cadence: Mapped[str] = mapped_column(String(24), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    payout_rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CircleDraw(TimestampMixin, Base):
    __tablename__ = "circle_draw"
    __table_args__ = (
        UniqueConstraint("circle_id", name="uq_circle_draw_circle_id"),
        Index("ix_circle_draw_circle_id", "circle_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    commitment_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    salt: Mapped[str | None] = mapped_column(String(160))
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payout_order: Mapped[list[str] | None] = mapped_column(JSONB)


class CircleCycle(TimestampMixin, Base):
    __tablename__ = "circle_cycle"
    __table_args__ = (
        CheckConstraint("position >= 1", name="circle_cycle_position_positive"),
        CheckConstraint("status in ('scheduled', 'collecting', 'paid_out', 'completed')", name="circle_cycle_status_valid"),
        UniqueConstraint("circle_id", "position", name="uq_circle_cycle_circle_position"),
        Index("ix_circle_cycle_due_date", "due_date"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    recipient_member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled", server_default="scheduled")


class CircleContribution(TimestampMixin, Base):
    __tablename__ = "circle_contribution"
    __table_args__ = (
        CheckConstraint(
            "status in ('due', 'processing', 'paid', 'failed', 'late_failed', 'arrears')",
            name="circle_contribution_status_valid",
        ),
        UniqueConstraint("cycle_id", "member_id", name="uq_circle_contribution_cycle_member"),
        Index("ix_circle_contribution_circle_id", "circle_id"),
        Index("ix_circle_contribution_payment_object_id", "payment_object_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("circle_cycle.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="due", server_default="due")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_object_id: Mapped[UUID | None] = mapped_column(ForeignKey("payment_object.id"))
    collected_journal_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entry.id"))
    late_failure_journal_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entry.id"))


class CirclePayout(TimestampMixin, Base):
    __tablename__ = "circle_payout"
    __table_args__ = (
        CheckConstraint("status in ('pending', 'processing', 'paid', 'failed')", name="circle_payout_status_valid"),
        UniqueConstraint("cycle_id", name="uq_circle_payout_cycle_id"),
        Index("ix_circle_payout_circle_id", "circle_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("circle_cycle.id", ondelete="CASCADE"), nullable=False)
    recipient_member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    shortfall_minor: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", server_default="pending")
    payment_object_id: Mapped[UUID | None] = mapped_column(ForeignKey("payment_object.id"))
    journal_entry_id: Mapped[UUID | None] = mapped_column(ForeignKey("journal_entry.id"))


class CircleArrearsRecord(TimestampMixin, Base):
    __tablename__ = "circle_arrears_record"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="circle_arrears_amount_positive"),
        Index("ix_circle_arrears_circle_id", "circle_id"),
        Index("ix_circle_arrears_member_id", "member_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("circle_cycle.id", ondelete="CASCADE"), nullable=False)
    contribution_id: Mapped[UUID | None] = mapped_column(ForeignKey("circle_contribution.id", ondelete="SET NULL"))
    member_id: Mapped[UUID] = mapped_column(ForeignKey("member.id", ondelete="RESTRICT"), nullable=False)
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)


class CircleShortfallRecord(TimestampMixin, Base):
    __tablename__ = "circle_shortfall_record"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="circle_shortfall_amount_positive"),
        Index("ix_circle_shortfall_circle_id", "circle_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    circle_id: Mapped[UUID] = mapped_column(ForeignKey("circle.id", ondelete="CASCADE"), nullable=False)
    cycle_id: Mapped[UUID] = mapped_column(ForeignKey("circle_cycle.id", ondelete="CASCADE"), nullable=False)
    payout_id: Mapped[UUID | None] = mapped_column(ForeignKey("circle_payout.id", ondelete="SET NULL"))
    amount_minor: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
