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
from app.services.side_size import effective_min
from app.services.club_match import fixture_side
from app.services.fixtures_reconcile import reconcile
from app.services.fixtures_source import org_grassroots_fixtures_checked
from app.services import squad_sides
from app.services.grade_labels import grade_is_women, org_grade_category_sets
from app.services.junior_fixtures import junior_fixture_ids

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


def _side_key_of(f: Fixture, sides: Optional[squad_sides.SquadSides]) -> Optional[str]:
    """The key of the squad's team that plays this fixture, as the edit form shows
    it: the one the club picked, else the one its grade implies."""
    if sides is None or not f.team_id:
        return None
    sq, side = sides.resolve(f.team_id, f.grade_id, f.side_key)
    return side.key if sq is not None and side is not None else None


async def _checked_side_key(db: AsyncSession, club_id, team_uuid, side_key: Optional[str]) -> Optional[str]:
    """A side key the club may put on a fixture: one of the named squad's own
    teams. Anything else is refused, not guessed."""
    if not side_key:
        return None
    if team_uuid is None:
        raise HTTPException(status_code=400, detail="Pick a squad before picking one of its teams.")
    sq = (await squad_sides.load(db, club_id)).squads.get(str(team_uuid))
    if sq is None or sq.side_for_key(side_key) is None:
        raise HTTPException(status_code=400, detail="That team is not one of this squad's teams.")
    return side_key


