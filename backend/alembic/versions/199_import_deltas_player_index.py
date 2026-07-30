"""Add a standalone index on import_effective_deltas.player_id.

The only index on this table was the composite (organisation_id, player_id)
from migration 070. v_effective_player_season_stats's import branch
(`SELECT ... FROM import_effective_deltas`, no WHERE clause — org-scoping
happens only via the outer join to `players`) gets correlated per-row against
`players` when queried without a season/grade filter (e.g. a club's public
leaderboard on "All seasons"). That correlated join filters this table by
`player_id` ALONE, which the composite index can't serve efficiently since
organisation_id isn't part of the filter — so Postgres falls back to a full
sequential scan of the table (shared across every club that's ever used
BetterImport), once per outer row. For a club with a large roster this turns
an ordinary leaderboard/milestones/players-page load into a multi-minute
hang. A standalone index on player_id lets that correlated lookup use an
index scan instead, regardless of table size.

Mirrored idempotently in app/main.py lifespan (migration 199 block).
"""
from alembic import op

revision = "199"
down_revision = "198"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_import_deltas_player "
        "ON import_effective_deltas(player_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_import_deltas_player")
