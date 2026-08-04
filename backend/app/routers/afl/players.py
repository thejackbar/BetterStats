"""Public players list, player profile, and comparison."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, get_db
from app.services.afl import aggregations

router = APIRouter(prefix="/afl-players", tags=["afl-players"])


@router.get("/by-org/{org_id}")
async def list_players(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return {"players": await aggregations.career_totals(db, org_id)}


@router.get("/compare")
async def compare_players(org_id: uuid.UUID,
                          ids: str = Query(..., description="comma-separated player ids"),
                          db: AsyncSession = Depends(get_db)):
    try:
        player_ids = [uuid.UUID(x) for x in ids.split(",") if x.strip()][:4]
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad player id")
    if len(player_ids) < 2:
        raise HTTPException(status_code=422, detail="Pick at least two players")
    totals = await aggregations.career_totals(db, org_id, player_ids)
    out = []
    for t in totals:
        seasons = await aggregations.season_by_season(db, org_id, t["player_id"])
        out.append({**t, "seasons": [s for s in seasons if s["grade_id"] is None]})
    return {"players": out}


@router.get("/{player_id}")
async def get_player(player_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, player_id)
    if player is None or player.organisation_id is None:
        raise HTTPException(status_code=404, detail="Player not found")
    org_id = player.organisation_id
    totals = await aggregations.career_totals(db, org_id, [player_id])
    seasons = await aggregations.season_by_season(db, org_id, player_id)
    games = await aggregations.player_game_log(db, org_id, player_id)
    best_haul = max((g for g in games if g["goals"] is not None),
                    key=lambda g: g["goals"], default=None)
    return {
        "id": str(player.id),
        "name": player.display_name,
        "photo_url": player.photo_url,
        "organisation_id": str(org_id),
        "career": totals[0] if totals else None,
        "seasons": seasons,
        "game_log": games,
        "best_haul": {
            "goals": best_haul["goals"],
            "game_id": str(best_haul["game_id"]),
            "round_name": best_haul["round_name"],
            "season_name": best_haul["season_name"],
        } if best_haul and (best_haul["goals"] or 0) > 0 else None,
    }
