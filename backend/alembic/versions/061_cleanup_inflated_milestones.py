"""Delete inflated career milestones minted from cross-club over-counts.

Companion cleanup to migration 060. Before the per-organisation scoping fix,
``sync._compute_milestones`` summed ``player_season_stats`` for a player with no
organisation filter, so a dual-club player (shared CA participant GUID — see
060) could cross career thresholds they never actually reached at their own club
(e.g. a "50 career matches" badge off an inflated 63 when the club total is 7).
``_compute_milestones`` only ever INSERTs — it never removes a badge once minted
— so those rows persist even after 060 corrects the displayed totals and after a
re-sync. This migration removes them.

Rule: for the four career-threshold milestone types, delete any badge whose
value exceeds the player's *org-scoped* career total (the same total
``_compute_milestones`` now computes). That deletes exactly the badges the
player no longer qualifies for and that sync will not re-mint. It's conservative
(achieved badges where value <= total are kept), idempotent (a second run finds
nothing left over threshold), and self-healing for any other source of a total
dropping below a minted threshold.

NULL-org players are left untouched (their stats can't be org-scoped), matching
the 060 view guard.

Revision ID: 061
Revises: 060
Create Date: 2026-06-02

"""
from alembic import op


revision = '061'
down_revision = '060'
branch_labels = None
depends_on = None


_CLEANUP_SQL = """
    WITH org_totals AS (
        SELECT
            p.id AS player_id,
            COALESCE(SUM(pss.runs), 0)    AS runs,
            COALESCE(SUM(pss.wickets), 0) AS wickets,
            COALESCE(SUM(pss.matches), 0) AS matches,
            COALESCE(SUM(pss.catches), 0) AS catches
        FROM players p
        -- Only join season rows that belong to the player's own organisation;
        -- cross-club rows (shared participant GUID) are excluded from the sum.
        LEFT JOIN player_season_stats pss
            ON pss.player_id = p.id
           AND EXISTS (
               SELECT 1 FROM seasons s
               WHERE s.id = pss.season_id
                 AND s.organisation_id = p.organisation_id
           )
        WHERE p.organisation_id IS NOT NULL
        GROUP BY p.id
    )
    DELETE FROM milestones m
    USING org_totals t
    WHERE m.player_id = t.player_id
      AND m.milestone_type IN ('runs', 'wickets', 'matches', 'catches')
      AND (
          (m.milestone_type = 'runs'    AND m.milestone_value > t.runs)    OR
          (m.milestone_type = 'wickets' AND m.milestone_value > t.wickets) OR
          (m.milestone_type = 'matches' AND m.milestone_value > t.matches) OR
          (m.milestone_type = 'catches' AND m.milestone_value > t.catches)
      )
"""


def upgrade() -> None:
    op.execute(_CLEANUP_SQL)


def downgrade() -> None:
    # Deleted badges are re-derivable by a sync (_compute_milestones), but the
    # specific rows can't be restored — this is a one-way cleanup of bad data.
    pass
