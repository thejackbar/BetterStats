"""AFL read-side aggregation helpers shared by the public routers.

Everything is org-scoped through grades→seasons (the games table has no
organisation column of its own) and reads only synced data — no live PlayHQ
calls on any public request path.
"""
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from . import milestone_rules


async def career_totals(db: AsyncSession, org_id: uuid.UUID,
                        player_ids: Optional[list[uuid.UUID]] = None) -> list[dict]:
    """Career totals per player, combining the synced whole-season rollup
    (grade_id IS NULL so per-grade rows don't double count) with imported
    (Import Stats upload) rows — sync wins per season, imported only fills a
    genuine gap, same rule the leaderboard/dashboard/records use. A LEFT JOIN
    to seasons (not INNER) so an imported row with no resolved season still
    counts toward the totals — it just can't move first_year/last_year."""
    where_player_s = "AND s.player_id = ANY(:pids)" if player_ids else ""
    where_player_i = "AND i.player_id = ANY(:pids)" if player_ids else ""
    params: dict = {"org": str(org_id)}
    if player_ids:
        params["pids"] = [str(p) for p in player_ids]
    res = await db.execute(text(f"""
        WITH combined AS (
            SELECT s.player_id, s.season_id, s.games, s.goals, s.behinds, s.bog_count, s.captain_games
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.grade_id IS NULL {where_player_s}
            UNION ALL
            SELECT i.player_id, i.season_id, i.games_played AS games, i.goals, i.behinds, i.bog_count, i.captain_games
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {where_player_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id,
               p.name,
               p.display_name_override,
               p.photo_url,
               COUNT(DISTINCT c.season_id)                AS seasons,
               COALESCE(SUM(c.games), 0)                  AS games,
               COALESCE(SUM(c.goals), 0)                  AS goals,
               COALESCE(SUM(c.behinds), 0)                AS behinds,
               COALESCE(SUM(c.bog_count), 0)               AS bogs,
               COALESCE(SUM(c.captain_games), 0)          AS captain_games,
               MIN(s.year)                                AS first_year,
               MAX(s.year)                                AS last_year
        FROM combined c
        JOIN players p ON p.id = c.player_id
        LEFT JOIN seasons s ON s.id = c.season_id
        GROUP BY c.player_id, p.name, p.display_name_override, p.photo_url
        ORDER BY games DESC, goals DESC
    """), params)
    return [dict(r._mapping) for r in res]


async def season_by_season(db: AsyncSession, org_id: uuid.UUID,
                           player_id: uuid.UUID) -> list[dict]:
    """Combines synced (afl_player_season_stats) with imported (Import Stats
    upload) rows, same sync-wins-per-season rule as career_totals. An
    imported row is inherently per-grade shaped (one row per uploaded sheet
    row) — there's no separate "whole season" aggregate row the way a synced
    season has (grade_id NULL alongside its own per-grade breakdown rows).
    So for any season covered ONLY by import, a whole-season total row is
    synthesised in Python by summing that season's per-grade rows, mirroring
    what the sync's own rollup would have produced. compare_players()
    filters this list down to grade_id IS NULL rows only, so without this
    synthesis an import-only season would silently vanish from Compare too.
    """
    res = await db.execute(text("""
        SELECT pss.season_id, s.name AS season_name, s.year,
               pss.grade_id, gr.name AS grade_name,
               pss.games, pss.goals, pss.behinds, pss.bog_count AS bogs,
               pss.captain_games
        FROM afl_player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        LEFT JOIN grades gr ON gr.id = pss.grade_id
        WHERE pss.organisation_id = :org AND pss.player_id = :pid
        UNION ALL
        SELECT i.season_id, s.name AS season_name, s.year,
               i.grade_id, gr.name AS grade_name,
               i.games_played AS games, i.goals, i.behinds, i.bog_count AS bogs,
               i.captain_games
        FROM afl_imported_stats i
        LEFT JOIN seasons s ON s.id = i.season_id
        LEFT JOIN grades gr ON gr.id = i.grade_id
        WHERE i.organisation_id = :org AND i.player_id = :pid
          AND NOT EXISTS (
            SELECT 1 FROM afl_player_season_stats s2
            WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
              AND s2.grade_id IS NULL AND s2.games > 0
          )
    """), {"org": str(org_id), "pid": str(player_id)})
    rows = [dict(r._mapping) for r in res]

    have_total = {r["season_id"] for r in rows if r["grade_id"] is None and r["season_id"] is not None}
    synthesised: dict = {}
    for r in rows:
        sid = r["season_id"]
        if sid is None or sid in have_total:
            continue
        t = synthesised.setdefault(sid, {
            "season_id": sid, "season_name": r["season_name"], "year": r["year"],
            "grade_id": None, "grade_name": None,
            "games": 0, "goals": 0, "behinds": 0, "bogs": 0, "captain_games": 0,
        })
        for f in ("games", "goals", "behinds", "bogs", "captain_games"):
            t[f] += r[f] or 0
    rows.extend(synthesised.values())

    # Three stable sorts, least-significant first (Python's sort is stable,
    # so each later pass only breaks ties the previous pass left standing) —
    # mirrors the original "year DESC NULLS LAST, name DESC, grade_id NULLS
    # FIRST" ordering (whole-season row before its own per-grade breakdown).
    rows.sort(key=lambda r: r["grade_id"] is not None)
    rows.sort(key=lambda r: r["season_name"] or "", reverse=True)
    rows.sort(key=lambda r: (r["year"] is None, -(r["year"] or 0)))
    return rows


