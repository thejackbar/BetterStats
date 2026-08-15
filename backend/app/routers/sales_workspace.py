"""Sales Workspace — Phase 1: the calling-focused lens over BetterCRM's
platform pipeline (see services/sales_workspace.py for the design rationale).

Gated by ``require_sales_or_super`` (routers/auth.py) rather than
``require_super_admin`` — a 'sales'-role user gets the same shape of access a
super admin does here, restricted to the deals they own (``owner_user_id``).
Every write re-uses the SAME crm_deals/crm_activities/crm_people rows the
Sales Pipeline board manages; there is no separate Sales Workspace schema.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubMembership, CrmDeal, MarketingClub, User, get_db
from app.routers.auth import SalesActor, require_sales_or_super
from app.services import crm as crm_service
from app.services import sales_workspace as sw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin/sales-workspace", tags=["sales-workspace"])


def _uuid_or_none(value: Optional[str]):
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid id")


async def _load_deal(db: AsyncSession, deal_id: str) -> CrmDeal:
    """The one chokepoint every handler loads a deal through. Always
    refreshes: db.get() on an object already in the identity map does NOT
    by itself repopulate attributes a prior commit()/rollback() in this same
    request expired (verified against a real Postgres instance while
    building this — a naive db.get()-only reload still threw MissingGreenlet
    the moment a handler serialised the deal after its own commit). A plain
    first-ever load in this request just costs one harmless extra
    primary-key SELECT."""
    did = _uuid_or_none(deal_id)
    deal = await db.get(CrmDeal, did) if did else None
    if deal is None:
        raise HTTPException(status_code=404, detail="Club not found")
    await db.refresh(deal)
    if deal.scope != crm_service.SCOPE_PLATFORM or deal.archived_at is not None:
        raise HTTPException(status_code=404, detail="Club not found")
    return deal


def _assert_can_touch(actor: SalesActor, deal: CrmDeal) -> None:
    if actor.role == "sales" and (deal.owner_user_id is None or str(deal.owner_user_id) != str(actor.user.id)):
        raise HTTPException(status_code=403, detail="This club isn't assigned to you")


def _require_super(actor: SalesActor) -> None:
    if actor.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin only")


# ─── Queue ────────────────────────────────────────────────────────────────────

@router.get("/clubs")
async def list_clubs(
    q: Optional[str] = None,
    stage_key: Optional[str] = None,
    owner_user_id: Optional[str] = None,
    never_called: bool = False,
    callback_due: bool = False,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """One row per club (an open platform deal), sorted by a simple priority
    heuristic by default. A 'sales'-role caller only ever sees their own
    deals — the owner_user_id query param is honoured for a super admin only."""
    pipeline = await crm_service.ensure_platform_pipeline(db)
    stage_by_id = {s.id: s for s in pipeline.stages}
    stage_by_key = {s.key: s for s in pipeline.stages}

    effective_owner = None
    if actor.role == "sales":
        effective_owner = actor.user.id
    elif owner_user_id:
        effective_owner = _uuid_or_none(owner_user_id)

    deals = await crm_service.list_deals(db, pipeline.id, status="open", owner_user_id=effective_owner)
    if stage_key:
        target = stage_by_key.get(stage_key)
        deals = [d for d in deals if target and d.stage_id == target.id]
    if q:
        needle = q.strip().lower()
        deals = [d for d in deals if needle in (d.title or "").lower()]

    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals))
    deal_ids = [d.id for d in deals]
    last_calls = await sw.last_calls_by_deal(db, deal_ids)
    follow_ups = await sw.next_follow_ups_by_deal(db, deal_ids)
    contact_counts = await sw.contact_counts_by_club(db, (d.marketing_club_id for d in deals))

    owner_ids = {d.owner_user_id for d in deals if d.owner_user_id}
    owners = {}
    if owner_ids:
        rows = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners = {u.id: u for u in rows}

    out = []
    for d in deals:
        row = crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club_by_id.get(d.marketing_club_id))
        owner = owners.get(d.owner_user_id)
        row["owner_name"] = (owner.display_name or owner.username) if owner else None
        row["contact_count"] = contact_counts.get(d.marketing_club_id, 0)
        last_call = last_calls.get(d.id)
        row["ever_called"] = last_call is not None
        row["last_call"] = crm_service._activity_dict(last_call) if last_call else None
        follow_up_at = follow_ups.get(d.id)
        row["next_follow_up_at"] = follow_up_at.isoformat() if follow_up_at else None
        # deal.updated_at is a cheap proxy for "recent signal" (it also moves
        # on engagement-driven auto-promotion elsewhere in the CRM engine) —
        # a full multi-source recency query per row isn't worth it for a v1
        # heuristic. See services/sales_workspace.priority_score's own note.
        row["priority_score"] = sw.priority_score(
            engagement_score=row["engagement_score"], ever_called=row["ever_called"],
            next_follow_up_at=follow_up_at, last_signal_at=d.updated_at,
        )
        out.append(row)

    if never_called:
        out = [r for r in out if not r["ever_called"]]
    if callback_due:
        now_iso = datetime.utcnow().isoformat()
        out = [r for r in out if r["next_follow_up_at"] and r["next_follow_up_at"] <= now_iso]

    out.sort(key=lambda r: r["priority_score"], reverse=True)
    return {
        "clubs": out,
        "stages": [{"id": str(s.id), "key": s.key, "name": s.name} for s in pipeline.stages],
    }


@router.get("/team")
async def team(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Sales reps, for the super admin's owner filter/assignment picker.
    Provisioning a new one is done from Super Admin -> Users (role 'sales')."""
    _require_super(actor)
    rows = (await db.execute(
        select(User, ClubMembership)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .where(ClubMembership.role == "sales")
        .order_by(User.display_name, User.username)
    )).all()
    return {"team": [
        {"id": str(u.id), "username": u.username, "display_name": u.display_name}
        for u, _m in rows
    ]}


