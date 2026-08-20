"""Index marketing_clubs on its normalised name, for wizard-selection scoring.

A registration-wizard club selection is now worth points on the club's
engagement score (twenty_sync.BONUS_CLUB_SELECTED). The beacon behind it names
the club as free text, so attributing one to a Club Directory row means
matching lower(TRIM(name)) — which had no index, so every lookup was a
sequential scan of the whole directory.

Measured on a loaded copy (6,000 directory clubs, 5,000 selection beacons):
940ms per single-club score without this index, on a path that runs inline on
every live signal and once per club on a full recalc. The expression matches
twenty_sync._WIZARD_SELECTION_CTE's name lookup exactly, so the planner can use
it there.

Not unique: two directory rows can legitimately share a name (a merge decision
for a person, not something a constraint should force), which is why the
lookups order by id and take one.

Revision ID: 268
Revises: 267
Create Date: 2026-08-20
"""
from alembic import op


revision = '268'
down_revision = '267'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_marketing_clubs_name_key "
        "ON marketing_clubs (lower(TRIM(BOTH FROM name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_marketing_clubs_name_key")
