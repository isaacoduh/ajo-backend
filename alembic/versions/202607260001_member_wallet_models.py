"""member wallet models

Revision ID: 202607260001
Revises: 202607250006
Create Date: 2026-07-26 00:00:01.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607260001"
down_revision: str | None = "202607250006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "member",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("country", sa.String(length=2), server_default="GB", nullable=False),
        sa.Column("screening_state", sa.String(length=40), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("country = 'GB'", name=op.f("ck_member_member_country_gb")),
        sa.CheckConstraint(
            "screening_state in ('pending', 'clear', 'review')",
            name=op.f("ck_member_member_screening_state_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_member_user_id_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_member")),
        sa.UniqueConstraint("user_id", name="uq_member_user_id"),
    )
    op.create_index("ix_member_screening_state", "member", ["screening_state"], unique=False)

    op.create_table(
        "wallet",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="GBP", nullable=False),
        sa.Column("pending_account_code", sa.String(length=80), nullable=False),
        sa.Column("available_account_code", sa.String(length=80), nullable=False),
        sa.Column("provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("currency = 'GBP'", name=op.f("ck_wallet_wallet_currency_gbp")),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["member.id"],
            name=op.f("fk_wallet_member_id_member"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wallet")),
        sa.UniqueConstraint("available_account_code", name="uq_wallet_available_account_code"),
        sa.UniqueConstraint("member_id", name="uq_wallet_member_id"),
        sa.UniqueConstraint("pending_account_code", name="uq_wallet_pending_account_code"),
    )
    op.create_index("ix_wallet_provisioned_at", "wallet", ["provisioned_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_wallet_provisioned_at", table_name="wallet")
    op.drop_table("wallet")
    op.drop_index("ix_member_screening_state", table_name="member")
    op.drop_table("member")
