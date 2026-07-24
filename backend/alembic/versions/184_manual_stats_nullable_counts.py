"""Scorecard upload — let untracked stat columns import as NULL, not 0.

Many historical cards simply don't track certain figures (a match-summary form
has no 4s/6s or maidens at all). Importing those as a hard 0 reads downstream
as "hit zero boundaries" / "bowled zero maidens", which pollutes boundary-rate
and discipline stats. NULL is the honest "not recorded" — SQL aggregates skip
it, matching how the synced per-game tables treat unknowns.

Keeps the server defaults, so existing writers (the CSV import, the manual-game
form) that send 0 are unchanged; only the scorecard review screen's "card
doesn't track this" toggles send NULL.

Revision ID: 184
Revises: 183
Create Date: 2026-07-24
"""
from alembic import op

revision = '184'
down_revision = '183'
branch_labels = None
depends_on = None

_COLS = (
    ("manual_batting_innings", ("fours", "sixes")),
    ("manual_bowling_spells", ("maidens", "wides", "no_balls")),
)


def upgrade() -> None:
    for table, cols in _COLS:
        for col in cols:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL")


def downgrade() -> None:
    for table, cols in _COLS:
        for col in cols:
            op.execute(f"UPDATE {table} SET {col} = 0 WHERE {col} IS NULL")
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} SET NOT NULL")
