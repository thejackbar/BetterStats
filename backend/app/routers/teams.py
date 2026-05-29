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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Grade, Organisation, Season, Team, User, get_db
from app.routers.auth import get_current_club

router = APIRouter(prefix="/teams", tags=["teams"])


def _serialize(t: Team) -> dict:
    return {
        "id": str(t.id),
        "organisation_id": str(t.organisation_id),
        "name": t.name,
        "short_name": t.short_name,
        "sequence": t.sequence,
        "grade_id": str(t.grade_id) if t.grade_id else None,
        "default_formation": t.default_formation,
        "is_active": t.is_active,
        "source": t.source,
    }


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
    stmt = select(Team).where(Team.organisation_id == club.id)
    if not include_inactive:
        stmt = stmt.where(Team.is_active.is_(True))
    stmt = stmt.order_by(Team.sequence.asc(), Team.name.asc())
    res = await db.execute(stmt)
    return [_serialize(t) for t in res.scalars().all()]


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
    return _serialize(t)


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
    return _serialize(t)


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


@router.post("/seed")
async def seed_teams(
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
    """
    existing_res = await db.execute(
        select(Team.name).where(Team.organisation_id == club.id)
    )
    existing = {(n or "").strip().lower() for n in existing_res.scalars().all()}

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
