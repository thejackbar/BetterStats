"""Public leaderboard — goals / games / Best on Ground / lifetime B&F votes,
season + grade filterable. BOG is a flat count of best-players mentions (per
the product decision; ranking is stored for future weighted views).

club_bf_votes/comp_bf_votes are a different shape of stat from the other four:
they only ever come from a historical Import Stats upload (routers/afl/imports.py)
— PlayHQ has no concept of club-internal best & fairest voting, so
afl_player_season_stats (wholly derived from synced game lines, see
services/afl/sync.py's _rollup_season_stats) never carries them. They're
queried straight off afl_imported_stats instead of the usual pss table, and
— because afl_imported_stats has no real grade_id, only a free-text
grade_label — a grade filter is not applied to a votes stat; a season filter
still works since imported rows do carry a resolved season_id.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl.aggregations import matching_grade_ids

router = APIRouter(prefix="/afl-leaderboard", tags=["afl-leaderboard"])

_STATS = {
    "goals": "SUM(pss.goals)",
    "games": "SUM(pss.games)",
    "bogs": "SUM(pss.bog_count)",
    "behinds": "SUM(pss.behinds)",
}
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

    if stat in _VOTE_STATS:
        col = _VOTE_STATS[stat]
        clauses = ["i.organisation_id = :org"]
        params: dict = {"org": str(org_id), "lim": limit}
        if season_id:
            clauses.append("i.season_id = :season")
            params["season"] = str(season_id)
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

    agg = _STATS[stat]
    clauses = ["pss.organisation_id = :org"]
    params: dict = {"org": str(org_id), "lim": limit}
    if season_id:
        clauses.append("pss.season_id = :season")
        params["season"] = str(season_id)
    if grade_id:
        clauses.append("pss.grade_id = ANY(:grade)")
        params["grade"] = await matching_grade_ids(db, org_id, grade_id)
    else:
        clauses.append("pss.grade_id IS NULL")
    where = " AND ".join(clauses)
    res = await db.execute(text(f"""
        SELECT pss.player_id, p.name, p.display_name_override, p.photo_url,
               SUM(pss.games) AS games,
               SUM(pss.goals) AS goals,
               SUM(pss.behinds) AS behinds,
               SUM(pss.bog_count) AS bogs,
               {agg} AS value
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        WHERE {where}
        GROUP BY pss.player_id, p.name, p.display_name_override, p.photo_url
        HAVING {agg} > 0
        ORDER BY value DESC, games ASC, p.name
        LIMIT :lim
    """), params)
    return {"stat": stat, "rows": [dict(r._mapping) for r in res]}
