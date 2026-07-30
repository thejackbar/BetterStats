"""Volunteer Management API — profiles, availability, an hours ledger.

Core capability (MANAGE_VOLUNTEERS), not a paid module — see services/volunteers.py.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, FeeMember, VolunteerHours, get_db
from app.routers.auth import get_current_user, get_current_club
from app.auth.capabilities import require_cap, MANAGE_VOLUNTEERS
from app.services import volunteers as volunteers_service

router = APIRouter(prefix="/club-admin/volunteers", tags=["club-admin-volunteers"])
_require = Depends(require_cap(MANAGE_VOLUNTEERS))


async def _member_or_404(db: AsyncSession, club: Organisation, member_id: str) -> FeeMember:
    m = await db.get(FeeMember, uuid.UUID(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    return m


@router.get("/directory")
async def directory(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    return {"volunteers": await volunteers_service.directory(db, club.id)}


class ProfileUpsert(BaseModel):
    member_id: str
    roles_interested: List[str] = []
    available_days: List[str] = []
    lives_nearby: bool = False
    notes: Optional[str] = None
    # Assigned ClubRole ids (the volunteer's roles). None = leave unchanged.
    role_ids: Optional[List[str]] = None


@router.post("/profiles")
async def upsert_profile(data: ProfileUpsert, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    member = await _member_or_404(db, club, data.member_id)
    p = await volunteers_service.upsert_profile(
        db, club.id, member.id, roles_interested=data.roles_interested, available_days=data.available_days,
        lives_nearby=data.lives_nearby, notes=data.notes,
    )
    if data.role_ids is not None:
        role_uuids = [uuid.UUID(r) for r in data.role_ids]
        await volunteers_service.set_member_roles(db, club.id, member.id, role_uuids)
    out = volunteers_service._profile_dict(p)
    out["role_ids"] = await volunteers_service.member_role_ids(db, club.id, member.id)
    await db.commit()
    return out


@router.get("/members/{member_id}/roles")
async def member_roles(member_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    await _member_or_404(db, club, member_id)
    return {"role_ids": await volunteers_service.member_role_ids(db, club.id, uuid.UUID(member_id))}


@router.get("/members/{member_id}/hours")
async def list_hours(member_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                     db: AsyncSession = Depends(get_db)):
    await _member_or_404(db, club, member_id)
    return {"hours": await volunteers_service.list_hours(db, club.id, uuid.UUID(member_id))}


class HoursCreate(BaseModel):
    member_id: str
    hours: float
    logged_date: Optional[date] = None
    activity: Optional[str] = None
    activity_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/hours")
async def log_hours(data: HoursCreate, current_user: User = Depends(get_current_user), _: User = _require,
                    club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    member = await _member_or_404(db, club, data.member_id)
    try:
        h = await volunteers_service.log_hours(
            db, club.id, member.id, hours=data.hours, logged_date=data.logged_date,
            activity=data.activity, activity_id=uuid.UUID(data.activity_id) if data.activity_id else None,
            notes=data.notes, created_by_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(h.id), "hours": float(h.hours)}


@router.delete("/hours/{hours_id}")
async def delete_hours(hours_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    h = await db.get(VolunteerHours, uuid.UUID(hours_id))
    if not h or h.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    await volunteers_service.delete_hours(db, h)
    await db.commit()
    return {"deleted": True}
