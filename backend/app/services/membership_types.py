"""Membership Management — the membership-type catalogue.

A club-adopted catalogue (Senior Player, Junior Player, Parent, Social
Member, Life Member, Coach, Selector, Volunteer, Umpire, Scorer, Sponsor
Contact, Committee Member, Honorary Member, …), cross-season unlike a
FeeSchedule $ tier. Nothing is seeded automatically — a club seeds the
starter set (or builds its own from scratch) the same way it adopts an
award-definitions template or a BetterComms starter template: opt-in, not
presumed.

STARTER_TYPES double as the "why these attributes" reference: is_playing
distinguishes Senior/Junior Player from every non-playing type;
requires_voting_rights/insurance/wwcc/playhq_registration are informational
flags a club can act on (e.g. a WWCC-required type feeding a future
qualification-expiry reminder) rather than anything enforced automatically
today.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MembershipType

# (name, description, is_playing, voting, insurance, wwcc, playhq, comms_group)
STARTER_TYPES = [
    ("Senior Player", "Registered senior playing member.", True, True, True, False, True, "Senior Players"),
    ("Junior Player", "Registered junior playing member.", True, False, True, True, True, "Junior Players / Parents"),
    ("Parent", "A junior player's parent or guardian.", False, False, False, True, False, "Junior Players / Parents"),
    ("Social Member", "Non-playing social membership.", False, True, False, False, False, "Social Members"),
    ("Life Member", "Permanent honour — set once, doesn't change season to season.", False, True, False, False, False, "Life Members"),
    ("Coach", "Accredited coaching staff.", False, False, True, True, False, "Coaches"),
    ("Selector", "Club selector.", False, True, False, False, False, "Committee"),
    ("Volunteer", "General club volunteer.", False, False, True, True, False, "Volunteers"),
    ("Umpire", "Club or panel umpire.", False, False, True, False, False, "Umpires & Scorers"),
    ("Scorer", "Club scorer.", False, False, True, False, False, "Umpires & Scorers"),
    ("Sponsor Contact", "A sponsor's nominated contact.", False, False, False, False, False, "Sponsors"),
    ("Committee Member", "Elected/appointed committee position holder.", False, True, False, False, False, "Committee"),
    ("Honorary Member", "Honorary membership — for a season, a number of years, or perpetual.", False, True, False, False, False, "Honorary Members"),
]


def _dict(t: MembershipType) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "description": t.description,
        "default_annual_fee": float(t.default_annual_fee) if t.default_annual_fee is not None else None,
        "is_playing": t.is_playing,
        "requires_voting_rights": t.requires_voting_rights,
        "requires_insurance": t.requires_insurance,
        "requires_wwcc": t.requires_wwcc,
        "requires_playhq_registration": t.requires_playhq_registration,
        "comms_group": t.comms_group,
        "sort_order": t.sort_order,
        "is_active": t.is_active,
    }


async def list_types(session: AsyncSession, organisation_id, *, include_inactive: bool = False) -> list[dict]:
    stmt = select(MembershipType).where(MembershipType.organisation_id == organisation_id)
    if not include_inactive:
        stmt = stmt.where(MembershipType.is_active.is_(True))
    stmt = stmt.order_by(MembershipType.sort_order, func.lower(MembershipType.name))
    rows = (await session.execute(stmt)).scalars().all()
    return [_dict(t) for t in rows]


async def create_type(session: AsyncSession, organisation_id, *, name: str, **fields) -> MembershipType:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(MembershipType).where(MembershipType.organisation_id == organisation_id,
                                     func.lower(MembershipType.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'A membership type called "{name}" already exists')
    t = MembershipType(organisation_id=organisation_id, name=name[:120], **_clean_fields(fields))
    session.add(t)
    await session.flush()
    return t


def _clean_fields(fields: dict) -> dict:
    allowed = (
        "description", "default_annual_fee", "is_playing", "requires_voting_rights",
        "requires_insurance", "requires_wwcc", "requires_playhq_registration",
        "comms_group", "sort_order",
    )
    return {k: v for k, v in fields.items() if k in allowed and v is not None}


async def update_type(session: AsyncSession, t: MembershipType, **fields) -> MembershipType:
    for k, v in _clean_fields(fields).items():
        setattr(t, k, v)
    t.updated_at = func.now()
    return t


async def archive_type(session: AsyncSession, t: MembershipType) -> None:
    """Soft-delete — existing members keep their reference (informational),
    it just drops off the "assign a type" picker for new members."""
    t.is_active = False


async def seed_starter_types(session: AsyncSession, organisation_id) -> int:
    """Idempotent — only inserts types the club doesn't already have (by
    name), so re-running (or seeding after the club has already added some of
    its own) never duplicates or clobbers anything."""
    existing_names = {
        n.lower() for n in (await session.execute(
            select(MembershipType.name).where(MembershipType.organisation_id == organisation_id)
        )).scalars().all()
    }
    seeded = 0
    for position, (name, desc, is_playing, voting, insurance, wwcc, playhq, group) in enumerate(STARTER_TYPES):
        if name.lower() in existing_names:
            continue
        session.add(MembershipType(
            organisation_id=organisation_id, name=name, description=desc, is_playing=is_playing,
            requires_voting_rights=voting, requires_insurance=insurance, requires_wwcc=wwcc,
            requires_playhq_registration=playhq, comms_group=group, sort_order=position,
        ))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded
