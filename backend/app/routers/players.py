from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import uuid

from app.models.db import Player, User, get_db
from app.routers.auth import get_current_user
from app.services.aggregations import (
    get_career_batting, get_career_bowling, get_career_fielding,
    get_player_batting_innings, get_player_bowling_spells,
)

router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
async def list_players(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Player)
        .where(Player.organisation_id == uuid.UUID(org_id))
        .order_by(Player.name)
    )
    players = result.scalars().all()
    return [
        {"id": str(p.id), "name": p.name, "claimed": p.claimed}
        for p in players
    ]


@router.get("/{player_id}")
async def get_player(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "id": str(player.id),
        "name": player.name,
        "organisation_id": str(player.organisation_id),
        "claimed": player.claimed,
    }


@router.get("/{player_id}/stats")
async def get_player_stats(
    player_id: str,
    season_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    batting = await get_career_batting(db, player_id)
    bowling = await get_career_bowling(db, player_id)
    fielding = await get_career_fielding(db, player_id)
    batting_innings = await get_player_batting_innings(db, player_id, season_id, grade_id)
    bowling_spells = await get_player_bowling_spells(db, player_id, season_id, grade_id)

    def _str_keys(d: dict | None) -> dict | None:
        if not d:
            return d
        return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in d.items()}

    return {
        "player": {"id": str(player.id), "name": player.name, "claimed": player.claimed},
        "career_batting": _str_keys(batting),
        "career_bowling": _str_keys(bowling),
        "career_fielding": _str_keys(fielding),
        "batting_innings": [_str_keys(i) for i in batting_innings],
        "bowling_spells": [_str_keys(s) for s in bowling_spells],
    }


@router.post("/{player_id}/claim")
async def claim_player_profile(
    player_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    if player.claimed:
        raise HTTPException(status_code=409, detail="Profile already claimed")

    player.claimed = True
    player.user_id = current_user.id
    await db.commit()
    return {"status": "claimed", "player_id": player_id}
