"""BetterSelect — teams (Phase 1).

First-class team records. BetterStats otherwise only has team *names* as
strings on games. Teams can be auto-seeded from existing appearance data
(POST /teams/seed) and/or created and edited by hand.

Players are NOT hard-assigned to teams (club-wide model): a team groups
fixtures and, later, scopes selection — but availability is asked club-wide
and any available player can be picked for any team.

All endpoints are scoped to the caller's club via get_current_club.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Game, GameAppearance, Grade, Organisation, Player, Season, Team, TeamMember, User, get_db
from app.routers.auth import get_current_club
from app.routers.availability import months_ago
from app.services.squad_membership import sync_squad_membership

router = APIRouter(prefix="/teams", tags=["teams"])

# Fallback squad-suggestion window (months) if the club hasn't set a dormancy
# value. Matches the availability "dormant" default.
DEFAULT_DORMANCY_MONTHS = 24


def _serialize(t: Team, grades: Optional[dict] = None) -> dict:
    return {
        "id": str(t.id),
        "organisation_id": str(t.organisation_id),
        "name": t.name,
        "short_name": t.short_name,
        "sequence": t.sequence,
        "grade_id": str(t.grade_id) if t.grade_id else None,
        "grade_name": (grades or {}).get(str(t.grade_id)) if t.grade_id else None,
        "default_formation": t.default_formation,
        "is_active": t.is_active,
        "source": t.source,
    }


async def _grade_name_map(db: AsyncSession, club_id) -> dict:
    """{grade_id_str: display_name} for grades this club's seasons own."""
    res = await db.execute(
        select(Grade.id, Grade.name, Grade.display_name_override)
        .join(Season, Grade.season_id == Season.id)
        .where(Season.organisation_id == club_id)
    )
    return {str(gid): (override or name) for gid, name, override in res.fetchall()}


async def ensure_team_grades(db: AsyncSession, club_id) -> int:
    """Auto-link teams with no grade_id to the grade they most recently played
    in (matched by team name against appearance data). Idempotent; returns how
    many were newly linked. Self-heals across seasons as new games sync.
    """
    unlinked = (await db.execute(
        select(Team).where(Team.organisation_id == club_id, Team.grade_id.is_(None))
    )).scalars().all()
    if not unlinked:
        return 0
    # Most-recent grade per team name, in one pass.
    rows = await db.execute(
        text(
            "SELECT DISTINCT ON (lower(ga.team_name)) lower(ga.team_name) AS tname, gr.id AS grade_id "
            "FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN grades gr ON g.grade_id = gr.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL AND ga.team_name <> '' "
            "ORDER BY lower(ga.team_name), g.played_at DESC NULLS LAST"
        ),
        {"org": str(club_id)},
    )
    name_to_grade = {tname: gid for tname, gid in rows.fetchall()}
    linked = 0
    for t in unlinked:
        gid = name_to_grade.get((t.name or "").strip().lower())
        if gid:
            t.grade_id = gid
            linked += 1
    if linked:
        await db.commit()
    return linked


def _guess_sequence(name: str) -> int:
    """Pull a hierarchy rank from a team name ('Applecross 2nd XI' -> 2)."""
    m = re.search(r"(\d+)", name or "")
    return int(m.group(1)) if m else 0


