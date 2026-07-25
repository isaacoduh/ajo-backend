"""jobs harness

Revision ID: 202607250004
Revises: 202607250003
Create Date: 2026-07-25 00:00:03.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202607250004"
down_revision: str | None = "202607250003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "failed_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.String(length=200), nullable=True),
        sa.Column("function_name", sa.String(length=200), nullable=False),
        sa.Column("queue_name", sa.String(length=200), nullable=True),
        sa.Column("try_number", sa.Integer(), nullable=True),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_type", sa.String(length=200), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_failed_jobs")),
    )


def downgrade() -> None:
    op.drop_table("failed_jobs")

