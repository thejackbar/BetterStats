"""Volunteer Management — profiles, availability, interests, and an hours ledger.

Reuses ``fee_members`` as "the person" (same as Membership Management and
Committee Administration) — a volunteer is a FeeMember whose profile carries
role interests and availability. Hours are a plain append-only ledger, summed
on read.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import VolunteerProfile, VolunteerHours, FeeMember


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


async def directory(session: AsyncSession, org_id) -> list[dict]:
    """Every volunteer profile with their member name and total logged hours
    — the volunteer directory's one fetch. Filtering (role/day/qualified) is
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
    out = []
    for profile, member in rows:
        d = _profile_dict(profile)
        d["full_name"] = member.full_name
        d["email"] = member.email
        d["mobile"] = member.mobile
        d["total_hours"] = float(hours_map.get(member.id, 0) or 0)
        out.append(d)
    return out


async def list_hours(session: AsyncSession, org_id, member_id) -> list[VolunteerHours]:
    return (await session.execute(
        select(VolunteerHours).where(VolunteerHours.organisation_id == org_id, VolunteerHours.member_id == member_id)
        .order_by(VolunteerHours.logged_date.desc())
    )).scalars().all()


async def log_hours(session: AsyncSession, org_id, member_id, *, hours: float, logged_date=None,
                    activity: Optional[str] = None, notes: Optional[str] = None,
                    created_by_user_id=None) -> VolunteerHours:
    if hours is None or hours <= 0:
        raise ValueError("Hours must be greater than 0")
    h = VolunteerHours(
        organisation_id=org_id, member_id=member_id, hours=hours,
        logged_date=logged_date or date.today(), activity=activity, notes=notes,
        created_by_user_id=created_by_user_id,
    )
    session.add(h)
    await session.flush()
    return h


async def delete_hours(session: AsyncSession, h: VolunteerHours) -> None:
    await session.delete(h)
