"""Historical-drift findings for the scheduled sync.

The scheduled sync only pulls fixtures played since a club's last run, so a
correction Cricket Australia makes to an older season is never re-read. This
table holds the cheap cross-check's verdict instead: one row per (club,
season), carrying whether CA's current season aggregates still agree with the
ones we stored, and enough of a sample to say what moved.

One row per pair, updated in place — the current state of a season, not a log
of every check. A season that drifts and is then rebuilt reads as ok rather
than leaving a stale warning on the club's Data Sync page.

``acknowledged_at`` is a human saying "seen, not rebuilding". It survives a
re-check that still finds drift (so the banner does not come back monthly for
a club that has decided to live with it) and is cleared by a re-check that
finds the season clean.

Revision ID: 258
Revises: 257
Create Date: 2026-08-16
"""
from alembic import op


revision = '258'
down_revision = '257'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_drift_findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            season_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            players_compared INTEGER NOT NULL DEFAULT 0,
            players_differing INTEGER NOT NULL DEFAULT 0,
            examples JSONB NOT NULL DEFAULT '[]'::jsonb,
            checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            acknowledged_at TIMESTAMPTZ,
            UNIQUE (organisation_id, season_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sync_drift_findings_open "
        "ON sync_drift_findings(organisation_id) "
        "WHERE status = 'drift' AND acknowledged_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync_drift_findings")
