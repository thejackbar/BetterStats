"""A player's action shot, and the choice of which shot fills the hero position.

`players.action_photo_data` / `.action_photo_mime` / `.action_photo_url` and `players.hero_source`.

Defined once in services/player_action_photo_ddl.py, which main.py's lifespan mirror also runs. Every statement is idempotent.
The downgrade drops only the four columns added here; the hero photo columns belong to migration 274.

Revision ID: 374
Revises: 373
"""
from alembic import op

from app.services.player_action_photo_ddl import STATEMENTS, DOWNGRADE

revision = "374"
down_revision = "373"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
