"""Roles & Activities API — the club's volunteer taxonomy (core capability,
not a paid module). Roles are shared by Volunteers and Qualifications, so role
reads/writes accept either MANAGE_VOLUNTEERS or MANAGE_QUALIFICATIONS;
Activities are volunteer-only (MANAGE_VOLUNTEERS). See services/roles_activities.py.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    User, Organisation, get_db,
    ClubRoleType, ClubRole, ClubActivityType, ClubActivity,
)
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, require_any_cap, MANAGE_VOLUNTEERS, MANAGE_QUALIFICATIONS
from app.services import roles_activities as svc

router = APIRouter(prefix="/club-admin/roles-activities", tags=["club-admin-roles-activities"])
_roles = Depends(require_any_cap(MANAGE_VOLUNTEERS, MANAGE_QUALIFICATIONS))
_acts = Depends(require_cap(MANAGE_VOLUNTEERS))


async def _or_404(db: AsyncSession, model, club: Organisation, row_id: str):
    row = await db.get(model, uuid.UUID(row_id))
    if not row or row.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Not found")
    return row


# name/title are Optional so a PATCH that only carries sort_order (drag-reorder)
# validates — creation is still guarded by the service layer, which raises
# "Name/Title is required" (→ 422) when it's missing or blank.
class TypeUpsert(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class RoleUpsert(BaseModel):
    title: Optional[str] = None
    role_type_id: Optional[str] = None
    description: Optional[str] = None
    is_committee: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ActivityUpsert(BaseModel):
    title: Optional[str] = None
    activity_type_id: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


def _uuid(v):
    return uuid.UUID(v) if v else None


# ─── Role types ──────────────────────────────────────────────────────────────
@router.get("/role-types")
async def list_role_types(include_inactive: bool = False, _: User = _roles,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await svc.list_role_types(db, club.id, include_inactive=include_inactive)
    return {"types": [svc._type_dict(t) for t in rows]}


@router.post("/role-types")
async def create_role_type(data: TypeUpsert, _: User = _roles, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    try:
        t = await svc.create_role_type(db, club.id, name=data.name, description=data.description,
                                       sort_order=data.sort_order or 0)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return svc._type_dict(t)


@router.patch("/role-types/{type_id}")
async def update_role_type(type_id: str, data: TypeUpsert, _: User = _roles,
                           club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    t = await _or_404(db, ClubRoleType, club, type_id)
    await svc.update_role_type(db, t, **data.model_dump(exclude_unset=True))
    await db.commit()
    return svc._type_dict(t)


@router.delete("/role-types/{type_id}")
async def archive_role_type(type_id: str, _: User = _roles, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    t = await _or_404(db, ClubRoleType, club, type_id)
    await svc.archive_role_type(db, t)
    await db.commit()
    return {"archived": True}


@router.post("/role-types/seed-starter")
async def seed_role_types(_: User = _roles, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_role_types(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# ─── Roles ───────────────────────────────────────────────────────────────────
@router.get("/roles")
async def list_roles(include_inactive: bool = False, committee: Optional[bool] = None, _: User = _roles,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"roles": await svc.list_roles(db, club.id, include_inactive=include_inactive, committee=committee)}


@router.post("/roles")
async def create_role(data: RoleUpsert, _: User = _roles, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    try:
        r = await svc.create_role(db, club.id, title=data.title, role_type_id=_uuid(data.role_type_id),
                                  description=data.description, is_committee=bool(data.is_committee))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return svc._role_dict(r)


@router.patch("/roles/{role_id}")
async def update_role(role_id: str, data: RoleUpsert, _: User = _roles,
                      club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    r = await _or_404(db, ClubRole, club, role_id)
    fields = data.model_dump(exclude_unset=True)
    if "role_type_id" in fields:
        fields["role_type_id"] = _uuid(fields["role_type_id"])
    await svc.update_role(db, r, **fields)
    await db.commit()
    return svc._role_dict(r)


@router.delete("/roles/{role_id}")
async def archive_role(role_id: str, _: User = _roles, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    r = await _or_404(db, ClubRole, club, role_id)
    await svc.archive_role(db, r)
    await db.commit()
    return {"archived": True}


@router.post("/roles/seed-starter")
async def seed_roles(committee: bool = False, _: User = _roles, club: Organisation = Depends(get_current_club),
                     db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_roles(db, club.id, committee=committee)
    await db.commit()
    return {"seeded": seeded}


# ─── Activity types ──────────────────────────────────────────────────────────
@router.get("/activity-types")
async def list_activity_types(include_inactive: bool = False, _: User = _acts,
                              club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await svc.list_activity_types(db, club.id, include_inactive=include_inactive)
    return {"types": [svc._type_dict(t) for t in rows]}


@router.post("/activity-types")
async def create_activity_type(data: TypeUpsert, _: User = _acts, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    try:
        t = await svc.create_activity_type(db, club.id, name=data.name, description=data.description,
                                           sort_order=data.sort_order or 0)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return svc._type_dict(t)


@router.patch("/activity-types/{type_id}")
async def update_activity_type(type_id: str, data: TypeUpsert, _: User = _acts,
                               club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    t = await _or_404(db, ClubActivityType, club, type_id)
    await svc.update_activity_type(db, t, **data.model_dump(exclude_unset=True))
    await db.commit()
    return svc._type_dict(t)


@router.delete("/activity-types/{type_id}")
async def archive_activity_type(type_id: str, _: User = _acts, club: Organisation = Depends(get_current_club),
                                db: AsyncSession = Depends(get_db)):
    t = await _or_404(db, ClubActivityType, club, type_id)
    await svc.archive_activity_type(db, t)
    await db.commit()
    return {"archived": True}


@router.post("/activity-types/seed-starter")
async def seed_activity_types(_: User = _acts, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_activity_types(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# ─── Activities ──────────────────────────────────────────────────────────────
@router.get("/activities")
async def list_activities(include_inactive: bool = False, _: User = _acts,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"activities": await svc.list_activities(db, club.id, include_inactive=include_inactive)}


@router.post("/activities")
async def create_activity(data: ActivityUpsert, _: User = _acts, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    try:
        a = await svc.create_activity(db, club.id, title=data.title,
                                      activity_type_id=_uuid(data.activity_type_id), description=data.description)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return svc._activity_dict(a)


@router.patch("/activities/{activity_id}")
async def update_activity(activity_id: str, data: ActivityUpsert, _: User = _acts,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    a = await _or_404(db, ClubActivity, club, activity_id)
    fields = data.model_dump(exclude_unset=True)
    if "activity_type_id" in fields:
        fields["activity_type_id"] = _uuid(fields["activity_type_id"])
    await svc.update_activity(db, a, **fields)
    await db.commit()
    return svc._activity_dict(a)


@router.delete("/activities/{activity_id}")
async def archive_activity(activity_id: str, _: User = _acts, club: Organisation = Depends(get_current_club),
                           db: AsyncSession = Depends(get_db)):
    a = await _or_404(db, ClubActivity, club, activity_id)
    await svc.archive_activity(db, a)
    await db.commit()
    return {"archived": True}


@router.post("/activities/seed-starter")
async def seed_activities(_: User = _acts, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    seeded = await svc.seed_starter_activities(db, club.id)
    await db.commit()
    return {"seeded": seeded}
