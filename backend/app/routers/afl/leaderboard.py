"""Public leaderboard — goals / games / Best on Ground, season + grade
filterable. BOG is a flat count of best-players mentions (per the product
decision; ranking is stored for future weighted views)."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db

router = APIRouter(prefix="/afl-leaderboard", tags=["afl-leaderboard"])

_STATS = {
    "goals": "SUM(pss.goals)",
    "games": "SUM(pss.games)",
    "bogs": "SUM(pss.bog_count)",
    "behinds": "SUM(pss.behinds)",
}


@router.get("/{org_id}")
async def leaderboard(org_id: uuid.UUID,
                      stat: str = Query("goals"),
                      season_id: Optional[uuid.UUID] = None,
                      grade_id: Optional[uuid.UUID] = None,
                      limit: int = Query(50, le=200),
                      db: AsyncSession = Depends(get_db)):
    if stat not in _STATS:
        raise HTTPException(status_code=422, detail=f"stat must be one of {sorted(_STATS)}")
    agg = _STATS[stat]
    clauses = ["pss.organisation_id = :org"]
    params: dict = {"org": str(org_id), "lim": limit}
    if season_id:
        clauses.append("pss.season_id = :season")
        params["season"] = str(season_id)
    if grade_id:
        clauses.append("pss.grade_id = :grade")
        params["grade"] = str(grade_id)
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
