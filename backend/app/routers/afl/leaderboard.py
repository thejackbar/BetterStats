"""Public leaderboard — goals / games / Best on Ground / lifetime B&F votes,
season + grade filterable. BOG is a flat count of best-players mentions (per
the product decision; ranking is stored for future weighted views).

Every stat here combines SYNCED (afl_player_season_stats) with IMPORTED
(afl_imported_stats, from a historical Import Stats upload) the same way the
admin Players list already does — sync wins per (player, season), imported
only fills a genuine gap — because without this, a club whose whole history
came from an Import Stats upload had real numbers in the admin Players list
but an empty public leaderboard (only afl_player_season_stats was ever read
here). A grade filter now also reaches imported rows: routers/afl/imports.py
promotes a resolved (season, grade label) into a real Grade row at commit
time, so afl_imported_stats.grade_id is a normal grade_id like any synced
row's — no free-text grade_label matching needed here.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl.aggregations import matching_grade_ids

router = APIRouter(prefix="/afl-leaderboard", tags=["afl-leaderboard"])

_STATS = {"goals": "goals", "games": "games", "bogs": "bog_count", "behinds": "behinds"}
_VOTE_STATS = {"club_bf_votes": "club_bf_votes", "comp_bf_votes": "comp_bf_votes"}


@router.get("/{org_id}")
async def leaderboard(org_id: uuid.UUID,
                      stat: str = Query("goals"),
                      season_id: Optional[uuid.UUID] = None,
                      grade_id: Optional[uuid.UUID] = None,
                      limit: int = Query(50, le=200),
                      db: AsyncSession = Depends(get_db)):
    if stat not in _STATS and stat not in _VOTE_STATS:
        raise HTTPException(status_code=422, detail=f"stat must be one of {sorted({*_STATS, *_VOTE_STATS})}")
    params: dict = {"org": str(org_id), "lim": limit}

    if stat in _VOTE_STATS:
        # Club/competition B&F votes only ever come from an Import Stats
        # upload — PlayHQ has no concept of club-internal B&F voting, so
        # afl_player_season_stats never carries them at all.
        col = _VOTE_STATS[stat]
        clauses = ["i.organisation_id = :org"]
        if season_id:
            clauses.append("i.season_id = :season")
            params["season"] = str(season_id)
        if grade_id:
            clauses.append("i.grade_id = ANY(:grade)")
            params["grade"] = await matching_grade_ids(db, org_id, grade_id)
        where = " AND ".join(clauses)
        res = await db.execute(text(f"""
            SELECT i.player_id, p.name, p.display_name_override, p.photo_url,
                   SUM(i.games_played) AS games,
                   SUM(i.goals) AS goals,
                   SUM(i.behinds) AS behinds,
                   SUM(i.bog_count) AS bogs,
                   SUM(i.{col}) AS value
            FROM afl_imported_stats i
            JOIN players p ON p.id = i.player_id
            WHERE {where}
            GROUP BY i.player_id, p.name, p.display_name_override, p.photo_url
            HAVING SUM(i.{col}) > 0
            ORDER BY value DESC, games ASC, p.name
            LIMIT :lim
        """), params)
        return {"stat": stat, "rows": [dict(r._mapping) for r in res]}

    value_col = _STATS[stat]

    if grade_id:
        params["grade"] = await matching_grade_ids(db, org_id, grade_id)
        synced_grade_clause = "s.grade_id = ANY(:grade)"
        imported_grade_clause = "i.grade_id = ANY(:grade)"
    else:
        synced_grade_clause = "s.grade_id IS NULL"
        imported_grade_clause = "TRUE"

    season_clause_s = ""
    season_clause_i = ""
    if season_id:
        params["season"] = str(season_id)
        season_clause_s = "AND s.season_id = :season"
        season_clause_i = "AND i.season_id = :season"

    res = await db.execute(text(f"""
        WITH combined AS (
            SELECT s.player_id, s.games, s.goals, s.behinds, s.bog_count
            FROM afl_player_season_stats s
            WHERE s.organisation_id = :org AND {synced_grade_clause} {season_clause_s}
            UNION ALL
            SELECT i.player_id, i.games_played AS games, i.goals, i.behinds, i.bog_count
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org AND {imported_grade_clause} {season_clause_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id, p.name, p.display_name_override, p.photo_url,
               SUM(c.games) AS games,
               SUM(c.goals) AS goals,
               SUM(c.behinds) AS behinds,
               SUM(c.bog_count) AS bogs,
               SUM(c.{value_col}) AS value
        FROM combined c
        JOIN players p ON p.id = c.player_id
        GROUP BY c.player_id, p.name, p.display_name_override, p.photo_url
        HAVING SUM(c.{value_col}) > 0
        ORDER BY value DESC, games ASC, p.name
        LIMIT :lim
    """), params)
    return {"stat": stat, "rows": [dict(r._mapping) for r in res]}
