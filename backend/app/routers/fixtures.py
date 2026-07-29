"""BetterSelect — fixtures (Phase 0).

Persisted upcoming / scheduled fixtures: the foundation availability and team
selection build on. BetterStats otherwise stores only completed games. Two
sources:

  - 'playhq': pulled from the partner API via POST /fixtures/sync. The PlayHQ
    game GUID is stored in playhq_id (NOT the PK) so it maps to games.playhq
    while still letting two clubs that play each other keep separate rows.
  - 'manual': created by hand (POST /fixtures) so admins can build lineups and
    social posts for friendlies / pre-season without an official PlayHQ game.

All endpoints are scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import uuid
import re
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_FIXTURES, require_cap
from app.models.db import Fixture, Grade, Organisation, Season, Team, User, get_db
from app.routers.auth import get_current_club
from app.services.club_match import club_match_keys
from app.services.fixtures_source import org_grassroots_fixtures

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def _serialize(f: Fixture, teams: Optional[dict] = None) -> dict:
    t = (teams or {}).get(str(f.team_id)) if f.team_id else None
    return {
        "id": str(f.id),
        "organisation_id": str(f.organisation_id),
        "grade_id": str(f.grade_id) if f.grade_id else None,
        "team_id": str(f.team_id) if f.team_id else None,
        "team_name": t["name"] if t else None,
        "team_short": t["short_name"] if t else None,
        "team_sequence": t["sequence"] if t else None,
        "source": f.source,
        "playhq_id": f.playhq_id,
        "label": f.label,
        "round": f.round,
        "played_on": f.played_on.isoformat() if f.played_on else None,
        "end_on": f.end_on.isoformat() if f.end_on else None,
        "start_time": f.start_time,
        "home_team": f.home_team,
        "away_team": f.away_team,
        "home_away": f.home_away,
        "opponent_name": f.opponent_name,
        "venue": f.venue,
        "status": f.status,
        "notes": f.notes,
    }


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _derive_sides(g: dict, club: Organisation) -> tuple[Optional[str], Optional[str]]:
    """Best-effort (home_away, opponent_name) from the club's perspective."""
    home = g.get("home_team") or ""
    away = g.get("away_team") or ""
    keys = club_match_keys(club)
    hl, al = home.lower(), away.lower()
    if any(k in hl for k in keys):
        return "HOME", away
    if any(k in al for k in keys):
        return "AWAY", home
    return None, None


