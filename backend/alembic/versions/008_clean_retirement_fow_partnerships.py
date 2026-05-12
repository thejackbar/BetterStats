"""Delete partnerships where any FOW row points to a non-dismissed batter

PSWL / women's grade scorecards on CA's side sometimes encode a *retirement*
as a fall-of-wicket row (with `order=N, runs=score-at-retirement,
participantId=retired-batter`). Combined with a missed real-wicket FOW,
the v3.0.2.3 count check (FOW count == dismissals) coincidentally passes:
1 retirement-FOW + 1 missed dismissal looks like 1 == 1, and the deriver
attributes the retirement-score to whichever pair is at the crease.

Example: match a89306dc innings 1. Wijesinghe out for 4 (no FOW recorded),
Innes retired not out at score 162. CA put `order=2 runs=162 pid=Innes`
in the FOW table. Deriver produced a 162-run "2nd wicket" stand between
Wijesinghe and Innes.

v3.0.2.6 hardens the deriver: every FOW participantId must point to a
batter whose `dismissal_type` is a real wicket (not Not Out, DNB, Absent,
Retired Hurt, Retired Not Out). This migration deletes existing rows that
were created before the harder check landed.

Idempotent.

Revision ID: 008
Revises: 007
Create Date: 2026-05-12
"""
from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM partnerships pt
        WHERE EXISTS (
            SELECT 1 FROM fall_of_wickets fw
            WHERE fw.game_id = pt.game_id
              AND fw.innings_number = pt.innings_number
              AND fw.player_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM batting_innings bi
                WHERE bi.game_id = fw.game_id
                  AND bi.innings_number = fw.innings_number
                  AND bi.player_id = fw.player_id
                  AND bi.not_out = FALSE
                  AND COALESCE(LOWER(bi.dismissal_type), '') NOT IN (
                    'absent', 'did not bat', 'dnb',
                    'retired hurt', 'retired not out'
                  )
              )
        )
        """
    )


def downgrade() -> None:
    pass
