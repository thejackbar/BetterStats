"""Super-admin API over the marketing club directory (BetterCricket outreach).

Cross-club platform tooling, so gated by ``require_super_admin`` (not a per-club
capability), same posture as the KlubPro migration router. Lets staff watch the
crawl, search/filter the collected clubs, export the selection into a BetterComms
campaign (the existing send pipeline), and download a CSV.
"""
from __future__ import annotations

from typing import List, Optional

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


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Live crawl status (running / waiting / paused / idle / complete / stopped)
    derived from the table + window settings — survives page refresh and restarts."""
    return await cd.crawl_status(db)


class CrawlControlBody(BaseModel):
    paused: bool


@router.post("/crawl/control")
async def crawl_control(body: CrawlControlBody, db: AsyncSession = Depends(get_db),
                        _=Depends(require_super_admin)):
    """Stop (paused=true) or resume (paused=false) the background crawler. The
    continuous runner idles while stopped and an in-flight batch aborts at the next
    page/club; the flag is persisted so a Stop survives a restart."""
    return await cd.set_crawl_paused(db, body.paused)


def _filter_kwargs(q, state, association, status, postcode_from, postcode_to, contact,
                   person=None, exclude_junior=False, exclude_emailed=False,
                   exclude_carnival=False, exclude_school=False, associations=None):
    """Normalise the directory filter query-params into club_filters kwargs."""
    return {
        "q": q, "state": state, "association": association, "status": status,
        "postcode_from": postcode_from, "postcode_to": postcode_to,
        "contact_filter": contact if contact in cd.CONTACT_FILTERS else None,
        "person": person, "exclude_junior": bool(exclude_junior),
        "exclude_emailed": bool(exclude_emailed),
        "exclude_carnival": bool(exclude_carnival), "exclude_school": bool(exclude_school),
        "associations": [a for a in (associations or []) if a],
    }


@router.get("/associations")
async def list_associations(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Distinct associations (name + id + club count) for the multi-select filter."""
    return await cd.list_associations(db)


class ShortcodeBody(BaseModel):
    short_code: str


@router.patch("/associations/{assoc_id}/shortcode")
async def set_assoc_shortcode(assoc_id: str, body: ShortcodeBody,
                              db: AsyncSession = Depends(get_db),
                              _=Depends(require_super_admin)):
    """Edit an association's (searchable) short code. Blank resets it to the
    name-derived acronym."""
    res = await cd.set_association_shortcode(db, assoc_id, body.short_code)
    if res is None:
        raise HTTPException(status_code=404, detail="Association not found")
    return res


class ResolveAssocBody(BaseModel):
    id: str
    name: str


async def _resolve_bg(assoc_id: str, name: str):
    async with async_session_maker() as session:
        await cd.resolve_association_clubs(session, assoc_id, name)


@router.post("/associations/resolve")
async def resolve_association(body: ResolveAssocBody, background: BackgroundTasks,
                              _=Depends(require_super_admin)):
    """Fetch an association's full club roster live from PlayHQ and link those
    clubs to it. Runs in the background (it makes many sequential API calls and
    can take 30-90s, longer while the daily sweep is also running), so the request
    returns immediately and never hits the proxy's gateway timeout — refresh the
    list shortly to see the roster fill in."""
    background.add_task(_resolve_bg, body.id, body.name)
    return {"started": True, "association": body.name}


