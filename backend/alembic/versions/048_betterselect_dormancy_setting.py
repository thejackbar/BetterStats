"""BetterSelect: configurable dormancy window.

The "dormant player" cutoff (and team squad-suggestion window) was hardcoded
to 2 years in two places. Make it a club setting: dormancy_months on
organisations. Default 24 = the previous behaviour. Stored in months so clubs
can pick mid-season values like 18.

Revision ID: 048
Revises: 047
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '048'
down_revision = '047'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("dormancy_months", sa.Integer(), nullable=False, server_default="24"),
    )


def downgrade() -> None:
    op.drop_column("organisations", "dormancy_months")
