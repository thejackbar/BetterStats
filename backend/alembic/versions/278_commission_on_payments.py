"""Earned commission rides on the Stripe payment, not the CRM deal's stage

Per direct instruction: a deal's stage is a human judgement somebody can drag
around; a confirmed Stripe payment is a fact. See
services/sales_commission_ddl.py, which holds the statements this and the
lifespan mirror in main.py both run, in one copy and in this order.

Revision ID: 278
Revises: 277
Create Date: 2026-08-23
"""
from alembic import op

from app.services.sales_commission_ddl import SALES_COMMISSION_SQL  # noqa: E402

revision = "278"
down_revision = "277"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The shared list is idempotent end to end, so re-running 277's statements
    # here is a no-op and the two migrations cannot drift from one another.
    for stmt in SALES_COMMISSION_SQL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_billing_invoices_commission_rep")
    for col in ("billing_reason", "amount_ex_tax_cents", "commission_rep_user_id",
                "commission_rate_percent", "commission_cents", "commission_kind"):
        op.execute(f"ALTER TABLE billing_invoices DROP COLUMN IF EXISTS {col}")
