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
    get_dismissal_breakdown, get_batting_by_position, get_batting_by_grade,
    get_season_by_season, get_player_milestones, get_player_partnerships,
    get_player_activity, get_upcoming_milestones_for_org,
)

router = APIRouter(prefix="/players", tags=["players"])


def _str_keys(d: dict | None) -> dict | None:
    if not d:
        return d
    return {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in d.items()}


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

    return {
        "player": {"id": str(player.id), "name": player.name, "claimed": player.claimed},
        "career_batting": _str_keys(batting),
        "career_bowling": _str_keys(bowling),
        "career_fielding": _str_keys(fielding),
        "batting_innings": [_str_keys(i) for i in batting_innings],
        "bowling_spells": [_str_keys(s) for s in bowling_spells],
    }


@router.get("/{player_id}/dismissals")
async def get_player_dismissals(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_dismissal_breakdown(db, player_id)


@router.get("/{player_id}/by-position")
async def get_player_by_position(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_batting_by_position(db, player_id)


@router.get("/{player_id}/by-grade")
async def get_player_by_grade(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_batting_by_grade(db, player_id)


@router.get("/{player_id}/seasons")
async def get_player_seasons(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_season_by_season(db, player_id)


@router.get("/{player_id}/milestones")
async def get_player_milestones_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await get_player_milestones(db, player_id)
    return [_str_keys(r) for r in rows]


@router.get("/{player_id}/partnerships")
async def get_player_partnerships_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    rows = await get_player_partnerships(db, player_id)
    return [_str_keys(r) for r in rows]


@router.get("/{player_id}/activity")
async def get_player_activity_endpoint(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_activity(db, player_id)


@router.get("/{player_id}/upcoming-milestones")
async def get_player_upcoming_milestones(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    RUN_MILESTONES = [50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]
    WICKET_MILESTONES = [10, 25, 50, 75, 100, 150, 200]
    MATCH_MILESTONES = [10, 25, 50, 100, 150, 200]

    from sqlalchemy import text
    agg_res = await db.execute(
        text("""
            SELECT
                COALESCE(SUM(runs), 0) AS total_runs,
                COALESCE(SUM(wickets), 0) AS total_wickets,
                COALESCE(SUM(matches), 0) AS total_matches
            FROM player_season_stats WHERE player_id=:pid
        """),
        {"pid": player_id}
    )
    agg = dict(agg_res.mappings().first() or {})
    total_runs = int(agg.get("total_runs") or 0)
    total_wickets = int(agg.get("total_wickets") or 0)
    total_matches = int(agg.get("total_matches") or 0)

    upcoming = []
    for m in RUN_MILESTONES:
        if total_runs < m:
            upcoming.append({"type": "runs", "current": total_runs, "target": m, "needed": m - total_runs})
            break
    for m in WICKET_MILESTONES:
        if total_wickets < m:
            upcoming.append({"type": "wickets", "current": total_wickets, "target": m, "needed": m - total_wickets})
            break
    for m in MATCH_MILESTONES:
        if total_matches < m:
            upcoming.append({"type": "matches", "current": total_matches, "target": m, "needed": m - total_matches})
            break
    return upcoming


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
