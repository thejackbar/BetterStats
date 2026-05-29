"""BetterSelect — availability (Phase 2).

Admin-recorded player availability for upcoming fixtures. Club-wide model:
the matrix is all active players x upcoming fixtures. There is no player-facing
input — recorded_by/at track the admin who set it.

All endpoints are scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, FixtureAvailability, Organisation, Player, User, get_db
from app.routers.auth import get_current_club, get_current_user

router = APIRouter(prefix="/availability", tags=["availability"])

VALID_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}


class AvailabilitySet(BaseModel):
    fixture_id: str
    player_id: str
    status: str
    note: Optional[str] = None


class AvailabilityBulk(BaseModel):
    items: list[AvailabilitySet]


async def _owned_fixture_ids(db: AsyncSession, club_id) -> set:
    res = await db.execute(select(Fixture.id).where(Fixture.organisation_id == club_id))
    return {r[0] for r in res.fetchall()}


async def _owned_player_ids(db: AsyncSession, club_id) -> set:
    res = await db.execute(select(Player.id).where(Player.organisation_id == club_id))
    return {r[0] for r in res.fetchall()}


async def _upsert(db: AsyncSession, item: AvailabilitySet, user_id,
                  fixture_ids: set, player_ids: set) -> None:
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {item.status}")
    fid = uuid.UUID(item.fixture_id)
    pid = uuid.UUID(item.player_id)
    # Tenancy: both fixture and player must belong to the caller's club.
    if fid not in fixture_ids or pid not in player_ids:
        raise HTTPException(status_code=404, detail="Fixture or player not found")
    res = await db.execute(
        select(FixtureAvailability).where(
            FixtureAvailability.fixture_id == fid,
            FixtureAvailability.player_id == pid,
        )
    )
    row = res.scalar_one_or_none()
    if row:
        row.status = item.status
        row.note = item.note
        row.recorded_by = user_id
        row.recorded_at = datetime.now(timezone.utc)
    else:
        db.add(FixtureAvailability(
            fixture_id=fid,
            player_id=pid,
            status=item.status,
            note=item.note,
            recorded_by=user_id,
        ))


@router.get("/matrix")
async def availability_matrix(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All active players x upcoming fixtures, with any recorded availability."""
    fx_res = await db.execute(
        select(Fixture)
        .where(Fixture.organisation_id == club.id, Fixture.played_on >= date.today())
        .order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    )
    fixtures = fx_res.scalars().all()

    pl_res = await db.execute(
        select(Player)
        .where(
            Player.organisation_id == club.id,
            Player.status == "active",
            Player.is_player.is_(True),
        )
        .order_by(func.coalesce(Player.display_name_override, Player.name))
    )
    players = pl_res.scalars().all()

    avail_map: dict[str, dict[str, dict]] = {}
    fixture_ids = [f.id for f in fixtures]
    if fixture_ids:
        av_res = await db.execute(
            select(FixtureAvailability).where(FixtureAvailability.fixture_id.in_(fixture_ids))
        )
        for a in av_res.scalars().all():
            avail_map.setdefault(str(a.fixture_id), {})[str(a.player_id)] = {
                "status": a.status,
                "note": a.note,
            }

    return {
        "fixtures": [
            {
                "id": str(f.id),
                "played_on": f.played_on.isoformat() if f.played_on else None,
                "start_time": f.start_time,
                "label": f.label,
                "opponent_name": f.opponent_name,
                "home_away": f.home_away,
                "grade_id": str(f.grade_id) if f.grade_id else None,
                "status": f.status,
            }
            for f in fixtures
        ],
        "players": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "skill_positions": p.skill_positions or [],
                "player_role": p.player_role,
            }
            for p in players
        ],
        "availability": avail_map,
    }


@router.post("")
async def set_availability(
    body: AvailabilitySet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    fixture_ids = await _owned_fixture_ids(db, club.id)
    player_ids = await _owned_player_ids(db, club.id)
    await _upsert(db, body, user.id, fixture_ids, player_ids)
    await db.commit()
    return {"status": "ok"}


@router.post("/bulk")
async def set_availability_bulk(
    body: AvailabilityBulk,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    fixture_ids = await _owned_fixture_ids(db, club.id)
    player_ids = await _owned_player_ids(db, club.id)
    for item in body.items:
        await _upsert(db, item, user.id, fixture_ids, player_ids)
    await db.commit()
    return {"status": "ok", "count": len(body.items)}


@router.get("")
async def list_for_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    res = await db.execute(
        select(FixtureAvailability).where(
            FixtureAvailability.fixture_id == uuid.UUID(fixture_id)
        )
    )
    return [
        {"player_id": str(a.player_id), "status": a.status, "note": a.note}
        for a in res.scalars().all()
    ]