# ─── Club drawer ──────────────────────────────────────────────────────────────

@router.get("/clubs/{deal_id}")
async def get_club(
    deal_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)

    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in pipeline.stages if s.id == deal.stage_id), None) if pipeline else None
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None

    contacts = await sw.merged_contacts(db, deal.marketing_club_id)
    activities = await crm_service.list_activities(db, deal_id=deal.id)
    activities_out = [crm_service._activity_dict(a) for a in activities]

    # Every ORM attribute this response needs is read into plain dicts/lists
    # BEFORE calling club_engagement_breakdown below — that function commits
    # to "read-only, always rollback", and a rollback expires every ORM
    # object still attached to this session (deal/stage/club included), which
    # would otherwise throw MissingGreenlet the moment _deal_dict tried to
    # read an attribute off `deal` afterward.
    deal_out = crm_service._deal_dict(deal, stage, club)
    stage_options = [{"id": str(s.id), "key": s.key, "name": s.name} for s in (pipeline.stages if pipeline else [])]

    engagement = None
    if club is not None:
        try:
            from app.routers.marketing import club_engagement_breakdown
            engagement = await club_engagement_breakdown(str(club.id), db)
        except HTTPException:
            engagement = None
        except Exception:  # noqa: BLE001 - the drawer must still render without it
            logger.exception("sales_workspace: engagement breakdown failed for club %s", club.id)
            engagement = None

    return {
        "deal": deal_out,
        "contacts": contacts,
        "activities": activities_out,
        "engagement": engagement,
        "stage_options": stage_options,
        "can_assign": actor.role == "super_admin",
    }


# ─── Calls ────────────────────────────────────────────────────────────────────

class CallLogBody(BaseModel):
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    outcome: str
    notes: Optional[str] = None
    next_follow_up_at: Optional[datetime] = None


@router.get("/call-outcomes")
async def call_outcomes(_: SalesActor = Depends(require_sales_or_super)):
    return {"groups": sw.outcome_options()}