async def grade_breakdown(db: AsyncSession, org_id: uuid.UUID,
                          player_id: uuid.UUID) -> list[dict]:
    """Career games/goals split by the grade turned out in — Seniors,
    Reserves, Colts, Under 18s and so on.

    Reads the per-grade rows only (grade_id IS NOT NULL), so it never double
    counts against the whole-season rollup rows sitting beside them, and
    combines synced with imported under the same sync-wins-per-season rule
    the rest of this module uses. Rows are folded together by merge group
    (grade_merge_logs), the same way the public grade filter in
    routers/afl/clubs.py folds them — otherwise a club that merged "Senior
    Men's" into "Seniors" gets two cards for one competition.

    A season with no grade resolved at all (an Import Stats upload that never
    named one) contributes to a player's career totals but to no grade here,
    so the sum of these rows can legitimately fall short of the career total.
    The caller shows that gap rather than this function inventing a bucket
    for it.
    """
    res = await db.execute(text("""
        WITH combined AS (
            SELECT s.grade_id, s.games, s.goals
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.player_id = :pid
              AND s.grade_id IS NOT NULL
            UNION ALL
            SELECT i.grade_id, i.games_played AS games, i.goals
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org AND i.player_id = :pid
              AND i.grade_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT gr.name AS name,
               MAX(gr.display_name_override) AS display_name_override,
               COALESCE(SUM(c.games), 0) AS games,
               COALESCE(SUM(c.goals), 0) AS goals
        FROM combined c
        JOIN grades gr ON gr.id = c.grade_id
        GROUP BY gr.name
    """), {"org": str(org_id), "pid": str(player_id)})
    rows = [dict(r._mapping) for r in res]
    if not rows:
        return []

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    buckets: dict[str, dict] = {}
    for row in rows:
        canonical = _resolve_canonical_grade(chain, row["name"])
        slot = buckets.setdefault(canonical, {
            "grade": canonical, "games": 0, "goals": 0, "_override": None,
        })
        # The canonical grade's own rename wins; an alias's only fills a gap.
        if row["display_name_override"] and (slot["_override"] is None or row["name"] == canonical):
            slot["_override"] = row["display_name_override"]
        slot["games"] += int(row["games"] or 0)
        slot["goals"] += int(row["goals"] or 0)

    out = [{
        "grade": b["_override"] or b["grade"],
        "games": b["games"],
        "goals": b["goals"],
    } for b in buckets.values()]
    out.sort(key=lambda r: (-r["games"], -r["goals"], r["grade"].lower()))
    return out


async def player_game_log(db: AsyncSession, org_id: uuid.UUID,
                          player_id: uuid.UUID, limit: int = 200) -> list[dict]:
    res = await db.execute(text("""
        SELECT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               g.result, g.is_final, gr.name AS grade_name,
               s.name AS season_name, s.year,
               d.round_name, d.round_abbrev, d.status,
               d.home_score, d.away_score, d.our_side,
               l.goals, l.behinds, l.bog_ranking, l.is_captain, l.jumper_number
        FROM afl_player_game_lines l
        JOIN games g ON g.id = l.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE l.player_id = :pid AND s.organisation_id = :org
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim
    """), {"org": str(org_id), "pid": str(player_id), "lim": limit})
    return [dict(r._mapping) for r in res]


def _resolve_canonical_grade(chain: dict[str, str], name: str, _seen: Optional[set] = None) -> str:
    """Follow a grade_merge_logs alias chain to its root, guarding a cycle."""
    seen = _seen or set()
    if name in seen:
        return name
    seen.add(name)
    nxt = chain.get(name)
    if nxt is None:
        return name
    return _resolve_canonical_grade(chain, nxt, seen)


