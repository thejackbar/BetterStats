"""Player Cards: more packs, starting-cards setting, everyone on the board, alert emails off by default

Defined once in services/player_card_packs_ddl.py, which main.py's lifespan mirror also runs. The one data step (switching the alert
columns off for rows saved under the old default, so nobody is emailed until they ask) is only here: it runs once, and a boot must
never repeat it over a choice a player made since.

Revision ID: 370
Revises: 369
"""
from alembic import op

from app.services.player_card_packs_ddl import STATEMENTS, DOWNGRADE

revision = "370"
down_revision = "369"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    op.execute("UPDATE player_card_prefs SET alert_swaps = FALSE, alert_wants = FALSE")


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
