"""Player Cards: a swap request holds many cards each way

Defined once in services/player_card_swaps_ddl.py (ITEM_STATEMENTS), which main.py's lifespan mirror also runs.
Downgrade drops only the items table this migration added; the columns it relaxed to optional stay optional.

Revision ID: 366
Revises: 365
"""
from alembic import op

from app.services.player_card_swaps_ddl import ITEM_STATEMENTS, ITEM_DOWNGRADE

revision = "366"
down_revision = "365"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in ITEM_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in ITEM_DOWNGRADE:
        op.execute(statement)
