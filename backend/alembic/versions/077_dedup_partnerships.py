"""De-duplicate partnerships and guard against exact-duplicate rows

The records "Top 25 Partnerships" table surfaced the same stand twice (e.g.
Lennon Marlin & Matthew Norris, 233, 1st wkt, 10th Grade 2016/17 appearing as
both rank 4 and 5). The view/query can't fan out — `v_effective_games` is
`games UNION ALL manual_games` over disjoint id spaces, and every other join is
on a primary key — so two output rows mean two physical `partnerships` rows for
the one stand.

The only writer is `sync.sync_grassroots_game_level_data`, which skips
already-synced games, so a genuinely identical stand only lands twice when a
game's per-game rows were duplicated (a re-pulled/duplicated game record). That
stays invisible on a player profile because headline career stats come from the
season-aggregate API (`player_season_stats`), not per-game rows — which is why
only the partnerships record exposed it.

This mirrors migration 030 (batting_innings): remove byte-identical duplicate
rows keeping the lowest id per group, then add a UNIQUE constraint so a future
sync bug can't silently re-create them. The key is the FULL row identity
(game/innings/wicket/both batters/runs) — two rows identical on all of those are
the same stand stored twice, so the dedup can never drop a legitimately distinct
partnership (a real second-innings stand differs by innings_number; a different
pair differs by batter ids).

Idempotent: rerunning the DELETE is a no-op once the data is clean.

Revision ID: 077
Revises: 076
Create Date: 2026-06-09
"""
from alembic import op


revision = '077'
down_revision = '076'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove exact-duplicate rows, keeping the one with the smallest id in each
    # group. GROUP BY treats NULL batter ids as equal, so NULL-batter dups are
    # collapsed too. MIN(id) is never NULL (id is the PK), so the NOT IN subquery
    # is safe.
    op.execute("""
        DELETE FROM partnerships
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM partnerships
            GROUP BY game_id, innings_number, wicket_number,
                     batter1_id, batter2_id, runs
        )
    """)

    op.create_unique_constraint(
        "uq_partnerships_identity",
        "partnerships",
        ["game_id", "innings_number", "wicket_number",
         "batter1_id", "batter2_id", "runs"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_partnerships_identity",
        "partnerships",
        type_="unique",
    )
