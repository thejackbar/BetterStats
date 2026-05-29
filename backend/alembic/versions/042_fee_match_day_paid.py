"""Link fee_match_days to their settling payment.

Adds fee_match_days.paid_payment_id (nullable FK → fee_payments) so a match
day can be marked Paid (creates a payment, links it) and Unpaid (deletes
the payment, FK nulls automatically). Multiple match-day rows can share
the same payment row — that's the bulk-payment case (one bank transfer
covers several days for several players).

Also drops fee_match_days.override_reason — superseded by the Mark Paid
toggle on the match-day row.

Revision ID: 042
Revises: 041
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '042'
down_revision = '041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fee_match_days",
        sa.Column("paid_payment_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fee_match_days_paid_payment",
        "fee_match_days", "fee_payments",
        ["paid_payment_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_fee_match_days_paid_payment",
        "fee_match_days", ["paid_payment_id"],
    )
    op.drop_column("fee_match_days", "override_reason")


def downgrade() -> None:
    op.add_column("fee_match_days", sa.Column("override_reason", sa.Text(), nullable=True))
    op.drop_index("ix_fee_match_days_paid_payment", table_name="fee_match_days")
    op.drop_constraint("fk_fee_match_days_paid_payment", "fee_match_days", type_="foreignkey")
    op.drop_column("fee_match_days", "paid_payment_id")
