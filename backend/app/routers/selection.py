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
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Fixture, FixtureLineup, Grade, Organisation, Player, Team, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import resolve_period_statuses
from app.services.selection_pool import assemble_selection

router = APIRouter(prefix="/selection", tags=["selection"])

# Selection-pool assembly — scoring, recency wall, women's/men's gender
# wall, squad tier and per-date availability — lives in
# app/services/selection_pool.py so BetterIQ reuses the identical model.


class LineupSlot(BaseModel):
    player_id: str
    batting_order: Optional[int] = None
    is_captain: bool = False
    is_wicket_keeper: bool = False


class LineupSet(BaseModel):
    players: list[LineupSlot]


class TeamSizeSet(BaseModel):
    size: int


async def _get_owned_fixture(db: AsyncSession, fixture_id: str, club_id) -> Fixture:
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return f


@router.get("/overview")
async def selection_overview(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """All upcoming fixtures with their finalised lineups, for the matchday
    board. One row per fixture, players in batting order, each carrying their
    skill roles + per-date availability so the board can derive a health
    summary (balance / keeper / captain / flags / status) without a second
    round-trip. Declared before /{fixture_id} so 'overview' isn't read as an id.
    """
    fx_res = await db.execute(
        select(Fixture)
        .where(Fixture.organisation_id == club.id, Fixture.played_on >= date.today())
        .order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    )
    fixtures = fx_res.scalars().all()
    if not fixtures:
        return {"fixtures": [], "default_team_size": club.default_team_size}

    # Team names, to show which of our teams each fixture belongs to.
    tm_res = await db.execute(select(Team).where(Team.organisation_id == club.id))
    team_names = {str(t.id): (t.short_name or t.name) for t in tm_res.scalars().all()}

    # Grade label per fixture (drives the small grade badge).
    grade_ids = {f.grade_id for f in fixtures if f.grade_id}
    grade_names: dict[str, str] = {}
    if grade_ids:
        gr_res = await db.execute(
            select(Grade.id, Grade.display_name_override, Grade.name).where(Grade.id.in_(grade_ids))
        )
        for gid, dno, nm in gr_res.fetchall():
            grade_names[str(gid)] = dno or nm

    # Lineups for these fixtures, with player display name + roles + flags, in order.
    rows_res = await db.execute(
        select(
            FixtureLineup.fixture_id,
            FixtureLineup.batting_order,
            FixtureLineup.is_captain,
            FixtureLineup.is_wicket_keeper,
            func.coalesce(Player.display_name_override, Player.name),
            Player.id,
            Player.skill_positions,
        )
        .join(Player, FixtureLineup.player_id == Player.id)
        .where(FixtureLineup.organisation_id == club.id)
        .order_by(FixtureLineup.batting_order.asc().nullslast())
    )
    by_fixture: dict[str, list] = {}
    for fid, order, cap, wk, name, pid, skills in rows_res.fetchall():
        by_fixture.setdefault(str(fid), []).append({
            "player_id": str(pid), "display_name": name,
            "batting_order": order, "is_captain": cap, "is_wicket_keeper": wk,
            "skill_positions": skills or [],
        })

    # Availability for every fixture's playing date (explicit answer wins, then
    # the period fallback) — same resolution the builder uses, so the board's
    # health flags match what you'd see inside.
    dates = sorted({f.played_on for f in fixtures if f.played_on})
    explicit: dict[tuple[str, str], str] = {}
    period_map: dict[str, dict] = {}
    if dates:
        av_res = await db.execute(
            text(
                "SELECT player_id, avail_date, status FROM player_availability "
                "WHERE organisation_id = :org AND avail_date BETWEEN :lo AND :hi"
            ),
            {"org": club.id, "lo": dates[0], "hi": dates[-1]},
        )
        for pid, d, status in av_res.fetchall():
            explicit[(d.isoformat(), str(pid))] = status
        period_map = await resolve_period_statuses(db, club.id, dates)

    def avail_for(date_iso: str | None, pid: str) -> str:
        if not date_iso:
            return "NO_RESPONSE"
        if (date_iso, pid) in explicit:
            return explicit[(date_iso, pid)]
        info = period_map.get(date_iso, {}).get(pid)
        return info["status"] if info else "NO_RESPONSE"

    out = []
    for f in fixtures:
        date_iso = f.played_on.isoformat() if f.played_on else None
        lineup = by_fixture.get(str(f.id), [])
        for p in lineup:
            p["availability"] = avail_for(date_iso, p["player_id"])
        out.append({
            "id": str(f.id),
            "label": f.label,
            "opponent_name": f.opponent_name,
            "home_away": f.home_away,
            "played_on": date_iso,
            "start_time": f.start_time,
            "round": f.round,
            "venue": f.venue,
            "team_name": team_names.get(str(f.team_id)) if f.team_id else None,
            "grade_name": grade_names.get(str(f.grade_id)) if f.grade_id else None,
            "lineup": lineup,
        })

    return {"fixtures": out, "default_team_size": club.default_team_size}


@router.get("/selected-players")
async def selected_players(
    on: Optional[str] = None,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Player ids named in ANY saved XI for a round.

    A "round" is a Mon–Sun week. Anchor it with ?on=YYYY-MM-DD (expanded to that
    date's week) or an explicit ?from=&to= window. Powers the cross-screen
    "Selected" filter: a player counts as selected if they're picked in some XI
    that round (one XI per date is enforced on save, so it's unambiguous).
    Declared before /{fixture_id} so the literal path isn't read as an id.
    """
    if from_ and to:
        start, end = date.fromisoformat(from_), date.fromisoformat(to)
    elif on:
        anchor = date.fromisoformat(on)
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=6)
    else:
        raise HTTPException(status_code=400, detail="Provide ?on= or ?from=&to=")
    if end < start:
        start, end = end, start

    res = await db.execute(
        text(
            "SELECT DISTINCT fl.player_id FROM fixture_lineups fl "
            "JOIN fixtures f ON fl.fixture_id = f.id "
            "WHERE fl.organisation_id = :org "
            "AND ((f.played_on BETWEEN :start AND :end) "
            "OR (f.end_on BETWEEN :start AND :end))"
        ),
        {"org": club.id, "start": start, "end": end},
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "player_ids": [str(r[0]) for r in res.fetchall()],
    }


@router.get("/{fixture_id}")
async def get_selection(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A fixture's lineup + the pickable pool with per-date availability.

    Pool players carry availability for the fixture date, squads, recency
    (last_played / is_dormant), squad tier, gender wall and a form score.
    Delegates to the shared assembler so BetterIQ analyses the same pool.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)
    return await assemble_selection(db, club, fx)


@router.get("/{fixture_id}/previous-xi")
async def previous_xi(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """The most recent prior fixture's named XI, for "fill from last week".

    Looks back for the same team's last fixture (before this one's date) that has
    a saved lineup; falls back to any of the club's prior fixtures with a lineup
    if the team has no history. Returns player ids in batting order plus the
    captain/keeper, so the selection board can seed empty slots.
    """
    fx = await _get_owned_fixture(db, fixture_id, club.id)

    # Candidate prior fixtures: before this fixture's date (nulls last), newest
    # first, same team preferred. We pick the first that actually has a lineup.
    q = (
        select(Fixture)
        .where(
            Fixture.organisation_id == club.id,
            Fixture.id != fx.id,
        )
    )
    if fx.played_on:
        q = q.where(Fixture.played_on < fx.played_on)
    q = q.order_by(Fixture.played_on.desc().nullslast(), Fixture.start_time.desc().nullslast())
    prior = (await db.execute(q)).scalars().all()

    # Prefer same-team history, then anything.
    ordered = [f for f in prior if fx.team_id and f.team_id == fx.team_id] + \
              [f for f in prior if not (fx.team_id and f.team_id == fx.team_id)]

    for f in ordered:
        rows = (await db.execute(
            select(FixtureLineup).where(FixtureLineup.fixture_id == f.id)
        )).scalars().all()
        if not rows:
            continue
        rows.sort(key=lambda r: (r.batting_order or 999))
        return {
            "source_fixture_id": str(f.id),
            "source_label": f.opponent_name or f.label,
            "source_round": f.round,
            "source_date": f.played_on.isoformat() if f.played_on else None,
            "player_ids": [str(r.player_id) for r in rows],
            "captain_id": next((str(r.player_id) for r in rows if r.is_captain), None),
            "wicket_keeper_id": next((str(r.player_id) for r in rows if r.is_wicket_keeper), None),
        }

    return {"source_fixture_id": None, "player_ids": [], "captain_id": None, "wicket_keeper_id": None}


@router.post("/default-team-size")
async def set_default_team_size(
    body: TeamSizeSet,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Persist the club's default lineup size (0 = no limit). Editable here by
    selectors so the Selection format selector sticks across reloads."""
    if body.size not in (0, 11, 12, 13):
        raise HTTPException(status_code=400, detail="Invalid team size")
    club.default_team_size = body.size
    await db.commit()
    return {"status": "ok", "default_team_size": body.size}


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

        # Clash policy: a player may be in only ONE XI per date. Block the save
        # if any picked player is already selected for another fixture that day.
        # ORM .in_() (portable param binding) rather than raw ANY(array).
        if fx.played_on:
            clash_res = await db.execute(
                select(func.coalesce(Player.display_name_override, Player.name))
                .select_from(FixtureLineup)
                .join(Fixture, FixtureLineup.fixture_id == Fixture.id)
                .join(Player, FixtureLineup.player_id == Player.id)
                .where(
                    FixtureLineup.organisation_id == club.id,
                    Fixture.id != fx.id,
                    Fixture.played_on == fx.played_on,
                    FixtureLineup.player_id.in_(seen),
                )
                .distinct()
                .order_by(func.coalesce(Player.display_name_override, Player.name))
            )
            clashing = [r[0] for r in clash_res.fetchall()]
            if clashing:
                names = ", ".join(clashing)
                raise HTTPException(
                    status_code=409,
                    detail=f"Already selected for another fixture on {fx.played_on.isoformat()}: {names}",
                )

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
