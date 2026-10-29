"""Player Cards: every card gets the full photo again (big_photos defaults to 'all')

376 made `top` the default, which took the full photo off Common and Rare cards. The default is `all` again. The column default is
changed by services/player_card_photos_ddl.STATEMENTS (which main.py's lifespan also runs); the one data step, moving the rows that
are still on the old default, is only here, because the lifespan re-runs every boot and must never overwrite a club's own choice.

Revision ID: 379
Revises: 378
"""
from alembic import op

revision = "379"
down_revision = "378"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE club_card_settings ALTER COLUMN big_photos SET DEFAULT 'all'")
    op.execute("UPDATE club_card_settings SET big_photos = 'all' WHERE big_photos = 'top'")


def downgrade() -> None:
    op.execute("ALTER TABLE club_card_settings ALTER COLUMN big_photos SET DEFAULT 'top'")
