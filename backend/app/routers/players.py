from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
from pydantic import BaseModel
from typing import Optional
import uuid

from app.models.db import Player, User, PlayerSyncRequest, get_db
from app.routers.auth import get_current_user
from app.services.aggregations import (
    get_career_batting, get_career_bowling, get_career_fielding,
    get_player_batting_innings, get_player_bowling_spells,
    get_dismissal_breakdown, get_batting_by_position, get_batting_by_grade,
    get_bowling_by_grade, get_player_team_breakdown,
    get_season_by_season, get_player_milestones, get_player_partnerships,
    get_player_activity, get_upcoming_milestones_for_org,
    get_player_rankings,
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
        .order_by(func.coalesce(Player.display_name_override, Player.name))
    )
    players = result.scalars().all()
    return [
        {"id": str(p.id), "name": p.name, "display_name": p.display_name, "claimed": p.claimed}
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
        "display_name": player.display_name,
        "organisation_id": str(player.organisation_id),
        "claimed": player.claimed,
        "playhq_id": player.playhq_id,
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

    batting = await get_career_batting(db, player_id, season_id)
    bowling = await get_career_bowling(db, player_id, season_id)
    fielding = await get_career_fielding(db, player_id, season_id)
    batting_innings = await get_player_batting_innings(db, player_id, season_id, grade_id)
    bowling_spells = await get_player_bowling_spells(db, player_id, season_id, grade_id)

    return {
        "player": {"id": str(player.id), "name": player.name, "display_name": player.display_name, "claimed": player.claimed, "organisation_id": str(player.organisation_id), "playhq_id": player.playhq_id, "photo_url": player.photo_url},
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
    return await get_batting_by_grade(db, player_id, str(player.organisation_id))


@router.get("/{player_id}/bowling-by-grade")
async def get_player_bowling_by_grade(player_id: str, db: AsyncSession = Depends(get_db)):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_bowling_by_grade(db, player_id, str(player.organisation_id))


@router.get("/{player_id}/team-breakdown")
async def get_player_team_breakdown_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_team_breakdown(
        db, player_id, str(player.organisation_id), season_id
    )


@router.get("/{player_id}/rankings")
async def get_player_rankings_endpoint(
    player_id: str,
    season_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return await get_player_rankings(db, player_id, str(player.organisation_id), season_id)


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

    # Per-grade match milestones — uses the same merge-aware breakdown the
    # Team tab does so canonical/merged grade names line up.
    breakdown = await get_player_team_breakdown(db, player_id, str(player.organisation_id))
    GRADE_MATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 250, 300]
    for row in breakdown.get("rows", []):
        matches_in_grade = int(row.get("matches") or 0)
        grade_name = row.get("grade_name")
        if not grade_name or matches_in_grade <= 0:
            continue
        next_target = next((m for m in GRADE_MATCH_MILESTONES if matches_in_grade < m), None)
        if next_target is None:
            continue
        needed = next_target - matches_in_grade
        # Only surface when within a meaningful window — otherwise the list
        # explodes for players who've sampled lots of grades briefly.
        if needed > 15:
            continue
        upcoming.append({
            "type": "matches",
            "current": matches_in_grade,
            "target": next_target,
            "needed": needed,
            "label": f"MATCHES — {grade_name}",
            "grade_name": grade_name,
        })

    upcoming.sort(key=lambda m: m.get("needed", 9999))
    return upcoming


class SyncRequestCreate(BaseModel):
    note: Optional[str] = None


@router.post("/{player_id}/request-sync")
async def request_player_sync(
    player_id: str,
    body: SyncRequestCreate = SyncRequestCreate(),
    db: AsyncSession = Depends(get_db),
):
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Prevent duplicate pending requests
    existing = await db.execute(
        text("""
            SELECT id FROM player_sync_requests
            WHERE player_id = :pid AND status = 'pending'
            LIMIT 1
        """),
        {"pid": player_id},
    )
    if existing.fetchone():
        return {"status": "already_pending"}

    req = PlayerSyncRequest(
        player_id=player.id,
        org_id=player.organisation_id,
        requester_note=body.note,
        status="pending",
    )
    db.add(req)
    await db.commit()
    return {"status": "requested"}


class PlayerRename(BaseModel):
    name: str


@router.patch("/{player_id}")
async def rename_player(
    player_id: str,
    body: PlayerRename,
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    player = await db.get(Player, uuid.UUID(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    old_name = player.name
    player.name = name
    # Keep player_achievements rows in sync for unlinked records
    await db.execute(
        text("UPDATE player_achievements SET player_name = :new WHERE player_id = :pid"),
        {"new": name, "pid": player_id},
    )
    await db.commit()
    return {"status": "renamed", "old_name": old_name, "new_name": name}


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
