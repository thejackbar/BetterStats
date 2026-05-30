"""BetterSelect — availability (Phase 2).

Admin-recorded player availability, keyed on (player, playing-date). One answer
for a date covers every fixture that day. The matrix is all active players x
playing dates; a two-day game contributes both its dates (week 1 = played_on,
week 2 = end_on). No player-facing input — recorded_by/at track the admin.

All endpoints are scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import (
    Fixture, PlayerAvailability, PlayerAvailabilityPeriod, Organisation, Player, User, get_db,
)
from app.routers.auth import get_current_club

router = APIRouter(prefix="/availability", tags=["availability"])

VALID_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}
# A period asserts a state, so NO_RESPONSE (the absence of an answer) isn't valid.
PERIOD_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE"}

# Fallback dormancy window (months) if a club hasn't set one. A player who last
# appeared more than this long ago is "dormant": surfaced behind a toggle so
# selection works off the current squad, not the entire historical roster.
# Distinct from the manual status='inactive' flag.
DEFAULT_DORMANCY_MONTHS = 24


def months_ago(d: date, months: int) -> date:
    """The date `months` calendar months before `d`, clamped to month length
    (e.g. 31 Mar minus 1 month -> 28/29 Feb). Avoids a python-dateutil dep."""
    total = (d.year * 12 + (d.month - 1)) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class AvailabilitySet(BaseModel):
    player_id: str
    date: date
    status: str
    note: Optional[str] = None


class AvailabilityBulk(BaseModel):
    items: list[AvailabilitySet]


class PeriodCreate(BaseModel):
    player_id: str
    start_date: date
    end_date: Optional[date] = None  # None = open-ended
    status: str = "UNAVAILABLE"
    reason: Optional[str] = None


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


async def resolve_period_statuses(
    db: AsyncSession, club_id, dates: list[date],
) -> dict[str, dict[str, dict]]:
    """{date_iso: {player_id_str: {status, reason, period_id, start, end}}} from
    covering availability periods.

    When several periods overlap a date, the most recently-starting one wins
    (tie-break: later created_at). Callers layer explicit per-date availability
    rows on top — an explicit answer always takes precedence over a period.
    """
    if not dates:
        return {}
    dmin, dmax = min(dates), max(dates)
    res = await db.execute(
        select(PlayerAvailabilityPeriod)
        .where(
            PlayerAvailabilityPeriod.organisation_id == club_id,
            PlayerAvailabilityPeriod.start_date <= dmax,
            or_(
                PlayerAvailabilityPeriod.end_date.is_(None),
                PlayerAvailabilityPeriod.end_date >= dmin,
            ),
        )
        .order_by(
            PlayerAvailabilityPeriod.start_date.asc(),
            PlayerAvailabilityPeriod.created_at.asc(),
        )
    )
    periods = res.scalars().all()
    out: dict[str, dict[str, dict]] = {}
    for d in dates:
        di = d.isoformat()
        for p in periods:
            if p.start_date <= d and (p.end_date is None or p.end_date >= d):
                # asc order => the last matching write wins (most recent period).
                out.setdefault(di, {})[str(p.player_id)] = {
                    "status": p.status,
                    "reason": p.reason,
                    "period_id": p.id,
                    "start": p.start_date.isoformat(),
                    "end": p.end_date.isoformat() if p.end_date else None,
                }
    return out


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
    # "dormant" = has played before but not within the club's dormancy window —
    # the auto-archive bucket (KlubPro-style) so selection works off current
    # players. Window is the club setting (months), defaulting to 24.
    months = club.dormancy_months if club.dormancy_months else DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)

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

    # Manual squad assignments (team_members) — the admin's source of truth —
    # unioned in so the squad filter reflects hand-picked members too, not just
    # recent appearance history.
    mem_res = await db.execute(
        text(
            "SELECT tm.player_id, t.name FROM team_members tm "
            "JOIN teams t ON tm.team_id = t.id "
            "WHERE tm.organisation_id = :org AND t.name IS NOT NULL AND t.name <> ''"
        ),
        {"org": club.id},
    )
    for pid, name in mem_res.fetchall():
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
                "source": "manual",
            }

        # Layer covering availability periods UNDER the explicit answers above: a
        # period supplies a date's status only where no per-date row exists.
        # Period-derived cells carry source='period' + reason/range so the UI can
        # mark them distinctly (and a click still writes an explicit override).
        period_map = await resolve_period_statuses(
            db, club.id, [date.fromisoformat(d) for d in date_keys]
        )
        for di, players_d in period_map.items():
            for pid, info in players_d.items():
                if avail_map.get(pid, {}).get(di) is not None:
                    continue  # explicit answer wins
                avail_map.setdefault(pid, {})[di] = {
                    "status": info["status"],
                    "note": info["reason"],
                    "source": "period",
                    "reason": info["reason"],
                    "period_start": info["start"],
                    "period_end": info["end"],
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
        "dormancy_months": months,
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
        "photo_url": p.photo_url,
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
    """All recorded availability for the caller's club on a given date —
    explicit per-date answers plus any covering period (explicit wins)."""
    res = await db.execute(
        select(PlayerAvailability).where(
            PlayerAvailability.organisation_id == club.id,
            PlayerAvailability.avail_date == on,
        )
    )
    rows = res.scalars().all()
    out = [
        {"player_id": str(a.player_id), "status": a.status, "note": a.note, "source": "manual"}
        for a in rows
    ]
    seen = {str(a.player_id) for a in rows}
    period_map = await resolve_period_statuses(db, club.id, [on])
    for pid, info in period_map.get(on.isoformat(), {}).items():
        if pid in seen:
            continue
        out.append({
            "player_id": pid,
            "status": info["status"],
            "note": info["reason"],
            "source": "period",
            "reason": info["reason"],
            "period_start": info["start"],
            "period_end": info["end"],
        })
    return out


@router.get("/periods")
async def list_periods(
    include_past: bool = False,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Availability periods for the club. Active/upcoming only by default; pass
    include_past=true for the full history."""
    name_col = func.coalesce(Player.display_name_override, Player.name)
    q = (
        select(PlayerAvailabilityPeriod, name_col)
        .join(Player, Player.id == PlayerAvailabilityPeriod.player_id)
        .where(PlayerAvailabilityPeriod.organisation_id == club.id)
    )
    if not include_past:
        q = q.where(or_(
            PlayerAvailabilityPeriod.end_date.is_(None),
            PlayerAvailabilityPeriod.end_date >= date.today(),
        ))
    q = q.order_by(PlayerAvailabilityPeriod.start_date.asc(), name_col.asc())
    res = await db.execute(q)
    return [
        {
            "id": p.id,
            "player_id": str(p.player_id),
            "player_name": name,
            "start_date": p.start_date.isoformat(),
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "status": p.status,
            "reason": p.reason,
        }
        for p, name in res.all()
    ]


@router.post("/periods")
async def create_period(
    body: PeriodCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    if body.status not in PERIOD_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    if body.end_date and body.end_date < body.start_date:
        raise HTTPException(status_code=400, detail="End date is before start date")
    try:
        pid = uuid.UUID(body.player_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid player_id")
    if pid not in await _owned_player_ids(db, club.id):
        raise HTTPException(status_code=404, detail="Player not found")
    period = PlayerAvailabilityPeriod(
        organisation_id=club.id,
        player_id=pid,
        start_date=body.start_date,
        end_date=body.end_date,
        status=body.status,
        reason=(body.reason or "").strip() or None,
        recorded_by=user.id,
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)
    return {"status": "ok", "id": period.id}


@router.delete("/periods/{period_id}")
async def delete_period(
    period_id: int,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    res = await db.execute(
        select(PlayerAvailabilityPeriod).where(
            PlayerAvailabilityPeriod.id == period_id,
            PlayerAvailabilityPeriod.organisation_id == club.id,  # cross-tenant guard
        )
    )
    period = res.scalar_one_or_none()
    if not period:
        raise HTTPException(status_code=404, detail="Period not found")
    await db.delete(period)
    await db.commit()
    return {"status": "ok"}
