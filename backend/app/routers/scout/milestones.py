"""BetterScout — the Milestones screen. See services/scout_milestones.py for
the thresholds/dating/seen-tracking logic; this router is thin.

Unlike the discovery/watchlist/compare write endpoints, "mark as seen" is
deliberately left open to EITHER role, not gated behind require_scout_owner
— it's a personal "I've reviewed this" acknowledgement with no effect on the
org's actual tracked-player data, closer to a read receipt than a write a
viewer shouldn't be trusted with."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user
from app.services import scout_milestones

router = APIRouter(prefix="/scout/milestones", tags=["scout-milestones"])


@router.get("")
async def get_milestones(
    seasons: int = Query(scout_milestones.DEFAULT_SEASONS_WINDOW, ge=1, le=10),
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_milestones.build_milestones(db, org.id, seasons_window=seasons)


class MarkSeenRequest(BaseModel):
    scouted_player_id: str
    milestone_type: str
    milestone_value: int


@router.post("/seen")
async def mark_seen(
    data: MarkSeenRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        await scout_milestones.mark_seen(db, org.id, data.scouted_player_id, data.milestone_type, data.milestone_value)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}


@router.post("/seen-all")
async def mark_all_seen(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    n = await scout_milestones.mark_all_seen(db, org.id)
    return {"status": "ok", "marked": n}
