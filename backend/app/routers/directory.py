"""BetterClubManager Directory API — the club's people (core capability, not a
paid module). Players are owned by Stats/Core; this owns the non-player side:
add/edit/archive non-playing members + third parties, and assign roles to any
person. Gated on MANAGE_MEMBERS for writes; reads allow any of the ClubManager
people capabilities so the Directory opens for volunteer/committee/qual managers
too. See services/directory.py.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import (
    require_cap, require_any_cap,
    MANAGE_MEMBERS, MANAGE_VOLUNTEERS, MANAGE_COMMITTEE, MANAGE_QUALIFICATIONS, MANAGE_FEES,
)
from app.services import directory as svc
from app.services import members as members_svc
from app.services import member_import as import_svc

router = APIRouter(prefix="/club-admin/directory", tags=["club-admin-directory"])
_read = Depends(require_any_cap(MANAGE_MEMBERS, MANAGE_VOLUNTEERS, MANAGE_COMMITTEE, MANAGE_QUALIFICATIONS))
_write = Depends(require_cap(MANAGE_MEMBERS))
# Importing people is a shared action — a BetterFees admin can bring in members too.
_import = Depends(require_any_cap(MANAGE_MEMBERS, MANAGE_FEES))


def _uuid(v):
    return uuid.UUID(v) if v else None


class MemberUpsert(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    member_category: Optional[str] = None
    notes: Optional[str] = None


class RoleBody(BaseModel):
    role_id: str


@router.get("/people")
async def list_people(_: User = _read, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"people": await svc.list_people(db, club.id), "categories": members_svc.MEMBER_CATEGORIES}


@router.post("/people")
async def create_member(data: MemberUpsert, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        mid = await members_svc.create_person(db, club.id, full_name=data.full_name, email=data.email,
                                               mobile=data.mobile, member_category=data.member_category, notes=data.notes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"member_id": mid}


@router.patch("/people/{member_id}")
async def update_member(member_id: str, data: MemberUpsert, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await members_svc.update_person(db, club.id, _uuid(member_id), **data.model_dump(exclude_unset=True))
    await db.commit()
    return {"ok": True}


@router.post("/people/{member_id}/archive")
async def archive_member(member_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await members_svc.set_archived(db, club.id, _uuid(member_id), True)
    await db.commit()
    return {"ok": True}


@router.post("/people/{member_id}/restore")
async def restore_member(member_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await members_svc.set_archived(db, club.id, _uuid(member_id), False)
    await db.commit()
    return {"ok": True}


@router.post("/players/{player_id}/ensure-member")
async def ensure_member(player_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Create (or find) the fee_members row for a Stats-owned player so it can be
    assigned ClubManager roles/quals. Idempotent."""
    try:
        mid = await members_svc.ensure_for_player(db, club.id, _uuid(player_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"member_id": mid}


@router.post("/people/{member_id}/roles")
async def add_role(member_id: str, data: RoleBody, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    try:
        await svc.add_role(db, club.id, _uuid(member_id), _uuid(data.role_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"ok": True}


@router.delete("/people/{member_id}/roles/{role_id}")
async def remove_role(member_id: str, role_id: str, _: User = _write, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    await svc.remove_role(db, club.id, _uuid(member_id), _uuid(role_id))
    await db.commit()
    return {"ok": True}


# ── shared non-player CSV import (also used by BetterFees Members) ────────────
class ImportBody(BaseModel):
    csv: str


@router.post("/import/preview")
async def import_preview(data: ImportBody, _: User = _import, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return await import_svc.preview(db, club.id, data.csv)


@router.post("/import/commit")
async def import_commit(data: ImportBody, _: User = _import, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    result = await import_svc.commit(db, club.id, data.csv)
    await db.commit()
    return result
