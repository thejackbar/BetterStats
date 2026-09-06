"""Who is close to a career milestone, asked once for the whole club.

Three surfaces answer "which of our players are about to reach something" —
the public club dashboard, the public Records page and the admin Milestones
report — and until v9.57.1 each carried its own copy of the query. Two of
them read the base ``player_season_stats`` table scoped to the club's own
seasons; the dashboard read the five-branch ``v_effective_player_season_stats``
view with ``LEFT JOIN ... ON pss.player_id = p.id`` and no season or org
narrowing on the view side, so the whole view had to be built for every
request. That is ~3.4s at a healthy club and past nginx's 60s ``/api/``
timeout at Hoxton Park Tigers, where the dashboard panel showed "No upcoming
milestones" while the admin report listed 23 — the failure and an empty club
render identically.

So this is the one definition, lifted from the two fast copies verbatim:

- **ACTIVE MEANS A SEASON ROW IN THE LAST THREE YEARS.** A player who has
  stopped turning out is not "two wickets away" in any useful sense, and
  every one of the three surfaces already agreed on that rule.
- **THE CLUB'S OWN SEASONS ONLY.** The ``EXISTS`` guard is migration 060's
  cross-club rule restated on the base table: CA reuses one participant GUID
  across every club a person plays for, so a second club's season rows hang
  off the same player id and would otherwise be summed into our career total.
- **NO ``HAVING runs > 0 OR wickets > 0``.** The dashboard's own copy carried
  one, which silently dropped anybody whose next milestone is a matches or
  catches one — most of Hoxton Park's 23.

``grade_matches`` is deliberately NOT here. It needs a per-grade appearance
scan and a grade name to hang off, and only the two surfaces with a column
for that detail draw it; they keep their own pass.
"""
from __future__ import annotations

import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.milestone_rules import next_threshold, reach_window

# Current year and the two before it. A season with no year at all is kept —
# an unknown date is not evidence the player has stopped playing.
ACTIVE_SEASON_YEARS = 2

# (milestone type, category, the column its total arrives in).
STAT_DEFS = (
    ("runs", "batting", "total_runs"),
    ("wickets", "bowling", "total_wickets"),
    ("matches", "matches", "total_matches"),
    ("catches", "fielding", "total_catches"),
)

_TOTALS_SQL = text("""
    WITH active_ids AS (
        SELECT DISTINCT pss.player_id
        FROM player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        WHERE s.organisation_id = :org_id
          AND (s.year IS NULL OR s.year >= :cutoff)
    )
    SELECT
        p.id::text AS player_id,
        COALESCE(p.display_name_override, p.name) AS player_name,
        p.gender AS gender,
        COALESCE(SUM(pss.runs), 0)    AS total_runs,
        COALESCE(SUM(pss.wickets), 0) AS total_wickets,
        COALESCE(SUM(pss.matches), 0) AS total_matches,
        COALESCE(SUM(pss.catches), 0) AS total_catches
    FROM players p
    JOIN active_ids ai ON ai.player_id = p.id
    JOIN player_season_stats pss ON pss.player_id = p.id
        -- Only this org's seasons (shared cross-club GUID guard, migration 060)
        AND EXISTS (
            SELECT 1 FROM seasons s2
            WHERE s2.id = pss.season_id AND s2.organisation_id = :org_id
        )
    WHERE p.organisation_id = :org_id AND p.is_player = TRUE
    GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
    ORDER BY COALESCE(p.display_name_override, p.name)
""")


async def active_player_totals(session: AsyncSession, org_id: str) -> list[dict]:
    """Career runs/wickets/matches/catches for the club's active players."""
    cutoff = datetime.date.today().year - ACTIVE_SEASON_YEARS
    rows = await session.execute(_TOTALS_SQL, {"org_id": org_id, "cutoff": cutoff})
    return [dict(r) for r in rows.mappings()]


def upcoming_from_totals(rows: list[dict]) -> list[dict]:
    """One entry per (player, stat) whose next threshold is within reach.

    Unsorted — the callers disagree about the order on purpose. The reports
    rank by how close a milestone is; the dashboard ranks by how big it is.
    """
    out: list[dict] = []
    for r in rows:
        for stat, category, col in STAT_DEFS:
            current = int(r[col] or 0)
            target = next_threshold(stat, current)
            if target is None:
                continue
            needed = target - current
            if needed > reach_window(stat, target):
                continue
            out.append({
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "gender": r["gender"],
                "type": stat,
                "category": category,
                "current": current,
                "target": target,
                "needed": needed,
                "detail": None,
            })
    return out


async def upcoming_career_milestones(session: AsyncSession, org_id: str) -> list[dict]:
    """The club's in-reach career milestones, unsorted."""
    return upcoming_from_totals(await active_player_totals(session, org_id))
