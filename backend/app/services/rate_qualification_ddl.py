"""The ONE copy of migration 282's DDL, run by alembic and by the lifespan mirror.

Two copies of a column definition is how the two land on different schemas. Same
rule services/vote_medal_ddl.py sets. Every statement is idempotent, because the
lifespan re-runs the whole list on every boot.
"""

RATE_MINIMUM_STATEMENTS = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stats_min_rate_innings INTEGER",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stats_min_rate_spells INTEGER",
]

RATE_MINIMUM_DOWNGRADE = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS stats_min_rate_innings",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS stats_min_rate_spells",
]