def _serialize(f: Fixture, teams: Optional[dict] = None, sides: Optional[squad_sides.SquadSides] = None) -> dict:
    t = (teams or {}).get(str(f.team_id)) if f.team_id else None
    # A squad that covers several teams names each fixture by its team ("2nd XI"),
    # and ranks it by that team's XI number, not by the squad's.
    team_name = t["name"] if t else None
    team_seq = t["sequence"] if t else None
    squad_name = team_name
    if sides is not None:
        named = sides.name(f.team_id, f.grade_id, f.side_key)
        if named:
            team_name = named
            squad_name = sides.squad_name(f.team_id, f.grade_id, f.side_key)
        ranked = sides.rank(f.team_id, f.grade_id, f.side_key)
        if ranked:
            team_seq = ranked
    return {
        "id": str(f.id),
        "organisation_id": str(f.organisation_id),
        "grade_id": str(f.grade_id) if f.grade_id else None,
        "team_id": str(f.team_id) if f.team_id else None,
        "side_key": _side_key_of(f, sides),
        "team_name": team_name,
        "team_short": t["short_name"] if t and team_name == t["name"] else team_name,
        "team_sequence": team_seq,
        "squad_name": squad_name,
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
    # By owning organisation id first, then by name. A first-word test alone
    # filed "North Beach v North Perth" as a HOME game for North Perth, with
    # North Perth itself as the opponent.
    side = fixture_side(club, home, away, g.get("home_org_id"), g.get("away_org_id"))
    if side == "home":
        return "HOME", away
    if side == "away":
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
    return {str(t.id): {"name": t.name, "short_name": t.short_name, "sequence": t.sequence, "size": t.default_team_size, "min": t.min_team_size} for t in res.scalars().all()}


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _match_team(our_name: Optional[str], teams: list[tuple], women: Optional[bool] = None):
    """Best-effort map a fixture's own-side team name to one of the club's teams.

    teams: list of (id, name, sequence) or (id, name, sequence, is_women), where
    ``is_women`` is True/False when the team's grade says which side it is and
    None when it has no grade. Returns a team id or None.

    Auto-seeded teams have no grade_id, so we match on the team *name* (which
    both the seed and the fixture sync derive from CA data), falling back to the
    grade number. Both steps require an unambiguous hit — never guess.

    The grade-number fallback respects the gender of the fixture's grade
    (``women``): a women's "...2nd XI" must not land on the men's second team
    because both are "2". A women's fixture needs a team known to be women's, and
    a men's one cannot take a team known to be women's.
    """
    n = _norm(our_name)
    if not n:
        return None
    teams = [t if len(t) > 3 else (*t, None) for t in teams]
    # 1. exact normalised name
    for tid, tname, _, _w in teams:
        if _norm(tname) == n:
            return tid
    # 2. grade number (e.g. "...1st Grade" -> 1), only if exactly one team ranks there
    m = re.search(r"(\d+)", n)
    if m:
        seq = int(m.group(1))
        hits = [
            tid for tid, _, tseq, tw in teams
            if tseq == seq and (women is None or (tw is True if women else tw is not True))
        ]
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
    team_id: Optional[str] = None    # which of our squads is playing
    side_key: Optional[str] = None   # which of that squad's teams ("2nd XI"), a grade key
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
    side_key: Optional[str] = None
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
    hide_juniors: bool = False,
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
    # Junior grades (per Manage Grades) can be left off the list; the default
    # keeps every fixture, as before.
    if hide_juniors and fixtures:
        junior_ids = await junior_fixture_ids(db, club.id, fixtures)
        fixtures = [f for f in fixtures if str(f.id) not in junior_ids]

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
    sides = await squad_sides.load(db, club.id)
    out = []
    for f in fixtures:
        d = _serialize(f, teams, sides)
        d["lineup_count"] = counts.get(str(f.id), 0)
        # Club lineup size (0 = no limit) so the list can derive the 3-state
        # "Completed XI" facet: none / in progress / complete.
        own = (teams.get(str(f.team_id)) or {}).get("size") if f.team_id else None
        d["format_size"] = own if own is not None else (club.default_team_size if club.default_team_size is not None else 11)
        # Fewest players the team may field, when it has a minimum below its size.
        d["format_min"] = effective_min((teams.get(str(f.team_id)) or {}).get("min"), d["format_size"]) if f.team_id else None
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
    side_key = await _checked_side_key(db, club.id, team_uuid, body.side_key)

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
        side_key=side_key,
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
    return _serialize(f, await _team_map(db, club.id), await squad_sides.load(db, club.id))


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
        # A team belongs to one squad: moving the fixture to another squad (or to
        # none) drops the old team unless a new one is named in the same request.
        if str(team_uuid) != (str(f.team_id) if f.team_id else None) and "side_key" not in data:
            data["side_key"] = None
        # Picked by hand: sync leaves a synced fixture's squad alone from now on.
        # "No team" hands the choice back to sync.
        data["team_pinned"] = team_uuid is not None
    if "side_key" in data:
        target_team = data["team_id"] if "team_id" in data else f.team_id
        data["side_key"] = await _checked_side_key(db, club.id, target_team, data["side_key"])
    for key, value in data.items():
        setattr(f, key, value)
    f.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(f)
    return _serialize(f, await _team_map(db, club.id), await squad_sides.load(db, club.id))


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
    """Make the club's synced fixtures match the Grassroots draw as it is now.

    Upserts on (organisation_id, playhq_id) so re-running is idempotent and two
    clubs that play each other keep separate rows. The Grassroots source already
    returns only upcoming/live matches dated today-or-later. (``playhq_id`` is the
    upstream match id — now the GR match GUID — kept as the column name for
    backwards compatibility, not a PlayHQ namespace anymore.)

    It also reconciles the other direction (``services/fixtures_reconcile``): a
    synced game CA no longer lists is moved onto its replacement's GUID, removed,
    or, when the club has picked an XI or collected votes on it, kept and marked
    CANCELLED. The match lists are fetched fresh (not from the 30 minute cache)
    so the button reflects the draw as it is when pressed.
    """
    games, listing = await org_grassroots_fixtures_checked(db, club, force=True)
    today = date.today()

    # Teams for name-based auto-attribution (id, name, sequence).
    tm_res = await db.execute(
        select(Team.id, Team.name, Team.sequence, Grade.fee_format, Grade.name)
        .select_from(Team).outerjoin(Grade, Team.grade_id == Grade.id)
        .where(Team.organisation_id == club.id)
    )
    grade_cats = await org_grade_category_sets(db, club.id)
    teams = [
        (tid, tname, tseq, grade_is_women(fee, gname, grade_cats) if gname else None)
        for tid, tname, tseq, fee, gname in tm_res.fetchall()
    ]

    sides = await squad_sides.load(db, club.id)
    existing_rows = list(
        (await db.execute(select(Fixture).where(Fixture.organisation_id == club.id))).scalars().all()
    )
    incoming_ids = {str(g["id"]) for g in games if g.get("id") and g.get("played_at")}
    rec = await reconcile(
        db,
        existing=existing_rows,
        games=[g for g in games if g.get("id") and g.get("played_at")],
        incoming_ids=incoming_ids,
        listing=listing,
        today=today,
        derive_sides=lambda g: _derive_sides(g, club),
    )
    by_gid = {f.playhq_id: f for f in existing_rows if f.playhq_id and f.source == "grassroots"}

    synced = 0
    teams_assigned = 0
    for g in games:
        gid = g.get("id")
        played = g.get("played_at")
        if not gid or not played:
            continue
        existing = by_gid.get(str(gid))
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
        # A two-day game: the feed lists both days. Only a later second day is
        # written; a one-day entry leaves `end_on` alone so an end date a person
        # typed on a synced game is not wiped by the next sync.
        _end = _parse_date(g.get("end_at"))
        if _end and target.played_on and _end > target.played_on:
            target.end_on = _end
        target.start_time = g.get("time")
        target.home_team = g.get("home_team")
        target.away_team = g.get("away_team")
        target.home_away = home_away
        target.opponent_name = opponent
        target.venue = g.get("venue")
        target.status = g.get("status") or "UPCOMING"
        # Auto-attribute our team by name — only when unset, so a manual
        # assignment is never overwritten by a later sync.
        # A squad the club has set up to cover this grade claims the fixture first:
        # "MACs plays the 1st and 2nd XI grades" says more than any team name.
        # A synced fixture that sits on a squad which does not play its grade (an
        # earlier name match guessed wrong, say a women's grade on the men's squad)
        # moves to the squad that does, unless someone picked it by hand.
        if target.grade_id is not None and not target.team_pinned:
            current = sides.squads.get(str(target.team_id)) if target.team_id else None
            key = sides.key_of_grade(target.grade_id)
            plays_it = current is not None and key is not None and current.side_for_key(key) is not None
            claimed = sides.squad_for_grade(target.grade_id) if (target.team_id is None or not plays_it) else None
            if claimed is not None and claimed.id != str(target.team_id):
                target.team_id = uuid.UUID(claimed.id)
                target.side_key = None
                teams_assigned += 1
        if teams and target.team_id is None:
            our_name = target.home_team if home_away == "HOME" else target.away_team if home_away == "AWAY" else None
            fx_women = grade_is_women(None, g.get("grade_name"), grade_cats) if g.get("grade_name") else None
            matched = _match_team(our_name, teams, fx_women)
            if matched:
                target.team_id = matched
                teams_assigned += 1
        if existing:
            target.updated_at = datetime.now(timezone.utc)
        else:
            db.add(target)
            by_gid[str(gid)] = target
        synced += 1

    await db.commit()

    if not synced and not rec.changed:
        return {
            "synced": 0, "teams_assigned": 0, "rekeyed": 0, "removed": 0, "cancelled": 0,
            "detail": "No upcoming Grassroots fixtures found for this club.",
        }
    detail = f"Synced {synced} fixture{'' if synced == 1 else 's'}"
    if teams_assigned:
        detail += f", auto-assigned {teams_assigned} to a team"
    elif not teams:
        detail += " — seed teams first to auto-assign them"
    n_removed = len(rec.removed)
    if n_removed:
        detail += f". Removed {n_removed} that {'is' if n_removed == 1 else 'are'} no longer on the draw"
    if rec.rekeyed:
        detail += f". Updated {len(rec.rekeyed)} that Cricket Australia re-listed"
    if rec.cancelled:
        n = len(rec.cancelled)
        detail += f". Marked {n} cancelled (you had picked a team or recorded votes, so {'it is' if n == 1 else 'they are'} kept)"
    return {
        "synced": synced,
        "teams_assigned": teams_assigned,
        "rekeyed": len(rec.rekeyed),
        "removed": n_removed,
        "cancelled": len(rec.cancelled),
        "detail": detail,
    }
