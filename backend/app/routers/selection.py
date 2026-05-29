"""BetterSelect Phase 3 — team selection (lineups).

Pick a side for a fixture from the available pool. The pool is the club's
players annotated with their availability for THAT fixture's playing date
(availability is keyed on date, so one answer covers every fixture that day),
plus squad membership and the dormancy/recency signal the availability matrix
already computes.

Lineups are per-fixture: the same player can be selected for two fixtures on
the same weekend (the shared-player split case). Whether that's allowed/warned
is a rule layer that reads these rows — the storage itself doesn't constrain it.

All endpoints scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, FixtureLineup, Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import DEFAULT_DORMANCY_MONTHS, months_ago

router = APIRouter(prefix="/selection", tags=["selection"])


class LineupSlot(BaseModel):
    player_id: str
    batting_order: Optional[int] = None
    is_captain: bool = False
    is_wicket_keeper: bool = False


class LineupSet(BaseModel):
    players: list[LineupSlot]


async def _get_owned_fixture(db: AsyncSession, fixture_id: str, club_id) -> Fixture:
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return f


@router.get("/{fixture_id}")
async def get_selection(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A fixture's lineup + the pickable pool with per-date availability.

    Pool players carry: availability status for the fixture date, squads (manual
    + recent history), recency (last_played / is_dormant), and whether they're
    already in the lineup. The frontend builds the selection board from this.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Existing lineup for this fixture.
    lu_res = await db.execute(
        select(FixtureLineup).where(FixtureLineup.fixture_id == fx.id)
    )
    lineup_rows = lu_res.scalars().all()
    lineup = {str(r.player_id): r for r in lineup_rows}

    months = club.dormancy_months if club.dormancy_months else DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)

    # last_played per player (recency).
    last_played: dict[str, date] = {}
    lp_res = await db.execute(
        text(
            "SELECT ga.player_id, MAX(g.played_at) FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org GROUP BY ga.player_id"
        ),
        {"org": club.id},
    )
    for pid, lp in lp_res.fetchall():
        last_played[str(pid)] = lp

    # Squads: manual membership unioned with recent appearance team-names.
    squads: dict[str, set] = {}
    sq_res = await db.execute(
        text(
            "SELECT DISTINCT ga.player_id, ga.team_name FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL "
            "AND ga.team_name <> '' AND g.played_at >= :cutoff"
        ),
        {"org": club.id, "cutoff": cutoff},
    )
    for pid, name in sq_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())
    mem_res = await db.execute(
        text(
            "SELECT tm.player_id, t.name FROM team_members tm "
            "JOIN teams t ON tm.team_id = t.id "
            "WHERE tm.organisation_id = :org AND t.name IS NOT NULL AND t.name <> ''"
        ),
        {"org": club.id},
    )
    for pid, name in mem_res.fetchall():
        squads.setdefault(str(pid), set()).add(name.strip())

    # Availability for this fixture's playing date(s). Availability is keyed on
    # date; the relevant answer is for played_on (week 1). One row per player.
    avail: dict[str, str] = {}
    if fx.played_on:
        av_res = await db.execute(
            text(
                "SELECT player_id, status FROM player_availability "
                "WHERE organisation_id = :org AND avail_date = :d"
            ),
            {"org": club.id, "d": fx.played_on},
        )
        for pid, status in av_res.fetchall():
            avail[str(pid)] = status

    # Players also already selected for ANOTHER fixture on the same date —
    # surfaced so the UI can flag a clash (rule layer decides if it's allowed).
    clash: dict[str, list] = {}
    if fx.played_on:
        cl_res = await db.execute(
            text(
                "SELECT fl.player_id, COALESCE(t.name, f.label, f.opponent_name) AS where_ "
                "FROM fixture_lineups fl "
                "JOIN fixtures f ON fl.fixture_id = f.id "
                "LEFT JOIN teams t ON f.team_id = t.id "
                "WHERE fl.organisation_id = :org AND f.id <> :fid "
                "AND f.played_on = :d"
            ),
            {"org": club.id, "fid": fx.id, "d": fx.played_on},
        )
        for pid, where_ in cl_res.fetchall():
            clash.setdefault(str(pid), []).append(where_ or "another fixture")

    pl_res = await db.execute(
        select(Player).where(
            Player.organisation_id == club.id,
            Player.is_player.is_(True),
        )
    )
    players = pl_res.scalars().all()

    pool = []
    for p in players:
        pid = str(p.id)
        lp = last_played.get(pid)
        dormant = bool(lp) and lp < cutoff
        manual_inactive = p.status == "inactive"
        pool.append({
            "id": pid,
            "display_name": p.display_name,
            "player_role": p.player_role,
            "skill_positions": p.skill_positions or [],
            "squads": sorted(squads.get(pid, [])),
            "availability": avail.get(pid, "NO_RESPONSE"),
            "last_played": lp.isoformat() if lp else None,
            "is_dormant": dormant and not manual_inactive,
            "is_inactive": manual_inactive,
            "is_current": not manual_inactive and not dormant,
            "selected": pid in lineup,
            "clash": clash.get(pid, []),
        })

    return {
        "fixture": {
            "id": str(fx.id),
            "label": fx.label,
            "opponent_name": fx.opponent_name,
            "home_away": fx.home_away,
            "played_on": fx.played_on.isoformat() if fx.played_on else None,
            "team_id": str(fx.team_id) if fx.team_id else None,
        },
        "lineup": [
            {
                "player_id": str(r.player_id),
                "batting_order": r.batting_order,
                "is_captain": r.is_captain,
                "is_wicket_keeper": r.is_wicket_keeper,
            }
            for r in sorted(lineup_rows, key=lambda r: (r.batting_order or 999))
        ],
        "pool": pool,
        "dormancy_months": months,
    }


@router.put("/{fixture_id}")
async def set_selection(
    fixture_id: str,
    body: LineupSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Replace a fixture's lineup with the given set of players.

    Full-replace (not incremental): the selection board sends the whole side.
    Validates players belong to the club; de-dupes; clamps roles. Cross-fixture
    clash is reported by GET but NOT blocked here — that policy is deferred.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Validate + de-dupe incoming player ids.
    seen: set[uuid.UUID] = set()
    slots: list[LineupSlot] = []
    for s in body.players:
        pid = uuid.UUID(s.player_id)
        if pid in seen:
            continue
        seen.add(pid)
        slots.append(s)

    if seen:
        owned_res = await db.execute(
            select(Player.id).where(
                Player.organisation_id == club.id,
                Player.id.in_(seen),
            )
        )
        owned = {r[0] for r in owned_res.fetchall()}
        missing = seen - owned
        if missing:
            raise HTTPException(status_code=400, detail="One or more players are not in your club")

    # Replace: clear existing rows, insert the new set.
    await db.execute(
        text("DELETE FROM fixture_lineups WHERE fixture_id = :fid"),
        {"fid": fx.id},
    )
    for s in slots:
        db.add(FixtureLineup(
            fixture_id=fx.id,
            player_id=uuid.UUID(s.player_id),
            organisation_id=club.id,
            batting_order=s.batting_order,
            is_captain=bool(s.is_captain),
            is_wicket_keeper=bool(s.is_wicket_keeper),
            selected_by=user.id,
        ))
    await db.commit()
    return {"status": "ok", "count": len(slots)}
