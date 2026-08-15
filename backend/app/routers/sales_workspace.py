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

from app.models.db import (
    ClubMembership, CrmActivity, CrmDeal, CrmPerson, MarketingClub, MarketingClubContact,
    SalesListClub, User, get_db,
)
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
    list_id: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """One row per club (an open platform deal), sorted by a simple priority
    heuristic by default. A 'sales'-role caller only ever sees their own
    deals — the owner_user_id query param is honoured for a super admin only.
    ``list_id`` narrows the queue to one Sales List's clubs (still whatever
    deal each one currently is, not a frozen snapshot)."""
    pipeline = await crm_service.ensure_platform_pipeline(db)
    stage_by_id = {s.id: s for s in pipeline.stages}
    stage_by_key = {s.key: s for s in pipeline.stages}

    effective_owner = None
    if actor.role == "sales":
        effective_owner = actor.user.id
    elif owner_user_id:
        effective_owner = _uuid_or_none(owner_user_id)

    deals = await crm_service.list_deals(db, pipeline.id, status="open", owner_user_id=effective_owner)
    if list_id:
        lid = _uuid_or_none(list_id)
        member_rows = (await db.execute(
            select(SalesListClub.marketing_club_id).where(SalesListClub.sales_list_id == lid)
        )).scalars().all()
        member_ids = set(member_rows)
        deals = [d for d in deals if d.marketing_club_id in member_ids]
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
        club = club_by_id.get(d.marketing_club_id)
        row = crm_service._deal_dict(d, stage_by_id.get(d.stage_id), club)
        owner = owners.get(d.owner_user_id)
        row["owner_name"] = (owner.display_name or owner.username) if owner else None
        row["contact_count"] = contact_counts.get(d.marketing_club_id, 0)
        row["not_interested"] = bool(club.not_interested) if club else False
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


