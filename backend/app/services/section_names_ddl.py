"""DDL for a club's own names for its public sections (migration 319).

THE ONE COPY. Both alembic (versions/319_section_names.py) and the lifespan
mirror in main.py run this same list. Every statement is idempotent, because
the lifespan re-runs the whole list on every boot.

One column: ``organisations.section_names`` holds only the sections a club has
renamed or linked to a sponsor, as {"fantasy": {"name": "Froth Fantasy Cricket",
"sponsor_id": "<uuid>"}}. NULL means every section keeps its standard name. The
sponsor's logo and link are read live from ``org_sponsors`` (services/section_names.py),
so a replaced logo or a deleted sponsor is never stale here.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS section_names JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS section_names",
]
