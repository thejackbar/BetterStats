"""Assets & Facilities API — club property, bookings, maintenance history.

Core capability (MANAGE_ASSETS), not a paid module — see services/assets.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, Facility, FacilityBooking, ClubAsset, MaintenanceLog, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_ASSETS
from app.services import assets as assets_service

router = APIRouter(prefix="/club-admin/assets", tags=["club-admin-assets"])
_require = Depends(require_cap(MANAGE_ASSETS))


async def _facility_or_404(db: AsyncSession, club: Organisation, facility_id: str) -> Facility:
    f = await db.get(Facility, uuid.UUID(facility_id))
    if not f or f.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Facility not found")
    return f


async def _booking_or_404(db: AsyncSession, club: Organisation, booking_id: str) -> FacilityBooking:
    b = await db.get(FacilityBooking, uuid.UUID(booking_id))
    if not b or b.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    return b


async def _asset_or_404(db: AsyncSession, club: Organisation, asset_id: str) -> ClubAsset:
    a = await db.get(ClubAsset, uuid.UUID(asset_id))
    if not a or a.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return a


async def _maintenance_log_or_404(db: AsyncSession, club: Organisation, log_id: str) -> MaintenanceLog:
    m = await db.get(MaintenanceLog, uuid.UUID(log_id))
    if not m or m.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Maintenance log not found")
    return m


# ─── Facilities ───────────────────────────────────────────────────────────────

@router.get("/facilities")
async def list_facilities(include_inactive: bool = False, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await assets_service.list_facilities(db, club.id, include_inactive=include_inactive)
    return {"facilities": [assets_service._facility_dict(f) for f in rows]}


class FacilityCreate(BaseModel):
    name: str
    facility_type: str = "other"
    description: Optional[str] = None
    key_location: Optional[str] = None


@router.post("/facilities")
async def create_facility(data: FacilityCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    try:
        f = await assets_service.create_facility(db, club.id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return assets_service._facility_dict(f)


@router.post("/facilities/seed-starter")
async def seed_facilities(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    n = await assets_service.seed_starter_facilities(db, club.id)
    await db.commit()
    return {"seeded": n}


@router.post("/items/seed-starter")
async def seed_items(_: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    n = await assets_service.seed_starter_assets(db, club.id)
    await db.commit()
    return {"seeded": n}


class FacilityPatch(BaseModel):
    name: Optional[str] = None
    facility_type: Optional[str] = None
    description: Optional[str] = None
    key_location: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch("/facilities/{facility_id}")
async def update_facility(facility_id: str, data: FacilityPatch, _: User = _require,
                          club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    f = await _facility_or_404(db, club, facility_id)
    await assets_service.update_facility(db, f, **data.model_dump(exclude_unset=True))
    await db.commit()
    return assets_service._facility_dict(f)


@router.delete("/facilities/{facility_id}")
async def delete_facility(facility_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                          db: AsyncSession = Depends(get_db)):
    f = await _facility_or_404(db, club, facility_id)
    await assets_service.delete_facility(db, f)
    await db.commit()
    return {"deleted": True}


# ─── Facility bookings ────────────────────────────────────────────────────────

@router.get("/bookings")
async def list_bookings(facility_id: Optional[str] = None, upcoming_only: bool = False, _: User = _require,
                        club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await assets_service.list_bookings(
        db, club.id, facility_id=uuid.UUID(facility_id) if facility_id else None, upcoming_only=upcoming_only,
    )
    return {"bookings": [assets_service._booking_dict(b) for b in rows]}


class BookingCreate(BaseModel):
    facility_id: str
    title: str
    starts_at: datetime
    ends_at: Optional[datetime] = None
    booked_by_member_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_mobile: Optional[str] = None
    owner_member_id: Optional[str] = None
    owner_name: Optional[str] = None
    notes: Optional[str] = None


@router.post("/bookings")
async def create_booking(data: BookingCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    await _facility_or_404(db, club, data.facility_id)
    fields = data.model_dump()
    facility_id = uuid.UUID(fields.pop("facility_id"))
    for f in ("booked_by_member_id", "owner_member_id"):
        fields[f] = uuid.UUID(fields[f]) if fields.get(f) else None
    try:
        b = await assets_service.create_booking(db, club.id, facility_id=facility_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return assets_service._booking_dict(b)


class BookingPatch(BaseModel):
    title: Optional[str] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    booked_by_member_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_mobile: Optional[str] = None
    owner_member_id: Optional[str] = None
    owner_name: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/bookings/{booking_id}")
async def update_booking(booking_id: str, data: BookingPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    b = await _booking_or_404(db, club, booking_id)
    fields = data.model_dump(exclude_unset=True)
    for f in ("booked_by_member_id", "owner_member_id"):
        if f in fields:
            fields[f] = uuid.UUID(fields[f]) if fields[f] else None
    await assets_service.update_booking(db, b, **fields)
    await db.commit()
    return assets_service._booking_dict(b)


@router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                         db: AsyncSession = Depends(get_db)):
    b = await _booking_or_404(db, club, booking_id)
    await assets_service.delete_booking(db, b)
    await db.commit()
    return {"deleted": True}


# ─── Club assets ──────────────────────────────────────────────────────────────

@router.get("/items")
async def list_assets(include_inactive: bool = False, category: Optional[str] = None, status: Optional[str] = None,
                      facility_id: Optional[str] = None, cost_min: Optional[float] = None, cost_max: Optional[float] = None,
                      acquired_from: Optional[date] = None, acquired_to: Optional[date] = None,
                      _: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    rows = await assets_service.list_assets(
        db, club.id, include_inactive=include_inactive, category=category, status=status,
        facility_id=uuid.UUID(facility_id) if facility_id else None,
        cost_min=cost_min, cost_max=cost_max, acquired_from=acquired_from, acquired_to=acquired_to)
    return {"assets": [assets_service._asset_dict(a) for a in rows]}


class AssetCreate(BaseModel):
    name: str
    category: str = "other"
    asset_tag: Optional[str] = None
    purchase_cost: Optional[float] = None
    purchase_date: Optional[date] = None
    condition: str = "good"
    status: str = "in_service"
    service_due_date: Optional[date] = None
    replace_due_date: Optional[date] = None
    facility_id: Optional[str] = None
    notes: Optional[str] = None


@router.post("/items")
async def create_asset(data: AssetCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    fields = data.model_dump()
    fields["facility_id"] = uuid.UUID(fields["facility_id"]) if fields.get("facility_id") else None
    try:
        a = await assets_service.create_asset(db, club.id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return assets_service._asset_dict(a)


class AssetPatch(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    asset_tag: Optional[str] = None
    purchase_cost: Optional[float] = None
    purchase_date: Optional[date] = None
    condition: Optional[str] = None
    status: Optional[str] = None
    service_due_date: Optional[date] = None
    replace_due_date: Optional[date] = None
    facility_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.patch("/items/{asset_id}")
async def update_asset(asset_id: str, data: AssetPatch, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    a = await _asset_or_404(db, club, asset_id)
    fields = data.model_dump(exclude_unset=True)
    if "facility_id" in fields:
        fields["facility_id"] = uuid.UUID(fields["facility_id"]) if fields["facility_id"] else None
    await assets_service.update_asset(db, a, **fields)
    await db.commit()
    return assets_service._asset_dict(a)


@router.delete("/items/{asset_id}")
async def delete_asset(asset_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                       db: AsyncSession = Depends(get_db)):
    a = await _asset_or_404(db, club, asset_id)
    await assets_service.delete_asset(db, a)
    await db.commit()
    return {"deleted": True}


# ─── Maintenance logs ─────────────────────────────────────────────────────────

@router.get("/maintenance-logs")
async def list_maintenance_logs(subject_type: str, subject_id: str, _: User = _require,
                                club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    if subject_type == "asset":
        await _asset_or_404(db, club, subject_id)
    elif subject_type == "facility":
        await _facility_or_404(db, club, subject_id)
    else:
        raise HTTPException(status_code=422, detail="subject_type must be 'asset' or 'facility'")
    rows = await assets_service.list_maintenance_logs(db, club.id, subject_type=subject_type, subject_id=uuid.UUID(subject_id))
    return {"logs": [assets_service._maintenance_log_dict(m) for m in rows]}


class MaintenanceLogCreate(BaseModel):
    subject_type: str
    subject_id: str
    performed_at: Optional[date] = None
    description: str
    cost: Optional[float] = None
    performed_by: Optional[str] = None
    next_due_date: Optional[date] = None


@router.post("/maintenance-logs")
async def create_maintenance_log(data: MaintenanceLogCreate, _: User = _require, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    if data.subject_type == "asset":
        await _asset_or_404(db, club, data.subject_id)
    elif data.subject_type == "facility":
        await _facility_or_404(db, club, data.subject_id)
    else:
        raise HTTPException(status_code=422, detail="subject_type must be 'asset' or 'facility'")
    fields = data.model_dump()
    subject_type = fields.pop("subject_type")
    subject_id = uuid.UUID(fields.pop("subject_id"))
    try:
        m = await assets_service.create_maintenance_log(db, club.id, subject_type=subject_type, subject_id=subject_id, **fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return assets_service._maintenance_log_dict(m)


@router.delete("/maintenance-logs/{log_id}")
async def delete_maintenance_log(log_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                                 db: AsyncSession = Depends(get_db)):
    m = await _maintenance_log_or_404(db, club, log_id)
    await assets_service.delete_maintenance_log(db, m)
    await db.commit()
    return {"deleted": True}
