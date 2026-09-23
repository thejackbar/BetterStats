"""BetterCricket annual invoicing — pay by invoice instead of by card.

A club can elect to be invoiced: the Primary Club Admin is emailed a Stripe
invoice for the modules they want (bundle and coupon discounts applied), with a
link to settle it through Stripe's hosted payment page, and is sent a renewal
invoice 14 days before each subscription period ends. The schema is defined
once in services/invoice_billing_ddl.py and shared with the lifespan mirror.

Revision ID: 308
Revises: 307
"""
from alembic import op

from app.services.invoice_billing_ddl import DOWNGRADE, STATEMENTS

revision = "308"
down_revision = "307"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
