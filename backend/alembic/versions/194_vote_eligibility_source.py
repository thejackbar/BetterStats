"""Vote eligibility source — which team list decides who can be voted for.

Votes were previously tied to the synced scorecard alone, so a club couldn't
vote until CA's weekly sync landed. A club can now vote off:
  * 'scorecard' — who actually played (the default, unchanged behaviour)
  * 'lineup'    — the XI saved in BetterSelect selection
  * 'playhq'    — the team list the club published on Play.Cricket

Set club-wide on vote_settings, overridable per fixture (a club that normally
waits for the scorecard might still want to vote on the night of a final).

vote_fixture_overrides.status becomes nullable so a row can carry a
source override alone, without also forcing a lock/reopen.

Revision ID: 194
Revises: 193
Create Date: 2026-07-29
"""
from alembic import op

revision = '194'
down_revision = '193'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE vote_settings ADD COLUMN IF NOT EXISTS "
        "eligibility_source TEXT NOT NULL DEFAULT 'scorecard'"
    )
    op.execute(
        "ALTER TABLE vote_fixture_overrides ADD COLUMN IF NOT EXISTS eligibility_source TEXT"
    )
    op.execute("ALTER TABLE vote_fixture_overrides ALTER COLUMN status DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE vote_settings DROP COLUMN IF EXISTS eligibility_source")
    op.execute("ALTER TABLE vote_fixture_overrides DROP COLUMN IF EXISTS eligibility_source")
