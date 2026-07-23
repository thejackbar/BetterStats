"""Events/Ticketing API.

Admin endpoints (registration management) are gated by the same
MANAGE_COMMITTEE capability as the Club Calendar (ClubEvent CRUD lives in
routers/committee.py) — ticketing is an extension of that calendar, not a
separate capability. The public registration endpoints are unauthenticated
by design (a prospective attendee has no login) and are keyed directly off
the event's UUID, the same posture the rest of this codebase uses for
unguessable-id public views (e.g. the public scorecard).

See services/events.py for why a priced event has no online payment
collection yet.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, Organisation, ClubEvent, EventRegistration, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_COMMITTEE
from app.services import committee as committee_service
from app.services import events as events_service

router = APIRouter(prefix="/club-admin/events", tags=["club-admin-events"])
public_router = APIRouter(prefix="/public/events", tags=["public-events"])
_require = Depends(require_cap(MANAGE_COMMITTEE))


async def _event_or_404(db: AsyncSession, club: Organisation, event_id: str) -> ClubEvent:
    e = await db.get(ClubEvent, uuid.UUID(event_id))
    if not e or e.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Event not found")
    return e


async def _registration_or_404(db: AsyncSession, event: ClubEvent, reg_id: str) -> EventRegistration:
    r = await db.get(EventRegistration, uuid.UUID(reg_id))
    if not r or r.event_id != event.id:
        raise HTTPException(status_code=404, detail="Registration not found")
    return r


# ─── Admin: registrations against one of our events ───────────────────────────

@router.get("/{event_id}/registrations")
async def list_registrations(event_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                             db: AsyncSession = Depends(get_db)):
    e = await _event_or_404(db, club, event_id)
    rows = await events_service.list_registrations(db, e.id)
    return {
        "registrations": [events_service._registration_dict(r) for r in rows],
        "registered_count": await events_service.registered_count(db, e.id),
        "capacity": e.capacity,
    }


class RegistrationCreate(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    quantity: int = 1
    notes: Optional[str] = None


@router.post("/{event_id}/registrations")
async def create_registration(event_id: str, data: RegistrationCreate, _: User = _require,
                              club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """An admin manually recording a registration (e.g. a phone/in-person RSVP)."""
    e = await _event_or_404(db, club, event_id)
    try:
        r = await events_service.create_registration(db, e, **data.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    await db.commit()
    return events_service._registration_dict(r)


class RegistrationPatch(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    quantity: Optional[int] = None
    amount_cents: Optional[int] = None
    payment_status: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/{event_id}/registrations/{reg_id}")
async def update_registration(event_id: str, reg_id: str, data: RegistrationPatch, _: User = _require,
                              club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    e = await _event_or_404(db, club, event_id)
    r = await _registration_or_404(db, e, reg_id)
    await events_service.update_registration(db, r, **data.model_dump(exclude_unset=True))
    await db.commit()
    return events_service._registration_dict(r)


@router.delete("/{event_id}/registrations/{reg_id}")
async def delete_registration(event_id: str, reg_id: str, _: User = _require, club: Organisation = Depends(get_current_club),
                              db: AsyncSession = Depends(get_db)):
    e = await _event_or_404(db, club, event_id)
    r = await _registration_or_404(db, e, reg_id)
    await events_service.delete_registration(db, r)
    await db.commit()
    return {"deleted": True}


# ─── Public: view an event + register (unauthenticated) ──────────────────────

@public_router.get("/{event_id}")
async def public_event(event_id: str, db: AsyncSession = Depends(get_db)):
    try:
        eid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Event not found")
    e = await db.get(ClubEvent, eid)
    if e is None:
        raise HTTPException(status_code=404, detail="Event not found")
    club = await db.get(Organisation, e.organisation_id)
    registered = await events_service.registered_count(db, e.id)
    spots_left = (e.capacity - registered) if e.capacity is not None else None
    return {
        **committee_service._event_dict(e),
        "club_name": club.name if club else None,
        "club_slug": getattr(club, "slug", None) if club else None,
        "spots_left": spots_left,
        "sold_out": spots_left is not None and spots_left <= 0,
    }


class PublicRegistrationCreate(BaseModel):
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    quantity: int = 1


@public_router.post("/{event_id}/register")
async def public_register(event_id: str, data: PublicRegistrationCreate, db: AsyncSession = Depends(get_db)):
    try:
        eid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Event not found")
    e = await db.get(ClubEvent, eid)
    if e is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        r = await events_service.create_registration(db, e, **data.model_dump())
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    await db.commit()
    return {
        "id": str(r.id), "full_name": r.full_name, "quantity": r.quantity,
        "amount_cents": r.amount_cents, "payment_status": r.payment_status,
    }
