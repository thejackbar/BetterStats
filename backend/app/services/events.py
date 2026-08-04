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

from app.models.db import ClubEvent, EventRegistration, ClubEventType

REGISTRATION_STATUSES = ("free", "awaiting_payment", "paid", "cancelled")

# Public/social event kinds typical for a cricket club.
STARTER_EVENT_TYPES = [
    ("Social Night", "A casual club social."),
    ("Awards Night", "Season presentation / awards."),
    ("Quiz Night", "Trivia fundraiser."),
    ("Curry Night", "Club curry/dinner night."),
    ("Presentation Day", "Junior/senior presentation day."),
    ("Fundraiser", "General fundraising event."),
    ("Sponsors' Function", "Sponsor thank-you / networking."),
    ("Season Launch", "Pre-season launch."),
    ("Registration Day", "Sign-on / registration day."),
    ("Working Bee", "Ground/clubhouse working bee."),
    ("Other", "Anything else."),
]

# Committee-only / internal events.
STARTER_COMMITTEE_EVENT_TYPES = [
    ("Committee Meeting", "Regular committee meeting."),
    ("Sub-committee Meeting", "A sub-committee meeting."),
    ("AGM", "Annual General Meeting."),
    ("Special General Meeting", "SGM / EGM."),
    ("Selection Meeting", "Team selection."),
    ("Budget / Finance Meeting", "Finance review."),
    ("Stock Take", "Canteen/bar/equipment stock take."),
    ("End of Season Review", "Season wrap-up / planning."),
]


def _event_type_dict(t: ClubEventType) -> dict:
    return {
        "id": str(t.id), "name": t.name, "description": t.description,
        "is_committee_only": t.is_committee_only, "sort_order": t.sort_order, "is_active": t.is_active,
    }


# ─── Event types ─────────────────────────────────────────────────────────────
async def list_event_types(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[ClubEventType]:
    stmt = select(ClubEventType).where(ClubEventType.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(ClubEventType.is_active.is_(True))
    stmt = stmt.order_by(ClubEventType.is_committee_only, ClubEventType.sort_order, func.lower(ClubEventType.name))
    return (await session.execute(stmt)).scalars().all()


async def create_event_type(session: AsyncSession, org_id, *, name: str, description=None,
                            is_committee_only: bool = False, sort_order: int = 0) -> ClubEventType:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(ClubEventType).where(ClubEventType.organisation_id == org_id,
                                    func.lower(ClubEventType.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'An event type called "{name}" already exists')
    t = ClubEventType(organisation_id=org_id, name=name[:120], description=description,
                      is_committee_only=is_committee_only, sort_order=sort_order)
    session.add(t)
    await session.flush()
    return t


async def update_event_type(session: AsyncSession, t: ClubEventType, **fields) -> ClubEventType:
    for f in ("name", "description", "is_committee_only", "sort_order", "is_active"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    return t


async def archive_event_type(session: AsyncSession, t: ClubEventType) -> None:
    t.is_active = False


async def seed_starter_event_types(session: AsyncSession, org_id, *, committee_only: bool = False) -> int:
    rows = STARTER_COMMITTEE_EVENT_TYPES if committee_only else STARTER_EVENT_TYPES
    existing = {n.lower() for n in (await session.execute(
        select(ClubEventType.name).where(ClubEventType.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for i, (name, desc) in enumerate(rows):
        if name.lower() in existing:
            continue
        session.add(ClubEventType(organisation_id=org_id, name=name, description=desc,
                                  is_committee_only=committee_only, sort_order=i))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


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


async def financials(session: AsyncSession, event_id) -> dict:
    """What an event took, and what is still outstanding.

    Every figure comes from the registrations themselves — `amount_cents` is
    what was charged and `payment_status` is where that money got to — so this
    is a read over data the club already has, not a second ledger. Costs are not
    tracked against an event yet, so this reports income, not profit.
    """
    rows = (await session.execute(
        select(EventRegistration.payment_status,
               func.count(EventRegistration.id),
               func.coalesce(func.sum(EventRegistration.quantity), 0),
               func.coalesce(func.sum(EventRegistration.amount_cents), 0))
        .where(EventRegistration.event_id == event_id)
        .group_by(EventRegistration.payment_status)
    )).all()

    by_status = {
        status: {"registrations": int(n), "tickets": int(qty), "amount": round(int(cents) / 100, 2)}
        for status, n, qty, cents in rows
    }
    take = lambda k, f: by_status.get(k, {}).get(f, 0)
    paid = take("paid", "amount")
    awaiting = take("awaiting_payment", "amount")
    return {
        "taken": paid,
        "awaiting_payment": awaiting,
        "cancelled": take("cancelled", "amount"),
        "free_registrations": take("free", "registrations"),
        # What the event is worth once everyone settles up.
        "expected": round(paid + awaiting, 2),
        "tickets_sold": sum(v["tickets"] for k, v in by_status.items() if k != "cancelled"),
        "by_status": by_status,
    }


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
