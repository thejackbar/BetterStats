"""Fee tracking API (Phases 1–3).

Membership tiers, members + per-season tiers, auto-derived match days, grade
fee-format overrides, payments, status + reports, and the Phase-3 conveniences:
season rollover, bulk tier assignment, and bank-statement CSV import.

Everything is scoped to the caller's club (get_current_club) and gated by the
MANAGE_FEES capability. Match fee = days_played × tier.match_day_rate.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from jose import jwt
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.config.settings import settings
from app.models.db import (
    User, Organisation, Season, Grade, Game, Player,
    FeeSchedule, FeeMember, FeeMemberSeason, FeeMatchDay, FeePayment,
    FeeSquareImportLog, MerchSquareConnection,
    FeeXeroConnection, FeeXeroImportLog, MembershipType,
    FEE_PAYMENT_TYPES, FEE_FORMATS, MEMBERSHIP_STATUSES, get_db,
)
from app.routers.auth import get_current_user, get_current_club
from app.auth.capabilities import (
    require_cap, require_any_cap, MANAGE_FEES, MANAGE_VOLUNTEERS, MANAGE_QUALIFICATIONS,
    MANAGE_COMMITTEE, MANAGE_ASSETS, MANAGE_CLUB_DIARY,
)
from app.services import fees as fee_service
from app.services import members as members_svc
from app.services import fees_square as fee_square_service
from app.services import fees_xero as fee_xero_service
from app.services import membership_types as membership_types_service
from app.services import square_client, square_sync
from app.services import xero_client

router = APIRouter(prefix="/club-admin/fees", tags=["club-admin-fees"])

_require = Depends(require_cap(MANAGE_FEES))

# Signed state for the Xero OAuth handshake — ties the public callback back to
# the club + user that started it, and self-expires. Mirrors merch.py's
# sign_square_state; Xero's connect flow lives entirely in this router (unlike
# Square, nothing else uses this connection) so it's defined here rather than
# in a separate module.
XERO_STATE_TYP = "xero_oauth"


def sign_xero_state(org_id, user_id) -> str:
    payload = {
        "org": str(org_id),
        "uid": str(user_id),
        "typ": XERO_STATE_TYP,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=20),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

# Bank-statement-friendly payment kinds + methods. Free-form 'Other' is allowed.
PAYMENT_KINDS = ("membership", "match_day")
PAYMENT_METHODS = ("EFT", "Cash", "PlayHQ", "Comp", "Other")


# _f/_financials now live in services/fees.py (extracted, not duplicated) so
# the member-portal "my fees" view computes from the exact same functions —
# aliased back here under their original names so every existing call site
# below is unchanged.
_f = fee_service._f
_financials = fee_service._financials


def _money(raw) -> Decimal:
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Invalid amount")


async def _season_or_404(db: AsyncSession, club: Organisation, season_id: str) -> Season:
    try:
        sid = uuid.UUID(season_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid season_id")
    season = await db.get(Season, sid)
    if not season or season.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Season not found")
    return season


# ───────────────────────────────────────────────────────────────────────────
# Fee schedule (rate card)
# ───────────────────────────────────────────────────────────────────────────

def _schedule_out(s: FeeSchedule) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "payment_type": s.payment_type,
        "membership_amount": _f(s.membership_amount),
        "match_day_rate": _f(s.match_day_rate),
        "display_order": s.display_order,
        "is_active": s.is_active,
    }


@router.get("/schedule")
async def list_schedule(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeeSchedule)
        .where(FeeSchedule.season_id == uuid.UUID(season_id))
        .order_by(FeeSchedule.display_order, FeeSchedule.name)
    )).scalars().all()
    return [_schedule_out(s) for s in rows]


class ScheduleCreate(BaseModel):
    season_id: str
    name: str
    payment_type: str = "standard"
    membership_amount: float = 0
    match_day_rate: float = 0


@router.post("/schedule")
async def create_schedule(
    data: ScheduleCreate,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, data.season_id)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    if data.payment_type not in FEE_PAYMENT_TYPES:
        raise HTTPException(status_code=422, detail=f"payment_type must be one of {FEE_PAYMENT_TYPES}")
    dup = (await db.execute(select(FeeSchedule).where(
        FeeSchedule.season_id == season.id, func.lower(FeeSchedule.name) == name.lower()
    ))).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="A tier with that name already exists this season")
    max_order = (await db.execute(select(func.coalesce(func.max(FeeSchedule.display_order), -1)).where(
        FeeSchedule.season_id == season.id
    ))).scalar_one()
    s = FeeSchedule(
        id=uuid.uuid4(), organisation_id=club.id, season_id=season.id, name=name,
        payment_type=data.payment_type, membership_amount=_money(data.membership_amount),
        match_day_rate=_money(data.match_day_rate), display_order=int(max_order) + 1,
    )
    db.add(s)
    await db.commit()
    return _schedule_out(s)


class SchedulePatch(BaseModel):
    name: Optional[str] = None
    payment_type: Optional[str] = None
    membership_amount: Optional[float] = None
    match_day_rate: Optional[float] = None
    is_active: Optional[bool] = None


@router.patch("/schedule/{schedule_id}")
async def patch_schedule(
    schedule_id: str,
    data: SchedulePatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    s = await db.get(FeeSchedule, uuid.UUID(schedule_id))
    if not s or s.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Tier not found")
    if data.name is not None:
        s.name = data.name.strip() or s.name
    if data.payment_type is not None:
        if data.payment_type not in FEE_PAYMENT_TYPES:
            raise HTTPException(status_code=422, detail=f"payment_type must be one of {FEE_PAYMENT_TYPES}")
        s.payment_type = data.payment_type
    if data.membership_amount is not None:
        s.membership_amount = _money(data.membership_amount)
    if data.match_day_rate is not None:
        s.match_day_rate = _money(data.match_day_rate)
    if data.is_active is not None:
        s.is_active = data.is_active
    await db.commit()
    return _schedule_out(s)


@router.delete("/schedule/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    s = await db.get(FeeSchedule, uuid.UUID(schedule_id))
    if not s or s.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Tier not found")
    # Members on this tier are set back to "needs tier" (FK is ON DELETE SET NULL).
    await db.delete(s)
    await db.commit()
    return {"ok": True}


@router.post("/schedule/seed-defaults")
async def seed_defaults(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, season_id)
    created = await fee_service.seed_default_schedule(db, club.id, season.id)
    await db.commit()
    return {"created": created}


class ScheduleCopy(BaseModel):
    season_id: str
    from_season_id: str


@router.post("/schedule/copy-from")
async def copy_schedule(
    data: ScheduleCopy,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    dest = await _season_or_404(db, club, data.season_id)
    src = await _season_or_404(db, club, data.from_season_id)
    existing = {
        (s.name or "").strip().lower() for s in (
            await db.execute(select(FeeSchedule).where(FeeSchedule.season_id == dest.id))
        ).scalars().all()
    }
    src_rows = (await db.execute(
        select(FeeSchedule).where(FeeSchedule.season_id == src.id).order_by(FeeSchedule.display_order)
    )).scalars().all()
    created = 0
    for s in src_rows:
        if (s.name or "").strip().lower() in existing:
            continue
        db.add(FeeSchedule(
            id=uuid.uuid4(), organisation_id=club.id, season_id=dest.id, name=s.name,
            payment_type=s.payment_type, membership_amount=s.membership_amount,
            match_day_rate=s.match_day_rate, display_order=s.display_order, is_active=s.is_active,
        ))
        created += 1
    await db.commit()
    return {"created": created}


# ───────────────────────────────────────────────────────────────────────────
# Grade fee-format overrides
# ───────────────────────────────────────────────────────────────────────────

@router.get("/grades")
async def list_grades(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, season_id)
    grades = (await db.execute(
        select(Grade).where(Grade.season_id == season.id).order_by(Grade.name)
    )).scalars().all()
    # Per-grade format breakdown so the admin can see what each grade is before
    # tagging it (e.g. spotting which "One Day" grades are actually women's).
    breakdown = (await db.execute(
        select(Game.grade_id, Game.match_format, func.count(Game.id))
        .join(Grade, Game.grade_id == Grade.id)
        .where(Grade.season_id == season.id)
        .group_by(Game.grade_id, Game.match_format)
    )).all()
    by_grade: dict = {}
    for gid, mf, cnt in breakdown:
        by_grade.setdefault(gid, []).append({"match_format": mf or "Unknown", "games": cnt})
    return [
        {
            "id": str(g.id),
            "name": g.display_name,
            "fee_format": g.fee_format,  # None = auto
            "formats": sorted(by_grade.get(g.id, []), key=lambda x: -x["games"]),
            "games": sum(x["games"] for x in by_grade.get(g.id, [])),
        }
        for g in grades
    ]


class GradeFormatPatch(BaseModel):
    fee_format: Optional[str] = None  # None / "" clears the override (auto)


@router.patch("/grades/{grade_id}")
async def patch_grade_format(
    grade_id: str,
    data: GradeFormatPatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    g = await db.get(Grade, uuid.UUID(grade_id))
    if not g:
        raise HTTPException(status_code=404, detail="Grade not found")
    season = await db.get(Season, g.season_id)
    if not season or season.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Grade not found")
    ff = (data.fee_format or "").strip().lower() or None
    if ff is not None and ff not in FEE_FORMATS:
        raise HTTPException(status_code=422, detail=f"fee_format must be one of {FEE_FORMATS} or null")
    g.fee_format = ff
    await db.commit()
    return {"id": str(g.id), "fee_format": g.fee_format}


# ───────────────────────────────────────────────────────────────────────────
# Members
# ───────────────────────────────────────────────────────────────────────────

async def _days_by_member_season(db: AsyncSession, season_id) -> dict:
    rows = (await db.execute(
        select(FeeMatchDay.member_season_id, func.coalesce(func.sum(FeeMatchDay.days_played), 0))
        .join(FeeMemberSeason, FeeMatchDay.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id)
        .group_by(FeeMatchDay.member_season_id)
    )).all()
    return {ms_id: float(days) for ms_id, days in rows}


async def _waived_days_by_member_season(db: AsyncSession, season_id) -> dict:
    """Sum days_played of waived games per member-season. Used to drop waived
    fees out of match_fee_payable so a fully-waived member reads Financial."""
    rows = (await db.execute(
        select(FeeMatchDay.member_season_id, func.coalesce(func.sum(FeeMatchDay.days_played), 0))
        .join(FeeMemberSeason, FeeMatchDay.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id, FeeMatchDay.waived_at.isnot(None))
        .group_by(FeeMatchDay.member_season_id)
    )).all()
    return {ms_id: float(days) for ms_id, days in rows}


async def _paid_by_member_season(db: AsyncSession, season_id) -> dict:
    """Sum payments grouped by (member_season_id, kind). Returns
    {ms_id: {'membership': X, 'match_day': Y}}."""
    rows = (await db.execute(
        select(FeePayment.member_season_id, FeePayment.kind, func.coalesce(func.sum(FeePayment.amount), 0))
        .join(FeeMemberSeason, FeePayment.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id)
        .group_by(FeePayment.member_season_id, FeePayment.kind)
    )).all()
    out: dict = {}
    for ms_id, kind, amount in rows:
        out.setdefault(ms_id, {"membership": 0.0, "match_day": 0.0})[kind] = float(amount)
    return out


# ───────────────────────────────────────────────────────────────────────────
# Membership types (migration 175) — the cross-season catalogue a member's
# membership_type_id points at. Distinct from FeeSchedule (the per-season $
# tier) — see services/membership_types.py.
# ───────────────────────────────────────────────────────────────────────────

@router.get("/membership-types")
async def list_membership_types(
    include_inactive: bool = False,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    return {"types": await membership_types_service.list_types(db, club.id, include_inactive=include_inactive)}


class MembershipTypeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    default_annual_fee: Optional[float] = None
    is_playing: bool = False
    requires_voting_rights: bool = False
    requires_insurance: bool = False
    requires_wwcc: bool = False
    requires_playhq_registration: bool = False
    comms_group: Optional[str] = None
    sort_order: int = 0


@router.post("/membership-types")
async def create_membership_type(
    data: MembershipTypeCreate,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    try:
        t = await membership_types_service.create_type(db, club.id, **data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return membership_types_service._dict(t)


class MembershipTypePatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_annual_fee: Optional[float] = None
    is_playing: Optional[bool] = None
    requires_voting_rights: Optional[bool] = None
    requires_insurance: Optional[bool] = None
    requires_wwcc: Optional[bool] = None
    requires_playhq_registration: Optional[bool] = None
    comms_group: Optional[str] = None
    sort_order: Optional[int] = None


@router.patch("/membership-types/{type_id}")
async def update_membership_type(
    type_id: str,
    data: MembershipTypePatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    t = await db.get(MembershipType, uuid.UUID(type_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Membership type not found")
    fields = data.model_dump(exclude_unset=True)
    if "name" in fields and fields["name"]:
        t.name = fields.pop("name").strip()[:120]
    await membership_types_service.update_type(db, t, **fields)
    await db.commit()
    return membership_types_service._dict(t)


@router.delete("/membership-types/{type_id}")
async def archive_membership_type(
    type_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    t = await db.get(MembershipType, uuid.UUID(type_id))
    if not t or t.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Membership type not found")
    await membership_types_service.archive_type(db, t)
    await db.commit()
    return {"archived": True}


@router.post("/membership-types/seed-starter")
async def seed_starter_membership_types(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    seeded = await membership_types_service.seed_starter_types(db, club.id)
    await db.commit()
    return {"seeded": seeded}


# Every fee-paying person in the club, regardless of season — the shared
# member/person picker used across BetterClubManager (Volunteers, Qualifications,
# Event organiser, Booking owner, Club Diary responsibility). Readable by any of
# those tools' capabilities, not just MANAGE_FEES.
_PEOPLE_CAPS = require_any_cap(
    MANAGE_FEES, MANAGE_VOLUNTEERS, MANAGE_QUALIFICATIONS,
    MANAGE_COMMITTEE, MANAGE_ASSETS, MANAGE_CLUB_DIARY)


@router.get("/all-members")
async def list_all_members(
    _: User = Depends(_PEOPLE_CAPS),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Everyone the club holds a member row for.

    Archived people are returned, flagged `archived`. They are not offered for
    anything new (the pickers drop them), but a record that already names one
    has to keep resolving to a name rather than showing a dash.
    """
    rows = (await db.execute(
        select(FeeMember).where(FeeMember.organisation_id == club.id)
        .order_by(func.lower(FeeMember.full_name))
    )).scalars().all()
    return {"members": [
        {"member_id": str(m.id), "full_name": m.full_name, "email": m.email, "mobile": m.mobile,
         "player_id": str(m.player_id) if m.player_id else None, "is_linked": m.player_id is not None,
         "archived": m.archived_at is not None, "needs_member": False}
        for m in rows
    ]}


