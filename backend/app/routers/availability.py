"""BetterSelect — availability (Phase 2).

Admin-recorded player availability, keyed on (player, playing-date). One answer
for a date covers every fixture that day. The matrix is all active players x
playing dates; a two-day game contributes both its dates (week 1 = played_on,
week 2 = end_on). No player-facing input — recorded_by/at track the admin.

All endpoints are scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, PlayerAvailability, Organisation, Player, User, get_db
from app.routers.auth import get_current_club

router = APIRouter(prefix="/availability", tags=["availability"])

VALID_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}

# A player who last appeared more than this many years ago is "dormant":
# surfaced behind a toggle so selection works off the current squad, not the
# entire historical roster. Distinct from the manual status='inactive' flag.
DORMANT_YEARS = 2


class AvailabilitySet(BaseModel):
    player_id: str
    date: date
    status: str
    note: Optional[str] = None


class AvailabilityBulk(BaseModel):
    items: list[AvailabilitySet]


async def _owned_player_ids(db: AsyncSession, club_id) -> set:
    res = await db.execute(select(Player.id).where(Player.organisation_id == club_id))
    return {r[0] for r in res.fetchall()}


async def _upsert(db: AsyncSession, item: AvailabilitySet, club_id, user_id, player_ids: set) -> None:
    if item.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {item.status}")
    pid = uuid.UUID(item.player_id)
    if pid not in player_ids:
        raise HTTPException(status_code=404, detail="Player not found")
    res = await db.execute(
        select(PlayerAvailability).where(
            PlayerAvailability.player_id == pid,
            PlayerAvailability.avail_date == item.date,
        )
    )
    row = res.scalar_one_or_none()
    if row:
        row.status = item.status
        row.note = item.note
        row.recorded_by = user_id
        row.recorded_at = datetime.now(timezone.utc)
    else:
        db.add(PlayerAvailability(
            organisation_id=club_id,
            player_id=pid,
            avail_date=item.date,
            status=item.status,
            note=item.note,
            recorded_by=user_id,
        ))


@router.get("/matrix")
async def availability_matrix(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All active players x upcoming playing dates, with recorded availability.

    Dates are the union of every upcoming fixture's played_on and end_on. Each
    date lists the fixtures occurring that day; a two-day game appears under
    both its dates (role 'day1'/'day2'), a one-day game under its single date.
    """
    fx_res = await db.execute(
        select(Fixture)
        .where(Fixture.organisation_id == club.id, Fixture.played_on >= date.today())
        .order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    )
    fixtures = fx_res.scalars().all()

    # date -> [fixture entries]
    by_date: dict[str, list[dict]] = {}
    for f in fixtures:
        spans = []
        if f.played_on:
            spans.append((f.played_on, "day1" if f.end_on and f.end_on != f.played_on else "single"))
        if f.end_on and f.end_on != f.played_on:
            spans.append((f.end_on, "day2"))
        for d, role in spans:
            by_date.setdefault(d.isoformat(), []).append({
                "id": str(f.id),
                "label": f.label,
                "opponent_name": f.opponent_name,
                "home_away": f.home_away,
                "role": role,
                "two_day": role in ("day1", "day2"),
            })

    # All real players (not just status=active): the frontend filter bar decides
    # what to show. We hand back enough per-player signal — manual status, plus
    # derived recency — for it to default to the "current squad" (~150) instead
    # of every historical name (~1500).
    pl_res = await db.execute(
        select(Player)
        .where(
            Player.organisation_id == club.id,
            Player.is_player.is_(True),
        )
        .order_by(func.coalesce(Player.display_name_override, Player.name))
    )
    players = pl_res.scalars().all()

    # Recency + squad derivation from appearance history (no schema needed).
    # "dormant" = has played before but not within DORMANT_YEARS — the
    # auto-archive bucket (KlubPro-style) so selection works off current players.
    cutoff = date.today() - timedelta(days=365 * DORMANT_YEARS)

    last_played_map: dict[uuid.UUID, date] = {}
    lp_res = await db.execute(
        text(
            "SELECT ga.player_id, MAX(g.played_at) AS last_played "
            "FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org "
            "GROUP BY ga.player_id"
        ),
        {"org": club.id},
    )
    for pid, lp in lp_res.fetchall():
        last_played_map[pid] = lp

    # Recent squads = team names a player appeared for inside the dormancy
    # window, i.e. the squads they currently belong to (not decades of history).
    squads_map: dict[uuid.UUID, set] = {}
    sq_res = await db.execute(
        text(
            "SELECT DISTINCT ga.player_id, ga.team_name "
            "FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org "
            "AND ga.team_name IS NOT NULL AND ga.team_name <> '' "
            "AND g.played_at >= :cutoff"
        ),
        {"org": club.id, "cutoff": cutoff},
    )
    for pid, name in sq_res.fetchall():
        squads_map.setdefault(pid, set()).add(name.strip())

    avail_map: dict[str, dict[str, dict]] = {}
    date_keys = list(by_date.keys())
    if date_keys:
        av_res = await db.execute(
            select(PlayerAvailability).where(
                PlayerAvailability.organisation_id == club.id,
                PlayerAvailability.avail_date.in_([date.fromisoformat(d) for d in date_keys]),
            )
        )
        for a in av_res.scalars().all():
            avail_map.setdefault(str(a.player_id), {})[a.avail_date.isoformat()] = {
                "status": a.status,
                "note": a.note,
            }

    return {
        "dates": [
            {"date": d, "fixtures": by_date[d]}
            for d in sorted(by_date.keys())
        ],
        "players": [
            _player_entry(p, last_played_map.get(p.id), squads_map.get(p.id), cutoff)
            for p in players
        ],
        "availability": avail_map,
        "all_squads": sorted({s for names in squads_map.values() for s in names}),
        "dormant_years": DORMANT_YEARS,
    }


