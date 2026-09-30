"""BetterFootball — BetterSelect: squads, fixtures, availability, the team
sheet and the league's selection rules.

Mounted behind ``require_module("select")`` in ``afl_main.py``. Reads need a
club; writes need ``MANAGE_SELECTIONS``, the capability cricket's BetterSelect
uses, so a club's selectors hold the same permission in both sports.

See ``services/afl/select.py`` for why the side is a field of positions and
``services/afl/select_rules.py`` for the rules.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.afl import AflLineupSlot, AflSelectionRule, AflSelectionRulePlayer
from app.models.db import (
    Fixture, Grade, Organisation, Player, PlayerAvailability, PlayerAvailabilityPeriod,
    Team, TeamMember, User, get_db,
)
from app.routers.auth import get_current_club, get_current_user
from app.services.afl import select as svc
from app.services.afl import select_rules as rules_svc
from app.services.afl.grade_labels import CATEGORY_LABELS, GRADE_CATEGORIES

router = APIRouter(prefix="/afl-select", tags=["afl-select"])

AVAIL_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE", "NO_RESPONSE"}
PERIOD_STATUSES = {"AVAILABLE", "UNAVAILABLE", "MAYBE"}


def _uuid(value, what: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail=f"Invalid {what}")


async def _team_or_404(db, club, team_id) -> Team:
    t = await db.get(Team, _uuid(team_id, "team id"))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Side not found")
    return t


async def _fixture_or_404(db, club, fixture_id) -> Fixture:
    fx = await db.get(Fixture, _uuid(fixture_id, "fixture id"))
    if not fx or fx.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fx


async def _player_or_404(db, club, player_id) -> Player:
    p = await db.get(Player, _uuid(player_id, "player id"))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    return p


# ─── Sides and squads ────────────────────────────────────────────────────────

class TeamIn(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    grade_id: Optional[str] = None
    is_active: Optional[bool] = None


class ReorderIn(BaseModel):
    ids: list[str]


class SquadIn(BaseModel):
    team_id: Optional[str] = None


def _team_out(t: Team, grade: Optional[Grade] = None, count: int = 0) -> dict:
    return {"id": str(t.id), "name": t.name, "short_name": t.short_name, "sequence": t.sequence,
            "is_active": t.is_active, "source": t.source,
            "grade_id": str(t.grade_id) if t.grade_id else None,
            "grade_name": grade.name if grade else None, "squad_count": count}


@router.get("/teams")
async def list_teams(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    teams = (await db.execute(select(Team).where(Team.organisation_id == club.id)
                              .order_by(Team.sequence, Team.name))).scalars().all()
    counts = dict((await db.execute(
        select(Player.squad_team_id, func.count()).where(
            Player.organisation_id == club.id, Player.squad_team_id.isnot(None),
            Player.status != "inactive").group_by(Player.squad_team_id))).fetchall())
    grades = {g.id: g for g in (await db.execute(select(Grade).where(
        Grade.id.in_([t.grade_id for t in teams if t.grade_id])))).scalars().all()} if teams else {}
    return [_team_out(t, grades.get(t.grade_id), counts.get(t.id, 0)) for t in teams]


@router.post("/teams")
async def create_team(body: TeamIn, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="A side needs a name")
    dup = (await db.execute(select(Team).where(Team.organisation_id == club.id,
                                               func.lower(Team.name) == name.lower()))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail=f"There's already a side called {dup.name}")
    top = (await db.execute(select(func.max(Team.sequence)).where(Team.organisation_id == club.id))).scalar() or 0
    t = Team(id=uuid.uuid4(), organisation_id=club.id, name=name[:120],
             short_name=(body.short_name or "").strip()[:40] or None, sequence=top + 1, source="manual")
    if body.grade_id:
        t.grade_id = _uuid(body.grade_id, "grade id")
    db.add(t)
    await db.commit()
    return _team_out(t)


@router.patch("/teams/{team_id}")
async def update_team(team_id: str, body: TeamIn, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    t = await _team_or_404(db, club, team_id)
    sent = body.model_fields_set
    if "name" in sent:
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="A side needs a name")
        t.name = name[:120]
    if "short_name" in sent:
        t.short_name = (body.short_name or "").strip()[:40] or None
    if "grade_id" in sent:
        t.grade_id = _uuid(body.grade_id, "grade id") if body.grade_id else None
    if "is_active" in sent and body.is_active is not None:
        t.is_active = bool(body.is_active)
    await db.commit()
    return _team_out(t)


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """A deleted side's players go back to no squad (the FK is SET NULL) and
    its fixtures stop naming a side. Nothing a player did goes with it."""
    t = await _team_or_404(db, club, team_id)
    await db.delete(t)
    await db.commit()
    return {"ok": True}


@router.post("/teams/reorder")
async def reorder_teams(body: ReorderIn, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """Stamp the order by position. The order is what makes a side 'higher'
    for the rules that count games in a higher side, so the whole list is sent."""
    teams = {str(t.id): t for t in (await db.execute(select(Team).where(Team.organisation_id == club.id))).scalars().all()}
    n = 0
    for tid in body.ids:
        t = teams.get(str(tid))
        if t:
            n += 1
            t.sequence = n
    await db.commit()
    return {"ok": True}


@router.post("/teams/seed")
async def seed_teams(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club),
                     user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    res = await svc.seed_teams(db, club.id)
    await db.commit()
    return res


@router.post("/teams/auto-assign")
async def auto_assign(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    res = await svc.auto_assign(db, club.id)
    await db.commit()
    return res


@router.get("/squads")
async def list_squads(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    """Every real player with the side they are in, their positions and when
    they last played, so the board can file the unassigned ones into active,
    lapsed and never-played."""
    from app.routers.availability import DEFAULT_DORMANCY_MONTHS, months_ago
    players = (await db.execute(select(Player).where(
        Player.organisation_id == club.id, Player.is_player.is_(True),
    ).order_by(func.coalesce(Player.display_name_override, Player.name)))).scalars().all()
    rows = (await db.execute(text("""
        SELECT l.player_id, MAX(g.played_at), COUNT(*) FILTER (WHERE g.played_at >= :yr)
          FROM afl_player_game_lines l
          JOIN afl_game_details d ON d.game_id = l.game_id AND l.side = d.our_side
          JOIN games g ON g.id = l.game_id
          JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
         WHERE l.played GROUP BY l.player_id
    """), {"org": str(club.id), "yr": date(date.today().year, 1, 1)})).fetchall()
    stats = {r[0]: (r[1], r[2]) for r in rows}
    months = club.dormancy_months or DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)
    out = []
    for p in players:
        last, n = stats.get(p.id, (None, 0))
        out.append({
            "id": str(p.id), "name": p.display_name, "photo_url": p.photo_url,
            "positions": list(p.skill_positions or []), "jumper": p.shirt_number,
            "status": p.status, "squad_id": str(p.squad_team_id) if p.squad_team_id else None,
            "last_played": last.isoformat() if last else None, "games_this_year": n or 0,
            "lapsed": bool(last and last < cutoff),
        })
    return {"players": out, "dormancy_months": months}


@router.put("/squads/{player_id}")
async def set_squad(player_id: str, body: SquadIn, db: AsyncSession = Depends(get_db),
                    club: Organisation = Depends(get_current_club),
                    user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    p = await _player_or_404(db, club, player_id)
    team_id = (await _team_or_404(db, club, body.team_id)).id if body.team_id else None
    await svc.set_squad(db, club.id, p, team_id)
    await db.commit()
    return {"ok": True, "squad_id": str(team_id) if team_id else None}


# ─── Fixtures ────────────────────────────────────────────────────────────────

class FixtureIn(BaseModel):
    label: Optional[str] = None
    played_on: Optional[date] = None
    start_time: Optional[str] = None
    team_id: Optional[str] = None
    opponent_name: Optional[str] = None
    venue: Optional[str] = None
    round: Optional[str] = None
    home_away: Optional[str] = None
    is_final: Optional[bool] = None


@router.get("/fixtures")
async def list_fixtures(when: str = "upcoming", team_id: Optional[str] = None,
                        db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    q = select(Fixture).where(Fixture.organisation_id == club.id)
    today = date.today()
    if when == "past":
        q = q.where(Fixture.played_on < today).order_by(Fixture.played_on.desc()).limit(60)
    else:
        q = q.where(Fixture.played_on >= today).order_by(Fixture.played_on, Fixture.start_time)
    if team_id:
        q = q.where(Fixture.team_id == _uuid(team_id, "team id"))
    fixtures = (await db.execute(q)).scalars().all()
    teams = {t.id: t for t in (await db.execute(select(Team).where(Team.organisation_id == club.id))).scalars().all()}
    gids = [f.grade_id for f in fixtures if f.grade_id]
    grades = {g.id: g for g in (await db.execute(select(Grade).where(Grade.id.in_(gids)))).scalars().all()} if gids else {}
    picked = dict((await db.execute(select(AflLineupSlot.fixture_id, func.count()).where(
        AflLineupSlot.organisation_id == club.id, AflLineupSlot.slot != svc.EMERGENCY,
    ).group_by(AflLineupSlot.fixture_id))).fetchall())
    return {
        "fixtures": [svc.fixture_out(f, teams.get(f.team_id), grades.get(f.grade_id), picked.get(f.id, 0))
                     for f in fixtures],
        "teams": [{"id": str(t.id), "name": t.name} for t in sorted(teams.values(), key=lambda t: t.sequence or 0)],
    }


@router.post("/fixtures/sync")
async def sync_fixtures(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    res = await svc.sync_fixtures(db, club.id)
    await db.commit()
    return res


def _apply_fixture(fx: Fixture, body: FixtureIn, sent: set) -> None:
    for f in ("label", "opponent_name", "venue", "round", "start_time"):
        if f in sent:
            setattr(fx, f, (getattr(body, f) or "").strip()[:200] or None)
    if "played_on" in sent:
        fx.played_on = body.played_on
    if "home_away" in sent:
        fx.home_away = body.home_away if body.home_away in ("HOME", "AWAY") else None
    if "is_final" in sent:
        fx.is_final = body.is_final


@router.post("/fixtures")
async def create_fixture(body: FixtureIn, db: AsyncSession = Depends(get_db),
                         club: Organisation = Depends(get_current_club),
                         user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """A game PlayHQ doesn't list — a practice match, a trial, a carnival."""
    if not body.played_on:
        raise HTTPException(status_code=422, detail="A fixture needs a date")
    if not (body.label or body.opponent_name):
        raise HTTPException(status_code=422, detail="Name the fixture or the opponent")
    fx = Fixture(id=uuid.uuid4(), organisation_id=club.id, source="manual", status="UPCOMING")
    _apply_fixture(fx, body, body.model_fields_set)
    if body.team_id:
        fx.team_id = (await _team_or_404(db, club, body.team_id)).id
        team = await db.get(Team, fx.team_id)
        fx.grade_id = team.grade_id
    db.add(fx)
    await db.commit()
    return svc.fixture_out(fx)


