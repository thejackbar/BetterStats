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

The Records page's own grade-scoped pass (one grade at a time, picked from a
dropdown) is still its own. ``grade_milestones`` below answers the different
question the notifications ask — every grade at once — and is the one place
that question is answered.
"""
from __future__ import annotations

import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.milestone_rules import crossed_thresholds, next_threshold, reach_window

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


# ─── Grade-level milestones, every grade at once ─────────────────────────────
#
# Asked for by the notifications: "50 matches in 1st Grade" is an honour a club
# marks, and the career scan cannot see it. Four rules decide the shape.
#
# - **A GRADE IS ITS NAME, FOLDED THROUGH THE CLUB'S OWN MERGES.** Grades are
#   per-season rows, so a total keyed on a grade id would restart every
#   season. The name is the grade; an active ``grade_merge_logs`` alias reads as
#   the grade it was merged into — the same rule the Records page's grade
#   filter applies, so a notification never names a total that page disagrees
#   with.
# - **ONLY ACTIVE PLAYERS ARE READ**, the career rule above. That also bounds
#   the scan: the per-innings views are narrowed by a bound array of player
#   ids, the shape the record book's timing work measured as the one the
#   planner can push down (a subquery there is a platform-wide scan).
# - **"REACHED" MEANS CROSSED RECENTLY, AND THE SCORECARD DATE SAYS WHEN.** Grade
#   milestones are not stored the way career ones are, so a threshold counts as
#   newly reached when the total including the last ``recent_since`` days clears
#   it and the total before them did not. Without that, a club switching this
#   on would be told about every grade milestone in its history.
# - **A PLAYER WHO HAS ONLY EVER PLAYED ONE GRADE IS LEFT OUT.** Their grade
#   total IS their career total, so a grade notice would restate the career one
#   a second time for the same innings.

_GRADE_STATS = (
    # (milestone type, per-innings view, alias, value expression, extra filter)
    ("grade_runs", "v_effective_batting_innings", "bi", "bi.runs",
     "AND NOT COALESCE(bi.did_not_bat, FALSE) "
     "AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')"),
    ("grade_wickets", "v_effective_bowling_spells", "bs", "bs.wickets", ""),
    ("grade_catches", "v_effective_fielding_stats", "fs", "fs.catches", ""),
    ("grade_matches", "game_appearances", "ga", None, ""),
)


def _grade_sql(table: str, alias: str, value: str | None, extra: str) -> str:
    # A match is counted once per game however many rows describe it; every
    # other stat is a sum.
    agg = "COUNT(DISTINCT game_id)" if value is None else "COALESCE(SUM(v), 0)"
    agg_before = ("COUNT(DISTINCT game_id) FILTER (WHERE played_at IS NULL OR played_at < :recent)"
                  if value is None else
                  "COALESCE(SUM(v) FILTER (WHERE played_at IS NULL OR played_at < :recent), 0)")
    return f"""
        WITH alias AS (
            SELECT DISTINCT ON (alias_name) alias_name, canonical_name
            FROM grade_merge_logs
            WHERE org_id = CAST(:org AS uuid) AND undone_at IS NULL
            ORDER BY alias_name, id DESC
        ),
        r AS (
            SELECT {alias}.player_id, {alias}.game_id, g.played_at,
                   COALESCE(a.canonical_name, gr.name) AS grade_name,
                   {value or '1'} AS v
            FROM {table} {alias}
            JOIN v_effective_games g ON g.id = {alias}.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN alias a ON a.alias_name = gr.name
            WHERE {alias}.player_id = ANY(CAST(:pids AS uuid[])) {extra}
        )
        SELECT player_id::text AS player_id, grade_name,
               {agg} AS total,
               {agg_before} AS before,
               MAX(played_at) AS last_played
        FROM r
        GROUP BY player_id, grade_name
    """


async def grade_milestones(session: AsyncSession, org_id: str, *,
                           recent_since: datetime.date) -> dict:
    """Grade-level milestones for the club's active players.

    Returns ``{"achieved": [...], "upcoming": [...]}``. ``achieved`` holds the
    thresholds crossed on or after ``recent_since``; ``upcoming`` the next
    threshold in each grade the player is still turning out in, when it is in
    reach. Each row carries ``grade`` (the name the club reads) and
    ``grade_key`` (a stable, case-folded key for de-duplication).
    """
    cutoff_year = datetime.date.today().year - ACTIVE_SEASON_YEARS
    people = (await session.execute(text("""
        SELECT p.id::text AS player_id,
               COALESCE(p.display_name_override, p.name) AS player_name,
               p.gender AS gender
        FROM players p
        WHERE p.organisation_id = :org AND p.is_player = TRUE
          AND EXISTS (
              SELECT 1 FROM player_season_stats pss
              JOIN seasons s ON s.id = pss.season_id
              WHERE pss.player_id = p.id AND s.organisation_id = :org
                AND (s.year IS NULL OR s.year >= :cutoff)
          )
    """), {"org": str(org_id), "cutoff": cutoff_year})).mappings().all()
    out = {"achieved": [], "upcoming": []}
    if not people:
        return out
    by_id = {r["player_id"]: r for r in people}
    pids = list(by_id)

    # The club's own spelling of a grade wins over the raw feed name.
    labels = {
        r[0]: r[1] for r in (await session.execute(text("""
            SELECT gr.name, gr.display_name_override
            FROM grades gr JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org AND gr.display_name_override IS NOT NULL
        """), {"org": str(org_id)})).all()
    }
    still_playing_from = datetime.date(cutoff_year, 1, 1)

    fetched = []
    grades_played: dict[str, set] = {}
    for mt, table, alias, value, extra in _GRADE_STATS:
        rows = (await session.execute(text(_grade_sql(table, alias, value, extra)), {
            "org": str(org_id), "pids": pids, "recent": recent_since,
        })).mappings().all()
        for r in rows:
            fetched.append((mt, r))
            if int(r["total"] or 0) > 0:
                grades_played.setdefault(r["player_id"], set()).add(r["grade_name"])

    for mt, r in fetched:
        total, before = int(r["total"] or 0), int(r["before"] or 0)
        # Judged on EVERY grade the player has any record in, not per stat: a
        # batter whose runs all sit in one grade may still turn out in two,
        # and only a genuinely one-grade career restates the career total.
        if total <= 0 or len(grades_played.get(r["player_id"], ())) < 2:
            continue
        person = by_id.get(r["player_id"])
        if person is None:
            continue
        name = r["grade_name"]
        base = {
            "player_id": r["player_id"],
            "player_name": person["player_name"],
            "gender": person["gender"],
            "type": mt,
            "grade": labels.get(name) or name,
            "grade_key": (name or "").strip().lower(),
        }
        earlier = set(crossed_thresholds(mt, before))
        for threshold in crossed_thresholds(mt, total):
            if threshold not in earlier:
                out["achieved"].append({**base, "milestone_value": threshold,
                                        "current": total})
        last = r["last_played"]
        if last is None or last < still_playing_from:
            continue
        target = next_threshold(mt, total)
        if target is None or target - total > reach_window(mt, target):
            continue
        out["upcoming"].append({**base, "current": total, "target": target,
                                "needed": target - total})
    return out
