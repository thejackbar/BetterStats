"""A record of the confirmed side being sent to the captain and the players.

`selection_notices` holds one row per send (who, when, whether it got out, and
the fingerprint of the side that was sent), so the automatic send on Confirm
does not repeat itself for a side the captain already has.

Runs services/selection_notice_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 329
Revises: 328
"""
from alembic import op

from app.services.selection_notice_ddl import STATEMENTS, DOWNGRADE

revision = "329"
down_revision = "328"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
