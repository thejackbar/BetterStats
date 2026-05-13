from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid

from app.models.db import get_db
from app.services.aggregations import (
    get_batting_leaderboard, get_bowling_leaderboard, get_fielding_leaderboard,
    get_batting_leaderboard_extended, get_bowling_leaderboard_extended,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


def _stringify(rows: list[dict]) -> list[dict]:
    return [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in r.items()} for r in rows]


@router.get("/batting")
async def batting_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    sort_by: str = Query("total_runs"),
    limit: int = Query(20, le=5000),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_batting_leaderboard_extended(db, org_id, season_id, grade_id, sort_by, limit)
    return _stringify(rows)


@router.get("/bowling")
async def bowling_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    sort_by: str = Query("total_wickets"),
    limit: int = Query(20, le=5000),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_bowling_leaderboard_extended(db, org_id, season_id, grade_id, sort_by, limit)
    return _stringify(rows)


@router.get("/fielding")
async def fielding_leaderboard(
    org_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    sort_by: str = Query("total_dismissals"),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    rows = await get_fielding_leaderboard(db, org_id, season_id, grade_id, sort_by, limit)
    return _stringify(rows)
