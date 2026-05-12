from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.models.db import get_db
from app.services.statlab import (
    query_players, query_grades, PLAYER_FIELDS, GRADE_FIELDS, OPERATOR_MAP,
)

router = APIRouter(prefix="/statlab", tags=["statlab"])


@router.get("/fields")
async def get_fields():
    """Return the available filterable/sortable fields for each group mode."""
    return {
        "player": list(PLAYER_FIELDS.keys()),
        "grade": list(GRADE_FIELDS.keys()),
        "team": list(GRADE_FIELDS.keys()),
        "operators": list(OPERATOR_MAP.keys()),
    }


@router.get("/query")
async def statlab_query(
    org_id: str,
    group_by: str = Query("player", pattern="^(player|grade|team)$"),
    mode: str = Query("career", pattern="^(career|season)$"),
    season_id: Optional[str] = Query(None),
    sort_by: str = Query("runs"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(100, ge=1, le=500),
    filters: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a flexible multi-filter cricket stats query.

    filters: repeated query param, each value is 'field:op:value'
             e.g. ?filters=runs:gte:500&filters=wickets:gte:50
    """
    if group_by == "player":
        rows = await query_players(
            db,
            org_id=org_id,
            mode=mode,
            season_id=season_id,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            filters=filters,
        )
    elif group_by in ("grade", "team"):
        rows = await query_grades(
            db,
            org_id=org_id,
            season_id=season_id,
            group_by_season=(group_by == "team"),
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            filters=filters,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown group_by: {group_by}")

    # Serialise Decimal/UUID types to plain Python
    def _clean(v):
        if v is None:
            return None
        t = type(v).__name__
        if t in ("Decimal", "UUID"):
            return str(v)
        return v

    return [{k: _clean(v) for k, v in row.items()} for row in rows]
