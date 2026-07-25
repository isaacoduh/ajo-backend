"""payments port

Revision ID: 202607250005
Revises: 202607250004
Create Date: 2026-07-25 00:00:04.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202607250005"
down_revision: str | None = "202607250004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payment_object",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_object_id", sa.String(length=200), nullable=False),
        sa.Column("flow", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="GBP", nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["journal_entry.id"],
            name=op.f("fk_payment_object_journal_entry_id_journal_entry"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_object")),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_object_idempotency_key"),
        sa.UniqueConstraint("provider", "provider_object_id", name="uq_payment_object_provider_object"),
    )
    op.create_table(
        "partner_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=False),
        sa.Column("provider_object_id", sa.String(length=200), nullable=False),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_event")),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_partner_event_provider_event"),
    )
    op.create_table(
        "recon_break",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_object_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recon_break")),
    )
    op.create_index("ix_payment_object_flow", "payment_object", ["flow"], unique=False)
    op.create_index("ix_payment_object_state", "payment_object", ["state"], unique=False)
    op.create_index("ix_partner_event_processed_at", "partner_event", ["processed_at"], unique=False)
    op.create_index("ix_partner_event_provider_object_id", "partner_event", ["provider_object_id"], unique=False)
    op.create_index("ix_recon_break_provider", "recon_break", ["provider"], unique=False)
    op.create_index("ix_recon_break_resolved_at", "recon_break", ["resolved_at"], unique=False)
    op.execute("REVOKE UPDATE, DELETE ON TABLE partner_event FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ajo') THEN
                REVOKE UPDATE, DELETE ON TABLE partner_event FROM ajo;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_recon_break_resolved_at", table_name="recon_break")
    op.drop_index("ix_recon_break_provider", table_name="recon_break")
    op.drop_index("ix_partner_event_provider_object_id", table_name="partner_event")
    op.drop_index("ix_partner_event_processed_at", table_name="partner_event")
    op.drop_index("ix_payment_object_state", table_name="payment_object")
    op.drop_index("ix_payment_object_flow", table_name="payment_object")
    op.drop_table("recon_break")
    op.drop_table("partner_event")
    op.drop_table("payment_object")

