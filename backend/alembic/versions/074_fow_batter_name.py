"""Fall of wicket: store the dismissed batter's name.

Adds a nullable ``batter_name`` to ``fall_of_wickets``. Our own batters resolve a
name via ``player_id`` → ``players``, but opposition batters in the cards we keep
have ``player_id = NULL`` (we don't tag opposition participants), leaving their
fall-of-wickets anonymous. Persisting the scorecard's ``playerShortName`` lets the
opponent half of our own games be named — and collapse-analysed — entirely from
the DB, without a live Grassroots fetch.

Additive + idempotent; back-filled going forward on the next sync / Full Rebuild.

Revision ID: 074
Revises: 073
Create Date: 2026-06-08

"""
from alembic import op


revision = '074'
down_revision = '073'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE fall_of_wickets ADD COLUMN IF NOT EXISTS batter_name TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE fall_of_wickets DROP COLUMN IF EXISTS batter_name")
