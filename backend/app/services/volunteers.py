"""Volunteer Management — profiles, availability, interests, and an hours ledger.

Reuses ``fee_members`` as "the person" (same as Membership Management and
Committee Administration) — a volunteer is a FeeMember whose profile carries
role interests and availability. Hours are a plain append-only ledger, summed
on read.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import VolunteerProfile, VolunteerHours, FeeMember, VolunteerRole, ClubRole, ClubActivity


def _profile_dict(p: VolunteerProfile) -> dict:
    return {
        "id": str(p.id), "member_id": str(p.member_id),
        "roles_interested": p.roles_interested or [],
        "available_days": p.available_days or [],
        "lives_nearby": p.lives_nearby, "notes": p.notes,
    }


async def get_profile(session: AsyncSession, org_id, member_id) -> Optional[VolunteerProfile]:
    return (await session.execute(
        select(VolunteerProfile).where(VolunteerProfile.organisation_id == org_id, VolunteerProfile.member_id == member_id)
    )).scalars().first()


async def upsert_profile(session: AsyncSession, org_id, member_id, **fields) -> VolunteerProfile:
    p = await get_profile(session, org_id, member_id)
    if p is None:
        p = VolunteerProfile(organisation_id=org_id, member_id=member_id)
        session.add(p)
    for f in ("roles_interested", "available_days", "lives_nearby", "notes"):
        if f in fields and fields[f] is not None:
            setattr(p, f, fields[f])
    p.updated_at = func.now()
    await session.flush()
    return p


async def _roles_by_member(session: AsyncSession, org_id) -> dict:
    """member_id -> [{id, title}] of the assigned (active) roles."""
    rows = (await session.execute(
        select(VolunteerRole.member_id, ClubRole.id, ClubRole.title)
        .join(ClubRole, ClubRole.id == VolunteerRole.role_id)
        .where(VolunteerRole.organisation_id == org_id)
        .order_by(func.lower(ClubRole.title))
    )).all()
    out: dict = {}
    for member_id, role_id, title in rows:
        out.setdefault(member_id, []).append({"id": str(role_id), "title": title})
    return out


async def member_role_ids(session: AsyncSession, org_id, member_id) -> list[str]:
    rows = (await session.execute(
        select(VolunteerRole.role_id).where(
            VolunteerRole.organisation_id == org_id, VolunteerRole.member_id == member_id)
    )).scalars().all()
    return [str(r) for r in rows]


async def set_member_roles(session: AsyncSession, org_id, member_id, role_ids) -> None:
    """Replace the volunteer's assigned roles with ``role_ids`` (a set of
    ClubRole ids belonging to this org)."""
    wanted = set()
    for rid in (role_ids or []):
        role = await session.get(ClubRole, rid)
        if role is not None and role.organisation_id == org_id:
            wanted.add(role.id)
    await session.execute(delete(VolunteerRole).where(
        VolunteerRole.organisation_id == org_id, VolunteerRole.member_id == member_id))
    for rid in wanted:
        session.add(VolunteerRole(organisation_id=org_id, member_id=member_id, role_id=rid))
    await session.flush()


async def directory(session: AsyncSession, org_id) -> list[dict]:
    """Every volunteer profile with their member name, assigned roles and total
    logged hours — the volunteer directory's one fetch. Filtering (role/day) is
    done client-side over this list, which stays small enough per club."""
    rows = (await session.execute(
        select(VolunteerProfile, FeeMember).join(FeeMember, FeeMember.id == VolunteerProfile.member_id)
        .where(VolunteerProfile.organisation_id == org_id)
        .order_by(func.lower(FeeMember.full_name))
    )).all()
    hours_map = dict((await session.execute(
        select(VolunteerHours.member_id, func.coalesce(func.sum(VolunteerHours.hours), 0))
        .where(VolunteerHours.organisation_id == org_id).group_by(VolunteerHours.member_id)
    )).all())
    roles_map = await _roles_by_member(session, org_id)
    out = []
    for profile, member in rows:
        d = _profile_dict(profile)
        d["full_name"] = member.full_name
        d["email"] = member.email
        d["mobile"] = member.mobile
        d["total_hours"] = float(hours_map.get(member.id, 0) or 0)
        d["roles"] = roles_map.get(member.id, [])
        out.append(d)
    return out


async def list_hours(session: AsyncSession, org_id, member_id) -> list[dict]:
    rows = (await session.execute(
        select(VolunteerHours, ClubActivity)
        .outerjoin(ClubActivity, ClubActivity.id == VolunteerHours.activity_id)
        .where(VolunteerHours.organisation_id == org_id, VolunteerHours.member_id == member_id)
        .order_by(VolunteerHours.logged_date.desc())
    )).all()
    out = []
    for h, act in rows:
        out.append({
            "id": str(h.id), "logged_date": h.logged_date.isoformat() if h.logged_date else None,
            "hours": float(h.hours),
            "activity_id": str(h.activity_id) if h.activity_id else None,
            # Prefer the catalogue activity title, else the free-text label.
            "activity": (act.title if act else None) or h.activity,
            "notes": h.notes,
        })
    return out


async def log_hours(session: AsyncSession, org_id, member_id, *, hours: float, logged_date=None,
                    activity: Optional[str] = None, activity_id=None, notes: Optional[str] = None,
                    created_by_user_id=None) -> VolunteerHours:
    if hours is None or hours <= 0:
        raise ValueError("Hours must be greater than 0")
    if activity_id is not None:
        act = await session.get(ClubActivity, activity_id)
        if act is None or act.organisation_id != org_id:
            raise ValueError("Activity not found")
    h = VolunteerHours(
        organisation_id=org_id, member_id=member_id, hours=hours,
        logged_date=logged_date or date.today(), activity=activity, activity_id=activity_id, notes=notes,
        created_by_user_id=created_by_user_id,
    )
    session.add(h)
    await session.flush()
    return h


async def delete_hours(session: AsyncSession, h: VolunteerHours) -> None:
    await session.delete(h)
