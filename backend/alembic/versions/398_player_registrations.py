"""Player Dashboard self-registration: `player_registrations` and the club's
"Let people add themselves" switch.

Runs services/player_registration_ddl.STATEMENTS; main.py's lifespan runs the
same list. Every statement is idempotent.

Revision ID: 398
Revises: 397
"""
from alembic import op

from app.services.player_registration_ddl import STATEMENTS, DOWNGRADE

revision = "398"
down_revision = "397"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
