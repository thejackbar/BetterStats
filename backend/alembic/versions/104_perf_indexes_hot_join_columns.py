"""Add missing indexes on the per-game tables' join columns.

The records board (and player profiles, yearbooks, BetterIQ team analysis) join
the per-game stat tables on player_id / game_id and the partnerships table on
game_id / batter1_id / batter2_id, but those foreign-key columns had no index
(Postgres does not index FKs automatically). The records partnership queries
filter by ``p1.organisation_id`` / ``p2.organisation_id`` and so had to scan the
whole global partnerships table joined to players, four times per request — the
main reason an all-time records load took ~7s for a club with 30+ seasons.

These indexes are purely additive: they change no query results, only the plan
the planner can choose. Created with IF NOT EXISTS so they're idempotent and
match the mirror in the main.py lifespan.

Revision ID: 104
Revises: 103
Create Date: 2026-06-25
"""
from alembic import op


revision = '104'
down_revision = '103'
branch_labels = None
depends_on = None


# (index name, table, column) — single-column FK/join indexes.
_INDEXES = [
    ("ix_partnerships_game", "partnerships", "game_id"),
    ("ix_partnerships_batter1", "partnerships", "batter1_id"),
    ("ix_partnerships_batter2", "partnerships", "batter2_id"),
    ("ix_batting_innings_player", "batting_innings", "player_id"),
    ("ix_batting_innings_game", "batting_innings", "game_id"),
    ("ix_bowling_spells_player", "bowling_spells", "player_id"),
    ("ix_bowling_spells_game", "bowling_spells", "game_id"),
    ("ix_fielding_stats_player", "fielding_stats", "player_id"),
    ("ix_fielding_stats_game", "fielding_stats", "game_id"),
    ("ix_games_grade", "games", "grade_id"),
]


def upgrade() -> None:
    for name, table, col in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({col})")


def downgrade() -> None:
    for name, _table, _col in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
