"""Worker persistence models."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FailedJob(Base):
    __tablename__ = "failed_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[str | None] = mapped_column(String(200))
    function_name: Mapped[str] = mapped_column(String(200), nullable=False)
    queue_name: Mapped[str | None] = mapped_column(String(200))
    try_number: Mapped[int | None] = mapped_column()
    args: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_type: Mapped[str] = mapped_column(String(200), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

