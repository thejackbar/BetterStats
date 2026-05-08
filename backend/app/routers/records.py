from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import uuid

from app.models.db import get_db, Grade, Season

router = APIRouter(prefix="/records", tags=["records"])

_LIMIT = 25


@router.get("/{org_id}/grades")
async def get_records_grades(
    org_id: str,
    season_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return grades for the org, optionally scoped to a season."""
    q = (
        select(Grade)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == uuid.UUID(org_id))
    )
    if season_id:
        q = q.where(Grade.season_id == uuid.UUID(season_id))
    result = await db.execute(q.order_by(Grade.name))
    grades = result.scalars().all()
    return [{"id": str(g.id), "name": g.name, "season_id": str(g.season_id)} for g in grades]
