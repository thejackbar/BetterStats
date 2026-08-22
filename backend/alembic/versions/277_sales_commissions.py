"""Sales commissions — a rate per rep, a snapshot on the deal, a payments ledger

See services/sales_commission_ddl.py, which holds the statements this and the
lifespan mirror in main.py both run, in one copy and in this order.

Revision ID: 277
Revises: 276
Create Date: 2026-08-22
"""
from alembic import op

from app.services.sales_commission_ddl import SALES_COMMISSION_SQL  # noqa: E402

revision = "277"
down_revision = "276"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in SALES_COMMISSION_SQL:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales_commission_payments")
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS commission_rate_percent")
    op.execute("DROP TABLE IF EXISTS sales_commission_rates")
