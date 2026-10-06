"""A club's own run and wicket milestone increments

Runs every 250, 500 or 1000 and wickets every 25, 50 or 100, picked on the
Milestones screen. NULL is the default scheme, so no club's list changes until
somebody chooses.

Revision ID: 321
Revises: 320
Create Date: 2026-10-06
"""
from alembic import op

from app.services.milestone_scheme_ddl import (  # noqa: E402
    DOWNGRADE,
    STATEMENTS,
)

revision = "321"
down_revision = "320"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
