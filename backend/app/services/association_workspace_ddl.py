"""An association socials workspace: an organisation row with no club behind it.

`organisations.workspace_kind` is NULL for every real club and 'association' for a
workspace (services/social_competition.py). One copy: alembic migration 392 and
main.py's lifespan both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS workspace_kind TEXT",
    "CREATE INDEX IF NOT EXISTS ix_organisations_workspace_kind "
    "ON organisations (workspace_kind) WHERE workspace_kind IS NOT NULL",
]

DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_organisations_workspace_kind",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS workspace_kind",
]
