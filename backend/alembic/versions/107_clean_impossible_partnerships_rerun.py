"""Re-run the impossible-partnership cleanup (revision 103 was skipped)

Migration 103 (clean_impossible_partnerships) deletes synced partnership rows
whose runs are impossible given the two batters' scores — e.g. the phantom
381-run 2nd-wicket stand at Gosnells (batters made 25 and 1). During the deploy
incident three PRs each grabbed revision 103, and the renumber that linearised
them left 103 = clean_impossible_partnerships. Any box whose `alembic_version`
had already reached 103 (recorded for a different migration before the renumber)
therefore SKIPPED the cleanup when it upgraded to head, so the bad rows survived
on production.

This migration repeats the exact same DELETE at a revision above the current
head so it runs regardless of what 103 meant historically. It is idempotent: a
DELETE with a WHERE clause removes nothing on a clean database, and the deriver
guard in sync.py stops new corrupt rows being inserted.

Revision ID: 107
Revises: 106
Create Date: 2026-06-26
"""
from alembic import op

revision = '107'
down_revision = '106'
branch_labels = None
depends_on = None

# Keep in step with sync._MAX_STAND_EXTRAS and migration 103.
_MAX_STAND_EXTRAS = 50


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM partnerships pt
        WHERE pt.runs IS NOT NULL
          AND pt.batter1_runs IS NOT NULL
          AND pt.batter2_runs IS NOT NULL
          AND pt.runs > pt.batter1_runs + pt.batter2_runs + {_MAX_STAND_EXTRAS}
        """
    )


def downgrade() -> None:
    # No-op: deleted data can only be restored via a hard refresh.
    pass