@router.get("/clubs")
async def list_clubs(
    q: Optional[str] = None,
    state: Optional[str] = None,
    association: Optional[str] = None,
    associations: Optional[List[str]] = Query(None),
    status: Optional[str] = None,
    postcode_from: Optional[str] = None,
    postcode_to: Optional[str] = None,
    contact: Optional[str] = None,   # '' | any_email | named_email | pst
    person: Optional[str] = None,
    exclude_junior: bool = False,
    exclude_emailed: bool = False,
    exclude_carnival: bool = False,
    exclude_school: bool = False,
    kind: Optional[str] = "club",
    group_by_association: bool = False,
    assoc_sort: str = "asc",
    club_sort: str = "asc",
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    stmt = select(MarketingClub).where(MarketingClub.detail_fetched_at.isnot(None))
    if kind:
        stmt = stmt.where(MarketingClub.kind == kind)
    kw = await cd.expand_shortcode(db, _filter_kwargs(
        q, state, association, status, postcode_from, postcode_to, contact,
        person, exclude_junior, exclude_emailed, exclude_carnival, exclude_school,
        associations))
    for cond in cd.club_filters(**kw):
        stmt = stmt.where(cond)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))

    def _dir(col, d):
        return col.desc() if (d or "").lower() == "desc" else col.asc()
    order = []
    if group_by_association:
        # group by the primary association; unassigned clubs sort last
        ac = func.lower(MarketingClub.association_name)
        order.append((ac.desc() if assoc_sort.lower() == "desc" else ac.asc()).nullslast())
    order.append(_dir(func.lower(MarketingClub.name), club_sort))
    stmt = stmt.order_by(*order).limit(limit).offset(offset)
    clubs = (await db.execute(stmt)).scalars().all()

    # Fetch all contacts for this page's clubs in ONE query (was N+1, which under
    # the sweep's DB load could stall the request long enough to 502).
    club_ids = [c.id for c in clubs]
    contacts_by_club: dict = {}
    if club_ids:
        rows = (await db.execute(
            select(MarketingClubContact)
            .where(MarketingClubContact.marketing_club_id.in_(club_ids))
            .order_by(MarketingClubContact.role_rank.asc())
        )).scalars().all()
        for ct in rows:
            contacts_by_club.setdefault(ct.marketing_club_id, []).append(ct)

    out = []
    for c in clubs:
        out.append({
            "id": str(c.id), "name": c.name, "playhq_id": c.playhq_id,
            "grassroots_guid": c.grassroots_guid, "association_name": c.association_name,
            "association_guid": c.association_guid, "associations": c.associations,
            "suburb": c.suburb, "state": c.state,
            "postcode": c.postcode, "address_line1": c.address_line1,
            "website_url": c.website_url, "status": c.status,
            "is_customer": c.existing_org_id is not None,
            "emailed_at": c.emailed_at.isoformat() if c.emailed_at else None,
            "emailed_via": c.emailed_via, "emailed_note": c.emailed_note,
            "excluded": c.excluded,
            "utm_code": c.utm_code or cd._default_utm(c.name),
            "contacts": [{
                "id": str(ct.id), "full_name": ct.full_name, "role": ct.role,
                "email": ct.email, "mobile": ct.mobile, "source": ct.source,
                "subscribed": ct.subscribed, "selected": ct.outreach_selected,
            } for ct in contacts_by_club.get(c.id, [])],
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
    # The same directory filters the page shows (so the export acts on the
    # currently-filtered list).
    q: Optional[str] = None
    state: Optional[str] = None
    association: Optional[str] = None
    status: Optional[str] = None
    postcode_from: Optional[str] = None
    postcode_to: Optional[str] = None
    contact: Optional[str] = None
    person: Optional[str] = None
    exclude_junior: bool = False
    exclude_emailed: bool = False
    exclude_carnival: bool = False
    exclude_school: bool = False
    associations: Optional[List[str]] = None
    # Default True: only push contacts a super admin ticked for outreach. Set
    # False to export every subscribed, emailable contact regardless of selection.
    selected_only: bool = True


@router.post("/export-comms")
async def export_comms(body: ExportBody, db: AsyncSession = Depends(get_db),
                       _=Depends(require_super_admin)):
    """Push the selected, currently-filtered contacts into comms_contacts under
    the outreach org, so a BetterAdmin Comms campaign can send to them with full
    unsubscribe/suppression. Excluded and already-emailed clubs are always
    skipped."""
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, body.exclude_junior,
        body.exclude_emailed, body.exclude_carnival, body.exclude_school, body.associations))
    return await cd.export_to_comms(
        db, organisation_id=body.organisation_id, selected_only=body.selected_only,
        filters=filters)


class EmailedBody(BaseModel):
    emailed: bool
    note: Optional[str] = None


@router.patch("/clubs/{club_id}/emailed")
async def set_club_emailed(club_id: str, body: EmailedBody,
                           db: AsyncSession = Depends(get_db),
                           _=Depends(require_super_admin)):
    """Manually mark / unmark a club as already emailed (e.g. via an external
    mailing tool) so it's excluded from future exports/sends."""
    res = await cd.mark_emailed(db, club_id, body.emailed, via="manual", note=body.note)
    if res is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return res


class ExcludedBody(BaseModel):
    excluded: bool


@router.patch("/clubs/{club_id}/excluded")
async def set_club_excluded(club_id: str, body: ExcludedBody,
                            db: AsyncSession = Depends(get_db),
                            _=Depends(require_super_admin)):
    """Exclude / un-exclude a club from outreach entirely. Excluded clubs are never
    exported (regardless of filters), and any contacts already exported to
    BetterAdmin Comms are flagged excluded there too (dropped from audiences).
    Reversible."""
    res = await cd.set_excluded(db, club_id, body.excluded)
    if res is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return res


class UtmBody(BaseModel):
    utm: str


@router.patch("/clubs/{club_id}/utm")
async def set_club_utm(club_id: str, body: UtmBody, db: AsyncSession = Depends(get_db),
                       _=Depends(require_super_admin)):
    """Manually edit a club's UTM code. A blank value resets it to the
    name-derived default (first word + '-cricket-club')."""
    res = await cd.set_utm(db, club_id, body.utm)
    if res is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return res


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
    q: Optional[str] = None,
    state: Optional[str] = None,
    association: Optional[str] = None,
    status: Optional[str] = None,
    postcode_from: Optional[str] = None,
    postcode_to: Optional[str] = None,
    contact: Optional[str] = None,
    person: Optional[str] = None,
    exclude_junior: bool = False,
    exclude_emailed: bool = False,
    exclude_carnival: bool = False,
    exclude_school: bool = False,
    associations: Optional[List[str]] = Query(None),
    only_with_email: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """CSV of the currently-filtered directory (one row per club+contact)."""
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        q, state, association, status, postcode_from, postcode_to, contact, person,
        exclude_junior, exclude_emailed, exclude_carnival, exclude_school, associations))
    csv_text = await cd.clubs_to_csv(db, only_with_email=only_with_email, filters=filters)
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marketing_clubs.csv"})
