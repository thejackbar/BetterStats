"""Fill-in names on partnerships/fielding + a club toggle to show them.

A fill-in (borrowed player) or CA-redacted junior already shows on the
batting/bowling scorecard card (no toggle, always on — see the "Fill-in
players on the game scorecard" work). This extends the same idea to
partnerships and fielding, but as a club-level choice: `batter1_name`/
`batter2_name` on `partnerships` and `player_name` on `fielding_stats` mirror
the existing `FallOfWicket.batter_name` pattern (a free-text fallback for
whichever side has no linkable `players` row), and
`organisations.include_fill_ins_in_stats` gates whether the scorecard read
path surfaces that name or drops the row. Matching (always-NULL) columns are
added to `manual_partnerships`/`manual_fielding_stats` purely so the
`v_effective_*` union views' column lists still line up.

Revision ID: 147
Revises: 146
Create Date: 2026-07-14
"""
from alembic import op


revision = '147'
down_revision = '146'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092: the schema is layered (dump + lifespan +
    # alembic), so a plain ADD COLUMN/CREATE can hit an already-existing
    # object and abort `alembic upgrade head`, crash-looping the backend.
    op.execute("ALTER TABLE partnerships ADD COLUMN IF NOT EXISTS batter1_name TEXT")
    op.execute("ALTER TABLE partnerships ADD COLUMN IF NOT EXISTS batter2_name TEXT")
    op.execute("ALTER TABLE manual_partnerships ADD COLUMN IF NOT EXISTS batter1_name TEXT")
    op.execute("ALTER TABLE manual_partnerships ADD COLUMN IF NOT EXISTS batter2_name TEXT")

    op.execute("ALTER TABLE fielding_stats ADD COLUMN IF NOT EXISTS player_name TEXT")
    op.execute("ALTER TABLE manual_fielding_stats ADD COLUMN IF NOT EXISTS player_name TEXT")
    # fielding_stats.player_id was never nullable in practice (nothing inserted
    # NULL), but its FK was ON DELETE CASCADE — inconsistent with every other
    # player-linked per-game table (batting_innings, partnerships,
    # fall_of_wickets all use SET NULL) and wrong now that a fill-in row can
    # legitimately hold player_id = NULL. Bring it in line.
    op.execute("ALTER TABLE fielding_stats ALTER COLUMN player_id DROP NOT NULL")
    op.execute("ALTER TABLE fielding_stats DROP CONSTRAINT IF EXISTS fielding_stats_player_id_fkey")
    op.execute(
        "ALTER TABLE fielding_stats ADD CONSTRAINT fielding_stats_player_id_fkey "
        "FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE SET NULL"
    )

    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
               "include_fill_ins_in_stats BOOLEAN NOT NULL DEFAULT true")

    # Free-text note when an admin promotes a fill-in into a real player (the
    # "claim a fill-in" flow) — e.g. a pasted PlayHQ profile URL kept purely
    # for the club's own reference, never parsed/verified server-side.
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS claim_note TEXT")

    # `CREATE OR REPLACE VIEW` only allows appending new columns at the END of
    # the SELECT list — inserting one in the middle shifts every later
    # column's position, which Postgres treats as renaming that column and
    # rejects ("cannot change name of view column ... to ..."). batter1_name/
    # batter2_name/player_name are therefore appended after the existing
    # `source` column, same placement migration 075 used for
    # v_effective_batting_innings.caught_behind — not inserted next to the
    # columns they conceptually belong with.
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_partnerships AS
        SELECT
            id, game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'api'::text AS source,
            batter1_name, batter2_name
        FROM partnerships
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'manual'::text AS source,
            batter1_name, batter2_name
        FROM manual_partnerships
    """)

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_fielding_stats AS
        SELECT
            id, game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'api'::text AS source,
            player_name
        FROM fielding_stats
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'manual'::text AS source,
            player_name
        FROM manual_fielding_stats
    """)


def downgrade() -> None:
    # CREATE OR REPLACE VIEW can't drop columns either (even trailing ones) —
    # DROP + CREATE fresh to actually remove the appended columns.
    op.execute("DROP VIEW IF EXISTS v_effective_fielding_stats")
    op.execute("""
        CREATE VIEW v_effective_fielding_stats AS
        SELECT
            id, game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'api'::text AS source
        FROM fielding_stats
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'manual'::text AS source
        FROM manual_fielding_stats
    """)
    op.execute("DROP VIEW IF EXISTS v_effective_partnerships")
    op.execute("""
        CREATE VIEW v_effective_partnerships AS
        SELECT
            id, game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'api'::text AS source
        FROM partnerships
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'manual'::text AS source
        FROM manual_partnerships
    """)
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS claim_note")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS include_fill_ins_in_stats")
    op.execute("ALTER TABLE fielding_stats DROP CONSTRAINT IF EXISTS fielding_stats_player_id_fkey")
    op.execute(
        "ALTER TABLE fielding_stats ADD CONSTRAINT fielding_stats_player_id_fkey "
        "FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE manual_fielding_stats DROP COLUMN IF EXISTS player_name")
    op.execute("ALTER TABLE fielding_stats DROP COLUMN IF EXISTS player_name")
    op.execute("ALTER TABLE manual_partnerships DROP COLUMN IF EXISTS batter2_name")
    op.execute("ALTER TABLE manual_partnerships DROP COLUMN IF EXISTS batter1_name")
    op.execute("ALTER TABLE partnerships DROP COLUMN IF EXISTS batter2_name")
    op.execute("ALTER TABLE partnerships DROP COLUMN IF EXISTS batter1_name")
