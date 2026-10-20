"""Hide a player at their own request.

`players.privacy_hidden_at / _by / _reason` record that the PERSON asked to be
removed from the public site. `players.is_public` (migration 265) still does
the hiding; these stop a club admin or a bulk import switching it back on, and
keep the sitemap, share cards and every `/players/{id}/...` route consistent.

Runs services/player_privacy_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 316
Revises: 315
"""
from alembic import op

from app.services.player_privacy_ddl import STATEMENTS, DOWNGRADE

revision = "316"
down_revision = "315"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
