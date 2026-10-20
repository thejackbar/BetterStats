"""DDL for the historical summary cut-off on a BetterImport batch (migration 328).

THE ONE COPY. Both alembic (versions/328_import_through_season.py) and the
lifespan mirror in main.py run this same list, and football's schema mirror
runs it by import (the shared ORM ``ImportBatch`` maps both columns). Every
statement is idempotent, because the lifespan re-runs the whole list on every
boot.

``through_year`` is the START year of the last season the sheet covers
(2004 for a book that ends with 2004/05). NULL is an ordinary import, which
claims to be the whole career as at today. ``through_label`` is the club's
own wording for it ("2004/05"), kept for the imports list.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS through_year INTEGER",
    "ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS through_label TEXT",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE import_batches DROP COLUMN IF EXISTS through_label",
    "ALTER TABLE import_batches DROP COLUMN IF EXISTS through_year",
]
