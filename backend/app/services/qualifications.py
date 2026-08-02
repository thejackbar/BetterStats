"""Qualification Management — WWCC, First Aid, coach/umpire/scorer accreditation.

A club-adopted catalogue (nothing auto-seeded), same posture as membership
types and committee positions. Recording a qualification computes its expiry
from the TYPE's default validity period at that moment — editing the type's
validity later does not retroactively change already-recorded expiry dates
(a qualification's expiry is a fact about when it was recorded, not a live
formula), which also means a club changing its default validity going
forward never silently alters someone's already-issued certificate dates.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import QualificationType, MemberQualification, FeeMember, QualificationRole, ClubRole

# (name, description, validity_months) — validity is a sensible DEFAULT the
# club can edit; actual renewal cycles vary by state/association.
STARTER_TYPES = [
    ("Working With Children Check", "State-based child safety clearance.", 60),
    ("First Aid", "Current first aid certificate.", 36),
    ("RSA", "Responsible Service of Alcohol certificate.", None),
    ("Coach Accreditation", "Cricket coaching accreditation (any level).", None),
    ("Umpire Accreditation", "Panel/club umpire accreditation.", 12),
    ("Scorer Accreditation", "Club or association scorer accreditation.", None),
]


def _type_dict(t: QualificationType) -> dict:
    return {
        "id": str(t.id), "name": t.name, "description": t.description,
        "validity_months": t.validity_months, "sort_order": t.sort_order, "is_active": t.is_active,
    }


def _months_from(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _qual_dict(q: MemberQualification, type_name: Optional[str] = None) -> dict:
    today = date.today()
    return {
        "id": str(q.id), "member_id": str(q.member_id), "qualification_type_id": str(q.qualification_type_id),
        "type_name": type_name,
        "obtained_at": q.obtained_at.isoformat() if q.obtained_at else None,
        "expires_at": q.expires_at.isoformat() if q.expires_at else None,
        "is_expired": bool(q.expires_at and q.expires_at < today),
        "expires_soon": bool(q.expires_at and today <= q.expires_at <= today + timedelta(days=60)),
        "certificate_ref": q.certificate_ref, "notes": q.notes,
    }


# ─── Types ────────────────────────────────────────────────────────────────────

async def list_types(session: AsyncSession, org_id, *, include_inactive: bool = False) -> list[QualificationType]:
    stmt = select(QualificationType).where(QualificationType.organisation_id == org_id)
    if not include_inactive:
        stmt = stmt.where(QualificationType.is_active.is_(True))
    stmt = stmt.order_by(QualificationType.sort_order, func.lower(QualificationType.name))
    return (await session.execute(stmt)).scalars().all()


async def create_type(session: AsyncSession, org_id, *, name: str, description: Optional[str] = None,
                      validity_months: Optional[int] = None, sort_order: int = 0) -> QualificationType:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    existing = (await session.execute(
        select(QualificationType).where(QualificationType.organisation_id == org_id,
                                        func.lower(QualificationType.name) == name.lower())
    )).scalars().first()
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            return existing
        raise ValueError(f'A qualification type called "{name}" already exists')
    t = QualificationType(organisation_id=org_id, name=name[:120], description=description,
                          validity_months=validity_months, sort_order=sort_order)
    session.add(t)
    await session.flush()
    return t


async def update_type(session: AsyncSession, t: QualificationType, **fields) -> QualificationType:
    for f in ("name", "description", "validity_months", "sort_order"):
        if f in fields and fields[f] is not None:
            setattr(t, f, fields[f])
    return t


async def archive_type(session: AsyncSession, t: QualificationType) -> None:
    t.is_active = False


async def seed_starter_types(session: AsyncSession, org_id) -> int:
    # Keyed by lower(name) so an archived starter type is REACTIVATED rather than
    # skipped (matching create_type) — a skip would leave the active list empty
    # and the seed button look like it did nothing.
    existing = {t.name.lower(): t for t in (await session.execute(
        select(QualificationType).where(QualificationType.organisation_id == org_id)
    )).scalars().all()}
    seeded = 0
    for position, (name, desc, validity) in enumerate(STARTER_TYPES):
        cur = existing.get(name.lower())
        if cur is not None:
            if not cur.is_active:
                cur.is_active = True; seeded += 1
            continue
        session.add(QualificationType(organisation_id=org_id, name=name, description=desc,
                                      validity_months=validity, sort_order=position))
        seeded += 1
    if seeded:
        await session.flush()
    return seeded


# ─── Qualification ↔ role links ──────────────────────────────────────────────

async def _roles_by_qualification(session: AsyncSession, org_id, qualification_ids) -> dict:
    """qualification_id -> [{id, title}] for the given qualification ids."""
    if not qualification_ids:
        return {}
    rows = (await session.execute(
        select(QualificationRole.qualification_id, ClubRole.id, ClubRole.title)
        .join(ClubRole, ClubRole.id == QualificationRole.role_id)
        .where(QualificationRole.organisation_id == org_id,
               QualificationRole.qualification_id.in_(qualification_ids))
        .order_by(func.lower(ClubRole.title))
    )).all()
    out: dict = {}
    for qid, role_id, title in rows:
        out.setdefault(qid, []).append({"id": str(role_id), "title": title})
    return out


async def set_qualification_roles(session: AsyncSession, org_id, qualification_id, role_ids) -> None:
    wanted = set()
    for rid in (role_ids or []):
        role = await session.get(ClubRole, rid)
        if role is not None and role.organisation_id == org_id:
            wanted.add(role.id)
    await session.execute(delete(QualificationRole).where(
        QualificationRole.organisation_id == org_id, QualificationRole.qualification_id == qualification_id))
    for rid in wanted:
        session.add(QualificationRole(organisation_id=org_id, qualification_id=qualification_id, role_id=rid))
    await session.flush()


# ─── Member qualifications ───────────────────────────────────────────────────

async def list_member_qualifications(session: AsyncSession, org_id, member_id) -> list[dict]:
    rows = (await session.execute(
        select(MemberQualification, QualificationType)
        .join(QualificationType, QualificationType.id == MemberQualification.qualification_type_id)
        .where(MemberQualification.organisation_id == org_id, MemberQualification.member_id == member_id)
        .order_by(QualificationType.name)
    )).all()
    roles_map = await _roles_by_qualification(session, org_id, [q.id for q, _ in rows])
    out = []
    for q, t in rows:
        d = _qual_dict(q, t.name)
        d["roles"] = roles_map.get(q.id, [])
        out.append(d)
    return out


async def add_qualification(session: AsyncSession, org_id, member_id, qualification_type_id, *,
                            obtained_at: Optional[date] = None, certificate_ref: Optional[str] = None,
                            notes: Optional[str] = None, role_ids=None) -> MemberQualification:
    qtype = await session.get(QualificationType, qualification_type_id)
    if qtype is None or str(qtype.organisation_id) != str(org_id):
        raise ValueError("Qualification type not found")
    obtained = obtained_at or date.today()
    expires_at = _months_from(obtained, qtype.validity_months) if qtype.validity_months else None
    q = MemberQualification(
        organisation_id=org_id, member_id=member_id, qualification_type_id=qtype.id,
        obtained_at=obtained, expires_at=expires_at, certificate_ref=certificate_ref, notes=notes,
    )
    session.add(q)
    await session.flush()
    if role_ids is not None:
        await set_qualification_roles(session, org_id, q.id, role_ids)
    return q


async def update_qualification(session: AsyncSession, q: MemberQualification, **fields) -> MemberQualification:
    for f in ("obtained_at", "expires_at", "certificate_ref", "notes"):
        if f in fields and fields[f] is not None:
            setattr(q, f, fields[f])
    q.updated_at = func.now()
    return q


async def delete_qualification(session: AsyncSession, q: MemberQualification) -> None:
    await session.delete(q)


async def expiring_report(session: AsyncSession, org_id, *, within_days: int = 60) -> dict:
    """Everyone whose qualification has expired or expires within
    ``within_days`` — the "automatic reminder" surface (no scheduled email
    sweep is built; this is the read-time view an admin checks)."""
    cutoff = date.today() + timedelta(days=within_days)
    rows = (await session.execute(
        select(MemberQualification, QualificationType, FeeMember)
        .join(QualificationType, QualificationType.id == MemberQualification.qualification_type_id)
        .join(FeeMember, FeeMember.id == MemberQualification.member_id)
        .where(MemberQualification.organisation_id == org_id,
              MemberQualification.expires_at.isnot(None), MemberQualification.expires_at <= cutoff)
        .order_by(MemberQualification.expires_at)
    )).all()
    out = []
    for q, t, m in rows:
        d = _qual_dict(q, t.name)
        d["full_name"] = m.full_name
        out.append(d)
    return {"within_days": within_days, "qualifications": out}
