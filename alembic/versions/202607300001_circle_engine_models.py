"""circle engine models

Revision ID: 202607300001
Revises: 202607260001
Create Date: 2026-07-30 00:00:01.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202607300001"
down_revision: str | None = "202607260001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "circle",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_member_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=40), server_default="draft", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="GBP", nullable=False),
        sa.Column("contribution_amount_minor", sa.Integer(), nullable=False),
        sa.Column("member_count_target", sa.Integer(), nullable=False),
        sa.Column("cycle_count", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=24), server_default="monthly", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("currency = 'GBP'", name=op.f("ck_circle_circle_currency_gbp")),
        sa.CheckConstraint("contribution_amount_minor > 0", name=op.f("ck_circle_circle_contribution_positive")),
        sa.CheckConstraint("member_count_target >= 2", name=op.f("ck_circle_circle_member_count_target_min")),
        sa.CheckConstraint("cycle_count >= 1", name=op.f("ck_circle_circle_cycle_count_positive")),
        sa.CheckConstraint(
            "state in ('draft', 'recruiting', 'agreement_pending', 'locked', 'draw_pending', 'active', 'completed', 'cancelled')",
            name=op.f("ck_circle_circle_state_valid"),
        ),
        sa.ForeignKeyConstraint(["owner_member_id"], ["member.id"], name=op.f("fk_circle_owner_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle")),
    )
    op.create_index("ix_circle_owner_member_id", "circle", ["owner_member_id"], unique=False)
    op.create_index("ix_circle_state", "circle", ["state"], unique=False)

    op.create_table(
        "circle_member",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role in ('owner', 'member')", name=op.f("ck_circle_member_circle_member_role_valid")),
        sa.CheckConstraint("status in ('active', 'removed')", name=op.f("ck_circle_member_circle_member_status_valid")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_member_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], name=op.f("fk_circle_member_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_member")),
        sa.UniqueConstraint("circle_id", "member_id", name="uq_circle_member_circle_member"),
    )
    op.create_index("ix_circle_member_member_id", "circle_member", ["member_id"], unique=False)

    op.create_table(
        "circle_invite",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("invited_by_member_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_member_id", sa.UUID(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('pending', 'accepted', 'expired', 'revoked')", name=op.f("ck_circle_invite_circle_invite_status_valid")),
        sa.ForeignKeyConstraint(["accepted_by_member_id"], ["member.id"], name=op.f("fk_circle_invite_accepted_by_member_id_member"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_invite_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_member_id"], ["member.id"], name=op.f("fk_circle_invite_invited_by_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_invite")),
        sa.UniqueConstraint("token", name="uq_circle_invite_token"),
    )
    op.create_index("ix_circle_invite_circle_id", "circle_invite", ["circle_id"], unique=False)

    op.create_table(
        "circle_agreement",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("contribution_amount_minor", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(length=24), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("payout_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_agreement_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], name=op.f("fk_circle_agreement_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_agreement")),
        sa.UniqueConstraint("circle_id", "member_id", name="uq_circle_agreement_circle_member"),
    )
    op.create_index("ix_circle_agreement_circle_id", "circle_agreement", ["circle_id"], unique=False)

    op.create_table(
        "circle_draw",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("commitment_hash", sa.String(length=64), nullable=False),
        sa.Column("salt", sa.String(length=160), nullable=True),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payout_order", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_draw_circle_id_circle"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_draw")),
        sa.UniqueConstraint("circle_id", name="uq_circle_draw_circle_id"),
    )
    op.create_index("ix_circle_draw_circle_id", "circle_draw", ["circle_id"], unique=False)

    op.create_table(
        "circle_cycle",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("recipient_member_id", sa.UUID(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="scheduled", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 1", name=op.f("ck_circle_cycle_circle_cycle_position_positive")),
        sa.CheckConstraint("status in ('scheduled', 'collecting', 'paid_out', 'completed')", name=op.f("ck_circle_cycle_circle_cycle_status_valid")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_cycle_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_member_id"], ["member.id"], name=op.f("fk_circle_cycle_recipient_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_cycle")),
        sa.UniqueConstraint("circle_id", "position", name="uq_circle_cycle_circle_position"),
    )
    op.create_index("ix_circle_cycle_due_date", "circle_cycle", ["due_date"], unique=False)

    op.create_table(
        "circle_contribution",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="due", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_object_id", sa.UUID(), nullable=True),
        sa.Column("collected_journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("late_failure_journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('due', 'processing', 'paid', 'failed', 'late_failed', 'arrears')", name=op.f("ck_circle_contribution_circle_contribution_status_valid")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_contribution_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collected_journal_entry_id"], ["journal_entry.id"], name=op.f("fk_circle_contribution_collected_journal_entry_id_journal_entry")),
        sa.ForeignKeyConstraint(["cycle_id"], ["circle_cycle.id"], name=op.f("fk_circle_contribution_cycle_id_circle_cycle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["late_failure_journal_entry_id"], ["journal_entry.id"], name=op.f("fk_circle_contribution_late_failure_journal_entry_id_journal_entry")),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], name=op.f("fk_circle_contribution_member_id_member"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_object_id"], ["payment_object.id"], name=op.f("fk_circle_contribution_payment_object_id_payment_object")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_contribution")),
        sa.UniqueConstraint("cycle_id", "member_id", name="uq_circle_contribution_cycle_member"),
    )
    op.create_index("ix_circle_contribution_circle_id", "circle_contribution", ["circle_id"], unique=False)
    op.create_index("ix_circle_contribution_payment_object_id", "circle_contribution", ["payment_object_id"], unique=False)

    op.create_table(
        "circle_payout",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("recipient_member_id", sa.UUID(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("shortfall_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("payment_object_id", sa.UUID(), nullable=True),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('pending', 'processing', 'paid', 'failed')", name=op.f("ck_circle_payout_circle_payout_status_valid")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_payout_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["circle_cycle.id"], name=op.f("fk_circle_payout_cycle_id_circle_cycle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["journal_entry.id"], name=op.f("fk_circle_payout_journal_entry_id_journal_entry")),
        sa.ForeignKeyConstraint(["payment_object_id"], ["payment_object.id"], name=op.f("fk_circle_payout_payment_object_id_payment_object")),
        sa.ForeignKeyConstraint(["recipient_member_id"], ["member.id"], name=op.f("fk_circle_payout_recipient_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_payout")),
        sa.UniqueConstraint("cycle_id", name="uq_circle_payout_cycle_id"),
    )
    op.create_index("ix_circle_payout_circle_id", "circle_payout", ["circle_id"], unique=False)

    op.create_table(
        "circle_arrears_record",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("contribution_id", sa.UUID(), nullable=True),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_circle_arrears_record_circle_arrears_amount_positive")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_arrears_record_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contribution_id"], ["circle_contribution.id"], name=op.f("fk_circle_arrears_record_contribution_id_circle_contribution"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cycle_id"], ["circle_cycle.id"], name=op.f("fk_circle_arrears_record_cycle_id_circle_cycle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["member_id"], ["member.id"], name=op.f("fk_circle_arrears_record_member_id_member"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_arrears_record")),
    )
    op.create_index("ix_circle_arrears_circle_id", "circle_arrears_record", ["circle_id"], unique=False)
    op.create_index("ix_circle_arrears_member_id", "circle_arrears_record", ["member_id"], unique=False)

    op.create_table(
        "circle_shortfall_record",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("circle_id", sa.UUID(), nullable=False),
        sa.Column("cycle_id", sa.UUID(), nullable=False),
        sa.Column("payout_id", sa.UUID(), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_circle_shortfall_record_circle_shortfall_amount_positive")),
        sa.ForeignKeyConstraint(["circle_id"], ["circle.id"], name=op.f("fk_circle_shortfall_record_circle_id_circle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["circle_cycle.id"], name=op.f("fk_circle_shortfall_record_cycle_id_circle_cycle"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payout_id"], ["circle_payout.id"], name=op.f("fk_circle_shortfall_record_payout_id_circle_payout"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_circle_shortfall_record")),
    )
    op.create_index("ix_circle_shortfall_circle_id", "circle_shortfall_record", ["circle_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_circle_shortfall_circle_id", table_name="circle_shortfall_record")
    op.drop_table("circle_shortfall_record")
    op.drop_index("ix_circle_arrears_member_id", table_name="circle_arrears_record")
    op.drop_index("ix_circle_arrears_circle_id", table_name="circle_arrears_record")
    op.drop_table("circle_arrears_record")
    op.drop_index("ix_circle_payout_circle_id", table_name="circle_payout")
    op.drop_table("circle_payout")
    op.drop_index("ix_circle_contribution_payment_object_id", table_name="circle_contribution")
    op.drop_index("ix_circle_contribution_circle_id", table_name="circle_contribution")
    op.drop_table("circle_contribution")
    op.drop_index("ix_circle_cycle_due_date", table_name="circle_cycle")
    op.drop_table("circle_cycle")
    op.drop_index("ix_circle_draw_circle_id", table_name="circle_draw")
    op.drop_table("circle_draw")
    op.drop_index("ix_circle_agreement_circle_id", table_name="circle_agreement")
    op.drop_table("circle_agreement")
    op.drop_index("ix_circle_invite_circle_id", table_name="circle_invite")
    op.drop_table("circle_invite")
    op.drop_index("ix_circle_member_member_id", table_name="circle_member")
    op.drop_table("circle_member")
    op.drop_index("ix_circle_state", table_name="circle")
    op.drop_index("ix_circle_owner_member_id", table_name="circle")
    op.drop_table("circle")
