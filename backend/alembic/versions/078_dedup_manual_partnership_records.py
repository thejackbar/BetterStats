"""Remove manual partnership records that duplicate a synced scorecard partnership

A club bulk-imported historical "best partnership" rows (manual_partnership_records)
as a stopgap before game-level sync reached those seasons. As the Grassroots
/scores sync caught up, some of those manual rows now duplicate a real synced
`partnerships` row (same batters, runs, wicket, grade and season) — so the Records
page listed the stand twice (e.g. the 233 Marlin/Norris opening stand at #4 and #5).
The records read-side now collapses the display, but a redundant manual row is no
longer needed once its synced equivalent exists: the synced partnership (parsed
from the actual scorecard) is authoritative.

This deletes ONLY manual records with an exact, high-confidence synced equivalent:
  * batters id-linked and matching (unordered),
  * equal runs and wicket number,
  * the same grade name (raw or display-overridden), and
  * the same season START year — the manual record stores the season start year
    (e.g. 2016 for 2016/17), while the synced game may be played in EITHER calendar
    year of a summer season, so we match on the Season's `year` (start year), NOT
    EXTRACT(YEAR FROM played_at). (The old importer duplicate-check used played_at's
    year, which is exactly why the 233 stand — played Jan 2017, season 2016 — slipped
    through and got imported as a duplicate.)

Manual records with no synced equivalent (older un-synced seasons; the 254/238
stands that have no synced partnership) are left untouched. Idempotent.

Revision ID: 078
Revises: 077
Create Date: 2026-06-09
"""
from alembic import op


revision = '078'
down_revision = '077'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM manual_partnership_records m
        WHERE m.batter1_id IS NOT NULL AND m.batter2_id IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM partnerships pt
            JOIN games   g  ON g.id  = pt.game_id
            JOIN grades  gr ON gr.id = g.grade_id
            JOIN seasons s  ON s.id  = gr.season_id
            WHERE s.organisation_id = m.org_id
              AND pt.is_club_innings IS NOT FALSE
              AND pt.runs          = m.runs
              AND pt.wicket_number = m.wicket_number
              AND (
                    (pt.batter1_id = m.batter1_id AND pt.batter2_id = m.batter2_id)
                 OR (pt.batter1_id = m.batter2_id AND pt.batter2_id = m.batter1_id)
              )
              AND lower(btrim(m.grade_name)) IN (
                    lower(btrim(gr.name)),
                    lower(btrim(COALESCE(gr.display_name_override, gr.name)))
              )
              AND m.season_year = COALESCE(
                    s.year,
                    NULLIF(substring(s.name from '([0-9]{4})'), '')::int
              )
          )
    """)


def downgrade() -> None:
    # No-op: deleted manual records can be re-imported from the source file.
    pass