@router.get("/people/search")
async def search_people(
    q: str = "",
    limit: int = 20,
    _: User = Depends(_PEOPLE_CAPS),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Find a person by typing their name — members AND the club's players who
    have no member row yet.

    A picker that has to offer everyone cannot ship everyone: a club with
    fifteen hundred people would send the whole roster to the browser to draw a
    dropdown somebody is about to type into anyway. So the search runs here and
    only the matches come back.

    A player with no member row comes back with `member_id: null` and
    `needs_member: true` — they are a real person the club can pick, but a
    member row has to be minted before anything can be linked to them.
    Archived people are never offered.
    """
    term = (q or "").strip()
    if not term:
        return {"people": [], "query": ""}
    limit = max(1, min(limit, 50))
    like = f"%{term.lower()}%"
    # Org-scoped on both sides of the read-through: a member row may point at
    # ANOTHER club's player, and a player of ours must not be judged "already
    # enrolled" by someone else's member row.
    rows = (await db.execute(text("""
        SELECT fm.id AS member_id, fm.full_name, fm.email, fm.mobile,
               fm.player_id, false AS needs_member
        FROM fee_members fm
        WHERE fm.organisation_id = :org
          AND fm.archived_at IS NULL
          AND LOWER(fm.full_name) LIKE :like
        UNION ALL
        SELECT NULL, COALESCE(p.display_name_override, p.name), p.email, p.phone,
               p.id, true
        FROM players p
        WHERE p.organisation_id = :org
          AND LOWER(COALESCE(p.display_name_override, p.name)) LIKE :like
          AND NOT EXISTS (
              SELECT 1 FROM fee_members fm
              WHERE fm.player_id = p.id AND fm.organisation_id = :org
          )
        ORDER BY 2
        LIMIT :lim
    """), {"org": club.id, "like": like, "lim": limit + 1})).mappings().all()
    people = [
        {"member_id": str(r["member_id"]) if r["member_id"] else None,
         "full_name": r["full_name"], "email": r["email"], "mobile": r["mobile"],
         "player_id": str(r["player_id"]) if r["player_id"] else None,
         "is_linked": r["player_id"] is not None,
         "archived": False, "needs_member": bool(r["needs_member"])}
        for r in rows[:limit]
    ]
    # One row over the limit was asked for purely to answer "is that all of
    # them", without a second COUNT over the same predicate.
    return {"people": people, "query": term, "more": len(rows) > limit}


@router.get("/members")
async def list_members(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeeMemberSeason, FeeMember, FeeSchedule)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == season.id)
        .order_by(func.lower(FeeMember.full_name))
    )).all()
    days_map = await _days_by_member_season(db, season.id)
    paid_map = await _paid_by_member_season(db, season.id)
    waived_map = await _waived_days_by_member_season(db, season.id)

    members = []
    summary = {
        "total_members": 0, "needs_tier": 0, "non_financial": 0,
        "membership_payable": 0.0, "match_fee_payable": 0.0, "total_payable": 0.0,
        "membership_paid": 0.0, "match_fee_paid": 0.0, "total_paid": 0.0,
        "membership_outstanding": 0.0, "match_fee_outstanding": 0.0, "total_outstanding": 0.0,
        "membership_credit": 0.0, "match_fee_credit": 0.0, "credit": 0.0,
        "match_fee_waived": 0.0,
        "match_days": 0.0,
    }
    for ms, member, schedule in rows:
        fin = _financials(schedule, days_map.get(ms.id, 0.0), paid_map.get(ms.id), waived_map.get(ms.id, 0.0))
        members.append({
            "member_id": str(member.id),
            "member_season_id": str(ms.id),
            "full_name": member.full_name,
            "player_id": str(member.player_id) if member.player_id else None,
            "is_linked": member.player_id is not None,
            "email": member.email,
            "mobile": member.mobile,
            "fee_schedule_id": str(ms.fee_schedule_id) if ms.fee_schedule_id else None,
            "is_new_registration": ms.is_new_registration,
            "membership_type_id": str(member.membership_type_id) if member.membership_type_id else None,
            "is_life_member": member.is_life_member,
            "is_honorary": member.is_honorary,
            "season_status": ms.status,
            **fin,
        })
        summary["total_members"] += 1
        summary["needs_tier"] += 1 if fin["needs_tier"] else 0
        summary["non_financial"] += 1 if fin["status"] == "non_financial" else 0
        for k in ("membership_payable", "match_fee_payable", "total_payable",
                  "membership_paid", "match_fee_paid", "total_paid",
                  "membership_outstanding", "match_fee_outstanding", "total_outstanding",
                  "membership_credit", "match_fee_credit", "credit",
                  "match_fee_waived", "match_days"):
            summary[k] += fin[k]
    for k in list(summary.keys()):
        if isinstance(summary[k], float):
            summary[k] = round(summary[k], 2)
    return {"members": members, "summary": summary}


class MemberCreate(BaseModel):
    season_id: str
    full_name: str
    email: Optional[str] = None
    mobile: Optional[str] = None
    fee_schedule_id: Optional[str] = None
    membership_type_id: Optional[str] = None


@router.post("/members")
async def create_member(
    data: MemberCreate,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Manually add a non-playing member (life member, sponsor, ICL, parent).
    Players who appear in a game are added automatically by the sync recompute."""
    season = await _season_or_404(db, club, data.season_id)
    full_name = (data.full_name or "").strip()
    if not full_name:
        raise HTTPException(status_code=422, detail="Name is required")

    schedule = await _resolve_schedule(db, club, season, data.fee_schedule_id)
    membership_type_id = None
    if data.membership_type_id:
        mt = await db.get(MembershipType, uuid.UUID(data.membership_type_id))
        if not mt or mt.organisation_id != club.id:
            raise HTTPException(status_code=422, detail="Membership type not found")
        membership_type_id = mt.id

    # The person row is created via the shared spine service (same create the
    # ClubManager Directory uses); BetterFees layers the fee season on top.
    member_id = uuid.UUID(await members_svc.create_person(
        db, club.id, full_name=full_name,
        email=(data.email or "").strip() or None, mobile=(data.mobile or "").strip() or None,
        membership_type_id=membership_type_id, current_tier=(schedule.name if schedule else None),
    ))
    db.add(FeeMemberSeason(
        id=uuid.uuid4(), member_id=member_id, season_id=season.id, organisation_id=club.id,
        fee_schedule_id=schedule.id if schedule else None,
    ))
    await db.commit()
    return {"member_id": str(member_id)}


class MemberEnroll(BaseModel):
    season_id: str
    member_id: Optional[str] = None   # an existing fee_members row
    player_id: Optional[str] = None   # a club player with no fee_members row yet
    fee_schedule_id: Optional[str] = None


@router.post("/members/enroll")
async def enroll_member(
    data: MemberEnroll,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Add an EXISTING person to a season's fee list — a player who sat out
    last season, or one who's new to the club and has never had a fee_members
    row at all. `create_member` above only ever creates a brand-new
    non-playing person; this is the search-driven counterpart (paired with
    `PersonSearch` / `GET /people/search` on the frontend), which finds
    anyone the club already knows — including a registered player with no
    fee_members row yet — rather than minting a duplicate manual entry for
    someone who already exists.

    Idempotent: enrolling someone already in this season just returns their
    existing row rather than erroring, so a double-click or a re-search of
    someone already added is harmless.
    """
    season = await _season_or_404(db, club, data.season_id)
    member_id = data.member_id
    if not member_id and data.player_id:
        try:
            member_id = await members_svc.ensure_for_player(db, club.id, uuid.UUID(data.player_id))
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    if not member_id:
        raise HTTPException(status_code=422, detail="member_id or player_id is required")

    member = await db.get(FeeMember, uuid.UUID(member_id))
    if not member or member.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")

    existing = (await db.execute(select(FeeMemberSeason).where(
        FeeMemberSeason.member_id == member.id, FeeMemberSeason.season_id == season.id
    ))).scalar_one_or_none()
    if existing:
        await db.commit()  # persist a freshly-minted fee_members row even if already enrolled
        return {"member_id": str(member.id), "member_season_id": str(existing.id), "already_enrolled": True}

    # A schedule pick, else fall back to the member's own carried-forward tier
    # name (same default `patch_member_season`/rollover use) so someone who's
    # played for the club before doesn't land in "Needs tier" for no reason.
    schedule = await _resolve_schedule(db, club, season, data.fee_schedule_id)
    if schedule is None and member.current_tier:
        dest_schedule_by_name = {
            (s.name or "").strip().lower(): s for s in (
                await db.execute(select(FeeSchedule).where(FeeSchedule.season_id == season.id))
            ).scalars().all()
        }
        schedule = dest_schedule_by_name.get(member.current_tier.strip().lower())

    ms = FeeMemberSeason(
        id=uuid.uuid4(), member_id=member.id, season_id=season.id, organisation_id=club.id,
        fee_schedule_id=schedule.id if schedule else None,
    )
    db.add(ms)
    if schedule is not None:
        member.current_tier = schedule.name
    await db.commit()
    return {"member_id": str(member.id), "member_season_id": str(ms.id), "already_enrolled": False}


class MemberImportPreview(BaseModel):
    csv: str


class MemberImportCommit(BaseModel):
    csv: str
    season_id: str


@router.post("/members/import/preview")
async def members_import_preview(data: MemberImportPreview, _: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Preview a non-player member CSV — the SAME shared importer the ClubManager
    Directory uses. Players are imported in Stats."""
    from app.services import member_import as member_import_svc
    return await member_import_svc.preview(db, club.id, data.csv)


@router.post("/members/import/commit")
async def members_import_commit(data: MemberImportCommit, _: User = _require, club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Import non-player members via the shared importer, then open a fee season
    row (as "needs tier") for each so they appear in this season's members list."""
    from app.services import member_import as member_import_svc
    season = await _season_or_404(db, club, data.season_id)
    result = await member_import_svc.commit(db, club.id, data.csv)
    result["added_to_season"] = await member_import_svc.open_member_seasons(
        db, club.id, season.id, result.pop("member_ids", []))
    await db.commit()
    return result


async def _resolve_schedule(db, club, season, fee_schedule_id) -> Optional[FeeSchedule]:
    if not fee_schedule_id:
        return None
    schedule = await db.get(FeeSchedule, uuid.UUID(fee_schedule_id))
    if not schedule or schedule.organisation_id != club.id or schedule.season_id != season.id:
        raise HTTPException(status_code=422, detail="Tier not found for this season")
    return schedule


@router.get("/members/{member_id}")
async def get_member(
    member_id: str,
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, season_id)
    member = await db.get(FeeMember, uuid.UUID(member_id))
    if not member or member.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")

    ms = (await db.execute(select(FeeMemberSeason).where(
        FeeMemberSeason.member_id == member.id, FeeMemberSeason.season_id == season.id
    ))).scalar_one_or_none()

    schedule = None
    entries = []
    payments = []
    fin = _financials(None, 0.0)
    if ms is not None:
        if ms.fee_schedule_id:
            schedule = await db.get(FeeSchedule, ms.fee_schedule_id)
        # Payments first — we need the match-day total before we can allocate
        # it across games.
        pay_rows = (await db.execute(
            select(FeePayment).where(FeePayment.member_season_id == ms.id)
            .order_by(FeePayment.paid_at.desc().nullslast(), FeePayment.created_at.desc())
        )).scalars().all()
        paid_totals = {"membership": 0.0, "match_day": 0.0}
        for p in pay_rows:
            paid_totals[p.kind] = paid_totals.get(p.kind, 0.0) + _f(p.amount)
            payments.append({
                "id": str(p.id),
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
                "amount": _f(p.amount),
                "kind": p.kind,
                "method": p.method,
                "bank_ref": p.bank_ref,
                "notes": p.notes,
            })

        # Match days oldest-first — that's the order match-fee money settles in.
        rows = (await db.execute(
            select(FeeMatchDay, Game, Grade)
            .outerjoin(Game, FeeMatchDay.game_id == Game.id)
            .outerjoin(Grade, Game.grade_id == Grade.id)
            .where(FeeMatchDay.member_season_id == ms.id)
            .order_by(FeeMatchDay.played_at.nullslast(), FeeMatchDay.id)
        )).all()
        rate = Decimal(str(_f(schedule.match_day_rate))) if schedule else Decimal("0")
        charges = [
            (_money(e.days_played) * rate) if e.days_played is not None else Decimal("0")
            for e, _game, _grade in rows
        ]
        waived_flags = [e.waived_at is not None for e, _game, _grade in rows]
        # Auto-allocate the member's match-fee money across these games, oldest
        # first. Per-game Paid/Part-paid/Unpaid is derived from money paid — not
        # a stored flag — so it stays correct as payments are added or removed.
        # Waived games settle for free and consume none of the money.
        alloc, _credit = fee_service.allocate_match_days(
            charges, paid_totals.get("match_day", 0.0), waived_flags)

        total_days = 0.0
        waived_days = 0.0
        for (e, game, grade), charge, (st, covered) in zip(rows, charges, alloc):
            total_days += _f(e.days_played)
            if e.waived_at is not None:
                waived_days += _f(e.days_played)
            entries.append({
                "id": str(e.id),
                "played_at": e.played_at.isoformat() if e.played_at else None,
                "fee_format": e.fee_format,
                "days_played": _f(e.days_played),
                "auto_derived": e.auto_derived,
                "charge": round(float(charge), 2),
                "status": st,                       # paid | partial | unpaid | na | waived
                "amount_covered": round(float(covered), 2),
                "is_paid": st == "paid",
                "waived": e.waived_at is not None,
                "waived_at": e.waived_at.isoformat() if e.waived_at else None,
                "waive_reason": e.waive_reason,
                "grade": grade.display_name if grade else None,
                "match": f"{game.home_team} v {game.away_team}" if game else None,
            })

        fin = _financials(schedule, total_days, paid_totals, waived_days)

    return {
        "member": {
            "id": str(member.id),
            "full_name": member.full_name,
            "player_id": str(member.player_id) if member.player_id else None,
            "is_linked": member.player_id is not None,
            "email": member.email,
            "mobile": member.mobile,
            "current_tier": member.current_tier,
            "notes": member.notes,
            "membership_type_id": str(member.membership_type_id) if member.membership_type_id else None,
            "is_life_member": member.is_life_member,
            "is_honorary": member.is_honorary,
            "honorary_expires_at": member.honorary_expires_at.isoformat() if member.honorary_expires_at else None,
        },
        "season": {"id": str(season.id), "name": season.name},
        "member_season": None if ms is None else {
            "id": str(ms.id),
            "fee_schedule_id": str(ms.fee_schedule_id) if ms.fee_schedule_id else None,
            "is_new_registration": ms.is_new_registration,
            "membership_payment_method": ms.membership_payment_method,
            "notes": ms.notes,
            "status": ms.status,
        },
        "financials": fin,
        "match_days": entries,
        "payments": payments,
    }


class MemberPatch(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    notes: Optional[str] = None
    membership_type_id: Optional[str] = None  # "" clears it
    is_life_member: Optional[bool] = None
    is_honorary: Optional[bool] = None
    honorary_expires_at: Optional[str] = None  # "" clears it (perpetual honorary)


@router.patch("/members/{member_id}")
async def patch_member(
    member_id: str,
    data: MemberPatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    member = await db.get(FeeMember, uuid.UUID(member_id))
    if not member or member.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    if data.full_name is not None:
        member.full_name = data.full_name.strip() or member.full_name
    if data.email is not None:
        member.email = data.email.strip() or None
    if data.mobile is not None:
        member.mobile = data.mobile.strip() or None
    if data.notes is not None:
        member.notes = data.notes.strip() or None
    if data.membership_type_id is not None:
        if data.membership_type_id == "":
            member.membership_type_id = None
        else:
            mt = await db.get(MembershipType, uuid.UUID(data.membership_type_id))
            if not mt or mt.organisation_id != club.id:
                raise HTTPException(status_code=422, detail="Membership type not found")
            member.membership_type_id = mt.id
    if data.is_life_member is not None:
        member.is_life_member = data.is_life_member
    if data.is_honorary is not None:
        member.is_honorary = data.is_honorary
    if data.honorary_expires_at is not None:
        if data.honorary_expires_at == "":
            member.honorary_expires_at = None
        else:
            try:
                member.honorary_expires_at = date.fromisoformat(data.honorary_expires_at)
            except ValueError:
                raise HTTPException(status_code=422, detail="Invalid honorary_expires_at date")
    await db.commit()
    return {"ok": True}


class MemberSeasonPatch(BaseModel):
    season_id: str
    fee_schedule_id: Optional[str] = None  # null clears the tier
    is_new_registration: Optional[bool] = None
    membership_payment_method: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


@router.patch("/members/{member_id}/season")
async def patch_member_season(
    member_id: str,
    data: MemberSeasonPatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, data.season_id)
    member = await db.get(FeeMember, uuid.UUID(member_id))
    if not member or member.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")

    ms = (await db.execute(select(FeeMemberSeason).where(
        FeeMemberSeason.member_id == member.id, FeeMemberSeason.season_id == season.id
    ))).scalar_one_or_none()
    if ms is None:
        ms = FeeMemberSeason(
            id=uuid.uuid4(), member_id=member.id, season_id=season.id, organisation_id=club.id,
        )
        db.add(ms)

    # fee_schedule_id is always present in the body; treat "" / null as clear.
    schedule = await _resolve_schedule(db, club, season, data.fee_schedule_id)
    ms.fee_schedule_id = schedule.id if schedule else None
    # Carry the chosen tier forward as the member's default for future seasons.
    if schedule is not None:
        member.current_tier = schedule.name

    if data.is_new_registration is not None:
        ms.is_new_registration = data.is_new_registration
    if data.membership_payment_method is not None:
        ms.membership_payment_method = data.membership_payment_method.strip() or None
    if data.notes is not None:
        ms.notes = data.notes.strip() or None
    if data.status is not None:
        if data.status not in MEMBERSHIP_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status — must be one of {MEMBERSHIP_STATUSES}")
        ms.status = data.status
    await db.commit()
    return {"ok": True}


@router.delete("/members/{member_id}/season")
async def remove_member_season(
    member_id: str,
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Take one member out of a season's fee list — for a player you know
    isn't coming back this season. Only removes their line in THIS season;
    the person record and every other season's history is untouched.

    Refused once a payment has been recorded against them this season —
    deleting the row would cascade-delete real money (fee_member_seasons →
    fee_payments is ON DELETE CASCADE). Nothing here un-charges match days;
    that's the recompute/waive tools' job, done first if a clean removal is
    still wanted.
    """
    season = await _season_or_404(db, club, season_id)
    member = await db.get(FeeMember, uuid.UUID(member_id))
    if not member or member.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member not found")
    ms = (await db.execute(select(FeeMemberSeason).where(
        FeeMemberSeason.member_id == member.id, FeeMemberSeason.season_id == season.id
    ))).scalar_one_or_none()
    if ms is None:
        raise HTTPException(status_code=404, detail="Not in this season")

    payment_count = (await db.execute(
        select(func.count()).select_from(FeePayment).where(FeePayment.member_season_id == ms.id)
    )).scalar_one()
    if payment_count:
        raise HTTPException(
            status_code=409,
            detail=f"{member.full_name} has {payment_count} payment{'s' if payment_count != 1 else ''} recorded this season — remove the payment(s) first",
        )
    await db.delete(ms)
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Match days
# ───────────────────────────────────────────────────────────────────────────

class MatchDayPatch(BaseModel):
    days_played: float


@router.patch("/match-days/{entry_id}")
async def patch_match_day(
    entry_id: str,
    data: MatchDayPatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Override an auto-derived match-day (e.g. drop a two-day game to 1). Flags
    the row so the weekly recompute leaves it alone afterwards."""
    e = await db.get(FeeMatchDay, uuid.UUID(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    ms = await db.get(FeeMemberSeason, e.member_season_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    if data.days_played < 0 or data.days_played > 5:
        raise HTTPException(status_code=422, detail="days_played out of range")
    e.days_played = _money(data.days_played)
    e.auto_derived = False
    await db.commit()
    return {"id": str(e.id), "days_played": _f(e.days_played), "auto_derived": e.auto_derived}


class MarkPaidRequest(BaseModel):
    paid_at: Optional[str] = None        # defaults to today
    method: Optional[str] = "EFT"
    bank_ref: Optional[str] = None
    notes: Optional[str] = None


@router.post("/match-days/{entry_id}/mark-paid")
async def mark_match_day_paid(
    entry_id: str,
    data: MarkPaidRequest,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single match day Paid: creates a fee_payment for
    (days_played × tier.match_day_rate) and links it on the row.

    No-op if the row is already paid (returns the existing link)."""
    from datetime import date as _date
    e = await db.get(FeeMatchDay, uuid.UUID(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    ms = await db.get(FeeMemberSeason, e.member_season_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    if e.paid_payment_id:
        return {"id": str(e.id), "paid_payment_id": str(e.paid_payment_id), "amount": None, "already_paid": True}
    if not ms.fee_schedule_id:
        raise HTTPException(status_code=422, detail="Member has no tier — assign one before marking paid")
    schedule = await db.get(FeeSchedule, ms.fee_schedule_id)
    rate = _f(schedule.match_day_rate) if schedule else 0.0
    amount = round(_f(e.days_played) * rate, 2)
    if amount <= 0:
        raise HTTPException(status_code=422, detail="Match-day rate is $0 for this tier — no payment needed")

    payment = FeePayment(
        id=uuid.uuid4(),
        member_season_id=ms.id,
        organisation_id=club.id,
        amount=_money(amount),
        paid_at=_parse_date(data.paid_at) or _date.today(),
        kind="match_day",
        method=(data.method or "").strip() or "EFT",
        bank_ref=(data.bank_ref or "").strip() or None,
        notes=(data.notes or "").strip() or (f"Match day {e.played_at.isoformat()}" if e.played_at else None),
        created_by_user_id=user.id,
    )
    db.add(payment)
    await db.flush()
    e.paid_payment_id = payment.id
    await db.commit()
    return {"id": str(e.id), "paid_payment_id": str(payment.id), "amount": amount, "already_paid": False}


@router.delete("/match-days/{entry_id}/mark-paid")
async def unmark_match_day_paid(
    entry_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Undo a Mark Paid: deletes the linked payment (which nulls
    paid_payment_id automatically via the FK)."""
    e = await db.get(FeeMatchDay, uuid.UUID(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    ms = await db.get(FeeMemberSeason, e.member_season_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    if not e.paid_payment_id:
        return {"id": str(e.id), "deleted": 0}
    payment = await db.get(FeePayment, e.paid_payment_id)
    deleted = 0
    if payment is not None:
        await db.delete(payment)
        deleted = 1
    e.paid_payment_id = None
    await db.commit()
    return {"id": str(e.id), "deleted": deleted}


class WaiveRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/match-days/{entry_id}/waive")
async def waive_match_day(
    entry_id: str,
    data: WaiveRequest,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Waive a single match day: forgive its fee without recording any money.

    The game settles (the row shows 'Waived' and counts toward the member being
    Financial), but a waiver is NOT a payment — it never enters the income /
    paid / credit totals. Stored as flags on the row, so it survives the weekly
    recompute and is fully reversible. Re-posting updates the reason note."""
    from datetime import datetime, timezone
    e = await db.get(FeeMatchDay, uuid.UUID(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    ms = await db.get(FeeMemberSeason, e.member_season_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    if e.waived_at is None:
        e.waived_at = datetime.now(timezone.utc)
        e.waived_by_user_id = user.id
    e.waive_reason = (data.reason or "").strip() or None
    await db.commit()
    return {
        "id": str(e.id),
        "waived": True,
        "waived_at": e.waived_at.isoformat() if e.waived_at else None,
        "waive_reason": e.waive_reason,
    }


@router.delete("/match-days/{entry_id}/waive")
async def unwaive_match_day(
    entry_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Undo a waive — the game is charged and derived as normal again."""
    e = await db.get(FeeMatchDay, uuid.UUID(entry_id))
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    ms = await db.get(FeeMemberSeason, e.member_season_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Entry not found")
    was_waived = e.waived_at is not None
    e.waived_at = None
    e.waived_by_user_id = None
    e.waive_reason = None
    await db.commit()
    return {"id": str(e.id), "waived": False, "changed": was_waived}


# ───────────────────────────────────────────────────────────────────────────
# Recompute
# ───────────────────────────────────────────────────────────────────────────

@router.post("/recompute")
async def recompute(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    season = await _season_or_404(db, club, season_id)
    result = await fee_service.recompute_fee_match_days(str(club.id), str(season.id))
    return result


# ───────────────────────────────────────────────────────────────────────────
# Payments
# ───────────────────────────────────────────────────────────────────────────

async def _member_season_for_payment(db, club, member_season_id) -> FeeMemberSeason:
    try:
        ms_id = uuid.UUID(member_season_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid member_season_id")
    ms = await db.get(FeeMemberSeason, ms_id)
    if not ms or ms.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Member season not found")
    return ms


def _payment_out(p: FeePayment, member: Optional[FeeMember] = None) -> dict:
    out = {
        "id": str(p.id),
        "member_season_id": str(p.member_season_id),
        "paid_at": p.paid_at.isoformat() if p.paid_at else None,
        "amount": _f(p.amount),
        "kind": p.kind,
        "method": p.method,
        "bank_ref": p.bank_ref,
        "notes": p.notes,
        "source": p.source,
    }
    if member is not None:
        out["member_id"] = str(member.id)
        out["full_name"] = member.full_name
    return out


@router.get("/payments")
async def list_payments(
    season_id: Optional[str] = None,
    member_season_id: Optional[str] = None,
    kind: Optional[str] = None,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """List payments by season (admin ledger view) or by single member_season."""
    if not season_id and not member_season_id:
        raise HTTPException(status_code=422, detail="Provide season_id or member_season_id")
    q = (
        select(FeePayment, FeeMember)
        .join(FeeMemberSeason, FeePayment.member_season_id == FeeMemberSeason.id)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .where(FeePayment.organisation_id == club.id)
    )
    if season_id:
        season = await _season_or_404(db, club, season_id)
        q = q.where(FeeMemberSeason.season_id == season.id)
    if member_season_id:
        ms = await _member_season_for_payment(db, club, member_season_id)
        q = q.where(FeePayment.member_season_id == ms.id)
    if kind:
        if kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"kind must be one of {PAYMENT_KINDS}")
        q = q.where(FeePayment.kind == kind)
    q = q.order_by(FeePayment.paid_at.desc().nullslast(), FeePayment.created_at.desc())
    rows = (await db.execute(q)).all()
    return [_payment_out(p, m) for p, m in rows]


class PaymentCreate(BaseModel):
    member_season_id: str
    amount: float
    kind: str = "membership"
    paid_at: Optional[str] = None  # ISO date YYYY-MM-DD
    method: Optional[str] = None
    bank_ref: Optional[str] = None
    notes: Optional[str] = None


def _parse_date(s: Optional[str]):
    if not s:
        return None
    from datetime import date
    try:
        return date.fromisoformat(s)
    except ValueError:
        raise HTTPException(status_code=422, detail="paid_at must be YYYY-MM-DD")


@router.post("/payments")
async def create_payment(
    data: PaymentCreate,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    ms = await _member_season_for_payment(db, club, data.member_season_id)
    if data.kind not in PAYMENT_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {PAYMENT_KINDS}")
    p = FeePayment(
        id=uuid.uuid4(),
        member_season_id=ms.id,
        organisation_id=club.id,
        amount=_money(data.amount),
        paid_at=_parse_date(data.paid_at),
        kind=data.kind,
        method=(data.method or "").strip() or None,
        bank_ref=(data.bank_ref or "").strip() or None,
        notes=(data.notes or "").strip() or None,
        created_by_user_id=user.id,
    )
    db.add(p)
    await db.commit()
    return _payment_out(p)


class PaymentPatch(BaseModel):
    amount: Optional[float] = None
    kind: Optional[str] = None
    paid_at: Optional[str] = None
    method: Optional[str] = None
    bank_ref: Optional[str] = None
    notes: Optional[str] = None


@router.patch("/payments/{payment_id}")
async def patch_payment(
    payment_id: str,
    data: PaymentPatch,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(FeePayment, uuid.UUID(payment_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if data.amount is not None:
        p.amount = _money(data.amount)
    if data.kind is not None:
        if data.kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"kind must be one of {PAYMENT_KINDS}")
        p.kind = data.kind
    if data.paid_at is not None:
        p.paid_at = _parse_date(data.paid_at)
    if data.method is not None:
        p.method = data.method.strip() or None
    if data.bank_ref is not None:
        p.bank_ref = data.bank_ref.strip() or None
    if data.notes is not None:
        p.notes = data.notes.strip() or None
    await db.commit()
    return _payment_out(p)


@router.delete("/payments/{payment_id}")
async def delete_payment(
    payment_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    p = await db.get(FeePayment, uuid.UUID(payment_id))
    if not p or p.organisation_id != club.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    await db.delete(p)
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Reports
# ───────────────────────────────────────────────────────────────────────────

@router.get("/reports/summary")
async def report_summary(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Single endpoint feeding the headline cards on the Reports page."""
    season = await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeeMemberSeason, FeeSchedule)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == season.id)
    )).all()
    days_map = await _days_by_member_season(db, season.id)
    paid_map = await _paid_by_member_season(db, season.id)
    waived_map = await _waived_days_by_member_season(db, season.id)

    by_payment_type: dict = {}
    overall = {"members": 0, "financial": 0, "non_financial": 0, "needs_tier": 0,
               "membership_payable": 0.0, "match_fee_payable": 0.0, "total_payable": 0.0,
               "membership_paid": 0.0, "match_fee_paid": 0.0, "total_paid": 0.0,
               "membership_outstanding": 0.0, "match_fee_outstanding": 0.0, "total_outstanding": 0.0,
               "membership_credit": 0.0, "match_fee_credit": 0.0, "credit": 0.0,
               "match_fee_waived": 0.0}
    for ms, schedule in rows:
        fin = _financials(schedule, days_map.get(ms.id, 0.0), paid_map.get(ms.id), waived_map.get(ms.id, 0.0))
        overall["members"] += 1
        overall[fin["status"]] = overall.get(fin["status"], 0) + 1
        for k in ("membership_payable", "match_fee_payable", "total_payable",
                  "membership_paid", "match_fee_paid", "total_paid",
                  "membership_outstanding", "match_fee_outstanding", "total_outstanding",
                  "membership_credit", "match_fee_credit", "credit",
                  "match_fee_waived"):
            overall[k] += fin[k]
        bucket_key = fin["payment_type"] or "unassigned"
        b = by_payment_type.setdefault(bucket_key, {
            "payment_type": bucket_key, "members": 0,
            "payable": 0.0, "paid": 0.0, "outstanding": 0.0, "credit": 0.0, "waived": 0.0,
        })
        b["members"] += 1
        b["payable"] += fin["total_payable"]
        b["paid"] += fin["total_paid"]
        b["outstanding"] += fin["total_outstanding"]
        b["credit"] += fin["credit"]
        b["waived"] += fin["match_fee_waived"]
    for k in list(overall.keys()):
        if isinstance(overall[k], float):
            overall[k] = round(overall[k], 2)
    for b in by_payment_type.values():
        for k in ("payable", "paid", "outstanding", "credit", "waived"):
            b[k] = round(b[k], 2)
    return {"overall": overall, "by_payment_type": list(by_payment_type.values())}


@router.get("/reports/non-financial")
async def report_non_financial(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """The follow-up list — every member with money owed, sorted biggest first."""
    season = await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeeMemberSeason, FeeMember, FeeSchedule)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == season.id)
    )).all()
    days_map = await _days_by_member_season(db, season.id)
    paid_map = await _paid_by_member_season(db, season.id)
    waived_map = await _waived_days_by_member_season(db, season.id)
    out = []
    for ms, member, schedule in rows:
        fin = _financials(schedule, days_map.get(ms.id, 0.0), paid_map.get(ms.id), waived_map.get(ms.id, 0.0))
        if fin["status"] != "non_financial":
            continue
        out.append({
            "member_id": str(member.id),
            "member_season_id": str(ms.id),
            "full_name": member.full_name,
            "email": member.email,
            "mobile": member.mobile,
            "tier": fin["tier"],
            "match_days": fin["match_days"],
            "membership_outstanding": fin["membership_outstanding"],
            "match_fee_outstanding": fin["match_fee_outstanding"],
            "total_outstanding": fin["total_outstanding"],
        })
    out.sort(key=lambda r: -r["total_outstanding"])
    return out


@router.get("/reports/cashflow")
async def report_cashflow(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Payments grouped by month, split by kind. Mirrors the spreadsheet's
    'paid by month' columns but dynamic — uses whatever months actually have
    payments rather than the fixed Oct–Mar buckets."""
    season = await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeePayment.paid_at, FeePayment.kind, func.sum(FeePayment.amount))
        .join(FeeMemberSeason, FeePayment.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season.id)
        .group_by(FeePayment.paid_at, FeePayment.kind)
    )).all()
    months: dict = {}
    for paid_at, kind, amount in rows:
        key = paid_at.strftime("%Y-%m") if paid_at else "unknown"
        bucket = months.setdefault(key, {"month": key, "membership": 0.0, "match_day": 0.0, "total": 0.0})
        bucket[kind] = bucket.get(kind, 0.0) + float(amount)
        bucket["total"] += float(amount)
    series = sorted(months.values(), key=lambda x: (x["month"] == "unknown", x["month"]))
    for b in series:
        for k in ("membership", "match_day", "total"):
            b[k] = round(b[k], 2)
    return series


@router.get("/reports/export")
async def report_export(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """CSV of the full member ledger for one season — same shape as the
    Membership Recovery spreadsheet's Fees Master sheet."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    season = await _season_or_404(db, club, season_id)
    rows = (await db.execute(
        select(FeeMemberSeason, FeeMember, FeeSchedule)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == season.id)
        .order_by(func.lower(FeeMember.full_name))
    )).all()
    days_map = await _days_by_member_season(db, season.id)
    paid_map = await _paid_by_member_season(db, season.id)
    waived_map = await _waived_days_by_member_season(db, season.id)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Full Name", "Email", "Mobile", "Tier", "Payment Type",
        "Match Days",
        "Membership Payable", "Membership Paid", "Membership Outstanding",
        "Match Fee Payable", "Match Fee Paid", "Match Fee Waived", "Match Fee Outstanding",
        "Total Payable", "Total Paid", "Total Outstanding",
        "Status",
    ])
    for ms, member, schedule in rows:
        fin = _financials(schedule, days_map.get(ms.id, 0.0), paid_map.get(ms.id), waived_map.get(ms.id, 0.0))
        w.writerow([
            member.full_name, member.email or "", member.mobile or "",
            fin["tier"] or "", fin["payment_type"] or "",
            fin["match_days"],
            fin["membership_payable"], fin["membership_paid"], fin["membership_outstanding"],
            fin["match_fee_payable"], fin["match_fee_paid"], fin["match_fee_waived"], fin["match_fee_outstanding"],
            fin["total_payable"], fin["total_paid"], fin["total_outstanding"],
            fin["status"],
        ])
    buf.seek(0)
    filename = f"fees-{season.name.replace('/', '-').replace(' ', '_')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


# ───────────────────────────────────────────────────────────────────────────
# Phase 3 — Season rollover
# ───────────────────────────────────────────────────────────────────────────

class RolloverRequest(BaseModel):
    season_id: str          # destination season
    from_season_id: str     # source season to copy from
    include_left_club: bool = False  # by default skip "Left Club" tiers


@router.post("/rollover")
async def rollover_members(
    data: RolloverRequest,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Open the destination season for every member that had a member-season
    in the source season — tier carried forward, payments left behind.

    Skips members that already have a row in the destination (idempotent),
    and by default skips anyone on a 'Left Club' tier (since they aren't
    members any more). Tier names are resolved against the *destination*
    season's schedule (so this only works after rate-card copy-forward).
    """
    dest = await _season_or_404(db, club, data.season_id)
    src = await _season_or_404(db, club, data.from_season_id)
    if dest.id == src.id:
        raise HTTPException(status_code=422, detail="Source and destination must differ")

    # Existing rows in the destination — skip these.
    existing_member_ids = {
        ms.member_id for ms in (
            await db.execute(select(FeeMemberSeason).where(FeeMemberSeason.season_id == dest.id))
        ).scalars().all()
    }

    # Source rows joined to their schedule, so we know each member's tier name
    # and payment_type at the time the season closed.
    src_rows = (await db.execute(
        select(FeeMemberSeason, FeeSchedule)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == src.id)
    )).all()

    # Destination schedule, keyed by lower-cased name for tier lookup.
    dest_schedule_by_name = {
        (s.name or "").strip().lower(): s for s in (
            await db.execute(select(FeeSchedule).where(FeeSchedule.season_id == dest.id))
        ).scalars().all()
    }

    created = 0
    skipped_left = 0
    skipped_existing = 0
    for ms_src, sched_src in src_rows:
        if ms_src.member_id in existing_member_ids:
            skipped_existing += 1
            continue
        if not data.include_left_club and sched_src is not None and sched_src.payment_type == "left_club":
            skipped_left += 1
            continue
        # Resolve the destination tier by name match; falls back to None
        # (members land in the "Needs Tier" queue) if the rate card doesn't
        # have that tier any more.
        dest_sched = None
        if sched_src is not None:
            dest_sched = dest_schedule_by_name.get((sched_src.name or "").strip().lower())
        db.add(FeeMemberSeason(
            id=uuid.uuid4(),
            member_id=ms_src.member_id,
            season_id=dest.id,
            organisation_id=club.id,
            fee_schedule_id=dest_sched.id if dest_sched else None,
            is_new_registration=False,
        ))
        created += 1
    await db.commit()
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_left_club": skipped_left,
    }


class RolloverUndoRequest(BaseModel):
    season_id: str


@router.post("/rollover/undo")
async def undo_rollover(
    data: RolloverUndoRequest,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Clear every member out of a season's fee list in one go.

    The fix for rolling players over before the new season's rate card was
    ready: every rolled-over row lands with no tier (or the wrong one, if a
    name happened to collide), so the season needs wiping and redoing once
    the schedule is copied across. Deliberately a season-wide reset rather
    than "undo only what the last rollover added" — by the time someone
    reaches for this, sorting rollover-added rows from anyone else added
    since isn't a distinction worth making; it's "start this season's roster
    again from nothing".

    A member with a payment already recorded this season is kept, never
    deleted — the same money guard `remove_member_season` applies to one row
    at a time, applied here across the whole season. The person themselves,
    and every other season, are untouched either way.
    """
    season = await _season_or_404(db, club, data.season_id)
    rows = (await db.execute(
        select(FeeMemberSeason, FeeMember)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .where(FeeMemberSeason.season_id == season.id)
    )).all()
    if not rows:
        return {"removed": 0, "kept_with_payments": []}

    ms_ids = [ms.id for ms, _ in rows]
    paid_ms_ids = {
        row[0] for row in (
            await db.execute(
                select(FeePayment.member_season_id).where(FeePayment.member_season_id.in_(ms_ids)).distinct()
            )
        ).all()
    }

    kept = []
    removed = 0
    for ms, member in rows:
        if ms.id in paid_ms_ids:
            kept.append(member.full_name)
            continue
        await db.delete(ms)
        removed += 1
    await db.commit()
    return {"removed": removed, "kept_with_payments": sorted(kept)}


# ───────────────────────────────────────────────────────────────────────────
# Phase 3 — Bulk tier assignment
# ───────────────────────────────────────────────────────────────────────────

class BulkTierRequest(BaseModel):
    season_id: str
    member_ids: List[str]   # the FeeMember.id list (not member_season_ids)
    fee_schedule_id: Optional[str] = None  # null clears the tier


@router.post("/members/bulk-tier")
async def bulk_set_tier(
    data: BulkTierRequest,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Set the tier on many members at once for one season — the 'graduate
    all students' button. Also carries the new tier forward to each member's
    current_tier (so next year's rollover defaults are right)."""
    season = await _season_or_404(db, club, data.season_id)
    if not data.member_ids:
        return {"updated": 0, "not_found": 0}
    schedule = await _resolve_schedule(db, club, season, data.fee_schedule_id)

    try:
        member_uuids = [uuid.UUID(m) for m in data.member_ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Invalid member_id")

    members = {
        m.id: m for m in (
            await db.execute(
                select(FeeMember).where(
                    FeeMember.organisation_id == club.id,
                    FeeMember.id.in_(member_uuids),
                )
            )
        ).scalars().all()
    }

    ms_rows = (await db.execute(
        select(FeeMemberSeason).where(
            FeeMemberSeason.season_id == season.id,
            FeeMemberSeason.member_id.in_(member_uuids),
        )
    )).scalars().all()
    existing_by_member = {ms.member_id: ms for ms in ms_rows}

    updated = 0
    for mid in member_uuids:
        member = members.get(mid)
        if member is None:
            continue
        ms = existing_by_member.get(mid)
        if ms is None:
            # Create the season row for any member missing one — useful when
            # someone wants to bulk-onboard a list of new members.
            ms = FeeMemberSeason(
                id=uuid.uuid4(), member_id=mid, season_id=season.id,
                organisation_id=club.id,
            )
            db.add(ms)
        ms.fee_schedule_id = schedule.id if schedule else None
        if schedule is not None:
            member.current_tier = schedule.name
        updated += 1
    await db.commit()
    not_found = len(data.member_ids) - updated
    return {"updated": updated, "not_found": not_found}


# ───────────────────────────────────────────────────────────────────────────
# Phase 3 — Bank CSV import
# ───────────────────────────────────────────────────────────────────────────

# A handful of header aliases the major Australian banks use. CSV column order
# varies, so detection is by header name (case-insensitive substring), not
# position.
_DATE_HEADERS = ("date", "transaction date", "posted date", "processed date")
_AMOUNT_HEADERS = ("amount", "credit", "credit amount", "deposit", "value")
_DEBIT_HEADERS = ("debit", "withdrawal", "debit amount")
_DESC_HEADERS = ("description", "narrative", "details", "transaction", "reference", "memo")


def _detect_col(headers, candidates):
    lower = [h.strip().lower() for h in headers]
    for i, h in enumerate(lower):
        if any(c == h for c in candidates):
            return i
    for i, h in enumerate(lower):
        if any(c in h for c in candidates):
            return i
    return None


_clean_description = fee_service.clean_description
_match_score = fee_service.match_score


@router.post("/payments/import/preview")
async def import_preview(
    season_id: str = Form(...),
    file: UploadFile = File(...),
    default_kind: str = Form("membership"),
    default_method: str = Form("EFT"),
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Parse an uploaded bank-statement CSV and propose a member match per row.

    Headers are auto-detected (works across CBA/NAB/ANZ formats). Debit-only
    rows and negative amounts are dropped. Each surviving row comes back with
    the top 3 member matches by confidence — the admin picks/confirms before
    committing.
    """
    season = await _season_or_404(db, club, season_id)
    if default_kind not in PAYMENT_KINDS:
        raise HTTPException(status_code=422, detail=f"default_kind must be one of {PAYMENT_KINDS}")

    raw = (await file.read()).decode("utf-8-sig", errors="ignore")
    if not raw.strip():
        raise HTTPException(status_code=422, detail="Empty CSV")
    reader = list(csv.reader(io.StringIO(raw)))
    if not reader:
        raise HTTPException(status_code=422, detail="Could not parse CSV")

    # Find the header row — the first row with a recognisable date column.
    header_idx = None
    headers = None
    for i, row in enumerate(reader[:10]):
        if _detect_col(row, _DATE_HEADERS) is not None and _detect_col(row, _DESC_HEADERS) is not None:
            header_idx = i
            headers = row
            break
    if header_idx is None:
        raise HTTPException(status_code=422, detail="Couldn't find Date and Description columns")

    date_col = _detect_col(headers, _DATE_HEADERS)
    desc_col = _detect_col(headers, _DESC_HEADERS)
    amount_col = _detect_col(headers, _AMOUNT_HEADERS)
    debit_col = _detect_col(headers, _DEBIT_HEADERS)
    if amount_col is None and debit_col is None:
        raise HTTPException(status_code=422, detail="Couldn't find Amount column")

    # Members for matching — pull their member_season for this season so we
    # have a target to attach payments to. Members without a season row are
    # excluded (rollover or auto-create them first).
    rows = (await db.execute(
        select(FeeMemberSeason, FeeMember)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .where(FeeMemberSeason.season_id == season.id)
    )).all()
    candidates = [(ms, m) for ms, m in rows]

    out = []
    for r_i, row in enumerate(reader[header_idx + 1:]):
        if not row or all(not (c or "").strip() for c in row):
            continue
        # Amount: prefer the credit column; fall back to a signed amount
        # column (negative = debit, skip).
        amount: Optional[float] = None
        if amount_col is not None and amount_col < len(row):
            raw_amount = (row[amount_col] or "").strip().replace(",", "")
            if raw_amount:
                try:
                    val = float(raw_amount)
                    if val > 0:
                        amount = val
                except ValueError:
                    pass
        if amount is None and debit_col is not None and debit_col < len(row):
            # Debit column populated → this is a withdrawal, skip.
            if (row[debit_col] or "").strip():
                continue
        if amount is None or amount <= 0:
            continue

        date_raw = (row[date_col] or "").strip() if date_col < len(row) else ""
        desc_raw = (row[desc_col] or "").strip() if desc_col < len(row) else ""

        cleaned = _clean_description(desc_raw)
        scored = [
            (_match_score(cleaned, m.full_name), ms, m) for ms, m in candidates
        ]
        scored.sort(key=lambda x: -x[0])
        top = [
            {
                "member_id": str(m.id),
                "member_season_id": str(ms.id),
                "full_name": m.full_name,
                "confidence": round(score, 3),
            }
            for score, ms, m in scored[:3] if score > 0
        ]
        best = top[0] if top else None

        out.append({
            "row_index": r_i,
            "paid_at_raw": date_raw,
            "paid_at": _normalise_date(date_raw),
            "description": desc_raw,
            "amount": round(amount, 2),
            "suggested": best,
            "candidates": top,
            "kind": default_kind,
            "method": default_method,
        })
    return {
        "rows": out,
        "default_kind": default_kind,
        "default_method": default_method,
    }


def _normalise_date(raw: str) -> Optional[str]:
    """Best-effort YYYY-MM-DD from common bank date formats."""
    from datetime import datetime
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class ImportCommitItem(BaseModel):
    member_season_id: str
    amount: float
    paid_at: Optional[str] = None
    kind: str = "membership"
    method: Optional[str] = None
    bank_ref: Optional[str] = None
    notes: Optional[str] = None


class ImportCommit(BaseModel):
    items: List[ImportCommitItem]


@router.post("/payments/import/commit")
async def import_commit(
    data: ImportCommit,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Persist a confirmed batch of payments from the CSV preview. All rows
    are validated up-front (one bad row = nothing inserted)."""
    if not data.items:
        return {"created": 0}

    # Validate every row before inserting anything so the user gets a clean
    # all-or-nothing result.
    ms_cache: dict = {}
    for i, item in enumerate(data.items):
        try:
            ms_id = uuid.UUID(item.member_season_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Row {i}: invalid member_season_id")
        if ms_id not in ms_cache:
            ms = await db.get(FeeMemberSeason, ms_id)
            if not ms or ms.organisation_id != club.id:
                raise HTTPException(status_code=422, detail=f"Row {i}: member season not found")
            ms_cache[ms_id] = ms
        if item.kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"Row {i}: kind must be one of {PAYMENT_KINDS}")
        if item.amount <= 0:
            raise HTTPException(status_code=422, detail=f"Row {i}: amount must be > 0")

    created = 0
    for item in data.items:
        ms_id = uuid.UUID(item.member_season_id)
        db.add(FeePayment(
            id=uuid.uuid4(),
            member_season_id=ms_id,
            organisation_id=club.id,
            amount=_money(item.amount),
            paid_at=_parse_date(item.paid_at),
            kind=item.kind,
            method=(item.method or "").strip() or None,
            bank_ref=(item.bank_ref or "").strip() or None,
            notes=(item.notes or "").strip() or None,
            created_by_user_id=user.id,
        ))
        created += 1
    await db.commit()
    return {"created": created}


# ───────────────────────────────────────────────────────────────────────────
# Phase 3.1 — Bulk payment (one deposit covering many players)
# ───────────────────────────────────────────────────────────────────────────

class BulkPaymentItem(BaseModel):
    member_season_id: str
    amount: float
    kind: str = "match_day"             # 'match_day' or 'membership'
    match_day_ids: List[str] = []       # specific days to link (kind=match_day only)
    notes: Optional[str] = None


class BulkPaymentRequest(BaseModel):
    paid_at: Optional[str] = None
    method: Optional[str] = "EFT"
    bank_ref: Optional[str] = None
    notes: Optional[str] = None
    expected_total: Optional[float] = None   # client-side sanity check (optional)
    items: List[BulkPaymentItem]


@router.post("/payments/bulk")
async def create_bulk_payment(
    data: BulkPaymentRequest,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """One deposit, many players. The captain-collects case: each item
    creates a separate fee_payment with the shared bank_ref/paid_at/method,
    and any match_day_ids get linked to the new payment so the player's
    Match Days view shows them as Paid.

    Validates everything up front so a bad row aborts the whole batch.
    """
    from datetime import date as _date
    if not data.items:
        raise HTTPException(status_code=422, detail="At least one item required")
    paid_at = _parse_date(data.paid_at) or _date.today()

    # Pre-flight: resolve every member_season + match-day so an invalid id
    # aborts before we write anything.
    ms_cache: dict = {}
    md_cache: dict = {}
    total = 0.0
    for i, item in enumerate(data.items):
        try:
            ms_id = uuid.UUID(item.member_season_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Row {i}: invalid member_season_id")
        if ms_id not in ms_cache:
            ms = await db.get(FeeMemberSeason, ms_id)
            if not ms or ms.organisation_id != club.id:
                raise HTTPException(status_code=422, detail=f"Row {i}: member season not found")
            ms_cache[ms_id] = ms
        if item.kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"Row {i}: kind must be one of {PAYMENT_KINDS}")
        if item.amount <= 0:
            raise HTTPException(status_code=422, detail=f"Row {i}: amount must be > 0")
        total += item.amount
        for raw_id in item.match_day_ids:
            try:
                md_id = uuid.UUID(raw_id)
            except (ValueError, TypeError):
                raise HTTPException(status_code=422, detail=f"Row {i}: invalid match_day id")
            if md_id not in md_cache:
                md = await db.get(FeeMatchDay, md_id)
                if not md or md.member_season_id != ms_id:
                    raise HTTPException(status_code=422, detail=f"Row {i}: match day doesn't belong to this member")
                md_cache[md_id] = md

    if data.expected_total is not None:
        if abs(round(total, 2) - round(float(data.expected_total), 2)) > 0.01:
            raise HTTPException(
                status_code=422,
                detail=f"Row totals (${total:.2f}) don't match the expected deposit (${data.expected_total:.2f})",
            )

    created = 0
    md_paid = 0
    for item in data.items:
        ms_id = uuid.UUID(item.member_season_id)
        payment = FeePayment(
            id=uuid.uuid4(),
            member_season_id=ms_id,
            organisation_id=club.id,
            amount=_money(item.amount),
            paid_at=paid_at,
            kind=item.kind,
            method=(data.method or "").strip() or "EFT",
            bank_ref=(data.bank_ref or "").strip() or None,
            notes=(item.notes or data.notes or "").strip() or None,
            created_by_user_id=user.id,
        )
        db.add(payment)
        await db.flush()
        created += 1
        if item.kind == "match_day" and item.match_day_ids:
            for raw_id in item.match_day_ids:
                md_id = uuid.UUID(raw_id)
                md = md_cache[md_id]
                # If the day was previously linked to a different payment,
                # leave that alone — admin should unmark it first.
                if md.paid_payment_id is None:
                    md.paid_payment_id = payment.id
                    md_paid += 1
    await db.commit()
    return {"created": created, "match_days_marked_paid": md_paid, "total": round(total, 2)}


# ───────────────────────────────────────────────────────────────────────────
# Square import — completed Square sales reviewed and matched to a member
# ───────────────────────────────────────────────────────────────────────────
# Reuses BetterMerch's existing per-club Square connection (`services.square_sync`
# / `MerchSquareConnection`) — there is no separate OAuth flow here. A club
# without a connection yet is pointed at BetterMerch's Square page to connect
# (Square OAuth is MANAGE_MERCH-capped there; nothing below writes to Square).

def _fee_square_status(conn: Optional[MerchSquareConnection]) -> dict:
    return {
        "configured": settings.square_configured,
        "connected": bool(conn and conn.access_token and conn.location_id),
        "location_name": conn.location_name if conn else None,
        "sync_fees": conn.sync_fees if conn else False,
        "fee_item_keywords": (conn.fee_item_keywords if conn and conn.fee_item_keywords else fee_square_service.DEFAULT_KEYWORDS),
        "last_sync_at": conn.fees_last_sync_at.isoformat() if conn and conn.fees_last_sync_at else None,
        "last_sync_status": conn.fees_last_sync_status if conn else None,
        "last_sync_error": conn.fees_last_sync_error if conn else None,
    }


@router.get("/square/status")
async def fee_square_status(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    return _fee_square_status(conn)


class FeeSquareSettings(BaseModel):
    sync_fees: Optional[bool] = None
    fee_item_keywords: Optional[str] = None


@router.post("/square/settings")
async def fee_square_settings(
    data: FeeSquareSettings,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await square_sync.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Square from BetterMerch first")
    if data.sync_fees is not None:
        conn.sync_fees = data.sync_fees
    if data.fee_item_keywords is not None:
        conn.fee_item_keywords = data.fee_item_keywords.strip() or None
    await db.commit()
    return _fee_square_status(conn)


@router.post("/square/preview")
async def fee_square_preview(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Completed Square sales matching the club's fee-item keywords, each with
    a suggested member match — nothing is written until /square/commit."""
    season = await _season_or_404(db, club, season_id)
    conn = await square_sync.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Square from BetterMerch first")
    if not conn.location_id:
        raise HTTPException(status_code=400, detail="Pick a Square location from BetterMerch first")
    if not conn.sync_fees:
        raise HTTPException(status_code=400, detail="Turn on Square fee import below first")
    try:
        rows = await fee_square_service.fetch_candidates(db, club, season.id, conn)
        conn.fees_last_sync_at = datetime.now(timezone.utc)
        conn.fees_last_sync_status = "ok"
        conn.fees_last_sync_error = None
        await db.commit()
    except square_client.SquareError as e:
        conn.fees_last_sync_at = datetime.now(timezone.utc)
        conn.fees_last_sync_status = "error"
        conn.fees_last_sync_error = str(e)[:500]
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    return {"rows": rows}


class FeeSquareCommitItem(BaseModel):
    external_ref: str
    item_name: str
    amount: float
    occurred_at: Optional[str] = None
    note: Optional[str] = None
    member_season_id: str
    kind: str = "match_day"


class FeeSquareCommit(BaseModel):
    items: List[FeeSquareCommitItem]


@router.post("/square/commit")
async def fee_square_commit(
    data: FeeSquareCommit,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Apply reviewed Square sales as fee payments. Every item must already
    carry the member the admin picked in the review UI — nothing here guesses.
    Any row already resolved since preview was fetched (another tab, a double
    click) is silently skipped rather than double-applied."""
    if not data.items:
        return {"created": 0, "skipped": 0}

    ms_cache: dict = {}
    for i, item in enumerate(data.items):
        try:
            ms_id = uuid.UUID(item.member_season_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Row {i}: invalid member_season_id")
        if ms_id not in ms_cache:
            ms = await db.get(FeeMemberSeason, ms_id)
            if not ms or ms.organisation_id != club.id:
                raise HTTPException(status_code=422, detail=f"Row {i}: member season not found")
            ms_cache[ms_id] = ms
        if item.kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"Row {i}: kind must be one of {PAYMENT_KINDS}")
        if item.amount <= 0:
            raise HTTPException(status_code=422, detail=f"Row {i}: amount must be > 0")

    created = 0
    skipped = 0
    for item in data.items:
        existing = (await db.execute(
            select(FeeSquareImportLog).where(
                FeeSquareImportLog.organisation_id == club.id,
                FeeSquareImportLog.external_ref == item.external_ref,
            )
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        payment = FeePayment(
            id=uuid.uuid4(),
            member_season_id=uuid.UUID(item.member_season_id),
            organisation_id=club.id,
            amount=_money(item.amount),
            paid_at=_parse_date(item.occurred_at),
            kind=item.kind,
            method="Square",
            notes=item.note or item.item_name,
            source="square",
            external_ref=item.external_ref,
            created_by_user_id=user.id,
        )
        db.add(payment)
        await db.flush()
        db.add(FeeSquareImportLog(
            id=uuid.uuid4(), organisation_id=club.id, external_ref=item.external_ref,
            status="applied", fee_payment_id=payment.id, item_name=item.item_name,
            note=item.note, amount=_money(item.amount), occurred_at=_parse_date(item.occurred_at),
            created_by_user_id=user.id,
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped}


class FeeSquareDismiss(BaseModel):
    external_ref: str
    item_name: Optional[str] = None
    note: Optional[str] = None
    amount: Optional[float] = None
    occurred_at: Optional[str] = None


@router.post("/square/dismiss")
async def fee_square_dismiss(
    data: FeeSquareDismiss,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Mark a Square sale as not a fee payment (e.g. a canteen item that
    happened to match a keyword) so it stops showing up in the review queue."""
    existing = (await db.execute(
        select(FeeSquareImportLog).where(
            FeeSquareImportLog.organisation_id == club.id,
            FeeSquareImportLog.external_ref == data.external_ref,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"ok": True, "already_resolved": True}
    db.add(FeeSquareImportLog(
        id=uuid.uuid4(), organisation_id=club.id, external_ref=data.external_ref,
        status="dismissed", item_name=data.item_name, note=data.note,
        amount=_money(data.amount) if data.amount is not None else None,
        occurred_at=_parse_date(data.occurred_at), created_by_user_id=user.id,
    ))
    await db.commit()
    return {"ok": True}


# ───────────────────────────────────────────────────────────────────────────
# Xero import — completed bank transactions reviewed and matched to a member
# ───────────────────────────────────────────────────────────────────────────
# Unlike Square, this connection is owned entirely by BetterFees, so its OAuth
# connect/disconnect lives here rather than being shared with another module.
# Read-only (accounting.transactions.read only) — nothing here ever writes to
# Xero. The public callback (routers/public_xero.py) exchanges the code and
# stores the token; this router covers status, tenant/bank-account pickers,
# settings, and the preview/commit/dismiss review flow.

def _fee_xero_status(conn: Optional[FeeXeroConnection]) -> dict:
    return {
        "configured": settings.xero_configured,
        "connected": bool(conn and conn.access_token),
        "tenant_name": conn.tenant_name if conn else None,
        "needs_tenant": bool(conn and conn.access_token and not conn.tenant_id),
        "bank_account_name": conn.bank_account_name if conn else None,
        "needs_bank_account": bool(conn and conn.access_token and conn.tenant_id and not conn.bank_account_id),
        "sync_enabled": conn.sync_enabled if conn else False,
        "last_sync_at": conn.last_sync_at.isoformat() if conn and conn.last_sync_at else None,
        "last_sync_status": conn.last_sync_status if conn else None,
        "last_sync_error": conn.last_sync_error if conn else None,
    }


@router.get("/xero/status")
async def fee_xero_status(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    return _fee_xero_status(conn)


@router.get("/xero/connect-url")
async def fee_xero_connect_url(
    current_user: User = Depends(require_cap(MANAGE_FEES)),
    club: Organisation = Depends(get_current_club),
):
    if not settings.xero_configured:
        raise HTTPException(status_code=400, detail="Xero is not configured on this server")
    state = sign_xero_state(club.id, current_user.id)
    return {"url": xero_client.authorize_url(state)}


@router.get("/xero/tenants")
async def fee_xero_tenants(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Xero first")
    try:
        token = await fee_xero_service.ensure_fresh_token(db, conn)
        tenants = await xero_client.list_connections(token)
    except xero_client.XeroError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"tenants": [{"id": t.get("tenantId"), "name": t.get("tenantName")} for t in tenants]}


class XeroTenantIn(BaseModel):
    tenant_id: str
    tenant_name: Optional[str] = None


@router.post("/xero/tenant")
async def fee_xero_set_tenant(
    body: XeroTenantIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Xero first")
    conn.tenant_id = body.tenant_id
    conn.tenant_name = body.tenant_name
    # Switching organisation invalidates any previously-picked bank account.
    conn.bank_account_id = None
    conn.bank_account_name = None
    await db.commit()
    return _fee_xero_status(conn)


@router.get("/xero/bank-accounts")
async def fee_xero_bank_accounts(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token or not conn.tenant_id:
        raise HTTPException(status_code=400, detail="Connect Xero and pick an organisation first")
    try:
        token = await fee_xero_service.ensure_fresh_token(db, conn)
        accounts = await xero_client.list_bank_accounts(token, conn.tenant_id)
    except xero_client.XeroError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"accounts": [{"id": a.get("AccountID"), "name": a.get("Name"), "code": a.get("Code")} for a in accounts]}


class XeroBankAccountIn(BaseModel):
    bank_account_id: str
    bank_account_name: Optional[str] = None


@router.post("/xero/bank-account")
async def fee_xero_set_bank_account(
    body: XeroBankAccountIn,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Xero first")
    conn.bank_account_id = body.bank_account_id
    conn.bank_account_name = body.bank_account_name
    await db.commit()
    return _fee_xero_status(conn)


class FeeXeroSettings(BaseModel):
    sync_enabled: Optional[bool] = None


@router.post("/xero/settings")
async def fee_xero_settings(
    data: FeeXeroSettings,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Xero first")
    if data.sync_enabled is not None:
        conn.sync_enabled = data.sync_enabled
    await db.commit()
    return _fee_xero_status(conn)


@router.post("/xero/preview")
async def fee_xero_preview(
    season_id: str,
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Completed Xero bank transactions on the chosen account, each with a
    suggested member match — nothing is written until /xero/commit."""
    season = await _season_or_404(db, club, season_id)
    conn = await fee_xero_service.get_connection(db, club.id)
    if not conn or not conn.access_token:
        raise HTTPException(status_code=400, detail="Connect Xero first")
    if not conn.tenant_id:
        raise HTTPException(status_code=400, detail="Pick a Xero organisation first")
    if not conn.bank_account_id:
        raise HTTPException(status_code=400, detail="Pick a Xero bank account first")
    if not conn.sync_enabled:
        raise HTTPException(status_code=400, detail="Turn on Xero import below first")
    try:
        rows = await fee_xero_service.fetch_candidates(db, club, season.id, conn)
        conn.last_sync_at = datetime.now(timezone.utc)
        conn.last_sync_status = "ok"
        conn.last_sync_error = None
        await db.commit()
    except xero_client.XeroError as e:
        conn.last_sync_at = datetime.now(timezone.utc)
        conn.last_sync_status = "error"
        conn.last_sync_error = str(e)[:500]
        await db.commit()
        raise HTTPException(status_code=502, detail=str(e))
    return {"rows": rows}


class FeeXeroCommitItem(BaseModel):
    external_ref: str
    description: str
    amount: float
    occurred_at: Optional[str] = None
    note: Optional[str] = None
    member_season_id: str
    kind: str = "match_day"


class FeeXeroCommit(BaseModel):
    items: List[FeeXeroCommitItem]


@router.post("/xero/commit")
async def fee_xero_commit(
    data: FeeXeroCommit,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Apply reviewed Xero bank transactions as fee payments. Every item must
    already carry the member the admin picked in the review UI. Any row
    already resolved since preview was fetched is silently skipped rather
    than double-applied."""
    if not data.items:
        return {"created": 0, "skipped": 0}

    ms_cache: dict = {}
    for i, item in enumerate(data.items):
        try:
            ms_id = uuid.UUID(item.member_season_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Row {i}: invalid member_season_id")
        if ms_id not in ms_cache:
            ms = await db.get(FeeMemberSeason, ms_id)
            if not ms or ms.organisation_id != club.id:
                raise HTTPException(status_code=422, detail=f"Row {i}: member season not found")
            ms_cache[ms_id] = ms
        if item.kind not in PAYMENT_KINDS:
            raise HTTPException(status_code=422, detail=f"Row {i}: kind must be one of {PAYMENT_KINDS}")
        if item.amount <= 0:
            raise HTTPException(status_code=422, detail=f"Row {i}: amount must be > 0")

    created = 0
    skipped = 0
    for item in data.items:
        existing = (await db.execute(
            select(FeeXeroImportLog).where(
                FeeXeroImportLog.organisation_id == club.id,
                FeeXeroImportLog.external_ref == item.external_ref,
            )
        )).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        payment = FeePayment(
            id=uuid.uuid4(),
            member_season_id=uuid.UUID(item.member_season_id),
            organisation_id=club.id,
            amount=_money(item.amount),
            paid_at=_parse_date(item.occurred_at),
            kind=item.kind,
            method="Xero",
            notes=item.note or item.description,
            source="xero",
            external_ref=item.external_ref,
            created_by_user_id=user.id,
        )
        db.add(payment)
        await db.flush()
        db.add(FeeXeroImportLog(
            id=uuid.uuid4(), organisation_id=club.id, external_ref=item.external_ref,
            status="applied", fee_payment_id=payment.id, description=item.description,
            amount=_money(item.amount), occurred_at=_parse_date(item.occurred_at),
            created_by_user_id=user.id,
        ))
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped}


class FeeXeroDismiss(BaseModel):
    external_ref: str
    description: Optional[str] = None
    amount: Optional[float] = None
    occurred_at: Optional[str] = None


@router.post("/xero/dismiss")
async def fee_xero_dismiss(
    data: FeeXeroDismiss,
    user: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Mark a Xero bank transaction as not a fee payment (e.g. sponsorship
    income sitting in the same account) so it stops showing up in review."""
    existing = (await db.execute(
        select(FeeXeroImportLog).where(
            FeeXeroImportLog.organisation_id == club.id,
            FeeXeroImportLog.external_ref == data.external_ref,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"ok": True, "already_resolved": True}
    db.add(FeeXeroImportLog(
        id=uuid.uuid4(), organisation_id=club.id, external_ref=data.external_ref,
        status="dismissed", description=data.description,
        amount=_money(data.amount) if data.amount is not None else None,
        occurred_at=_parse_date(data.occurred_at), created_by_user_id=user.id,
    ))
    await db.commit()
    return {"ok": True}


@router.post("/xero/disconnect")
async def fee_xero_disconnect(
    _: User = _require,
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    conn = await fee_xero_service.get_connection(db, club.id)
    if conn:
        if conn.refresh_token:
            try:
                await xero_client.revoke_token(conn.refresh_token)
            except Exception:
                pass  # best-effort; still drop our stored copy
        await db.delete(conn)
        await db.commit()
    return {"ok": True}
