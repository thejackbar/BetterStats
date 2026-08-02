"""BetterClubManager Facilities — the booking-requests approval queue.

Each pending request is checked against every confirmed booking on that space
(conflict detection) before it's shown. Approving a clean request creates a
real facility_booking. Raw SQL, out of the ORM/Alembic model graph.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _iso(dt):
    return dt.isoformat() if dt else None


async def _clashes_for(db: AsyncSession, org_id, facility_id, starts_at, ends_at) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT title, starts_at, ends_at FROM facility_bookings
        WHERE organisation_id = :org AND facility_id = :fac
          AND starts_at < :ends AND :starts < COALESCE(ends_at, starts_at + INTERVAL '1 hour')
        ORDER BY starts_at
    """), {"org": org_id, "fac": facility_id, "starts": starts_at, "ends": ends_at})).mappings().all()
    return [{"title": r["title"], "starts_at": _iso(r["starts_at"]), "ends_at": _iso(r["ends_at"])} for r in rows]


async def list_pending(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT r.id, r.facility_id, r.title, r.starts_at, r.ends_at, r.requester_name, r.requester_email, r.note, f.name AS facility_name
        FROM facility_booking_requests r JOIN facilities f ON f.id = r.facility_id
        WHERE r.organisation_id = :org AND r.status = 'pending'
        ORDER BY r.starts_at
    """), {"org": org_id})).mappings().all()
    out = []
    for r in rows:
        clashes = await _clashes_for(db, org_id, r["facility_id"], r["starts_at"], r["ends_at"])
        out.append({
            "id": str(r["id"]), "facility_id": str(r["facility_id"]), "facility_name": r["facility_name"],
            "title": r["title"], "starts_at": _iso(r["starts_at"]), "ends_at": _iso(r["ends_at"]),
            "requester_name": r["requester_name"], "requester_email": r["requester_email"], "note": r["note"],
            "clashes": clashes,
        })
    return out


async def create(db: AsyncSession, org_id, *, facility_id, title, starts_at, ends_at, requester_name=None, requester_email=None, note=None) -> str:
    rid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO facility_booking_requests (id, organisation_id, facility_id, title, starts_at, ends_at, requester_name, requester_email, note)
        VALUES (:id, :org, :fac, :title, :starts, :ends, :rn, :re, :note)
    """), {"id": rid, "org": org_id, "fac": facility_id, "title": title, "starts": starts_at, "ends": ends_at,
           "rn": requester_name, "re": requester_email, "note": note})
    return str(rid)


async def approve(db: AsyncSession, org_id, req_id, *, force=False) -> dict:
    r = (await db.execute(text("""
        SELECT facility_id, title, starts_at, ends_at, requester_name, note FROM facility_booking_requests
        WHERE id = :id AND organisation_id = :org AND status = 'pending'
    """), {"id": req_id, "org": org_id})).mappings().first()
    if not r:
        return {"ok": False, "error": "not_found"}
    clashes = await _clashes_for(db, org_id, r["facility_id"], r["starts_at"], r["ends_at"])
    if clashes and not force:
        return {"ok": False, "clashes": clashes}
    await db.execute(text("""
        INSERT INTO facility_bookings (id, organisation_id, facility_id, title, starts_at, ends_at, contact_name, notes)
        VALUES (:id, :org, :fac, :title, :starts, :ends, :cn, :note)
    """), {"id": uuid.uuid4(), "org": org_id, "fac": r["facility_id"], "title": r["title"],
           "starts": r["starts_at"], "ends": r["ends_at"], "cn": r["requester_name"], "note": r["note"]})
    await db.execute(text("UPDATE facility_booking_requests SET status='approved', decided_at=NOW() WHERE id=:id AND organisation_id=:org"), {"id": req_id, "org": org_id})
    return {"ok": True}


async def decline(db: AsyncSession, org_id, req_id) -> dict:
    await db.execute(text("UPDATE facility_booking_requests SET status='declined', decided_at=NOW() WHERE id=:id AND organisation_id=:org AND status='pending'"), {"id": req_id, "org": org_id})
    return {"ok": True}


async def clear_all(db: AsyncSession, org_id) -> int:
    res = await db.execute(text("DELETE FROM facility_booking_requests WHERE organisation_id=:org"), {"org": org_id})
    return res.rowcount or 0
