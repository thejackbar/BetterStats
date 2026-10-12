"""Fantasy lock time and queued transfers: fantasy_rounds.lock_manual, fantasy_queued_transfers

A lock time an admin sets by hand survives the nightly round refresh, and a transfer
made after a round locks waits for that round to be scored. Defined once in
services/fantasy_queue_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 327
Revises: 326
"""
from alembic import op

from app.services.fantasy_queue_ddl import STATEMENTS, DOWNGRADE

revision = "327"
down_revision = "326"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