def _player_entry(p: Player, last_played: Optional[date], squads: Optional[set], cutoff: date) -> dict:
    # Derived recency. inactive (manual) takes precedence; otherwise dormant if
    # they've played but not since the cutoff. Never-played players are neither
    # (e.g. a freshly-added manual player with no appearance history yet).
    manual_inactive = p.status == "inactive"
    dormant = bool(last_played) and last_played < cutoff
    return {
        "id": str(p.id),
        "display_name": p.display_name,
        "skill_positions": p.skill_positions or [],
        "player_role": p.player_role,
        "status": p.status,
        "last_played": last_played.isoformat() if last_played else None,
        "squads": sorted(squads) if squads else [],
        "is_inactive": manual_inactive,
        "is_dormant": dormant and not manual_inactive,
        # Convenience flag the UI defaults its filter on: a "current" player is
        # neither manually inactive nor dormant.
        "is_current": not manual_inactive and not dormant,
    }


@router.post("")
async def set_availability(
    body: AvailabilitySet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    player_ids = await _owned_player_ids(db, club.id)
    await _upsert(db, body, club.id, user.id, player_ids)
    await db.commit()
    return {"status": "ok"}


@router.post("/bulk")
async def set_availability_bulk(
    body: AvailabilityBulk,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    player_ids = await _owned_player_ids(db, club.id)
    for item in body.items:
        await _upsert(db, item, club.id, user.id, player_ids)
    await db.commit()
    return {"status": "ok", "count": len(body.items)}


@router.get("")
async def list_for_date(
    on: date,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All recorded availability for the caller's club on a given date."""
    res = await db.execute(
        select(PlayerAvailability).where(
            PlayerAvailability.organisation_id == club.id,
            PlayerAvailability.avail_date == on,
        )
    )
    return [
        {"player_id": str(a.player_id), "status": a.status, "note": a.note}
        for a in res.scalars().all()
    ]
