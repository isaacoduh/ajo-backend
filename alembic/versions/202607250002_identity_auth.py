"""identity auth

Revision ID: 202607250002
Revises: 202607250001
Create Date: 2026-07-25 00:00:01.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607250002"
down_revision: str | None = "202607250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("token_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )
    op.create_table(
        "refresh_token",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_refresh_token_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"],
            ["refresh_token.id"],
            name=op.f("fk_refresh_token_replaced_by_token_id_refresh_token"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_token")),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_token_hash"),
    )
    op.create_index("ix_refresh_token_family_id", "refresh_token", ["family_id"], unique=False)
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_refresh_token_user_id", table_name="refresh_token")
    op.drop_index("ix_refresh_token_family_id", table_name="refresh_token")
    op.drop_table("refresh_token")
    op.drop_table("user")
