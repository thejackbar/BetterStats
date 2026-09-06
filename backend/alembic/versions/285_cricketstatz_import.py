"""Import a club's history from its own public CricketStatz site

A club moving to BetterCricket can point us at its CricketStatz club page and
have its whole record brought across: every season, every match, every
scorecard, and the record book CricketStatz had already computed.

Numbered 285 rather than 282: origin/main had already reached 284, and two
migrations sharing a revision id break Alembic outright.

Revision ID: 285
Revises: 284
Create Date: 2026-09-06
"""
from alembic import op

from app.services.cricketstatz_ddl import DOWNGRADE, STATEMENTS  # noqa: E402

revision = "285"
down_revision = "284"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
