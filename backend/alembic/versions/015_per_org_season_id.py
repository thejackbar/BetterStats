"""Key seasons per club instead of by the shared Cricket Australia GUID

Season rows used the raw Cricket Australia season GUID as their primary key.
That GUID ("Summer 2025/26" etc.) is a national identifier — CA returns the
same one to every club. With a single club this was harmless, but the moment
a second club synced, its season loop landed on the first club's rows and the
per-season `DELETE player_season_stats ... ` + re-insert overwrote the first
club's aggregate stats with the second club's players.

Seasons are now keyed per club: id = uuid5(organisation_id, grassroots_id),
with the raw CA GUID kept in the new grassroots_id column for the stats API
calls.

This migration renames every existing season id in place to its per-club id.
Yearbooks (and their honour boards, club awards, sections and images) are
re-pointed onto the renamed rows so none of that manually-entered content is
lost. Grades, games and player_season_stats are sync-derived and tangled, so
they're allowed to cascade away and get rebuilt — every club must run a full
sync afterwards. Players and all other manual data (manual partnership
records, merge history, award definitions) are untouched.

Revision ID: 015
Revises: 014
Create Date: 2026-05-19
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('seasons', sa.Column('grassroots_id', sa.Text(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id::text, organisation_id::text FROM seasons"
    )).fetchall()

    for old_id, org_id in rows:
        if not org_id:
            continue
        new_id = str(uuid.uuid5(uuid.UUID(org_id), old_id))
        # Clone the row under its per-club id, carrying the raw CA GUID.
        conn.execute(sa.text("""
            INSERT INTO seasons (id, organisation_id, grassroots_id, name, year, synced_at, display_order)
            SELECT CAST(:new AS UUID), organisation_id, :old, name, year, synced_at, display_order
            FROM seasons WHERE id = CAST(:old AS UUID)
        """), {"new": new_id, "old": old_id})
        # Move yearbooks onto the renamed season so honour boards survive.
        conn.execute(sa.text(
            "UPDATE yearbooks SET season_id = CAST(:new AS UUID) WHERE season_id = CAST(:old AS UUID)"
        ), {"new": new_id, "old": old_id})
        # Drop the old row — grades, games and player_season_stats cascade
        # away and get rebuilt on the next sync.
        conn.execute(sa.text("DELETE FROM seasons WHERE id = CAST(:old AS UUID)"), {"old": old_id})

    # Milestones are derived from games that just cascaded away; the sync
    # recomputes them.
    conn.execute(sa.text("DELETE FROM milestones"))


def downgrade():
    op.drop_column('seasons', 'grassroots_id')
