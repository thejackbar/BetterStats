"""Super-admin API over the marketing club directory (BetterCricket outreach).

Cross-club platform tooling, so gated by ``require_super_admin`` (not a per-club
capability), same posture as the KlubPro migration router. Lets staff watch the
crawl, search/filter the collected clubs, export the selection into a BetterComms
campaign (the existing send pipeline), and download a CSV.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db, async_session_maker, MarketingClub, MarketingClubContact
from app.routers.auth import require_super_admin
from app.services import club_directory as cd

router = APIRouter(prefix="/club-admin/marketing", tags=["marketing"])


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    return await cd.directory_stats(db)


@router.get("/clubs")
async def list_clubs(
    q: Optional[str] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    kind: Optional[str] = "club",
    with_email: bool = False,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    stmt = select(MarketingClub).where(MarketingClub.detail_fetched_at.isnot(None))
    if kind:
        stmt = stmt.where(MarketingClub.kind == kind)
    if state:
        stmt = stmt.where(MarketingClub.state == state)
    if status:
        stmt = stmt.where(MarketingClub.status == status)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(MarketingClub.name).like(like),
                              func.lower(MarketingClub.association_name).like(like)))
    if with_email:
        stmt = stmt.where(MarketingClub.contact_email.isnot(None))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    stmt = stmt.order_by(MarketingClub.name.asc()).limit(limit).offset(offset)
    clubs = (await db.execute(stmt)).scalars().all()

    out = []
    for c in clubs:
        contacts = (await db.execute(
            select(MarketingClubContact)
            .where(MarketingClubContact.marketing_club_id == c.id)
            .order_by(MarketingClubContact.role_rank.asc())
        )).scalars().all()
        out.append({
            "id": str(c.id), "name": c.name, "playhq_id": c.playhq_id,
            "grassroots_guid": c.grassroots_guid, "association_name": c.association_name,
            "association_guid": c.association_guid, "associations": c.associations,
            "suburb": c.suburb, "state": c.state,
            "postcode": c.postcode, "address_line1": c.address_line1,
            "website_url": c.website_url, "status": c.status,
            "is_customer": c.existing_org_id is not None,
            "contacts": [{
                "id": str(ct.id), "full_name": ct.full_name, "role": ct.role,
                "email": ct.email, "mobile": ct.mobile, "source": ct.source,
                "subscribed": ct.subscribed, "selected": ct.outreach_selected,
            } for ct in contacts],
        })
    return {"total": total or 0, "limit": limit, "offset": offset, "clubs": out}


async def _crawl_bg(limit: Optional[int], rediscover: bool):
    async with async_session_maker() as session:
        await cd.crawl_batch(session, limit=limit, rediscover=rediscover)


@router.post("/crawl")
async def trigger_crawl(
    background: BackgroundTasks,
    limit: Optional[int] = None,
    rediscover: bool = False,
    _=Depends(require_super_admin),
):
    """Kick off one crawl batch in the background. Returns immediately; poll
    /stats to watch associations_pending shrink. The crawl is rate-limited, so it
    takes a while — leave it running. First run (empty directory) discovers every
    club; pass rediscover=true to re-page the club list and pick up new clubs."""
    background.add_task(_crawl_bg, limit, rediscover)
    return {"started": True, "limit": limit or "configured nightly limit",
            "rediscover": rediscover}


class ExportBody(BaseModel):
    organisation_id: Optional[str] = None
    states: Optional[list[str]] = None
    include_associations: bool = False
    # Default True: only push contacts a super admin ticked for outreach. Set
    # False to export every subscribed, emailable contact regardless of selection.
    selected_only: bool = True


@router.post("/export-comms")
async def export_comms(body: ExportBody, db: AsyncSession = Depends(get_db),
                       _=Depends(require_super_admin)):
    """Push the selected contacts into comms_contacts under the outreach org, so
    a BetterComms campaign can send to them with full unsubscribe/suppression."""
    return await cd.export_to_comms(
        db, organisation_id=body.organisation_id, states=body.states,
        include_associations=body.include_associations,
        selected_only=body.selected_only)


class ContactSelectBody(BaseModel):
    selected: bool


@router.patch("/contacts/{contact_id}")
async def set_contact_selected(contact_id: str, body: ContactSelectBody,
                               db: AsyncSession = Depends(get_db),
                               _=Depends(require_super_admin)):
    """Tick / untick one contact for outreach. This is how a super admin decides
    which of a club's committee receive the BetterComms email."""
    contact = await db.get(MarketingClubContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    contact.outreach_selected = body.selected
    await db.commit()
    return {"id": contact_id, "selected": contact.outreach_selected}


@router.post("/sync-suppressions")
async def sync_suppressions(organisation_id: Optional[str] = None,
                            db: AsyncSession = Depends(get_db),
                            _=Depends(require_super_admin)):
    """Pull comms unsubscribes/bounces back into the directory's suppression flag."""
    return await cd.sync_suppressions(db, organisation_id=organisation_id)


@router.get("/export.csv")
async def export_csv(
    state: Optional[str] = None,
    include_associations: bool = False,
    only_with_email: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    csv_text = await cd.clubs_to_csv(
        db, states=[state] if state else None,
        only_with_email=only_with_email, include_associations=include_associations)
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marketing_clubs.csv"})
