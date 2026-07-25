"""screening notifications

Revision ID: 202607250006
Revises: 202607250005
Create Date: 2026-07-25 00:00:05.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202607250006"
down_revision: str | None = "202607250005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "screening_result",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("subject_name", sa.String(length=200), nullable=False),
        sa.Column("subject_country", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("hits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_screening_result_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_screening_result")),
    )


def downgrade() -> None:
    op.drop_table("screening_result")