async def _assert_grade_in_club(db: AsyncSession, grade_id: Optional[uuid.UUID], club_id) -> None:
    if grade_id is None:
        return
    grade = await db.get(Grade, grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    season = await db.get(Season, grade.season_id)
    if not season or season.organisation_id != club_id:
        raise HTTPException(status_code=403, detail="Grade does not belong to your club")


async def _get_owned_team(db: AsyncSession, team_id: str, club_id) -> Team:
    t = await db.get(Team, uuid.UUID(team_id))
    if not t or t.organisation_id != club_id:
        raise HTTPException(status_code=404, detail="Team not found")
    return t


class TeamCreate(BaseModel):
    name: str
    short_name: Optional[str] = None
    sequence: Optional[int] = None
    grade_id: Optional[str] = None
    default_formation: Optional[str] = None
    is_active: Optional[bool] = True


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    sequence: Optional[int] = None
    grade_id: Optional[str] = None
    default_formation: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_teams(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    await ensure_team_grades(db, club.id)  # lazy auto-link so grades show here too
    stmt = select(Team).where(Team.organisation_id == club.id)
    if not include_inactive:
        stmt = stmt.where(Team.is_active.is_(True))
    stmt = stmt.order_by(Team.sequence.asc(), Team.name.asc())
    res = await db.execute(stmt)
    grades = await _grade_name_map(db, club.id)
    return [_serialize(t, grades) for t in res.scalars().all()]


@router.get("/grade-options")
async def grade_options(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """Grades from the club's most recent season(s) — to populate the team
    grade picker. Returns the latest two seasons that actually have grades."""
    seasons = (await db.execute(
        select(Season).where(Season.organisation_id == club.id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
    )).scalars().all()
    season_ids = [s.id for s in seasons]
    grades_res = await db.execute(
        select(Grade).where(Grade.season_id.in_(season_ids)).order_by(Grade.name)
    )
    by_season: dict = {}
    for g in grades_res.scalars().all():
        by_season.setdefault(str(g.season_id), []).append({"id": str(g.id), "name": g.display_name})
    out = []
    for s in seasons:
        gl = by_season.get(str(s.id))
        if gl:
            out.append({"season_id": str(s.id), "season_name": s.name, "year": s.year, "grades": gl})
        if len(out) >= 2:  # latest two seasons with grades is plenty for "current grade"
            break
    return {"seasons": out}


@router.post("", status_code=201)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")
    grade_uuid = uuid.UUID(body.grade_id) if body.grade_id else None
    await _assert_grade_in_club(db, grade_uuid, club.id)
    t = Team(
        id=uuid.uuid4(),
        organisation_id=club.id,
        name=name,
        short_name=body.short_name,
        sequence=body.sequence if body.sequence is not None else _guess_sequence(name),
        grade_id=grade_uuid,
        default_formation=body.default_formation,
        is_active=True if body.is_active is None else body.is_active,
        source="manual",
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _serialize(t, await _grade_name_map(db, club.id))


@router.patch("/{team_id}")
async def update_team(
    team_id: str,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    t = await _get_owned_team(db, team_id, club.id)
    data = body.model_dump(exclude_unset=True)
    if "grade_id" in data:
        grade_uuid = uuid.UUID(data["grade_id"]) if data["grade_id"] else None
        await _assert_grade_in_club(db, grade_uuid, club.id)
        data["grade_id"] = grade_uuid
    if data.get("name"):
        data["name"] = data["name"].strip()
    for key, value in data.items():
        setattr(t, key, value)
    t.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(t)
    return _serialize(t, await _grade_name_map(db, club.id))


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    t = await _get_owned_team(db, team_id, club.id)
    await db.delete(t)
    await db.commit()


class SeedTeamsBody(BaseModel):
    # When provided (even as an empty list), only these exact names are
    # created as squads — powers the "tick which teams to bring in" auto-seed
    # modal, which sources the list from GET /teams/seed-candidates. When
    # omitted entirely (no body sent), falls back to the original
    # single-season auto-discovery below, for backward compatibility.
    names: Optional[list[str]] = None


@router.get("/seed-candidates")
async def seed_candidates(
    seasons: int = 3,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Distinct team names our players appeared for over the last `seasons`
    seasons (default 3) — the picker behind the auto-seed modal, so an admin
    can tick which ones should become squads before anything is created.

    Each candidate reports how many of our players and games it covers, and
    whether a squad with that name already exists (so the UI can skip it).
    """
    seasons = max(1, min(int(seasons or 3), 60))

    season_rows = (await db.execute(
        select(Season.id, Season.name)
        .where(Season.organisation_id == club.id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
        .limit(seasons)
    )).all()
    season_ids = [r[0] for r in season_rows]
    season_names = [r[1] for r in season_rows]
    if not season_ids:
        return {"seasons_considered": [], "candidates": []}

    rows = (await db.execute(
        select(
            GameAppearance.team_name,
            func.count(distinct(GameAppearance.player_id)).label("players"),
            func.count().label("games"),
            func.max(Game.played_at).label("last_played"),
        )
        .join(Game, Game.id == GameAppearance.game_id)
        .join(Grade, Grade.id == Game.grade_id)
        .join(Player, Player.id == GameAppearance.player_id)
        .where(
            Player.organisation_id == club.id,
            Grade.season_id.in_(season_ids),
            GameAppearance.team_name.isnot(None),
            GameAppearance.team_name != "",
        )
        .group_by(GameAppearance.team_name)
        .order_by(func.count(distinct(GameAppearance.player_id)).desc(), func.count().desc())
    )).all()

    existing_res = await db.execute(
        select(Team.name).where(Team.organisation_id == club.id)
    )
    existing = {(n or "").strip().lower() for n in existing_res.scalars().all()}

    candidates = []
    for name, players_n, games_n, last_played in rows:
        clean = (name or "").strip()
        if not clean:
            continue
        candidates.append({
            "name": clean,
            "players": int(players_n),
            "games": int(games_n),
            "last_played": last_played.isoformat() if last_played else None,
            "exists": clean.lower() in existing,
        })

    return {"seasons_considered": season_names, "candidates": candidates}


@router.post("/seed")
async def seed_teams(
    body: Optional[SeedTeamsBody] = None,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Auto-seed teams from the team names our players appeared for in the
    most recent season (the current / upcoming season).

    Scoped to a single season so decades of historical team names don't flood
    the list. Picks the latest season (by year, then name) that actually has
    appearances. Idempotent: only names not already present (case-insensitive)
    are added, as source='auto'. Existing teams are left untouched.

    If `names` is supplied in the body (the auto-seed modal's tick-box flow),
    that exact list is created instead of re-discovering a season — the
    caller has already picked which candidates from GET /teams/seed-candidates
    it wants brought in.
    """
    existing_res = await db.execute(
        select(Team.name).where(Team.organisation_id == club.id)
    )
    existing = {(n or "").strip().lower() for n in existing_res.scalars().all()}

    if body is not None and body.names is not None:
        created = 0
        for name in body.names:
            clean = (name or "").strip()
            if not clean or clean.lower() in existing:
                continue
            db.add(Team(
                id=uuid.uuid4(),
                organisation_id=club.id,
                name=clean,
                sequence=_guess_sequence(clean),
                source="auto",
                is_active=True,
            ))
            existing.add(clean.lower())
            created += 1
        await db.commit()
        return {"created": created, "total_discovered": len(body.names), "season": None}

    # Most recent season this club has team-name appearances in.
    season_row = (await db.execute(
        text(
            "SELECT s.id, s.name FROM seasons s "
            "JOIN grades gr ON gr.season_id = s.id "
            "JOIN games g ON g.grade_id = gr.id "
            "JOIN game_appearances ga ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL "
            "AND ga.team_name <> '' "
            "GROUP BY s.id, s.name, s.year "
            "ORDER BY s.year DESC NULLS LAST, s.name DESC "
            "LIMIT 1"
        ),
        {"org": club.id},
    )).first()

    if not season_row:
        return {"created": 0, "total_discovered": 0, "season": None}

    season_id, season_name = season_row

    names_res = await db.execute(
        text(
            "SELECT DISTINCT ga.team_name FROM game_appearances ga "
            "JOIN players p ON ga.player_id = p.id "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN grades gr ON g.grade_id = gr.id "
            "WHERE p.organisation_id = :org AND gr.season_id = :season "
            "AND ga.team_name IS NOT NULL AND ga.team_name <> ''"
        ),
        {"org": club.id, "season": season_id},
    )
    discovered = [r[0] for r in names_res.fetchall()]

    created = 0
    for name in discovered:
        clean = (name or "").strip()
        if not clean or clean.lower() in existing:
            continue
        db.add(Team(
            id=uuid.uuid4(),
            organisation_id=club.id,
            name=clean,
            sequence=_guess_sequence(clean),
            source="auto",
            is_active=True,
        ))
        existing.add(clean.lower())
        created += 1

    await db.commit()
    return {"created": created, "total_discovered": len(discovered), "season": season_name}


# ─── Squad membership (manual player <-> team) ──────────────────────────────

class MemberAdd(BaseModel):
    player_id: str


@router.get("/{team_id}/members")
async def list_team_members(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
):
    """A team's squad: manually-assigned members + history-derived suggestions.

    - members: players the admin has added to this team's squad.
    - suggestions: players who appeared for this team (by name) within
      SQUAD_SUGGEST_YEARS but aren't assigned yet — "add to squad" candidates.
    """
    team = await _get_owned_team(db, team_id, club.id)

    mem_res = await db.execute(
        text(
            "SELECT tm.player_id, COALESCE(p.display_name_override, p.name) AS name, "
            "p.player_role, p.status "
            "FROM team_members tm JOIN players p ON tm.player_id = p.id "
            "WHERE tm.team_id = :tid ORDER BY name"
        ),
        {"tid": team.id},
    )
    members = [
        {"id": str(r[0]), "display_name": r[1], "player_role": r[2], "status": r[3]}
        for r in mem_res.fetchall()
    ]
    member_ids = {m["id"] for m in members}

    # Suggestions from appearance history for this team NAME, recent window only,
    # excluding anyone already assigned. Window = club dormancy setting (months).
    months = club.dormancy_months if club.dormancy_months else DEFAULT_DORMANCY_MONTHS
    cutoff = months_ago(date.today(), months)
    sug_res = await db.execute(
        text(
            "SELECT ga.player_id, COALESCE(p.display_name_override, p.name) AS name, "
            "p.player_role, MAX(g.played_at) AS last_played, COUNT(*) AS apps "
            "FROM game_appearances ga "
            "JOIN games g ON ga.game_id = g.id "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name = :tname "
            "AND g.played_at >= :cutoff "
            "GROUP BY ga.player_id, name, p.player_role "
            "ORDER BY apps DESC, name"
        ),
        {"org": club.id, "tname": team.name, "cutoff": cutoff},
    )
    suggestions = [
        {
            "id": str(r[0]),
            "display_name": r[1],
            "player_role": r[2],
            "last_played": r[3].isoformat() if r[3] else None,
            "appearances": r[4],
        }
        for r in sug_res.fetchall()
        if str(r[0]) not in member_ids
    ]

    return {"team_id": str(team.id), "team_name": team.name,
            "members": members, "suggestions": suggestions}


@router.post("/{team_id}/members", status_code=201)
async def add_team_member(
    team_id: str,
    body: MemberAdd,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    team = await _get_owned_team(db, team_id, club.id)
    pid = uuid.UUID(body.player_id)
    player = await db.get(Player, pid)
    if not player or player.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Player not found")
    existing = await db.get(TeamMember, {"team_id": team.id, "player_id": pid})
    if existing:
        return {"status": "exists"}
    db.add(TeamMember(team_id=team.id, player_id=pid,
                      organisation_id=club.id, added_by=user.id))
    await db.commit()
    return {"status": "added"}


@router.delete("/{team_id}/members/{player_id}", status_code=204)
async def remove_team_member(
    team_id: str,
    player_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    team = await _get_owned_team(db, team_id, club.id)
    tm = await db.get(TeamMember, {"team_id": team.id, "player_id": uuid.UUID(player_id)})
    if tm:
        await db.delete(tm)
        await db.commit()


# ─── Squad assignment (one selection-pool squad per player) ─────────────────
# Distinct from team_members (the multi-squad M2M kept for suggestions): this is
# the single squad that drives the Squads board and selection's "suggested
# first" ordering, stored as players.squad_team_id.

class SquadAssign(BaseModel):
    player_ids: list[str]
    squad_team_id: Optional[str] = None  # None / "" → unassign


@router.post("/squad-assign")
async def squad_assign(
    body: SquadAssign,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Set (or clear) the assigned squad for one or many players in one call.

    Powers both drag-to-reassign (one id) and bulk-add (many) on the Squads
    board. squad_team_id=None unassigns. Skips ids that aren't this club's.

    The assignment is mirrored into team_members so the "Squad" filter resolves
    to the same set on every BetterSelect screen.
    """
    target = None
    if body.squad_team_id:
        target = await _get_owned_team(db, body.squad_team_id, club.id)  # 404 if not owned

    updated = 0
    for raw in body.player_ids:
        try:
            pid = uuid.UUID(raw)
        except (ValueError, TypeError):
            continue
        player = await db.get(Player, pid)
        if not player or player.organisation_id != club.id:
            continue
        old_team_id = player.squad_team_id
        new_team_id = target.id if target else None
        player.squad_team_id = new_team_id
        await sync_squad_membership(db, club.id, pid, old_team_id, new_team_id, user.id)
        updated += 1
    await db.commit()
    return {"status": "ok", "updated": updated,
            "squad_team_id": str(target.id) if target else None}


def _later(a, b):
    """Max of two optional dates (None-safe)."""
    if a is None:
        return b
    if b is None:
        return a
    return a if a >= b else b


@router.get("/auto-assign-suggest")
async def auto_assign_suggest(
    seasons: int = 2,
    only_unassigned: bool = True,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Suggest a squad for each player from where they actually played most over
    the last `seasons` seasons. Read-only — returns a preview; the caller applies
    the accepted moves through POST /teams/squad-assign.

    Matching mirrors how squads were seeded/auto-linked:
      1. primary — the team name a player appeared for most maps to a squad by
         name (lower(game_appearances.team_name) == lower(teams.name));
      2. fallback — if that name has no squad (e.g. the squad was renamed), the
         grade they played most in maps to the squad linked to a grade of the
         same name (handles cross-season grade_id differences by grade NAME).

    `only_unassigned` (default True) restricts suggestions to players who have no
    squad yet, so existing/manual assignments are never silently overwritten.
    Players with no appearances in the window are left untouched; players whose
    top team/grade matches no squad are returned under `unmatched`.
    """
    await ensure_team_grades(db, club.id)  # make sure squads are grade-linked for the fallback
    seasons = max(1, min(int(seasons or 2), 60))

    teams = (await db.execute(
        select(Team).where(Team.organisation_id == club.id)
    )).scalars().all()
    team_by_id = {t.id: t for t in teams}
    by_lname: dict[str, Team] = {}
    for t in teams:
        by_lname.setdefault((t.name or "").strip().lower(), t)

    # Squad-by-grade-name lookup (for the rename fallback).
    grade_ids = [t.grade_id for t in teams if t.grade_id]
    grade_name_by_id: dict = {}
    if grade_ids:
        for gid, gname in (await db.execute(
            select(Grade.id, Grade.name).where(Grade.id.in_(grade_ids))
        )).all():
            grade_name_by_id[gid] = gname
    by_grade_name: dict[str, Team] = {}
    for t in teams:
        gname = grade_name_by_id.get(t.grade_id)
        if gname:
            by_grade_name.setdefault(gname.strip().lower(), t)

    # The latest `seasons` seasons this club has any record of.
    season_rows = (await db.execute(
        select(Season.id, Season.name)
        .where(Season.organisation_id == club.id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
        .limit(seasons)
    )).all()
    season_ids = [r[0] for r in season_rows]
    season_names = [r[1] for r in season_rows]
    if not season_ids:
        return {"seasons_considered": [], "suggestions": [], "unmatched": []}

    # Appearance counts per (player, team_name, grade_name) inside the window —
    # one pass; both signals accumulated in Python.
    rows = (await db.execute(
        select(
            GameAppearance.player_id,
            func.lower(GameAppearance.team_name).label("tname"),
            func.lower(Grade.name).label("gname"),
            func.count().label("games"),
            func.max(Game.played_at).label("last_played"),
        )
        .join(Game, Game.id == GameAppearance.game_id)
        .join(Grade, Grade.id == Game.grade_id)
        .join(Player, Player.id == GameAppearance.player_id)
        .where(
            Player.organisation_id == club.id,
            Grade.season_id.in_(season_ids),
            GameAppearance.team_name.isnot(None),
            GameAppearance.team_name != "",
        )
        .group_by(GameAppearance.player_id, func.lower(GameAppearance.team_name), func.lower(Grade.name))
    )).all()

    # pid -> {team_name|grade_name -> [games, last_played]}
    team_tot: dict = {}
    grade_tot: dict = {}
    for pid, tname, gname, games, last_played in rows:
        if tname:
            slot = team_tot.setdefault(pid, {}).setdefault(tname, [0, None])
            slot[0] += int(games); slot[1] = _later(slot[1], last_played)
        if gname:
            slot = grade_tot.setdefault(pid, {}).setdefault(gname, [0, None])
            slot[0] += int(games); slot[1] = _later(slot[1], last_played)

    def _top(d):
        # Most games, tie-break on most recent appearance.
        if not d:
            return None
        return max(d.items(), key=lambda kv: (kv[1][0], (kv[1][1] or date.min)))

    players = (await db.execute(
        select(Player).where(Player.organisation_id == club.id)
    )).scalars().all()

    suggestions, unmatched = [], []
    for p in players:
        if only_unassigned and p.squad_team_id is not None:
            continue
        top_team = _top(team_tot.get(p.id))
        if not top_team:
            continue  # no appearances in the window — leave untouched
        tname, (games, last_played) = top_team
        target = by_lname.get(tname)
        matched_by = "team_name"
        if not target:
            top_grade = _top(grade_tot.get(p.id))
            if top_grade:
                gname, (g_games, g_last) = top_grade
                target = by_grade_name.get(gname)
                if target:
                    matched_by, games, last_played = "grade", g_games, g_last
        if not target:
            unmatched.append({
                "player_id": str(p.id), "player_name": p.display_name,
                "top_team_name": tname, "games": int(games),
            })
            continue
        if target.id == p.squad_team_id:
            continue  # already where they belong
        cur = team_by_id.get(p.squad_team_id)
        suggestions.append({
            "player_id": str(p.id),
            "player_name": p.display_name,
            "current_team_id": str(p.squad_team_id) if p.squad_team_id else None,
            "current_team_name": cur.name if cur else None,
            "team_id": str(target.id),
            "team_name": target.name,
            "team_sequence": target.sequence or 0,
            "games": int(games),
            "matched_by": matched_by,
            "last_played": last_played.isoformat() if last_played else None,
        })

    suggestions.sort(key=lambda s: (s["team_sequence"], s["team_name"], -s["games"]))
    unmatched.sort(key=lambda u: -u["games"])
    return {
        "seasons_considered": season_names,
        "suggestions": suggestions,
        "unmatched": unmatched,
    }
