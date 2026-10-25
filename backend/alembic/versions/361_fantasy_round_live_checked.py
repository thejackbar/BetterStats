"""Fantasy rounds remember when their running scores were last checked: fantasy_rounds.live_checked_at

Defined once in services/fantasy_live_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 361
Revises: 360
"""
from alembic import op

from app.services.fantasy_live_ddl import STATEMENTS, DOWNGRADE

revision = "361"
down_revision = "360"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