@router.post("/clubs/{deal_id}/calls")
async def log_call(
    deal_id: str,
    body: CallLogBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if body.outcome not in sw.CALL_OUTCOMES:
        raise HTTPException(status_code=422, detail="Unknown call outcome")

    person = None
    if body.directory_contact_id or body.crm_person_id:
        try:
            person = await sw.resolve_or_materialize_person(
                db, marketing_club_id=deal.marketing_club_id,
                directory_contact_id=_uuid_or_none(body.directory_contact_id),
                crm_person_id=_uuid_or_none(body.crm_person_id),
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    await sw.log_call(
        db, deal=deal, person=person, outcome=body.outcome, notes=body.notes,
        next_follow_up_at=body.next_follow_up_at, created_by_user_id=actor.user.id,
    )
    await db.commit()
    return await get_club(deal_id, actor, db)


class NoteBody(BaseModel):
    body: str
    pinned: bool = False


@router.post("/clubs/{deal_id}/notes")
async def add_note(
    deal_id: str,
    body: NoteBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not (body.body or "").strip():
        raise HTTPException(status_code=422, detail="Note can't be empty")
    await sw.log_note(db, deal=deal, body=body.body.strip(), pinned=body.pinned, created_by_user_id=actor.user.id)
    await db.commit()
    return {"status": "ok"}


class ContactBody(BaseModel):
    full_name: str
    role: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.post("/clubs/{deal_id}/contacts")
async def add_contact(
    deal_id: str,
    body: ContactBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not deal.marketing_club_id:
        raise HTTPException(status_code=422, detail="This club has no Club Directory record to attach a contact to")
    if not (body.full_name or "").strip():
        raise HTTPException(status_code=422, detail="A name is required")
    if not ((body.email or "").strip() or (body.mobile or "").strip()):
        raise HTTPException(status_code=422, detail="An email or mobile number is required")
    await sw.add_directory_contact(
        db, marketing_club_id=deal.marketing_club_id, full_name=body.full_name.strip(),
        role=body.role, email=body.email, mobile=body.mobile,
    )
    await db.commit()
    return {"status": "ok"}


# ─── Assignment (super admin only) ────────────────────────────────────────────

class AssignBody(BaseModel):
    owner_user_id: Optional[str] = None  # None/omitted = unassign


@router.patch("/clubs/{deal_id}/assign")
async def assign(
    deal_id: str,
    body: AssignBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    _require_super(actor)
    deal = await _load_deal(db, deal_id)
    owner_id = _uuid_or_none(body.owner_user_id)
    owner_name = None
    if owner_id:
        owner = await db.get(User, owner_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="User not found")
        owner_name = owner.display_name or owner.username
    await crm_service.update_deal(db, deal, owner_user_id=owner_id)
    await sw.log_reassignment(db, deal=deal, owner_name=owner_name, created_by_user_id=actor.user.id)
    await db.commit()
    # commit() expires every attribute on `deal` — refresh before reading any
    # of them again (same MissingGreenlet trap this codebase documents
    # elsewhere: serialising an ORM object right after commit() lazy-loads
    # outside the greenlet).
    await db.refresh(deal)
    pipeline = await crm_service.get_deal_pipeline(db, deal)
    stage = next((s for s in pipeline.stages if s.id == deal.stage_id), None) if pipeline else None
    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    return crm_service._deal_dict(deal, stage, club)


# ─── Start a trial on the contact's behalf ────────────────────────────────────

class StartTrialBody(BaseModel):
    admin_first_name: str
    admin_last_name: str
    admin_display_name: str = ""
    admin_username: str
    admin_email: str
    admin_mobile_number: str = ""
    slug: Optional[str] = None
    short_name: Optional[str] = None
    contact_email: Optional[str] = None


@router.post("/clubs/{deal_id}/start-trial")
async def start_trial(
    deal_id: str,
    body: StartTrialBody,
    background_tasks: BackgroundTasks,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """The salesperson's equivalent of Super Admin -> All Clubs -> New Club —
    reuses that exact flow (org creation, first sync, every-module trial,
    Primary Admin invite email, Twenty push) rather than a second
    implementation, called directly with this rep as the acting user. Scoped
    to a club already in the rep's own queue (can't spin up an arbitrary new
    org) and refuses if it's already registered or has no real CA id on file.

    The deal itself isn't moved to the 'trial' stage here — create_club's own
    background CRM sync (crm.sync_super_admin_trial_registration) finds and
    advances this SAME open deal via its marketing_club_id, which is what
    keeps 'trial' meaning "an actual registration happened", never something
    a call outcome alone can set."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    if not deal.marketing_club_id:
        raise HTTPException(status_code=422, detail="This club isn't linked to a Club Directory prospect yet")
    club = await db.get(MarketingClub, deal.marketing_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    if club.existing_org_id:
        raise HTTPException(status_code=409, detail="This club is already registered")
    if not club.grassroots_guid:
        raise HTTPException(
            status_code=422,
            detail="This club has no Cricket Australia id on file — start it from All Clubs instead",
        )

    from app.routers.self_serve_trial import _slugify, _unique_slug
    slug = (body.slug or "").strip().lower()
    if not slug:
        slug = await _unique_slug(db, _slugify(club.name))

    from app.routers.club_admin import ClubCreate, create_club as _create_club
    payload = ClubCreate(
        org_id=club.grassroots_guid, name=club.name, slug=slug,
        short_name=body.short_name or club.short_name,
        contact_email=body.contact_email or club.contact_email,
        admin_first_name=body.admin_first_name, admin_last_name=body.admin_last_name,
        admin_display_name=body.admin_display_name, admin_username=body.admin_username,
        admin_email=body.admin_email, admin_mobile_number=body.admin_mobile_number,
    )
    result = await _create_club(payload, background_tasks, current_user=actor.user, db=db)

    await crm_service.log_activity(
        db, deal_id=deal.id, type="system",
        body=f"Trial started for {result['name']} by {actor.user.display_name or actor.user.username}",
        created_by_user_id=actor.user.id,
    )
    await db.commit()
    return result
