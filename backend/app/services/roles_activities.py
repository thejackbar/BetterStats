"""Roles & Activities — the club's volunteer taxonomy.

A shared catalogue used by BOTH Volunteers (a volunteer holds one or more
Roles) and Qualifications (a qualification is tagged with the Roles it's
required for), plus Activities that describe what a volunteer's logged hours
were spent on. Nothing is auto-seeded — a club adopts the starter set below or
builds its own, the same opt-in posture as Qualifications' starter types.

Both Roles and Activities carry a club-defined Type (its own small catalogue,
also with a starter set). Types are archived (is_active=False), not deleted,
so a role/activity pointing at one keeps its grouping.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    ClubRoleType, ClubRole, ClubActivityType, ClubActivity,
)

# ─── Starter sets ────────────────────────────────────────────────────────────
STARTER_ROLE_TYPES = [
    ("Committee Member", "Elected/appointed committee positions."),
    ("Ground Staff", "Ground, nets and facility upkeep."),
    ("Coach", "Coaching and player development."),
    ("Food & Beverage", "Canteen, bar and catering."),
    ("Other", "Anything that doesn't fit the above."),
]

# (title, role_type_name) — everyday, non-committee roles a VOLUNTEER fills.
STARTER_ROLES = [
    ("Head Coach", "Coach"),
    ("Junior Coach", "Coach"),
    ("Groundskeeper", "Ground Staff"),
    ("Canteen Manager", "Food & Beverage"),
    ("Bar Steward", "Food & Beverage"),
    ("Scorer", "Other"),
    ("Team Manager", "Other"),
    ("First Aid Officer", "Other"),
    ("Cleaner", "Other"),
    ("Photographer", "Other"),
]

# (title, description) — the elected/appointed COMMITTEE roles. These are the
# same roles the Committee Administration "Positions" tab holds terms against
# (a committee role IS a committee position). Mirrors the old committee starter
# positions so the two catalogues are one.
STARTER_COMMITTEE_ROLES = [
    ("President", "Overall leadership, chairs meetings, primary club spokesperson."),
    ("Vice President", "Deputises for the President; often leads a portfolio area."),
    ("Treasurer", "Club finances, budgets, membership fee oversight, financial reporting."),
    ("Secretary", "Meeting minutes, correspondence, statutory/association paperwork."),
    ("Junior Coordinator", "Junior program — registrations, coaching, grading."),
    ("Senior Coordinator", "Senior teams — registrations, grading, team management."),
    ("Selection Chair", "Chairs the selection panel across grades."),
    ("Coach Coordinator", "Coaching appointments, accreditation, development."),
    ("Grounds Manager", "Ground/wicket preparation and maintenance liaison."),
    ("Equipment Manager", "Club kit, balls, training equipment."),
    ("Bar Manager", "Bar operations, licensing compliance, RSA rostering."),
    ("Volunteer Coordinator", "Recruits and rosters club volunteers."),
    ("Sponsorship Manager", "Sponsor relationships and obligations."),
    ("Social Media Officer", "Club social media and website content."),
]

STARTER_ACTIVITY_TYPES = [
    ("Committee & Administration", "Meetings, paperwork, governance."),
    ("Ground & Equipment", "Ground prep and gear upkeep."),
    ("Coaching & Training", "Coaching sessions and training setup."),
    ("Food & Beverage", "Canteen and bar shifts."),
    ("Match Day", "Match-day duties — scoring, umpiring, setup."),
    ("Fundraising & Events", "Fundraisers and social events."),
    ("Other", "Anything else."),
]

# (title, activity_type_name)
STARTER_ACTIVITIES = [
    ("Committee Meeting", "Committee & Administration"),
    ("Administration / Paperwork", "Committee & Administration"),
    ("Ground Preparation", "Ground & Equipment"),
    ("Equipment Maintenance", "Ground & Equipment"),
    ("Coaching Session", "Coaching & Training"),
    ("Training Setup", "Coaching & Training"),
    ("Canteen Shift", "Food & Beverage"),
    ("Bar Shift", "Food & Beverage"),
    ("Match Day Duty", "Match Day"),
    ("Scoring", "Match Day"),
    ("Umpiring", "Match Day"),
    ("Fundraising Event", "Fundraising & Events"),
    ("Working Bee", "Ground & Equipment"),
    ("Other", "Other"),
]


# ─── Serialisers ─────────────────────────────────────────────────────────────
def _type_dict(t) -> dict:
    return {"id": str(t.id), "name": t.name, "description": t.description,
            "sort_order": t.sort_order, "is_active": t.is_active}


def _role_dict(r: ClubRole, type_name: Optional[str] = None) -> dict:
    return {"id": str(r.id), "title": r.title,
            "role_type_id": str(r.role_type_id) if r.role_type_id else None,
            "role_type_name": type_name, "description": r.description,
            "is_committee": r.is_committee,
            "sort_order": r.sort_order, "is_active": r.is_active}


def _activity_dict(a: ClubActivity, type_name: Optional[str] = None) -> dict:
    return {"id": str(a.id), "title": a.title,
            "activity_type_id": str(a.activity_type_id) if a.activity_type_id else None,
            "activity_type_name": type_name, "description": a.description,
            "sort_order": a.sort_order, "is_active": a.is_active}


# ─── Generic type catalogue helpers (role types + activity types) ────────────
async def _list_types(session: AsyncSession, model, org_id, *, include_inactive: bool) -> list:
    stmt = select(model).where(model.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(model.is_active.is_(True))
    stmt = stmt.order_by(model.sort_order, func.lower(model.name))
    return (await session.execute(stmt)).scalars().all()


async def _create_type(session: AsyncSession, model, org_id, *, name: str,
                       description: Optional[str] = None, sort_order: int = 0):
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(model).where(model.organisation_id == org_id, func.lower(model.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'A type called "{name}" already exists')
    t = model(organisation_id=org_id, name=name[:120], description=description, sort_order=sort_order)
    session.add(t)
    await session.flush()
    return t


async def _get_or_create_type(session: AsyncSession, model, org_id, name: str):
    name = (name or "").strip()
    if not name:
        return None
    existing = (await session.execute(
        select(model).where(model.organisation_id == org_id, func.lower(model.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        return existing
    t = model(organisation_id=org_id, name=name[:120])
    session.add(t)
    await session.flush()
    return t


async def _update_type(session: AsyncSession, t, **fields):
    for f in ("name", "description", "sort_order", "is_active"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    return t


async def _seed_types(session: AsyncSession, model, org_id, rows) -> int:
    existing = {n.lower() for n in (await session.execute(
        select(model.name).where(model.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for i, (name, desc) in enumerate(rows):
        if name.lower() in existing:
            continue
        session.add(model(organisation_id=org_id, name=name, description=desc, sort_order=i))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Roles ───────────────────────────────────────────────────────────────────
async def list_role_types(session, org_id, *, include_inactive=False):
    return await _list_types(session, ClubRoleType, org_id, include_inactive=include_inactive)


async def create_role_type(session, org_id, **kw):
    return await _create_type(session, ClubRoleType, org_id, **kw)


async def update_role_type(session, t, **kw):
    return await _update_type(session, t, **kw)


async def archive_role_type(session, t):
    t.is_active = False


async def seed_starter_role_types(session, org_id) -> int:
    return await _seed_types(session, ClubRoleType, org_id, STARTER_ROLE_TYPES)


async def list_roles(session: AsyncSession, org_id, *, include_inactive: bool = False,
                     committee: Optional[bool] = None) -> list[dict]:
    stmt = (select(ClubRole, ClubRoleType)
            .outerjoin(ClubRoleType, ClubRoleType.id == ClubRole.role_type_id)
            .where(ClubRole.organisation_id == org_id))
    if not include_inactive:
        stmt = stmt.where(ClubRole.is_active.is_(True))
    if committee is not None:
        stmt = stmt.where(ClubRole.is_committee.is_(committee))
    stmt = stmt.order_by(ClubRole.is_committee.desc(), ClubRole.sort_order, func.lower(ClubRole.title))
    rows = (await session.execute(stmt)).all()
    return [_role_dict(r, t.name if t else None) for r, t in rows]


async def create_role(session: AsyncSession, org_id, *, title: str, role_type_id=None,
                      description: Optional[str] = None, is_committee: bool = False) -> ClubRole:
    title = (title or "").strip()
    if not title:
        raise ValueError("Title is required")
    existing = (await session.execute(
        select(ClubRole).where(ClubRole.organisation_id == org_id, func.lower(ClubRole.title) == title.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            if role_type_id is not None:
                existing.role_type_id = role_type_id
            existing.is_committee = is_committee
            return existing
        raise ValueError(f'A role called "{title}" already exists')
    r = ClubRole(organisation_id=org_id, title=title[:200], role_type_id=role_type_id,
                 description=description, is_committee=is_committee)
    session.add(r)
    await session.flush()
    return r


async def update_role(session: AsyncSession, r: ClubRole, **fields) -> ClubRole:
    for f in ("title", "description", "sort_order", "is_active", "is_committee"):
        if f in fields and fields[f] is not None:
            setattr(r, f, fields[f])
    if "role_type_id" in fields:
        r.role_type_id = fields["role_type_id"]
    return r


async def archive_role(session: AsyncSession, r: ClubRole) -> None:
    r.is_active = False


async def seed_starter_roles(session: AsyncSession, org_id, *, committee: bool = False) -> int:
    """Seed a starter set of roles. committee=True seeds the elected/appointed
    COMMITTEE roles (which the Committee Positions tab holds terms against);
    committee=False seeds everyday volunteer roles + the role-type starter set."""
    existing_titles = {t.lower() for t in (await session.execute(
        select(ClubRole.title).where(ClubRole.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    if committee:
        for i, (title, desc) in enumerate(STARTER_COMMITTEE_ROLES):
            if title.lower() in existing_titles:
                continue
            rtype = await _get_or_create_type(session, ClubRoleType, org_id, "Committee Member")
            session.add(ClubRole(organisation_id=org_id, title=title, description=desc,
                                 role_type_id=rtype.id if rtype else None, is_committee=True, sort_order=i))
            seeded += 1
    else:
        await seed_starter_role_types(session, org_id)
        for i, (title, type_name) in enumerate(STARTER_ROLES):
            if title.lower() in existing_titles:
                continue
            rtype = await _get_or_create_type(session, ClubRoleType, org_id, type_name)
            session.add(ClubRole(organisation_id=org_id, title=title,
                                 role_type_id=rtype.id if rtype else None, sort_order=i))
            seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Activities ──────────────────────────────────────────────────────────────
async def list_activity_types(session, org_id, *, include_inactive=False):
    return await _list_types(session, ClubActivityType, org_id, include_inactive=include_inactive)


async def create_activity_type(session, org_id, **kw):
    return await _create_type(session, ClubActivityType, org_id, **kw)


async def update_activity_type(session, t, **kw):
    return await _update_type(session, t, **kw)


async def archive_activity_type(session, t):
    t.is_active = False


async def seed_starter_activity_types(session, org_id) -> int:
    return await _seed_types(session, ClubActivityType, org_id, STARTER_ACTIVITY_TYPES)


async def list_activities(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[dict]:
    stmt = (select(ClubActivity, ClubActivityType)
            .outerjoin(ClubActivityType, ClubActivityType.id == ClubActivity.activity_type_id)
            .where(ClubActivity.organisation_id == org_id))
    if not include_inactive:
        stmt = stmt.where(ClubActivity.is_active.is_(True))
    stmt = stmt.order_by(ClubActivity.sort_order, func.lower(ClubActivity.title))
    rows = (await session.execute(stmt)).all()
    return [_activity_dict(a, t.name if t else None) for a, t in rows]


async def create_activity(session: AsyncSession, org_id, *, title: str, activity_type_id=None,
                          description: Optional[str] = None) -> ClubActivity:
    title = (title or "").strip()
    if not title:
        raise ValueError("Title is required")
    existing = (await session.execute(
        select(ClubActivity).where(ClubActivity.organisation_id == org_id, func.lower(ClubActivity.title) == title.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            if activity_type_id is not None:
                existing.activity_type_id = activity_type_id
            return existing
        raise ValueError(f'An activity called "{title}" already exists')
    a = ClubActivity(organisation_id=org_id, title=title[:200], activity_type_id=activity_type_id, description=description)
    session.add(a)
    await session.flush()
    return a


async def update_activity(session: AsyncSession, a: ClubActivity, **fields) -> ClubActivity:
    for f in ("title", "activity_type_id", "description", "sort_order", "is_active"):
        if f in fields and fields[f] is not None:
            setattr(a, f, fields[f])
    return a


async def archive_activity(session: AsyncSession, a: ClubActivity) -> None:
    a.is_active = False


async def seed_starter_activities(session: AsyncSession, org_id) -> int:
    """Seeds the starter activity types AND a set of common activities."""
    await seed_starter_activity_types(session, org_id)
    existing_titles = {t.lower() for t in (await session.execute(
        select(ClubActivity.title).where(ClubActivity.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for i, (title, type_name) in enumerate(STARTER_ACTIVITIES):
        if title.lower() in existing_titles:
            continue
        atype = await _get_or_create_type(session, ClubActivityType, org_id, type_name)
        session.add(ClubActivity(organisation_id=org_id, title=title,
                                 activity_type_id=atype.id if atype else None, sort_order=i))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded
