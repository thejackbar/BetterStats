"""Events/Ticketing — registrations against a ClubEvent.

The ClubEvent calendar CRUD itself (create/update/delete an event, including
the ticketing fields) lives in services/committee.py alongside the rest of
the Club Calendar — this file is just the registration/capacity layer on top.

A priced registration is created here at ``awaiting_payment`` regardless —
routers/events.py::public_register decides on top of that whether to mint a
real Stripe Connect Checkout Session (club has connected Stripe, see
migration 178/180) or leave it for manual reconciliation (club hasn't). Per
the migration 177 docstring, Square is NOT wired up for this: the per-club
Square connection (BetterMerch) was authorised with READ-ONLY OAuth scopes
(ITEMS_READ/INVENTORY_READ/ORDERS_READ) — creating a Square Payment Link
needs PAYMENTS_WRITE/ORDERS_WRITE, which would force every already-connected
club to re-authorise. That's real follow-on work, not done here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubEvent, EventRegistration

REGISTRATION_STATUSES = ("free", "awaiting_payment", "paid", "cancelled")


def _registration_dict(r: EventRegistration) -> dict:
    return {
        "id": str(r.id), "event_id": str(r.event_id), "full_name": r.full_name,
        "email": r.email, "phone": r.phone, "quantity": r.quantity,
        "amount_cents": r.amount_cents, "payment_status": r.payment_status,
        "notes": r.notes, "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def registered_count(session: AsyncSession, event_id) -> int:
    """Sum of quantity across non-cancelled registrations — what counts
    against capacity."""
    total = (await session.execute(
        select(func.coalesce(func.sum(EventRegistration.quantity), 0)).where(
            EventRegistration.event_id == event_id, EventRegistration.payment_status != "cancelled",
        )
    )).scalar_one()
    return int(total)


async def list_registrations(session: AsyncSession, event_id) -> list[EventRegistration]:
    stmt = select(EventRegistration).where(EventRegistration.event_id == event_id).order_by(EventRegistration.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def create_registration(session: AsyncSession, event: ClubEvent, *, full_name: str,
                              email: Optional[str] = None, phone: Optional[str] = None,
                              quantity: int = 1, notes: Optional[str] = None) -> EventRegistration:
    full_name = (full_name or "").strip()
    if not full_name:
        raise ValueError("Name is required")
    quantity = max(1, int(quantity or 1))
    if not event.registration_open:
        raise ValueError("Registration is closed for this event")
    if event.registration_deadline is not None:
        deadline = event.registration_deadline
        now = datetime.now(timezone.utc) if deadline.tzinfo is not None else datetime.utcnow()
        if now > deadline:
            raise ValueError("The registration deadline has passed")
    if event.capacity is not None:
        current = await registered_count(session, event.id)
        remaining = event.capacity - current
        if quantity > remaining:
            raise ValueError(f"Only {max(0, remaining)} spot(s) left" if remaining > 0 else "This event is fully booked")
    amount_cents = event.ticket_price_cents * quantity if event.is_ticketed else 0
    r = EventRegistration(
        organisation_id=event.organisation_id, event_id=event.id, full_name=full_name[:200],
        email=(email or None), phone=(phone or None), quantity=quantity, amount_cents=amount_cents,
        payment_status="awaiting_payment" if amount_cents > 0 else "free",
        notes=notes,
    )
    session.add(r)
    await session.flush()
    return r


async def update_registration(session: AsyncSession, r: EventRegistration, **fields) -> EventRegistration:
    for f in ("full_name", "email", "phone", "quantity", "amount_cents", "payment_status", "notes"):
        if f in fields and fields[f] is not None:
            setattr(r, f, fields[f])
    return r


async def delete_registration(session: AsyncSession, r: EventRegistration) -> None:
    await session.delete(r)
