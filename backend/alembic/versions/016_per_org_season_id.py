"""Key seasons per club instead of by the shared Cricket Australia GUID

Season rows used the raw Cricket Australia season GUID as their primary key.
That GUID ("Summer 2025/26" etc.) is a national identifier — CA returns the
same one to every club. With a single club this was harmless, but the moment
a second club synced, its season loop landed on the first club's rows and the
per-season `DELETE player_season_stats ...` + re-insert overwrote the first
club's aggregate stats with the second club's players.

Seasons are now keyed per club: id = uuid5(organisation_id, grassroots_id),
with the raw CA GUID kept in the new grassroots_id column for the stats API
calls.

This migration clears the sync-derived game/stat tables and renames every
season id in place to its per-club id. Deletes are done explicitly in
dependency order rather than via ON DELETE CASCADE, because the live FK
constraints predate the cascade rules in the models and a cascading
`DELETE FROM seasons` fails against them. Yearbooks (and their honour boards,
club awards, sections and images) are re-pointed onto the renamed rows so no
manually-entered content is lost. Players and all other manual data (manual
partnership records, merge history, award definitions) are untouched. Every
club must run a full sync afterwards to rebuild.

Revision ID: 016
Revises: 015
Create Date: 2026-05-19
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Idempotent so a re-run after a failed deploy is safe.
    conn.execute(sa.text("ALTER TABLE seasons ADD COLUMN IF NOT EXISTS grassroots_id TEXT"))

    # Clear sync-derived data in dependency order (children before parents).
    # Not relying on ON DELETE CASCADE — the live FKs may not have it.
    for table in (
        "batting_innings", "bowling_spells", "fielding_stats",
        "fall_of_wickets", "partnerships", "milestones",
        "games", "grades", "player_season_stats",
    ):
        conn.execute(sa.text(f"DELETE FROM {table}"))

    # Rename each season to its per-club id. Nothing references seasons now
    # except yearbooks, which are re-pointed so honour-board content survives.
    rows = conn.execute(sa.text(
        "SELECT id::text, organisation_id::text FROM seasons"
    )).fetchall()
    for old_id, org_id in rows:
        if not org_id:
            continue
        new_id = str(uuid.uuid5(uuid.UUID(org_id), old_id))
        conn.execute(sa.text("""
            INSERT INTO seasons (id, organisation_id, grassroots_id, name, year, synced_at, display_order)
            SELECT CAST(:new AS UUID), organisation_id, :old, name, year, synced_at, display_order
            FROM seasons WHERE id = CAST(:old AS UUID)
        """), {"new": new_id, "old": old_id})
        conn.execute(sa.text(
            "UPDATE yearbooks SET season_id = CAST(:new AS UUID) WHERE season_id = CAST(:old AS UUID)"
        ), {"new": new_id, "old": old_id})
        conn.execute(sa.text(
            "DELETE FROM seasons WHERE id = CAST(:old AS UUID)"
        ), {"old": old_id})


def downgrade():
    op.drop_column('seasons', 'grassroots_id')
