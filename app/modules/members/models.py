"""Member persistence models."""

from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Member(TimestampMixin, Base):
    __tablename__ = "member"
    __table_args__ = (
        CheckConstraint("country = 'GB'", name="member_country_gb"),
        CheckConstraint("screening_state in ('pending', 'clear', 'review')", name="member_screening_state_valid"),
        UniqueConstraint("user_id", name="uq_member_user_id"),
        Index("ix_member_screening_state", "screening_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="GB", server_default="GB")
    screening_state: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="pending",
        server_default="pending",
    )
