"""The ONE copy of migration 321's DDL, run by alembic and by the lifespan mirror.

Same one-copy rule as services/rate_qualification_ddl.py. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

Two nullable columns: NULL means the club has not chosen, which is the default
scheme (500 then every 1000 runs, 50 then every 100 wickets). Read through
services/milestone_rules.load_scheme, never directly.
"""

STATEMENTS = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS milestone_runs_step INTEGER",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS milestone_wickets_step INTEGER",
]

DOWNGRADE = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS milestone_runs_step",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS milestone_wickets_step",
]