@router.patch("/fixtures/{fixture_id}")
async def update_fixture(fixture_id: str, body: FixtureIn, db: AsyncSession = Depends(get_db),
                         club: Organisation = Depends(get_current_club),
                         user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """A synced fixture takes a side and a finals answer only — the rest is
    PlayHQ's and the next sync would put it back."""
    fx = await _fixture_or_404(db, club, fixture_id)
    sent = set(body.model_fields_set)
    if fx.source != "manual":
        sent &= {"is_final"}
    _apply_fixture(fx, body, sent)
    if "team_id" in body.model_fields_set:
        fx.team_id = (await _team_or_404(db, club, body.team_id)).id if body.team_id else None
    await db.commit()
    return svc.fixture_out(fx)


@router.delete("/fixtures/{fixture_id}")
async def delete_fixture(fixture_id: str, db: AsyncSession = Depends(get_db),
                         club: Organisation = Depends(get_current_club),
                         user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    fx = await _fixture_or_404(db, club, fixture_id)
    if fx.source != "manual":
        raise HTTPException(status_code=409, detail="A PlayHQ fixture comes back on the next sync; only a fixture added here can be deleted")
    await db.delete(fx)
    await db.commit()
    return {"ok": True}


# ─── Availability ────────────────────────────────────────────────────────────

class AvailIn(BaseModel):
    player_id: str
    date: date
    status: str
    note: Optional[str] = None


class AvailBulk(BaseModel):
    items: list[AvailIn]


class PeriodIn(BaseModel):
    player_id: str
    start_date: date
    end_date: Optional[date] = None
    status: str = "UNAVAILABLE"
    reason: Optional[str] = None


class SelfServiceIn(BaseModel):
    enabled: Optional[bool] = None
    require_pin: Optional[bool] = None


@router.get("/availability")
async def availability(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    """Players by upcoming match date. The dates are the same list the
    player's own self-service link offers, read off the one fixtures table."""
    from app.routers.availability import resolve_period_statuses, upcoming_fixtures_by_date
    by_date = await upcoming_fixtures_by_date(db, club.id)
    days = [date.fromisoformat(d) for d in by_date]
    squads = await list_squads(db, club)
    avail: dict[str, dict] = {}
    if days:
        periods = await resolve_period_statuses(db, club.id, days)
        for di, pl in periods.items():
            for pid, info in pl.items():
                avail.setdefault(pid, {})[di] = {"status": info["status"], "note": info["reason"],
                                                 "source": "period", "period_id": info["period_id"]}
        rows = (await db.execute(select(PlayerAvailability).where(
            PlayerAvailability.organisation_id == club.id, PlayerAvailability.avail_date.in_(days)))).scalars().all()
        for a in rows:
            avail.setdefault(str(a.player_id), {})[a.avail_date.isoformat()] = {
                "status": a.status, "note": a.note, "source": a.source or "admin"}
    teams = await list_teams(db, club)
    return {"dates": [{"date": d, "fixtures": by_date[d]} for d in sorted(by_date)],
            "players": squads["players"], "availability": avail, "teams": teams,
            "dormancy_months": squads["dormancy_months"]}


async def _upsert_avail(db, club, item: AvailIn, user: User, owned: set) -> None:
    if item.status not in AVAIL_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown availability")
    pid = _uuid(item.player_id, "player id")
    if pid not in owned:
        raise HTTPException(status_code=404, detail="Player not found")
    row = (await db.execute(select(PlayerAvailability).where(
        PlayerAvailability.player_id == pid, PlayerAvailability.avail_date == item.date))).scalar_one_or_none()
    if row is None:
        row = PlayerAvailability(organisation_id=club.id, player_id=pid, avail_date=item.date)
        db.add(row)
    row.status = item.status
    row.note = (item.note or "").strip()[:300] or None
    row.source = "admin"
    row.recorded_by = user.id


async def _owned(db, club) -> set:
    return set((await db.execute(select(Player.id).where(Player.organisation_id == club.id))).scalars().all())


@router.post("/availability")
async def set_availability(body: AvailIn, db: AsyncSession = Depends(get_db),
                           club: Organisation = Depends(get_current_club),
                           user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    await _upsert_avail(db, club, body, user, await _owned(db, club))
    await db.commit()
    return {"ok": True}


@router.post("/availability/bulk")
async def set_availability_bulk(body: AvailBulk, db: AsyncSession = Depends(get_db),
                                club: Organisation = Depends(get_current_club),
                                user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    owned = await _owned(db, club)
    for it in body.items[:2000]:
        await _upsert_avail(db, club, it, user, owned)
    await db.commit()
    return {"ok": True, "saved": min(len(body.items), 2000)}


@router.get("/availability/periods")
async def list_periods(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    rows = (await db.execute(select(PlayerAvailabilityPeriod).where(
        PlayerAvailabilityPeriod.organisation_id == club.id).order_by(PlayerAvailabilityPeriod.start_date.desc()))).scalars().all()
    return [{"id": r.id, "player_id": str(r.player_id), "start_date": r.start_date.isoformat(),
             "end_date": r.end_date.isoformat() if r.end_date else None, "status": r.status,
             "reason": r.reason} for r in rows]


@router.post("/availability/periods")
async def create_period(body: PeriodIn, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    if body.status not in PERIOD_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown availability")
    if body.end_date and body.end_date < body.start_date:
        raise HTTPException(status_code=422, detail="The end is before the start")
    p = await _player_or_404(db, club, body.player_id)
    row = PlayerAvailabilityPeriod(organisation_id=club.id, player_id=p.id, start_date=body.start_date,
                                   end_date=body.end_date, status=body.status,
                                   reason=(body.reason or "").strip()[:300] or None, recorded_by=user.id)
    db.add(row)
    await db.commit()
    return {"id": row.id}


@router.delete("/availability/periods/{period_id}")
async def delete_period(period_id: int, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    row = await db.get(PlayerAvailabilityPeriod, period_id)
    if not row or row.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.get("/availability/self-service")
async def get_self_service(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    from app.routers.availability import _self_service_payload
    return await _self_service_payload(db, club)


@router.post("/availability/self-service")
async def update_self_service(body: SelfServiceIn, db: AsyncSession = Depends(get_db),
                              club: Organisation = Depends(get_current_club),
                              user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """The player's own link, shared with cricket's page and its PIN rules."""
    from app.routers.availability import SelfServiceUpdate, update_self_service as upd
    return await upd(SelfServiceUpdate(**body.model_dump(exclude_unset=True)), db=db, club=club, user=user)


@router.post("/availability/self-service/regenerate")
async def regenerate_self_service(db: AsyncSession = Depends(get_db),
                                  club: Organisation = Depends(get_current_club),
                                  user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    from app.routers.availability import regenerate_self_service as regen
    return await regen(db=db, club=club, user=user)


# ─── The team sheet ──────────────────────────────────────────────────────────

class SlotIn(BaseModel):
    player_id: str
    slot: str
    sort_order: Optional[int] = None
    is_captain: bool = False
    is_vice_captain: bool = False


class LineupIn(BaseModel):
    items: list[SlotIn]


@router.get("/fixtures/{fixture_id}/selection")
async def get_selection(fixture_id: str, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club)):
    fx = await _fixture_or_404(db, club, fixture_id)
    return await svc.selection(db, club, fx)


@router.put("/fixtures/{fixture_id}/lineup")
async def save_lineup(fixture_id: str, body: LineupIn, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """Replace the side for a fixture. A rule the club marked as blocking
    refuses the save with the reasons; a warning is the selector's to weigh,
    and the board asks before it sends."""
    fx = await _fixture_or_404(db, club, fixture_id)
    facts = await svc.fixture_facts(db, club.id, fx)
    players = (await db.execute(select(Player).where(Player.organisation_id == club.id))).scalars().all()
    owned = {str(p.id) for p in players}
    ids = [it.player_id for it in body.items]
    picked = [p for p in players if str(p.id) in set(ids)]
    result = await rules_svc.evaluate(db, club, facts, picked)
    try:
        rows = svc.validate_lineup([it.model_dump() for it in body.items], result.team_size, owned)
    except svc.LineupError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    playing = [r["player_id"] for r in rows if r["slot"] != svc.EMERGENCY]
    blocked = result.blocking(playing, {str(p.id): p.display_name for p in picked})
    if blocked:
        raise HTTPException(status_code=422, detail={"message": "This side breaks a rule the club enforces",
                                                     "reasons": blocked})
    await db.execute(delete(AflLineupSlot).where(AflLineupSlot.fixture_id == fx.id))
    for r in rows:
        db.add(AflLineupSlot(fixture_id=fx.id, player_id=uuid.UUID(r["player_id"]), organisation_id=club.id,
                             slot=r["slot"], sort_order=r["sort_order"], is_captain=r["is_captain"],
                             is_vice_captain=r["is_vice_captain"], selected_by=user.id))
    await db.commit()
    return {"ok": True, "saved": len(rows)}


@router.get("/fixtures/{fixture_id}/previous")
async def previous_side(fixture_id: str, db: AsyncSession = Depends(get_db),
                        club: Organisation = Depends(get_current_club)):
    fx = await _fixture_or_404(db, club, fixture_id)
    return {"lineup": await svc.previous_lineup(db, club.id, fx)}


@router.get("/fixtures/{fixture_id}/team-sheet")
async def team_sheet(fixture_id: str, db: AsyncSession = Depends(get_db),
                     club: Organisation = Depends(get_current_club)):
    fx = await _fixture_or_404(db, club, fixture_id)
    data = await svc.selection(db, club, fx)
    names = {p["id"]: p["name"] for p in data["players"]}
    return {"text": svc.team_sheet(data["fixture"], data["lineup"], names, data["team_size"])}


# ─── Rules ───────────────────────────────────────────────────────────────────

class RuleIn(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    severity: Optional[str] = None
    scope: Optional[dict] = None
    config: Optional[dict] = None
    enabled: Optional[bool] = None


class RulePlayerIn(BaseModel):
    player_id: str
    mode: str
    incident_date: Optional[date] = None
    note: Optional[str] = None


async def _rule_or_404(db, club, rule_id) -> AflSelectionRule:
    r = await db.get(AflSelectionRule, _uuid(rule_id, "rule id"))
    if not r or r.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Rule not found")
    return r


async def _rules_payload(db, club) -> dict:
    rows = await rules_svc.list_rules(db, club.id)
    marks = await rules_svc.rule_players(db, club.id)
    pids = {m.player_id for ms in marks.values() for m in ms}
    names = {p.id: p.display_name for p in (await db.execute(select(Player).where(Player.id.in_(pids)))).scalars().all()} if pids else {}
    grades = (await db.execute(text("""
        SELECT DISTINCT gr.name FROM grades gr JOIN seasons s ON s.id = gr.season_id
         WHERE s.organisation_id = :org AND s.year >= (
            SELECT COALESCE(MAX(year), 0) - 1 FROM seasons WHERE organisation_id = :org)
         ORDER BY gr.name
    """), {"org": str(club.id)})).scalars().all()
    teams = await list_teams(db, club)
    return {
        "rules": [rules_svc.rule_out(r, [
            {"id": str(m.id), "player_id": str(m.player_id), "name": names.get(m.player_id, ""),
             "mode": m.mode, "incident_date": m.incident_date.isoformat() if m.incident_date else None,
             "note": m.note} for m in marks.get(str(r.id), [])]) for r in rows],
        "kinds": [{"kind": k, **v} for k, v in rules_svc.RULE_KINDS.items()],
        "grades": list(grades),
        "categories": [{"key": c, "label": CATEGORY_LABELS[c]} for c in GRADE_CATEGORIES],
        "teams": [{"id": t["id"], "name": t["name"]} for t in teams],
    }


@router.get("/rules")
async def list_rules(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club)):
    return await _rules_payload(db, club)


@router.post("/rules")
async def create_rule(body: RuleIn, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    if body.kind not in rules_svc.RULE_KINDS:
        raise HTTPException(status_code=422, detail="Unknown kind of rule")
    top = (await db.execute(select(func.max(AflSelectionRule.sort_order)).where(
        AflSelectionRule.organisation_id == club.id))).scalar() or 0
    r = AflSelectionRule(id=uuid.uuid4(), organisation_id=club.id, kind=body.kind,
                         name=(body.name or "").strip()[:120] or None,
                         severity=rules_svc.clean_severity(body.kind, body.severity),
                         scope=rules_svc.clean_scope(body.scope), config=rules_svc.clean_config(body.kind, body.config),
                         enabled=body.enabled is not False, sort_order=top + 1)
    db.add(r)
    await db.commit()
    return rules_svc.rule_out(r)


@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleIn, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    r = await _rule_or_404(db, club, rule_id)
    sent = body.model_fields_set
    if "name" in sent:
        r.name = (body.name or "").strip()[:120] or None
    if "severity" in sent:
        r.severity = rules_svc.clean_severity(r.kind, body.severity)
    if "scope" in sent:
        r.scope = rules_svc.clean_scope(body.scope)
    if "config" in sent:
        r.config = rules_svc.clean_config(r.kind, body.config)
    if "enabled" in sent and body.enabled is not None:
        r.enabled = bool(body.enabled)
    await db.commit()
    return rules_svc.rule_out(r)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db),
                      club: Organisation = Depends(get_current_club),
                      user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    r = await _rule_or_404(db, club, rule_id)
    await db.delete(r)
    await db.commit()
    return {"ok": True}


@router.post("/rules/{rule_id}/players")
async def add_rule_player(rule_id: str, body: RulePlayerIn, db: AsyncSession = Depends(get_db),
                          club: Organisation = Depends(get_current_club),
                          user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    r = await _rule_or_404(db, club, rule_id)
    if body.mode not in rules_svc.MODES:
        raise HTTPException(status_code=422, detail="Unknown kind of entry")
    if body.mode == "incident" and not body.incident_date:
        raise HTTPException(status_code=422, detail="Give the date it happened")
    p = await _player_or_404(db, club, body.player_id)
    m = AflSelectionRulePlayer(id=uuid.uuid4(), rule_id=r.id, player_id=p.id, organisation_id=club.id,
                               mode=body.mode, incident_date=body.incident_date if body.mode == "incident" else None,
                               note=(body.note or "").strip()[:300] or None)
    db.add(m)
    await db.commit()
    return {"id": str(m.id)}


@router.delete("/rules/{rule_id}/players/{mark_id}")
async def delete_rule_player(rule_id: str, mark_id: str, db: AsyncSession = Depends(get_db),
                             club: Organisation = Depends(get_current_club),
                             user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    m = await db.get(AflSelectionRulePlayer, _uuid(mark_id, "entry id"))
    if not m or m.organisation_id != club.id or str(m.rule_id) != str(_uuid(rule_id, "rule id")):
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


@router.post("/rules/starter")
async def starter_rules(db: AsyncSession = Depends(get_db), club: Organisation = Depends(get_current_club),
                        user: User = Depends(require_cap(MANAGE_SELECTIONS))):
    """The two rules every football club runs under: a senior team size
    (18 on the ground, up to 10 on the bench, 3 emergencies) and the AFL
    community concussion stand-down of 21 days. Skip-don't-replace: a kind the
    club already has is left alone, so pressing it twice changes nothing.
    Everything else needs the league's own numbers, and a number made up here
    would be quoted back at us."""
    have = {r.kind for r in await rules_svc.list_rules(db, club.id)}
    added = []
    top = (await db.execute(select(func.max(AflSelectionRule.sort_order)).where(
        AflSelectionRule.organisation_id == club.id))).scalar() or 0
    for kind, severity, cfg in (("team_size", "info", {}), ("concussion", "block", {})):
        if kind in have:
            continue
        top += 1
        db.add(AflSelectionRule(id=uuid.uuid4(), organisation_id=club.id, kind=kind, severity=severity,
                                scope={}, config=rules_svc.clean_config(kind, cfg), enabled=True, sort_order=top))
        added.append(kind)
    await db.commit()
    return {"added": added}