@router.get("/performance")
async def performance(
    owner_user_id: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Today/this-week activity + the assigned -> attempted -> contacted ->
    engaged -> trial -> won funnel, per rep. A 'sales'-role caller always
    sees only their own numbers (owner_user_id is honoured for a super
    admin only, same restriction pattern as the queue list)."""
    effective_owner = actor.user.id if actor.role == "sales" else (_uuid_or_none(owner_user_id) if owner_user_id else None)
    summary = await sw.performance_summary(db, owner_user_id=effective_owner)
    by_rep = await sw.funnel_by_rep(db, owner_user_id=effective_owner)
    return {"summary": summary, "by_rep": by_rep}


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
    deal_out["not_interested"] = bool(club.not_interested) if club else False
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


# ─── Email actions ─────────────────────────────────────────────────────────────

@router.get("/email-templates")
async def email_templates(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    from app.services import platform_settings as ps
    from app.services import sales_email as se
    links = await ps.get_demo_booking_links(db)
    rep_name = actor.user.display_name or actor.user.username
    return {
        "templates": [{"key": k, "label": v} for k, v in se.TEMPLATE_LABELS.items()],
        "demo_link_configured": bool(links.get(rep_name)),
    }


class EmailBody(BaseModel):
    directory_contact_id: Optional[str] = None
    crm_person_id: Optional[str] = None
    template: str  # 'information' | 'trial_information' | 'demo' | 'custom'
    subject: Optional[str] = None  # required for 'custom'
    body: Optional[str] = None  # required for 'custom'


@router.post("/clubs/{deal_id}/email")
async def send_email(
    deal_id: str,
    body: EmailBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    from app.services import platform_settings as ps
    from app.services import sales_email as se

    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)

    if not (body.directory_contact_id or body.crm_person_id):
        raise HTTPException(status_code=422, detail="Pick a contact to email")
    try:
        person = await sw.resolve_or_materialize_person(
            db, marketing_club_id=deal.marketing_club_id,
            directory_contact_id=_uuid_or_none(body.directory_contact_id),
            crm_person_id=_uuid_or_none(body.crm_person_id),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    to_email = (person.email or "").strip()
    if not to_email:
        raise HTTPException(status_code=422, detail="This contact has no email address on file")

    # Refuse an opted-out / do-not-contact contact — the same rule the
    # drawer's badge/toggle enforces, re-checked server-side so a stale
    # client can't route around it.
    if person.directory_contact_id:
        contact_row = await db.get(MarketingClubContact, person.directory_contact_id)
        if contact_row is not None:
            if contact_row.do_not_contact:
                raise HTTPException(status_code=422, detail="This contact has asked not to be contacted")
            if not contact_row.subscribed or contact_row.unsubscribed_at or contact_row.bounced:
                raise HTTPException(status_code=422, detail="This contact has opted out of email")

    club = await db.get(MarketingClub, deal.marketing_club_id) if deal.marketing_club_id else None
    club_name = club.name if club else deal.title
    rep_name = actor.user.display_name or actor.user.username
    template = body.template

    if template == "custom":
        if not (body.subject or "").strip() or not (body.body or "").strip():
            raise HTTPException(status_code=422, detail="Subject and body are required for a custom email")
        subject, html_body, text_body = se.render_custom(body.subject.strip(), body.body.strip(), rep_name)
    elif template in se.BUILT_IN_TEMPLATES:
        calendly_url = None
        if template == "demo":
            links = await ps.get_demo_booking_links(db)
            calendly_url = links.get(rep_name)
        subject, html_body, text_body = se.render_template(
            template, contact_name=person.full_name, club_name=club_name, rep_name=rep_name,
            calendly_url=calendly_url,
        )
    else:
        raise HTTPException(status_code=422, detail="Unknown email template")

    # utm_code: auto-generate + persist the same way club_directory.py does
    # for a crawled club, so a link sent before the club had one still gets
    # tracked attribution from here on — both to the club (utm_id) and to
    # this sending rep (utm_content), per direct instruction.
    utm_code = None
    if club is not None:
        if not club.utm_code:
            from app.services.club_directory import _default_utm
            club.utm_code = _default_utm(club.name)
        utm_code = club.utm_code or None
    html_body = se.apply_sales_utm(html_body, template_key=template, rep_username=actor.user.username, utm_code=utm_code)

    try:
        await se.send_sales_email(
            to_email=to_email, to_name=person.full_name, subject=subject, html=html_body, text=text_body,
            rep_name=rep_name, rep_email=actor.user.email,
        )
    except Exception as e:  # noqa: BLE001 - surfaced to the rep, this is an explicit action, not best-effort
        raise HTTPException(status_code=502, detail=f"Could not send email: {e}")

    await crm_service.log_activity(
        db, deal_id=deal.id, person_id=person.id, type="email",
        body=f"{se.TEMPLATE_LABELS.get(template, template)} sent to {to_email}",
        created_by_user_id=actor.user.id,
        meta={"template": template, "subject": subject},
    )
    await db.commit()
    return {"status": "sent"}


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


class DoNotContactBody(BaseModel):
    do_not_contact: bool
    reason: Optional[str] = None


@router.patch("/clubs/{deal_id}/contacts/{contact_id}/do-not-contact")
async def set_contact_do_not_contact(
    deal_id: str,
    contact_id: str,
    body: DoNotContactBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Scoped through the deal (not a bare contact id) so the same ownership
    check every other write here uses applies — a sales rep can only flag a
    contact belonging to a club that's actually theirs."""
    deal = await _load_deal(db, deal_id)
    _assert_can_touch(actor, deal)
    cid = _uuid_or_none(contact_id)
    contact = await db.get(MarketingClubContact, cid) if cid else None
    if contact is None or contact.marketing_club_id != deal.marketing_club_id:
        raise HTTPException(status_code=404, detail="Contact not found")
    await sw.set_contact_do_not_contact(db, contact, body.do_not_contact, body.reason)
    await db.commit()
    return {"status": "ok"}


# ─── Follow-ups queue ──────────────────────────────────────────────────────────

@router.get("/follow-ups")
async def follow_ups(
    owner_user_id: Optional[str] = None,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    effective_owner = actor.user.id if actor.role == "sales" else (_uuid_or_none(owner_user_id) if owner_user_id else None)
    rows = await sw.list_follow_ups(db, owner_user_id=effective_owner)

    deal_ids = {a.deal_id for a in rows if a.deal_id}
    deals = {}
    if deal_ids:
        deal_rows = (await db.execute(select(CrmDeal).where(CrmDeal.id.in_(deal_ids)))).scalars().all()
        deals = {d.id: d for d in deal_rows}
    club_by_id = await crm_service.clubs_by_ids(db, (d.marketing_club_id for d in deals.values()))
    person_ids = {a.person_id for a in rows if a.person_id}
    people = {}
    if person_ids:
        person_rows = (await db.execute(select(CrmPerson).where(CrmPerson.id.in_(person_ids)))).scalars().all()
        people = {p.id: p for p in person_rows}
    owner_ids = {d.owner_user_id for d in deals.values() if d.owner_user_id}
    owners = {}
    if owner_ids:
        owner_rows = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners = {u.id: u for u in owner_rows}

    out = []
    for a in rows:
        deal = deals.get(a.deal_id)
        club = club_by_id.get(deal.marketing_club_id) if deal else None
        person = people.get(a.person_id) if a.person_id else None
        owner = owners.get(deal.owner_user_id) if deal and deal.owner_user_id else None
        due_at = a.next_follow_up_at
        bucket = "upcoming"
        if due_at is not None:
            due_naive = due_at.replace(tzinfo=None) if due_at.tzinfo else due_at
            today = datetime.utcnow().date()
            if due_naive.date() < today:
                bucket = "overdue"
            elif due_naive.date() == today:
                bucket = "today"
        out.append({
            "activity_id": str(a.id),
            "deal_id": str(a.deal_id) if a.deal_id else None,
            "club_name": club.name if club else (deal.title if deal else None),
            "contact_name": person.full_name if person else None,
            "owner_name": (owner.display_name or owner.username) if owner else None,
            "outcome": a.outcome,
            "notes": a.body,
            "due_at": due_at.isoformat() if due_at else None,
            "bucket": bucket,
        })
    return {"follow_ups": out}


@router.post("/follow-ups/{activity_id}/done")
async def complete_follow_up(
    activity_id: str,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    aid = _uuid_or_none(activity_id)
    activity = await db.get(CrmActivity, aid) if aid else None
    if activity is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    deal = await _load_deal(db, str(activity.deal_id)) if activity.deal_id else None
    if deal is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    _assert_can_touch(actor, deal)
    await sw.mark_follow_up_done(db, activity)
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


class BulkAssignBody(BaseModel):
    deal_ids: list[str]
    owner_user_ids: list[str]  # one id = assign all to them; several = split evenly, round-robin


@router.post("/bulk-assign")
async def bulk_assign(
    body: BulkAssignBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Filter the queue down to a batch (never called, a state, a stage,
    unassigned…) then assign the whole selection in one action — "Assign
    selected -> Sam" or "Split evenly among Sam / Jake / Sarah", per the
    brief. Super-admin only, same as the single-deal PATCH .../assign."""
    _require_super(actor)
    if not body.deal_ids:
        raise HTTPException(status_code=422, detail="Select at least one club")
    owner_ids = [_uuid_or_none(o) for o in body.owner_user_ids if o]
    if not owner_ids:
        raise HTTPException(status_code=422, detail="Pick at least one salesperson")

    owners = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
    found_ids = {u.id for u in owners}
    missing = [str(o) for o in owner_ids if o not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Unknown salesperson id(s): {', '.join(missing)}")
    owner_names = {u.id: (u.display_name or u.username) for u in owners}

    deal_uuids = [_uuid_or_none(d) for d in body.deal_ids]
    deals = (await db.execute(
        select(CrmDeal).where(
            CrmDeal.id.in_(deal_uuids), CrmDeal.scope == crm_service.SCOPE_PLATFORM,
            CrmDeal.archived_at.is_(None),
        )
    )).scalars().all()
    if not deals:
        raise HTTPException(status_code=404, detail="None of the selected clubs could be found")

    counts = await sw.bulk_assign(
        db, deals=deals, owner_ids=owner_ids, owner_names=owner_names, created_by_user_id=actor.user.id,
    )
    await db.commit()
    return {
        "assigned": len(deals),
        "skipped": len(body.deal_ids) - len(deals),
        "by_rep": {owner_names.get(uuid.UUID(k), k): v for k, v in counts.items()},
    }


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


# ─── Sales Lists ──────────────────────────────────────────────────────────────
# A thin provenance/import layer over the same crm_deals rows — importing a
# list never creates a second record of a club's history, and assigning one
# reuses the existing POST /bulk-assign (filter the queue to ?list_id=..,
# select, assign) rather than a second assignment code path.

@router.get("/lists")
async def sales_lists(actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db)):
    """Every Sales List, for the picker on the Sales Lists page and the
    queue's list filter. Open to both roles — a rep narrowing their own
    queue to one list is a read, not an admin action."""
    return {"lists": await sw.list_sales_lists(db)}


@router.get("/lists/{list_id}")
async def sales_list_detail(
    list_id: str, actor: SalesActor = Depends(require_sales_or_super), db: AsyncSession = Depends(get_db),
):
    lid = _uuid_or_none(list_id)
    result = await sw.get_sales_list(db, lid) if lid else None
    if result is None:
        raise HTTPException(status_code=404, detail="List not found")
    return result


class ImportWizardClubsBody(BaseModel):
    name: str
    description: str = ""
    days: int = 90
    club_keys: list[str]


@router.post("/lists/from-wizard-clubs")
async def import_from_wizard_clubs(
    body: ImportWizardClubsBody,
    actor: SalesActor = Depends(require_sales_or_super),
    db: AsyncSession = Depends(get_db),
):
    """Bulk-import a Wizard Clubs selection into a new Sales List — matches
    each one to its Club Directory row and ensures it has an open platform
    deal, so it shows up in the queue immediately. Super-admin only, same
    posture as bulk-assign (this is sales-ops list-building, not a rep's
    daily calling work)."""
    _require_super(actor)
    days = max(1, min(body.days, 730))
    result = await sw.create_list_from_wizard_clubs(
        db, name=body.name, description=body.description, days=days,
        club_keys=body.club_keys, created_by_user_id=actor.user.id,
    )
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result.get("detail") or result["error"])
    await db.commit()
    return result
