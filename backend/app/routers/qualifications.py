"""Qualification Management API — accreditation types + member qualifications.

Core capability (MANAGE_QUALIFICATIONS), not a paid module — see
services/qualifications.py.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, FeeMember, QualificationType, MemberQualification, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_QUALIFICATIONS
from app.services import qualifications as qualifications_service

router = APIRouter(prefix="/club-admin/qualifications", tags=["club-admin-qualifications"])
_require = Depends(require_cap(MANAGE_QUALIFICATIONS))


async def _member_or_404(db: AsyncSession, club: Organisation, member_id: str) -> FeeMember:
    m = await db.get(FeeMember, uuid.UUID(member_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    return m


# ─── Types ────────────────────────────────────────────────────────────────────

@router.get("/types")
async def list_types(include_inactive: bool = False, _: User = _require,
                     club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await qualifications_service.list_types(db, club.id, include_inactive=include_inactive)
    return {"types": [qualifications_service._type_dict(t) for t in rows]}


class TypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    validity_months: Optional[int] = None
    sort_order: int = 0


@router.post("/types")
async def create_type(data: TypeCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    try:
        t = await qualifications_service.create_type(db, club.id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return qualifications_service._type_dict(t)


class TypePatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    validity_months: Optional[int] = None
    sort_order: Optional[int] = None


@router.patch("/types/{type_id}")
async def update_type(type_id: str, data: TypePatch, _: User = _require, club: Organisation = Depends(get_current_club),
                      db: AsyncSession = Depends(get_db)):
    t = await db.get(QualificationType, uuid.UUID(type_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Qualification type not found")
    await qualifications_service.update_type(db, t, **data.model_dump(exclude_unset=True))
    await db.commit()
    return qualifications_service._type_dict(t)


@router.delete("/types/{type_id}")
async def archive_type(type_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    t = await db.get(QualificationType, uuid.UUID(type_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Qualification type not found")
    await qualifications_service.archive_type(db, t)
    await db.commit()
    return {"archived": True}


@router.post("/types/seed-starter")
async def seed_starter_types(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    seeded = await qualifications_service.seed_starter_types(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# ─── Member qualifications ───────────────────────────────────────────────────

@router.get("/members/{member_id}")
async def list_member_qualifications(member_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                                     db: AsyncSession = Depends(get_db)):
    await _member_or_404(db, club, member_id)
    return {"qualifications": await qualifications_service.list_member_qualifications(db, club.id, uuid.UUID(member_id))}


class QualificationCreate(BaseModel):
    member_id: str
    qualification_type_id: str
    obtained_at: Optional[date] = None
    certificate_ref: Optional[str] = None
    notes: Optional[str] = None


@router.post("/members/qualification")
async def add_qualification(data: QualificationCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                            db: AsyncSession = Depends(get_db)):
    member = await _member_or_404(db, club, data.member_id)
    try:
        q = await qualifications_service.add_qualification(
            db, club.id, member.id, uuid.UUID(data.qualification_type_id),
            obtained_at=data.obtained_at, certificate_ref=data.certificate_ref, notes=data.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return qualifications_service._qual_dict(q)


class QualificationPatch(BaseModel):
    obtained_at: Optional[date] = None
    expires_at: Optional[date] = None
    certificate_ref: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/qualification/{qualification_id}")
async def update_qualification(qualification_id: str, data: QualificationPatch, _: User = _require,
                               club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    q = await db.get(MemberQualification, uuid.UUID(qualification_id))
    if not q or q.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Qualification not found")
    await qualifications_service.update_qualification(db, q, **data.model_dump(exclude_unset=True))
    await db.commit()
    return qualifications_service._qual_dict(q)


@router.delete("/qualification/{qualification_id}")
async def delete_qualification(qualification_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                               db: AsyncSession = Depends(get_db)):
    q = await db.get(MemberQualification, uuid.UUID(qualification_id))
    if not q or q.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Qualification not found")
    await qualifications_service.delete_qualification(db, q)
    await db.commit()
    return {"deleted": True}


@router.get("/expiring")
async def expiring_report(within_days: int = 60, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    return await qualifications_service.expiring_report(db, club.id, within_days=within_days)