async def _assert_grade_in_club(db: AsyncSession, grade_id: Optional[uuid.UUID], club_id) -> None:
    """Reject a grade_id that belongs to another club (cross-tenant guard)."""
    if grade_id is None:
        return
    grade = await db.get(Grade, grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    season = await db.get(Season, grade.season_id)
    if not season or season.organisation_id != club_id:
        raise HTTPException(status_code=403, detail="Grade does not belong to your club")


async def _assert_team_in_club(db: AsyncSession, team_id: Optional[uuid.UUID], club_id) -> None:
    """Reject a team_id that belongs to another club (cross-tenant guard)."""
    if team_id is None:
        return
    team = await db.get(Team, team_id)
    if not team or team.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Team not found")


async def _team_map(db: AsyncSession, club_id) -> dict:
    """{team_id_str: {name, short_name}} for the club — used to enrich fixtures
    with the playing team's name without an async lazy-load on f.team."""
    res = await db.execute(select(Team).where(Team.organisation_id == club_id))
    return {str(t.id): {"name": t.name, "short_name": t.short_name, "sequence": t.sequence} for t in res.scalars().all()}


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _match_team(our_name: Optional[str], teams: list[tuple]):
    """Best-effort map a fixture's own-side team name to one of the club's teams.

    teams: list of (id, name, sequence). Returns a team id or None.

    Auto-seeded teams have no grade_id, so we match on the team *name* (which
    both the seed and the fixture sync derive from CA data), falling back to the
    grade number. Both steps require an unambiguous hit — never guess.
    """
    n = _norm(our_name)
    if not n:
        return None
    # 1. exact normalised name
    for tid, tname, _ in teams:
        if _norm(tname) == n:
            return tid
    # 2. grade number (e.g. "...1st Grade" -> 1), only if exactly one team ranks there
    m = re.search(r"(\d+)", n)
    if m:
        seq = int(m.group(1))
        hits = [tid for tid, _, tseq in teams if tseq == seq]
        if len(hits) == 1:
            return hits[0]
    return None


async def _get_owned_fixture(db: AsyncSession, fixture_id: str, club_id) -> Fixture:
    f = await db.get(Fixture, uuid.UUID(fixture_id))
    if not f or f.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return f


class FixtureCreate(BaseModel):
    label: Optional[str] = None
    opponent_name: Optional[str] = None
    home_away: Optional[str] = None  # HOME | AWAY | BYE
    grade_id: Optional[str] = None
    team_id: Optional[str] = None    # which of our teams is playing
    round: Optional[str] = None
    played_on: Optional[date] = None
    end_on: Optional[date] = None
    start_time: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = "UPCOMING"
    notes: Optional[str] = None


class FixtureUpdate(BaseModel):
    label: Optional[str] = None
    opponent_name: Optional[str] = None
    home_away: Optional[str] = None
    grade_id: Optional[str] = None
    team_id: Optional[str] = None
    round: Optional[str] = None
    played_on: Optional[date] = None
    end_on: Optional[date] = None
    start_time: Optional[str] = None
    venue: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def list_fixtures(
    upcoming_only: bool = False,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """List the caller's club fixtures, soonest first.

    Each fixture carries `lineup_count` — how many players are picked — so the
    list can show selection progress at a glance.
    """
    stmt = select(Fixture).where(Fixture.organisation_id == club.id)
    if upcoming_only:
        stmt = stmt.where(Fixture.played_on >= date.today())
    stmt = stmt.order_by(Fixture.played_on.asc().nullslast(), Fixture.start_time.asc().nullslast())
    res = await db.execute(stmt)
    fixtures = res.scalars().all()

    counts: dict[str, int] = {}
    if fixtures:
        cnt_res = await db.execute(
            text(
                "SELECT fixture_id, COUNT(*) FROM fixture_lineups "
                "WHERE organisation_id = :org GROUP BY fixture_id"
            ),
            {"org": club.id},
        )
        counts = {str(fid): n for fid, n in cnt_res.fetchall()}

    teams = await _team_map(db, club.id)
    out = []
    for f in fixtures:
        d = _serialize(f, teams)
        d["lineup_count"] = counts.get(str(f.id), 0)
        # Club lineup size (0 = no limit) so the list can derive the 3-state
        # "Completed XI" facet: none / in progress / complete.
        d["format_size"] = club.default_team_size if club.default_team_size is not None else 11
        out.append(d)
    return out


@router.post("", status_code=201)
async def create_fixture(
    body: FixtureCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    """Create a manual fixture for the caller's club (no PlayHQ game required)."""
    grade_uuid = uuid.UUID(body.grade_id) if body.grade_id else None
    await _assert_grade_in_club(db, grade_uuid, club.id)
    team_uuid = uuid.UUID(body.team_id) if body.team_id else None
    await _assert_team_in_club(db, team_uuid, club.id)

    us = club.short_name or club.name
    home_team = away_team = None
    if body.home_away == "HOME":
        home_team, away_team = us, body.opponent_name
    elif body.home_away == "AWAY":
        home_team, away_team = body.opponent_name, us

    f = Fixture(
        id=uuid.uuid4(),
        organisation_id=club.id,
        source="manual",
        grade_id=grade_uuid,
        team_id=team_uuid,
        label=body.label,
        round=body.round,
        played_on=body.played_on,
        end_on=body.end_on,
        start_time=body.start_time,
        home_team=home_team,
        away_team=away_team,
        home_away=body.home_away,
        opponent_name=body.opponent_name,
        venue=body.venue,
        status=body.status or "UPCOMING",
        notes=body.notes,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _serialize(f, await _team_map(db, club.id))


@router.patch("/{fixture_id}")
async def update_fixture(
    fixture_id: str,
    body: FixtureUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    f = await _get_owned_fixture(db, fixture_id, club.id)
    data = body.model_dump(exclude_unset=True)
    if "grade_id" in data:
        grade_uuid = uuid.UUID(data["grade_id"]) if data["grade_id"] else None
        await _assert_grade_in_club(db, grade_uuid, club.id)
        data["grade_id"] = grade_uuid
    if "team_id" in data:
        team_uuid = uuid.UUID(data["team_id"]) if data["team_id"] else None
        await _assert_team_in_club(db, team_uuid, club.id)
        data["team_id"] = team_uuid
    for key, value in data.items():
        setattr(f, key, value)
    f.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(f)
    return _serialize(f, await _team_map(db, club.id))


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    f = await _get_owned_fixture(db, fixture_id, club.id)
    await db.delete(f)
    await db.commit()


@router.post("/sync")
async def sync_fixtures(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_FIXTURES)),
):
    """Pull upcoming fixtures from the Grassroots /scores API and upsert them.

    Upserts on (organisation_id, playhq_id) so re-running is idempotent and two
    clubs that play each other keep separate rows. The Grassroots source already
    returns only upcoming/live matches dated today-or-later. (``playhq_id`` is the
    upstream match id — now the GR match GUID — kept as the column name for
    backwards compatibility, not a PlayHQ namespace anymore.)
    """
    games = await org_grassroots_fixtures(db, club)
    if not games:
        return {"synced": 0, "detail": "No upcoming Grassroots fixtures found for this club."}

    # Teams for name-based auto-attribution (id, name, sequence).
    tm_res = await db.execute(
        select(Team.id, Team.name, Team.sequence).where(Team.organisation_id == club.id)
    )
    teams = [(tid, tname, tseq) for tid, tname, tseq in tm_res.fetchall()]

    synced = 0
    teams_assigned = 0
    for g in games:
        gid = g.get("id")
        played = g.get("played_at")
        if not gid or not played:
            continue
        existing = (
            await db.execute(
                select(Fixture).where(
                    Fixture.organisation_id == club.id,
                    Fixture.playhq_id == str(gid),
                )
            )
        ).scalar_one_or_none()
        home_away, opponent = _derive_sides(g, club)
        target = existing or Fixture(id=uuid.uuid4(), organisation_id=club.id)
        target.source = "grassroots"
        target.playhq_id = str(gid)
        # Was never set here before — every synced fixture read grade_id=NULL,
        # starving any grade/team filter (e.g. BetterSelect Votes) of options.
        # See services.votes.effective_grade_ids for the read-side fallback
        # covering fixtures synced before this line existed.
        if g.get("db_grade_id"):
            try:
                target.grade_id = uuid.UUID(g["db_grade_id"])
            except ValueError:
                pass
        target.round = g.get("round")
        target.played_on = _parse_date(played)
        target.start_time = g.get("time")
        target.home_team = g.get("home_team")
        target.away_team = g.get("away_team")
        target.home_away = home_away
        target.opponent_name = opponent
        target.venue = g.get("venue")
        target.status = g.get("status") or "UPCOMING"
        # Auto-attribute our team by name — only when unset, so a manual
        # assignment is never overwritten by a later sync.
        if teams and target.team_id is None:
            our_name = target.home_team if home_away == "HOME" else target.away_team if home_away == "AWAY" else None
            matched = _match_team(our_name, teams)
            if matched:
                target.team_id = matched
                teams_assigned += 1
        if existing:
            target.updated_at = datetime.now(timezone.utc)
        else:
            db.add(target)
        synced += 1

    await db.commit()
    detail = f"Synced {synced} fixture{'' if synced == 1 else 's'}"
    if teams_assigned:
        detail += f", auto-assigned {teams_assigned} to a team"
    elif not teams:
        detail += " — seed teams first to auto-assign them"
    return {"synced": synced, "teams_assigned": teams_assigned, "detail": detail}
