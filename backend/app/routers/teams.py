"""BetterSelect — teams (Phase 1).

First-class team records. BetterStats otherwise only has team *names* as
strings on games. Teams can be auto-seeded from existing appearance data
(POST /teams/seed) and/or created and edited by hand.

Players are NOT hard-assigned to teams (club-wide model): a team groups
fixtures and, later, scopes selection — but availability is asked club-wide
and any available player can be picked for any team.
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
from app.models.db import Organisation, Team, User, get_db
from app.routers.auth import get_current_user

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


class TeamCreate(BaseModel):
    organisation_id: str
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
    org_id: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(Team).where(Team.organisation_id == uuid.UUID(org_id))
    if not include_inactive:
        stmt = stmt.where(Team.is_active.is_(True))
    stmt = stmt.order_by(Team.sequence.asc(), Team.name.asc())
    res = await db.execute(stmt)
    return [_serialize(t) for t in res.scalars().all()]


@router.post("", status_code=201)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    org = await db.get(Organisation, uuid.UUID(body.organisation_id))
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name is required")
    t = Team(
        id=uuid.uuid4(),
        organisation_id=org.id,
        name=name,
        short_name=body.short_name,
        sequence=body.sequence if body.sequence is not None else _guess_sequence(name),
        grade_id=uuid.UUID(body.grade_id) if body.grade_id else None,
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
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    t = await db.get(Team, uuid.UUID(team_id))
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    data = body.model_dump(exclude_unset=True)
    if "grade_id" in data:
        data["grade_id"] = uuid.UUID(data["grade_id"]) if data["grade_id"] else None
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
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    t = await db.get(Team, uuid.UUID(team_id))
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    await db.delete(t)
    await db.commit()


@router.post("/seed")
async def seed_teams(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Auto-seed teams from distinct team names our players have appeared for.

    Idempotent: only names not already present (case-insensitive) are added,
    as source='auto'. Existing teams are left untouched.
    """
    org_uuid = uuid.UUID(org_id)
    org = await db.get(Organisation, org_uuid)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    existing_res = await db.execute(
        select(Team.name).where(Team.organisation_id == org_uuid)
    )
    existing = {(n or "").strip().lower() for n in existing_res.scalars().all()}

    names_res = await db.execute(
        text(
            "SELECT DISTINCT ga.team_name FROM game_appearances ga "
            "JOIN players p ON ga.player_id = p.id "
            "WHERE p.organisation_id = :org AND ga.team_name IS NOT NULL "
            "AND ga.team_name <> ''"
        ),
        {"org": org_uuid},
    )
    discovered = [r[0] for r in names_res.fetchall()]

    created = 0
    for name in discovered:
        clean = (name or "").strip()
        if not clean or clean.lower() in existing:
            continue
        db.add(Team(
            id=uuid.uuid4(),
            organisation_id=org_uuid,
            name=clean,
            sequence=_guess_sequence(clean),
            source="auto",
            is_active=True,
        ))
        existing.add(clean.lower())
        created += 1

    await db.commit()
    return {"created": created, "total_discovered": len(discovered)}
