"""BetterScout — watchlists (Kanban boards, tags, recruiting fields)

Replaces scout_tracked_players (the phase-2 bookmark) with the real thing:
scout_watchlists (multiple per org) -> scout_watchlist_columns (renameable
Kanban columns, seeded 4 neutral defaults per new watchlist) ->
scout_watchlist_cards (one card per player per watchlist, carrying tags,
the fixed core fields, region/level picklists, and free-text recruiting
fields). See models/scout.py for the full column-by-column rationale.

Revision ID: 238
Revises: 237
"""
from alembic import op

revision = "238"
down_revision = "237"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_tracked_players")

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_watchlists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_watchlists_org ON scout_watchlists(scout_org_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_watchlist_columns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            watchlist_id UUID NOT NULL REFERENCES scout_watchlists(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_watchlist_columns_watchlist "
        "ON scout_watchlist_columns(watchlist_id, position)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_watchlist_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            watchlist_id UUID NOT NULL REFERENCES scout_watchlists(id) ON DELETE CASCADE,
            column_id UUID NOT NULL REFERENCES scout_watchlist_columns(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            tags JSONB NOT NULL DEFAULT '[]',
            role TEXT,
            batting_hand TEXT,
            bowling_action TEXT,
            bowling_type TEXT,
            region TEXT,
            level TEXT,
            transfer_preference TEXT,
            visa_status TEXT,
            agent_contact TEXT,
            availability_window TEXT,
            fee_expectations TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_watchlist_card UNIQUE (watchlist_id, scouted_player_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_watchlist_cards_column "
        "ON scout_watchlist_cards(column_id, position)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_watchlist_cards")
    op.execute("DROP TABLE IF EXISTS scout_watchlist_columns")
    op.execute("DROP TABLE IF EXISTS scout_watchlists")
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_tracked_players (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_tracked_player UNIQUE (scout_org_id, scouted_player_id)
        )
    """)
