"""Players — record which BetterImport batch minted a player

A historical stats import (routers/imports.py) creates a real ``players`` row
for every "add as new player" name in the sheet, but nothing recorded WHICH
batch created it. Undoing the batch therefore had no way to tell an
import-minted player from a pre-existing one, so it left every created record
behind — a mis-mapped upload (e.g. surname-only names) survived its own undo
and clogged the club's Players page with empty records.

``players.import_batch_id`` is that marker: set only when the import commit
itself creates the row, NULL for every synced or hand-added player. Undo uses
it to find the batch's own players and deletes the ones its undo leaves empty
(see services/import_cleanup.py — anything real attached keeps the record).
A player re-imported by a later batch has the marker moved forward to that
batch, since undoing THAT batch is now what would leave them empty.

ON DELETE SET NULL: a deleted batch row must never take a player with it —
the marker is bookkeeping, not ownership.

Players created by imports before this shipped carry no marker; clean those
with ``python -m app.scripts.purge_import_only_players <org>``.

Revision ID: 234
Revises: 233
"""
from alembic import op

revision = "234"
down_revision = "233"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS import_batch_id UUID "
        "REFERENCES import_batches(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS import_batch_id")
