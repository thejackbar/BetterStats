"""Delete partnerships derived from incomplete fall-of-wicket data

Some historical Grassroots scorecards have only a subset of their fall-of-wicket
rows recorded (e.g. 1 FOW for an innings where 7 wickets actually fell). The
partnership deriver previously consumed those rows uncritically, producing
phantom partnerships attributed to the openers — e.g. Blakey + Johnson credited
with a 215-run 5th-wicket stand for a match where they scored 9 and 2.

The deriver now refuses to emit partnerships unless the FOW count matches the
number of dismissals in the batting card. This migration purges existing rows
that were created under the old logic so the records page reflects reality.

Idempotent: rerunning is a no-op once the deriver fix is in place.

Revision ID: 006
Revises: 005
Create Date: 2026-05-12
"""
from alembic import op

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM partnerships pt
        WHERE EXISTS (
            SELECT 1 FROM games g WHERE g.id = pt.game_id
        )
        AND (
            SELECT COUNT(*) FROM fall_of_wickets fw
            WHERE fw.game_id = pt.game_id
              AND fw.innings_number = pt.innings_number
        ) <> (
            SELECT COUNT(*) FROM batting_innings bi
            WHERE bi.game_id = pt.game_id
              AND bi.innings_number = pt.innings_number
              AND bi.not_out = FALSE
              AND COALESCE(LOWER(bi.dismissal_type), '') NOT IN (
                'absent', 'did not bat', 'dnb', 'retired hurt'
              )
        )
        """
    )


def downgrade() -> None:
    # No-op: deleted data can only be restored via a hard refresh.
    pass
