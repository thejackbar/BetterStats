"""Delete partnerships whose runs are impossible given the batters' scores

CA occasionally records a corrupt cumulative `score_at_fall` in a fall-of-wicket
row — observed 435 for a 49-run innings (game 008f934b…, Gosnells 4th Grade,
2017-01-21). The partnership deriver turns the jump from the previous wicket's
score into the stand, producing a phantom 381-run 2nd-wicket partnership between
two batters who made 25 and 1.

The FOW-count check (migration 006) and the retirement check (migration 008)
both pass here because the row COUNT is right and both FOW rows point to genuinely
dismissed batters — only the score VALUE is garbage. The deriver now also rejects
any innings whose derived stand exceeds the two batters' innings totals plus a
generous extras allowance (or goes negative). This migration purges the rows that
were stored before that guard landed.

Idempotent: rerunning is a no-op once the deriver fix is in place.

Revision ID: 103
Revises: 102
Create Date: 2026-06-25
"""
from alembic import op

revision = '103'
down_revision = '102'
branch_labels = None
depends_on = None

# Keep in step with sync._MAX_STAND_EXTRAS.
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
