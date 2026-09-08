"""CricketStatz as the record for a season the club also syncs

A club that syncs from Cricket Australia and imports its CricketStatz history
holds the same matches twice. `seasons.stats_source = 'cricketstatz'` lets the
club say which source is the record for a season; the effective views apply it
on read, so nothing is deleted and clearing the marker puts the synced copy
straight back.

Revision ID: 287
Revises: 286
"""
from alembic import op

from app.services.superseded_ddl import DOWNGRADE, STATEMENTS

revision = "287"
down_revision = "286"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
