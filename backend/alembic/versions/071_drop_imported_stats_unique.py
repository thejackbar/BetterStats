"""Drop the over-strict uq_imported_stats_key.

The BetterImport reconciler computes a player's effective stats by accumulating
ALL of their ``imported_stats`` rows, and "latest upload wins" is enforced by
deleting a player's prior rows before each commit (routers/imports.py::commit).
So more than one row for the same (player, scope, season, grade) cell is a
normal, correct case — e.g. several seasons that couldn't be matched to a club
season all land as career / NULL-season rows and should simply sum.

The unique index from migration 070 turned that normal case into a
UniqueViolation → HTTP 500 on commit (hit on a real ~1,600-player club import
whose season labels didn't all match). Drop it; the plain lookup index
``ix_imported_stats_org_player`` remains.

Revision ID: 071
Revises: 070
Create Date: 2026-06-06

"""
from alembic import op


revision = '071'
down_revision = '070'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_imported_stats_key")


def downgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_imported_stats_key ON imported_stats
        (organisation_id, player_id, scope,
         COALESCE(season_id, '00000000-0000-0000-0000-000000000000'::uuid),
         COALESCE(grade_label, ''))
        """
    )
