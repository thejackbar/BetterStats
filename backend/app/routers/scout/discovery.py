"""BetterScout — player discovery routes. Every route requires a signed-in
Scout Org user (get_current_scout_user); there is no club/entitlement
concept to gate on here, unlike every other Better module."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutedPlayer, ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user
from app.services import playhq_client, scout_discovery
from app.services import iq_scout

router = APIRouter(prefix="/scout", tags=["scout-discovery"])


@router.get("/clubs/search")
async def search_clubs(
    q: str = "", current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
):
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    return [
        {"id": org.get("id"), "name": org.get("name")}
        for org in results
        if org.get("id") and org.get("name")
    ]


@router.get("/clubs/{org_guid}/roster")
async def get_club_roster(
    org_guid: str, club_name: str | None = None,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    return await scout_discovery.get_or_start_club_roster(db, org_guid, club_name=club_name)


@router.post("/clubs/{org_guid}/roster/refresh")
async def refresh_club_roster(
    org_guid: str, club_name: str | None = None,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    return await scout_discovery.get_or_start_club_roster(db, org_guid, club_name=club_name, force=True)


@router.get("/clubs/{org_guid}/grades")
async def get_club_grades(
    org_guid: str, current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
):
    return await iq_scout.external_club_teams(org_guid)


class AddPlayerRequest(BaseModel):
    org_guid: str
    player_id: str
    club_name: str | None = None


@router.post("/players/add")
async def add_player(
    data: AddPlayerRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    try:
        return await scout_discovery.add_player(db, org.id, data.org_guid, data.player_id, data.club_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class AddManualPlayerRequest(BaseModel):
    name: str
    club_name: str | None = None
    notes: str | None = None


@router.post("/players/manual")
async def add_manual_player(
    data: AddManualPlayerRequest,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    if not (data.name or "").strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    _, org = current
    return await scout_discovery.add_manual_player(db, org.id, data.name.strip(), data.club_name, data.notes)


@router.get("/players")
async def list_players(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_discovery.list_tracked_players(db, org.id)


@router.get("/players/{player_id}")
async def get_player(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(ScoutedPlayer, player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")
    return scout_discovery.player_out(player)


@router.post("/players/{player_id}/refresh")
async def refresh_player(
    player_id: str,
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await scout_discovery.refresh_player(db, player_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
