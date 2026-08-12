"""BetterScout — the Compare screen. See services/scout_compare.py. Reading
a comparison is open to either role; minting a share link is a write
(require_scout_owner), same rule every other share-link endpoint follows."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user, require_scout_owner
from app.services import scout_compare

router = APIRouter(prefix="/scout/compare", tags=["scout-compare"])


@router.get("")
async def get_comparison(
    players: str = Query(""),
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    ids = [p for p in players.split(",") if p]
    return await scout_compare.build_comparison(db, org.id, ids)


class ShareComparisonRequest(BaseModel):
    player_ids: list[str]


@router.post("/share")
async def share_comparison(
    data: ShareComparisonRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(require_scout_owner),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        return await scout_compare.create_share_link(db, org.id, data.player_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
