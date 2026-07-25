"""ledger primitives

Revision ID: 202607250003
Revises: 202607250002
Create Date: 2026-07-25 00:00:02.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607250003"
down_revision: str | None = "202607250002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_account",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=24), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="GBP", nullable=False),
        sa.Column("balance_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("account_type in ('asset', 'liability', 'income', 'expense', 'equity')", name=op.f("ck_ledger_account_ledger_account_type_valid")),
        sa.CheckConstraint("currency = 'GBP'", name=op.f("ck_ledger_account_ledger_account_currency_gbp")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_account")),
        sa.UniqueConstraint("code", name=op.f("uq_ledger_account_code")),
    )
    op.create_table(
        "journal_entry",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="GBP", nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=True),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("reversed_entry_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("currency = 'GBP'", name=op.f("ck_journal_entry_journal_entry_currency_gbp")),
        sa.ForeignKeyConstraint(
            ["reversed_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_journal_entry_reversed_entry_id_journal_entry"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry")),
        sa.UniqueConstraint("entry_hash", name="uq_journal_entry_entry_hash"),
        sa.UniqueConstraint("idempotency_key", name="uq_journal_entry_idempotency_key"),
    )
    op.create_table(
        "posting",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("side", sa.String(length=6), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_posting_posting_amount_positive")),
        sa.CheckConstraint("side in ('debit', 'credit')", name=op.f("ck_posting_posting_side_valid")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["ledger_account.id"],
            name=op.f("fk_posting_account_id_ledger_account"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_posting_journal_entry_id_journal_entry"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posting")),
    )
    op.create_index("ix_journal_entry_created_at", "journal_entry", ["created_at"], unique=False)
    op.create_index("ix_posting_account_id", "posting", ["account_id"], unique=False)
    op.create_index("ix_posting_journal_entry_id", "posting", ["journal_entry_id"], unique=False)
    op.execute("REVOKE UPDATE, DELETE ON TABLE journal_entry, posting FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ajo') THEN
                REVOKE UPDATE, DELETE ON TABLE journal_entry, posting FROM ajo;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_posting_journal_entry_id", table_name="posting")
    op.drop_index("ix_posting_account_id", table_name="posting")
    op.drop_index("ix_journal_entry_created_at", table_name="journal_entry")
    op.drop_table("posting")
    op.drop_table("journal_entry")
    op.drop_table("ledger_account")