async def matching_grade_ids(db: AsyncSession, org_id: uuid.UUID, grade_id: uuid.UUID) -> list[uuid.UUID]:
    """Every grade_id (any season) that shares a merge group with ``grade_id`` —
    so filtering "this grade" transparently absorbs whatever's been merged
    into (or was merged from) it, the way Merge Grades promises. A grade
    exists once per season it's fielded in (grades.season_id), so "this
    grade across all time" is every row sharing its name/merge-group, not
    just the one row the caller happened to pick."""
    name_row = await db.execute(text("SELECT name FROM grades WHERE id = :gid"), {"gid": str(grade_id)})
    name = name_row.scalar()
    if not name:
        return [grade_id]

    logs = await db.execute(text(
        "SELECT alias_name, canonical_name FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL"
    ), {"org": str(org_id)})
    chain = {r.alias_name: r.canonical_name for r in logs}

    canonical = _resolve_canonical_grade(chain, name)
    group_names = {canonical} | {a for a in chain if _resolve_canonical_grade(chain, a) == canonical}

    rows = await db.execute(text("""
        SELECT gr.id FROM grades gr JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = :org AND gr.name = ANY(:names)
    """), {"org": str(org_id), "names": list(group_names)})
    ids = [r.id for r in rows]
    return ids or [grade_id]


async def club_results_summary(db: AsyncSession, org_id: uuid.UUID,
                               season_id: Optional[uuid.UUID] = None) -> dict:
    """Headline W/L/D across the club (optionally one season).

    Reads the games/afl_game_details tables only, unlike the goals/games/BOG
    combines elsewhere in this module — a win/loss/draw is a property of one
    specific MATCH, and a season-total Import Stats upload has no per-match
    data to draw a result from at all, so there's nothing to combine in from
    afl_imported_stats here.

    Import RESULTS uploads (routers/afl/result_imports.py) are a different
    story and need no special handling: they write real games rows carrying a
    real result letter, so they count here the same as a synced game. A bye
    is stored with status 'BYE' and a NULL result, which is what keeps it out
    of both the W/L/D tallies and the played count."""
    season_clause = "AND s.id = :season" if season_id else ""
    params: dict = {"org": str(org_id)}
    if season_id:
        params["season"] = str(season_id)
    res = await db.execute(text(f"""
        SELECT COUNT(*) FILTER (WHERE g.result = 'W') AS wins,
               COUNT(*) FILTER (WHERE g.result = 'L') AS losses,
               COUNT(*) FILTER (WHERE g.result = 'D') AS draws,
               COUNT(*) FILTER (WHERE d.status = 'FINAL') AS played
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org {season_clause}
    """), params)
    return dict(res.one()._mapping)


async def upcoming_milestones(db: AsyncSession, org_id: uuid.UUID, limit: int = 50) -> list[dict]:
    """Live-computed "in reach" milestones — no stored milestones table, same
    approach as Core's get_upcoming_milestones_for_org. Scoped to players
    active in the club's 3 most recent seasons (synced or imported) so a
    decades-retired player's long-crossed totals don't clutter the list —
    career-wide totals, not season-scoped, since a milestone is a lifetime
    tally regardless of which season the dashboard filter has picked."""
    res = await db.execute(text("""
        WITH combined AS (
            SELECT s.player_id, s.season_id, s.games, s.goals
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND s.grade_id IS NULL
            UNION ALL
            SELECT i.player_id, i.season_id, i.games_played AS games, i.goals
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        ),
        recent_seasons AS (
            SELECT s.id
            FROM seasons s
            JOIN combined c ON c.season_id = s.id
            WHERE s.organisation_id = :org
            GROUP BY s.id, s.year, s.name
            ORDER BY s.year DESC NULLS LAST, s.name DESC
            LIMIT 3
        ),
        active_players AS (
            SELECT DISTINCT c.player_id
            FROM combined c
            WHERE c.season_id IN (SELECT id FROM recent_seasons)
        )
        SELECT p.id AS player_id,
               COALESCE(p.display_name_override, p.name) AS name,
               COALESCE(SUM(c.games), 0) AS career_games,
               COALESCE(SUM(c.goals), 0) AS career_goals
        FROM players p
        JOIN combined c ON c.player_id = p.id
        WHERE p.organisation_id = :org AND p.id IN (SELECT player_id FROM active_players)
        GROUP BY p.id, p.name, p.display_name_override
        HAVING COALESCE(SUM(c.games), 0) > 0 OR COALESCE(SUM(c.goals), 0) > 0
    """), {"org": str(org_id)})
    rows = [dict(r._mapping) for r in res]

    def importance_score(target, needed):
        return (target ** 2) / (needed + 1)

    upcoming = []
    for row in rows:
        totals = {"games": int(row["career_games"] or 0), "goals": int(row["career_goals"] or 0)}
        for stat, current in totals.items():
            target = milestone_rules.next_threshold(stat, current)
            if target is None:
                continue
            needed = target - current
            if needed > milestone_rules.reach_window(stat, target):
                continue
            upcoming.append({
                "player_id": str(row["player_id"]),
                "name": row["name"],
                "type": stat,
                "current": current,
                "target": target,
                "needed": needed,
                "score": importance_score(target, needed),
            })

    upcoming.sort(key=lambda x: x["score"], reverse=True)
    return upcoming[:limit]
