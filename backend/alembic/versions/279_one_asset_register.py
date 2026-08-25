"""One asset register: merch_assets carried into club_assets

Per direct instruction: inventory is one thing, and property / facilities /
fixed assets / equipment are another. `merch_assets` was never inventory — see
services/asset_register_ddl.py, which holds the statements this and the
lifespan mirror in main.py both run, in one copy and in this order.

`merch_assets` is left in place and read by nothing after this, the call
migration 267 made for `vote_settings`.

Revision ID: 279
Revises: 278
Create Date: 2026-08-24
"""
from alembic import op

from app.services.asset_register_ddl import ASSET_REGISTER_SQL  # noqa: E402

revision = "279"
down_revision = "278"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in ASSET_REGISTER_SQL:
        op.execute(stmt)


def downgrade() -> None:
    # `source`, NOT `merch_asset_id`. Both a gap-filled row and an inserted one
    # carry the id, so deleting on it would take the club's OWN pre-existing
    # assets with it — the verification caught exactly that.
    #
    # What still cannot be undone is the gap-fill itself: those fields were NULL
    # and now hold the merch figure, with no record of which. That is the honest
    # position, and it is why the fill only ever writes where nothing was.
    op.execute("DELETE FROM club_assets WHERE source = 'merch'")
    op.execute("DROP INDEX IF EXISTS uq_club_assets_merch_asset")
    op.execute("ALTER TABLE club_assets DROP COLUMN IF EXISTS merch_asset_id")
    op.execute("ALTER TABLE club_assets DROP COLUMN IF EXISTS source")
