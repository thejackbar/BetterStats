"""Events/Ticketing API.

Admin endpoints (registration management) are gated by the same
MANAGE_COMMITTEE capability as the Club Calendar (ClubEvent CRUD lives in
routers/committee.py) — ticketing is an extension of that calendar, not a
separate capability. The public registration endpoints are unauthenticated
by design (a prospective attendee has no login) and are keyed directly off
the event's UUID, the same posture the rest of this codebase uses for
unguessable-id public views (e.g. the public scorecard).

Priced-event checkout reuses the SAME per-club Stripe Connect account the
member portal and merch storefront use — see public_register below. A club
that hasn't connected Stripe yet keeps the original manual-reconciliation
behaviour (registration lands `awaiting_payment`, the club follows up by
hand) unchanged.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import User, Organisation, ClubEvent, EventRegistration, get_db
from app.routers.auth import get_current_club
from app.auth.capabilities import require_cap, MANAGE_COMMITTEE
from app.services import committee as committee_service
from app.services import events as events_service
from app.services import stripe_connect_client

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
    """Creates the registration, then — only when the event is priced AND
    the club's Stripe Connect account has charges_enabled — mints a
    Checkout Session and returns its URL instead of a plain confirmation.
    Commits exactly once at the end: reading `r.id`/`r.amount_cents` after
    an earlier commit would risk the async "expired attribute" trap this
    codebase has hit before (see routers/public_merch_store.py's checkout
    endpoint for the same fix), so everything needed is read before the
    only commit."""
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

    if r.amount_cents <= 0:
        await db.commit()
        return {"id": str(r.id), "full_name": r.full_name, "quantity": r.quantity,
                "amount_cents": r.amount_cents, "payment_status": r.payment_status}

    org = await db.get(Organisation, e.organisation_id)
    if not org or not org.stripe_connect_account_id or not org.stripe_connect_charges_enabled:
        # Club hasn't connected Stripe — keep the original manual-reconciliation
        # behaviour, unchanged.
        await db.commit()
        return {"id": str(r.id), "full_name": r.full_name, "quantity": r.quantity,
                "amount_cents": r.amount_cents, "payment_status": r.payment_status}

    registration_id, amount_cents = r.id, r.amount_cents
    success_url = f"{settings.public_base_url}/events/{e.id}?paid=1"
    cancel_url = f"{settings.public_base_url}/events/{e.id}?paid=0"
    try:
        checkout_session = await stripe_connect_client.create_event_checkout_session(
            connected_account_id=org.stripe_connect_account_id, registration_id=str(registration_id),
            org_id=str(org.id), description=e.title, amount_cents=amount_cents,
            success_url=success_url, cancel_url=cancel_url,
        )
    except stripe_connect_client.StripeNotConfigured:
        await db.commit()
        return {"id": str(r.id), "full_name": r.full_name, "quantity": r.quantity,
                "amount_cents": r.amount_cents, "payment_status": r.payment_status}

    r.stripe_checkout_session_id = checkout_session.id
    await db.commit()
    return {"id": str(registration_id), "checkout_url": checkout_session.url}
