"""Fantasy managers who join after the season has started (migration 323).

A squad's `total_points` is re-derived from its round rows every time a round is
settled (`fantasy_squad.recompute_squad_totals`), so the points a late joiner
starts on cannot live in `total_points`. They are kept in `catchup_points`, which
the recompute adds back. `joined_round` (already on the table) is the first round
the squad scores in; earlier rounds are never scored for it.

ONE copy of the DDL, per the vote_medal_ddl rule: alembic's 323 and main.py's
lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE fantasy_squads ADD COLUMN IF NOT EXISTS catchup_points NUMERIC(8,2) NOT NULL DEFAULT 0",
]

# Drops only the column this migration added.
DOWNGRADE = [
    "ALTER TABLE fantasy_squads DROP COLUMN IF EXISTS catchup_points",
]
