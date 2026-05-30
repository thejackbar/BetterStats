"""BetterSelect: club default lineup size.

Persists the club's default team size (11 a side by default) so the Selection
screen's format selector survives a reload instead of resetting to a hard-coded
value. 0 = no limit. Backfills every existing club to 11.

Revision ID: 052
Revises: 051
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa


revision = '052'
down_revision = '051'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organisations",
        sa.Column("default_team_size", sa.Integer(), nullable=False, server_default="11"),
    )


def downgrade() -> None:
    op.drop_column("organisations", "default_team_size")
