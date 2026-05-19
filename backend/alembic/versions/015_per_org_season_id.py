"""Key seasons per club instead of by the shared Cricket Australia GUID

Season rows used the raw Cricket Australia season GUID as their primary key.
That GUID ("Summer 2025/26" etc.) is a national identifier — CA returns the
same one to every club. With a single club this was harmless, but the moment
a second club synced, its season loop found the first club's row, left the
organisation_id untouched, and — worse — the per-season
`DELETE player_season_stats WHERE season_id = ...` then re-insert overwrote
the first club's aggregate stats with the second club's players.

Seasons are now keyed per club: id = uuid5(organisation_id, grassroots_id),
with the raw CA GUID kept in the new grassroots_id column for the stats API
calls.

The existing rows can't be salvaged in place (their ids are wrong and one
club's stats are already overwritten), so this wipes all sync-derived season
data — seasons cascade to grades, games, batting/bowling/fielding, fall of
wickets, partnerships and player_season_stats. Players are NOT touched (no FK
to seasons), and neither is any manual data: manual partnership records,
yearbooks, honour boards, club awards and merge history all survive. Every
club must run a full sync afterwards to rebuild.

Revision ID: 015
Revises: 014
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seasons', sa.Column('grassroots_id', sa.Text(), nullable=True))
    # One-time rebuild. Cascades through the whole game/stat tree; players and
    # all manually-entered data are left intact.
    op.execute("DELETE FROM seasons")
    op.execute("DELETE FROM milestones")


def downgrade():
    op.drop_column('seasons', 'grassroots_id')
