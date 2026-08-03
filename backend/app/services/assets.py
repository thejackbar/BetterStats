"""Assets & Facilities — general club property (mower, clubhouse, nets,
scoreboard) and a maintenance/service history shared between the two.

A NEW, separate concern from BetterMerch's merch_assets (a paid-module
retail/kit stock table) — general club property isn't retrofitted there, the
same reasoning already applied to committee_positions vs the public
club_committee table. Gated by the MANAGE_ASSETS capability (core, not a
paid module — every club owns some property worth tracking).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Facility, FacilityBooking, ClubAsset, MaintenanceLog


def _facility_dict(f: Facility) -> dict:
    return {
        "id": str(f.id), "name": f.name, "facility_type": f.facility_type,
        "description": f.description, "key_location": f.key_location, "is_active": f.is_active,
    }


def _booking_dict(b: FacilityBooking) -> dict:
    return {
        "id": str(b.id), "facility_id": str(b.facility_id), "title": b.title,
        "starts_at": b.starts_at.isoformat() if b.starts_at else None,
        "ends_at": b.ends_at.isoformat() if b.ends_at else None,
        "booked_by_member_id": str(b.booked_by_member_id) if b.booked_by_member_id else None,
        "contact_name": b.contact_name, "contact_email": b.contact_email, "contact_mobile": b.contact_mobile,
        "owner_member_id": str(b.owner_member_id) if b.owner_member_id else None,
        "owner_name": b.owner_name,
        "notes": b.notes,
    }


def _asset_dict(a: ClubAsset) -> dict:
    return {
        "id": str(a.id), "name": a.name, "category": a.category, "asset_tag": a.asset_tag,
        "purchase_cost": float(a.purchase_cost) if a.purchase_cost is not None else None,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "condition": a.condition, "status": a.status,
        "service_due_date": a.service_due_date.isoformat() if a.service_due_date else None,
        "replace_due_date": a.replace_due_date.isoformat() if a.replace_due_date else None,
        "facility_id": str(a.facility_id) if a.facility_id else None,
        "notes": a.notes, "is_active": a.is_active,
    }


def _maintenance_log_dict(m: MaintenanceLog) -> dict:
    return {
        "id": str(m.id), "subject_type": m.subject_type, "subject_id": str(m.subject_id),
        "performed_at": m.performed_at.isoformat() if m.performed_at else None,
        "description": m.description,
        "cost": float(m.cost) if m.cost is not None else None,
        "performed_by": m.performed_by,
        "next_due_date": m.next_due_date.isoformat() if m.next_due_date else None,
    }


# ─── Facilities ───────────────────────────────────────────────────────────────

async def list_facilities(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[Facility]:
    stmt = select(Facility).where(Facility.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(Facility.is_active.is_(True))
    stmt = stmt.order_by(func.lower(Facility.name))
    return (await session.execute(stmt)).scalars().all()


async def create_facility(session: AsyncSession, org_id, **fields) -> Facility:
    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")
    f = Facility(
        organisation_id=org_id, name=name[:200], facility_type=fields.get("facility_type") or "other",
        description=fields.get("description"), key_location=fields.get("key_location"),
    )
    session.add(f)
    await session.flush()
    return f


async def update_facility(session: AsyncSession, f: Facility, **fields) -> Facility:
    for field in ("name", "facility_type", "description", "key_location", "is_active"):
        if field in fields and fields[field] is not None:
            setattr(f, field, fields[field])
    return f


async def delete_facility(session: AsyncSession, f: Facility) -> None:
    await session.delete(f)


# ─── Facility bookings ────────────────────────────────────────────────────────

async def list_bookings(session: AsyncSession, org_id, *, facility_id=None, upcoming_only: bool = False) -> list[FacilityBooking]:
    from datetime import datetime, timezone
    stmt = select(FacilityBooking).where(FacilityBooking.organisation_id == org_id)
    if facility_id:
        stmt = stmt.where(FacilityBooking.facility_id == facility_id)
    if upcoming_only:
        stmt = stmt.where(FacilityBooking.starts_at >= datetime.now(timezone.utc))
    stmt = stmt.order_by(FacilityBooking.starts_at)
    return (await session.execute(stmt)).scalars().all()


async def create_booking(session: AsyncSession, org_id, *, facility_id, **fields) -> FacilityBooking:
    title = (fields.get("title") or "").strip()
    if not title or not fields.get("starts_at"):
        raise ValueError("Title and start time are required")
    b = FacilityBooking(
        organisation_id=org_id, facility_id=facility_id, title=title[:300],
        starts_at=fields["starts_at"], ends_at=fields.get("ends_at"),
        booked_by_member_id=fields.get("booked_by_member_id"),
        contact_name=fields.get("contact_name"), contact_email=fields.get("contact_email"),
        contact_mobile=fields.get("contact_mobile"), owner_member_id=fields.get("owner_member_id"),
        owner_name=fields.get("owner_name"), notes=fields.get("notes"),
    )
    session.add(b)
    await session.flush()
    return b


async def update_booking(session: AsyncSession, b: FacilityBooking, **fields) -> FacilityBooking:
    for field in ("title", "starts_at"):
        if field in fields and fields[field] is not None:
            setattr(b, field, fields[field])
    # Nullable fields may be cleared explicitly ("present in the payload").
    for field in ("ends_at", "booked_by_member_id", "contact_name", "contact_email",
                  "contact_mobile", "owner_member_id", "owner_name", "notes"):
        if field in fields:
            setattr(b, field, fields[field])
    return b


async def delete_booking(session: AsyncSession, b: FacilityBooking) -> None:
    await session.delete(b)


# ─── Club assets ──────────────────────────────────────────────────────────────

async def list_assets(session: AsyncSession, org_id, *, include_inactive: bool = False,
                      category: Optional[str] = None, status: Optional[str] = None,
                      facility_id=None, cost_min=None, cost_max=None,
                      acquired_from=None, acquired_to=None) -> list[ClubAsset]:
    stmt = select(ClubAsset).where(ClubAsset.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(ClubAsset.is_active.is_(True))
    if category:
        stmt = stmt.where(ClubAsset.category == category)
    if status:
        stmt = stmt.where(ClubAsset.status == status)
    if facility_id:
        stmt = stmt.where(ClubAsset.facility_id == facility_id)
    if cost_min is not None:
        stmt = stmt.where(ClubAsset.purchase_cost >= cost_min)
    if cost_max is not None:
        stmt = stmt.where(ClubAsset.purchase_cost <= cost_max)
    if acquired_from is not None:
        stmt = stmt.where(ClubAsset.purchase_date >= acquired_from)
    if acquired_to is not None:
        stmt = stmt.where(ClubAsset.purchase_date <= acquired_to)
    stmt = stmt.order_by(func.lower(ClubAsset.name))
    return (await session.execute(stmt)).scalars().all()


async def create_asset(session: AsyncSession, org_id, **fields) -> ClubAsset:
    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")
    a = ClubAsset(
        organisation_id=org_id, name=name[:200], category=fields.get("category") or "other",
        asset_tag=fields.get("asset_tag"), purchase_cost=fields.get("purchase_cost"),
        purchase_date=fields.get("purchase_date"), condition=fields.get("condition") or "good",
        status=fields.get("status") or "in_service", service_due_date=fields.get("service_due_date"),
        replace_due_date=fields.get("replace_due_date"), facility_id=fields.get("facility_id"),
        notes=fields.get("notes"),
    )
    session.add(a)
    await session.flush()
    return a


async def update_asset(session: AsyncSession, a: ClubAsset, **fields) -> ClubAsset:
    for field in ("name", "category", "asset_tag", "purchase_cost", "purchase_date", "condition", "status",
                  "service_due_date", "replace_due_date", "facility_id", "notes", "is_active"):
        if field in fields and fields[field] is not None:
            setattr(a, field, fields[field])
    a.updated_at = func.now()
    return a


async def delete_asset(session: AsyncSession, a: ClubAsset) -> None:
    await session.delete(a)


# ─── Maintenance logs (shared: an asset or a facility) ───────────────────────

async def list_maintenance_logs(session: AsyncSession, org_id, *, subject_type: str, subject_id) -> list[MaintenanceLog]:
    stmt = (
        select(MaintenanceLog)
        .where(MaintenanceLog.organisation_id == org_id, MaintenanceLog.subject_type == subject_type,
               MaintenanceLog.subject_id == subject_id)
        .order_by(MaintenanceLog.performed_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


async def create_maintenance_log(session: AsyncSession, org_id, *, subject_type: str, subject_id, **fields) -> MaintenanceLog:
    if subject_type not in ("asset", "facility"):
        raise ValueError("subject_type must be 'asset' or 'facility'")
    description = (fields.get("description") or "").strip()
    if not description:
        raise ValueError("Description is required")
    m = MaintenanceLog(
        organisation_id=org_id, subject_type=subject_type, subject_id=subject_id,
        performed_at=fields.get("performed_at") or date.today(), description=description[:2000],
        cost=fields.get("cost"), performed_by=fields.get("performed_by"),
        next_due_date=fields.get("next_due_date"),
    )
    session.add(m)
    await session.flush()
    return m


async def delete_maintenance_log(session: AsyncSession, m: MaintenanceLog) -> None:
    await session.delete(m)


# ── Starter Packs (BetterClubManager setup) ─────────────────────────────────
STARTER_FACILITIES = [
    {"name": "Main Ground", "facility_type": "ground", "description": "Turf oval"},
    {"name": "Turf Wicket Block", "facility_type": "ground", "description": "Centre square"},
    {"name": "Practice Nets", "facility_type": "nets", "description": "Synthetic bays"},
    {"name": "Clubrooms", "facility_type": "clubroom", "description": "Bar + social space"},
    {"name": "Function Room", "facility_type": "clubroom", "description": "Hireable room"},
]
STARTER_ASSETS = [
    {"name": "Junior kit bag", "category": "kit"},
    {"name": "Senior kit bag", "category": "kit"},
    {"name": "Bowling machine", "category": "equipment"},
    {"name": "Portable nets", "category": "equipment"},
    {"name": "Line marker", "category": "grounds"},
    {"name": "Scoring tablet", "category": "tech"},
    {"name": "Covers (roll-on)", "category": "grounds"},
]


async def seed_starter_facilities(session: AsyncSession, org_id) -> int:
    if await list_facilities(session, org_id):
        return 0
    for f in STARTER_FACILITIES:
        await create_facility(session, org_id, **f)
    return len(STARTER_FACILITIES)


async def seed_starter_assets(session: AsyncSession, org_id) -> int:
    if await list_assets(session, org_id):
        return 0
    for a in STARTER_ASSETS:
        await create_asset(session, org_id, **a)
    return len(STARTER_ASSETS)
