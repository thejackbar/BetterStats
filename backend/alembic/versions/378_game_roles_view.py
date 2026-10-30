"""One view of who captained and kept wicket, for synced and hand-entered games alike.

`v_game_roles`: game_appearances flags unioned with manual_game_roles, so the stats lenses that filter on the
captain or the keeper (Records, Leaderboard, a player's captain record, StatLab) see both kinds of game.

Runs services/manual_game_roles_ddl.VIEW_STATEMENTS, the same list main.py's lifespan runs. Idempotent.

Revision ID: 378
Revises: 377
"""
from alembic import op

from app.services.manual_game_roles_ddl import VIEW_STATEMENTS, VIEW_DOWNGRADE

revision = "378"
down_revision = "377"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in VIEW_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in VIEW_DOWNGRADE:
        op.execute(stmt)
