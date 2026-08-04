"""AFL read-side aggregation helpers shared by the public routers.

Everything is org-scoped through grades→seasons (the games table has no
organisation column of its own) and reads only synced data — no live PlayHQ
calls on any public request path.
"""
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def career_totals(db: AsyncSession, org_id: uuid.UUID,
                        player_ids: Optional[list[uuid.UUID]] = None) -> list[dict]:
    """Career totals per player from the whole-season rollup rows
    (grade_id IS NULL so per-grade rows don't double count)."""
    where_player = "AND pss.player_id = ANY(:pids)" if player_ids else ""
    params: dict = {"org": str(org_id)}
    if player_ids:
        params["pids"] = [str(p) for p in player_ids]
    res = await db.execute(text(f"""
        SELECT pss.player_id,
               p.name,
               p.display_name_override,
               p.photo_url,
               COUNT(DISTINCT pss.season_id)              AS seasons,
               COALESCE(SUM(pss.games), 0)                AS games,
               COALESCE(SUM(pss.goals), 0)                AS goals,
               COALESCE(SUM(pss.behinds), 0)              AS behinds,
               COALESCE(SUM(pss.bog_count), 0)            AS bogs,
               COALESCE(SUM(pss.captain_games), 0)        AS captain_games,
               MIN(s.year)                                AS first_year,
               MAX(s.year)                                AS last_year
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE pss.organisation_id = :org
          AND pss.grade_id IS NULL
          {where_player}
        GROUP BY pss.player_id, p.name, p.display_name_override, p.photo_url
        ORDER BY games DESC, goals DESC
    """), params)
    return [dict(r._mapping) for r in res]


async def season_by_season(db: AsyncSession, org_id: uuid.UUID,
                           player_id: uuid.UUID) -> list[dict]:
    res = await db.execute(text("""
        SELECT pss.season_id, s.name AS season_name, s.year,
               pss.grade_id, gr.name AS grade_name,
               pss.games, pss.goals, pss.behinds, pss.bog_count AS bogs,
               pss.captain_games
        FROM afl_player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        LEFT JOIN grades gr ON gr.id = pss.grade_id
        WHERE pss.organisation_id = :org AND pss.player_id = :pid
        ORDER BY s.year DESC NULLS LAST, s.name DESC, pss.grade_id NULLS FIRST
    """), {"org": str(org_id), "pid": str(player_id)})
    return [dict(r._mapping) for r in res]


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
    """Headline W/L/D across the club (optionally one season)."""
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
