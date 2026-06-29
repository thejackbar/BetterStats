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
from app.services import twenty_sync

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
                   exclude_carnival=False, exclude_school=False, associations=None,
                   exclude_exported=False, exclude_suppressed=False, visited=False,
                   countries=None):
    """Normalise the directory filter query-params into club_filters kwargs."""
    return {
        "q": q, "state": state, "association": association, "status": status,
        "postcode_from": postcode_from, "postcode_to": postcode_to,
        "contact_filter": contact if contact in cd.CONTACT_FILTERS else None,
        "person": person, "exclude_junior": bool(exclude_junior),
        "exclude_emailed": bool(exclude_emailed),
        "exclude_carnival": bool(exclude_carnival), "exclude_school": bool(exclude_school),
        "exclude_exported": bool(exclude_exported),
        "exclude_suppressed": bool(exclude_suppressed),
        "visited": bool(visited),
        "associations": [a for a in (associations or []) if a],
        "countries": [c for c in (countries or []) if c],
    }


@router.get("/associations")
async def list_associations(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Distinct associations (name + id + club count) for the multi-select filter."""
    return await cd.list_associations(db)


@router.get("/countries")
async def list_countries(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Distinct countries (name + club count) for the multi-select filter."""
    return await cd.list_countries(db)


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
    countries: Optional[List[str]] = Query(None),
    status: Optional[str] = None,
    postcode_from: Optional[str] = None,
    postcode_to: Optional[str] = None,
    contact: Optional[str] = None,   # '' | any_email | named_email | pst
    person: Optional[str] = None,
    exclude_junior: bool = False,
    exclude_emailed: bool = False,
    exclude_carnival: bool = False,
    exclude_school: bool = False,
    exclude_exported: bool = False,
    exclude_suppressed: bool = False,
    visited: bool = False,
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
        associations, exclude_exported=exclude_exported,
        exclude_suppressed=exclude_suppressed, visited=visited, countries=countries))
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

    # Site visits attributable to each club (usage breadcrumbs, resolved through
    # utm_code + manual aliases), fetched for the whole page in one query.
    visit_stats = await cd.club_visit_stats(db, [c.id for c in clubs])

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
            "visits": visit_stats.get(str(c.id)),
            "trial_modules": c.trial_modules or [],
            "requested_trial_modules": c.requested_trial_modules or [],
            "demo_status": c.demo_status,
            "contacts": [{
                "id": str(ct.id), "full_name": ct.full_name, "role": ct.role,
                "email": ct.email, "mobile": ct.mobile, "source": ct.source,
                "subscribed": ct.subscribed, "selected": ct.outreach_selected,
                "exported": ct.exported_at is not None,
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
    exclude_exported: bool = False
    exclude_suppressed: bool = False
    visited: bool = False
    associations: Optional[List[str]] = None
    countries: Optional[List[str]] = None
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
        body.exclude_emailed, body.exclude_carnival, body.exclude_school, body.associations,
        exclude_exported=body.exclude_exported, exclude_suppressed=body.exclude_suppressed,
        visited=body.visited, countries=body.countries))
    return await cd.export_to_comms(
        db, organisation_id=body.organisation_id, selected_only=body.selected_only,
        filters=filters)


class ExportTwentyBody(BaseModel):
    # Same directory filters the page shows, so the export acts on the currently
    # filtered list (the targeted subset that enters the CRM).
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
    exclude_exported: bool = False
    exclude_suppressed: bool = False
    visited: bool = False
    associations: Optional[List[str]] = None
    countries: Optional[List[str]] = None
    # all | named | pst — which officers of each matched club to push.
    contact_scope: str = "all"
    # Honour the per-officer outreach tick (de-selected officers are skipped).
    selected_only: bool = True
    # Optional cap on clubs per run (None = all matched).
    limit: Optional[int] = None


@router.post("/export-twenty")
async def export_twenty(body: ExportTwentyBody, db: AsyncSession = Depends(get_db),
                        _=Depends(require_super_admin)):
    """Push the currently-filtered directory subset into Twenty CRM (Companies +
    Associations + People). Idempotent — re-running upserts and skips unchanged
    records. Excluded clubs are always skipped."""
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, body.exclude_junior,
        body.exclude_emailed, body.exclude_carnival, body.exclude_school, body.associations,
        exclude_exported=body.exclude_exported, exclude_suppressed=body.exclude_suppressed,
        visited=body.visited, countries=body.countries))
    scope = body.contact_scope if body.contact_scope in ("all", "named", "pst") else "all"
    return await twenty_sync.export_to_twenty(
        filters=filters, contact_scope=scope, selected_only=body.selected_only,
        limit=body.limit)


@router.post("/refresh-twenty-engagement")
async def refresh_twenty_engagement(_=Depends(require_super_admin)):
    """Recompute the engagement rollup (score / tier / 30-day sessions / last seen)
    for every club already in Twenty and PATCH it onto its Company. Runs daily on a
    schedule too; this is the on-demand trigger. Only touches already-exported
    clubs — it never pulls a new club into the CRM."""
    return await twenty_sync.refresh_engagement()


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


class BulkActionBody(BaseModel):
    value: bool  # the new emailed / excluded state to apply
    note: Optional[str] = None
    # The same directory filters the page shows, so the action hits exactly the
    # currently-filtered list.
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
    exclude_exported: bool = False
    exclude_suppressed: bool = False
    visited: bool = False
    associations: Optional[List[str]] = None
    countries: Optional[List[str]] = None


async def _bulk_filters(db: AsyncSession, body: BulkActionBody) -> dict:
    return await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, body.exclude_junior,
        body.exclude_emailed, body.exclude_carnival, body.exclude_school, body.associations,
        exclude_exported=body.exclude_exported, exclude_suppressed=body.exclude_suppressed,
        visited=body.visited, countries=body.countries))


@router.post("/clubs/bulk-emailed")
async def bulk_mark_emailed(body: BulkActionBody, db: AsyncSession = Depends(get_db),
                            _=Depends(require_super_admin)):
    """Mark / unmark every club in the current filtered list as already emailed."""
    filters = await _bulk_filters(db, body)
    return await cd.bulk_mark_emailed(db, body.value, via="manual", note=body.note,
                                      filters=filters)


@router.post("/clubs/bulk-excluded")
async def bulk_set_excluded(body: BulkActionBody, db: AsyncSession = Depends(get_db),
                            _=Depends(require_super_admin)):
    """Exclude / un-exclude every club in the current filtered list. Propagates to
    any contacts already exported to BetterAdmin Comms."""
    filters = await _bulk_filters(db, body)
    return await cd.bulk_set_excluded(db, body.value, filters=filters)


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


@router.get("/clubs/{club_id}/visits")
async def club_visits(club_id: str, db: AsyncSession = Depends(get_db),
                      _=Depends(require_super_admin)):
    """The usage breadcrumbs for one club: who visited the public site from a link
    tagged with the club's UTM code (or a mapped alias) — totals, pages viewed and
    recent visits."""
    club = await db.get(MarketingClub, club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return await cd.club_visit_detail(db, club.id)


@router.get("/utm-values")
async def utm_values(db: AsyncSession = Depends(get_db), _=Depends(require_super_admin)):
    """Every raw UTM value seen on a site visit, with how it currently resolves —
    so a super admin can map the unmatched ones (e.g. 'executive' → Leederville)
    or mark noise ('meta', 'chatgpt.com') as ignored."""
    return await cd.list_utm_values(db)


class UtmAliasBody(BaseModel):
    utm_value: str
    marketing_club_id: Optional[str] = None
    ignore: bool = False


@router.put("/utm-aliases")
async def set_utm_alias(body: UtmAliasBody, db: AsyncSession = Depends(get_db),
                        _=Depends(require_super_admin)):
    """Map a UTM value to a club, mark it ignored, or clear it (no club + not
    ignored removes the mapping)."""
    res = await cd.set_utm_alias(db, body.utm_value, body.marketing_club_id, body.ignore)
    if res is None:
        raise HTTPException(status_code=404, detail="Unknown club or empty UTM value")
    return res


class SalesBody(BaseModel):
    trial_modules: Optional[list[str]] = None
    requested_trial_modules: Optional[list[str]] = None
    demo_status: Optional[str] = None
    set_demo: bool = False  # send true to apply demo_status (incl. clearing it)


@router.patch("/clubs/{club_id}/sales")
async def set_club_sales(club_id: str, body: SalesBody, db: AsyncSession = Depends(get_db),
                         _=Depends(require_super_admin)):
    """Set a prospect's sales-pipeline state: which modules it's trialing / has
    requested a trial for, and its demo follow-on state. Only fields supplied are
    changed (demo_status only when set_demo is true, so it can be cleared)."""
    res = await cd.set_sales_state(
        db, club_id,
        trial_modules=body.trial_modules,
        requested_trial_modules=body.requested_trial_modules,
        demo_status=(body.demo_status if body.set_demo else ...),
    )
    if res is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return res


def _contact_out(ct: MarketingClubContact) -> dict:
    return {
        "id": str(ct.id), "full_name": ct.full_name, "role": ct.role,
        "email": ct.email, "mobile": ct.mobile, "source": ct.source,
        "subscribed": ct.subscribed, "selected": ct.outreach_selected,
        "exported": ct.exported_at is not None,
    }


class ContactUpdateBody(BaseModel):
    # All optional — tick/untick for outreach AND/OR edit the editable fields.
    selected: Optional[bool] = None
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


async def _email_clashes(db, club_id, email: str, exclude_id=None) -> bool:
    stmt = select(MarketingClubContact.id).where(
        MarketingClubContact.marketing_club_id == club_id,
        func.lower(MarketingClubContact.email) == email)
    if exclude_id is not None:
        stmt = stmt.where(MarketingClubContact.id != exclude_id)
    return await db.scalar(stmt) is not None


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdateBody,
                         db: AsyncSession = Depends(get_db),
                         _=Depends(require_super_admin)):
    """Tick / untick a contact for outreach and/or edit its role, name, email and
    mobile. Email is normalised and kept unique per club."""
    contact = await db.get(MarketingClubContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if body.selected is not None:
        contact.outreach_selected = body.selected
    if body.role is not None:
        contact.role = body.role.strip() or None
    if body.full_name is not None:
        contact.full_name = body.full_name.strip() or None
    if body.mobile is not None:
        contact.mobile = body.mobile.strip() or None
    if body.email is not None:
        new_email = (body.email or "").strip().lower() or None
        if new_email != contact.email:
            if new_email and await _email_clashes(db, contact.marketing_club_id, new_email, contact.id):
                raise HTTPException(status_code=409,
                                    detail="Another contact for this club already uses that email")
            contact.email = new_email
    contact.updated_at = func.now()
    await db.commit()
    await db.refresh(contact)
    return _contact_out(contact)


class ContactCreateBody(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None


@router.post("/clubs/{club_id}/contacts")
async def add_contact(club_id: str, body: ContactCreateBody,
                      db: AsyncSession = Depends(get_db),
                      _=Depends(require_super_admin)):
    """Add a committee contact to a club by hand (e.g. an officer PlayHQ doesn't
    publish). Pre-ticked for outreach when it has an email."""
    club = await db.get(MarketingClub, club_id)
    if not club:
        raise HTTPException(status_code=404, detail="Club not found")
    email = (body.email or "").strip().lower() or None
    if email and await _email_clashes(db, club.id, email):
        raise HTTPException(status_code=409,
                            detail="Another contact for this club already uses that email")
    contact = MarketingClubContact(
        marketing_club_id=club.id,
        role=(body.role or "").strip() or None,
        full_name=(body.full_name or "").strip() or None,
        email=email, mobile=(body.mobile or "").strip() or None,
        source="manual", role_rank=50, subscribed=True,
        outreach_selected=bool(email),
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return _contact_out(contact)


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, db: AsyncSession = Depends(get_db),
                         _=Depends(require_super_admin)):
    """Remove a contact from a club's directory record."""
    contact = await db.get(MarketingClubContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()
    return {"status": "ok"}


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
    exclude_exported: bool = False,
    exclude_suppressed: bool = False,
    visited: bool = False,
    associations: Optional[List[str]] = Query(None),
    countries: Optional[List[str]] = Query(None),
    only_with_email: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """CSV of the currently-filtered directory (one row per club+contact)."""
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        q, state, association, status, postcode_from, postcode_to, contact, person,
        exclude_junior, exclude_emailed, exclude_carnival, exclude_school, associations,
        exclude_exported=exclude_exported, exclude_suppressed=exclude_suppressed,
        visited=visited, countries=countries))
    csv_text = await cd.clubs_to_csv(db, only_with_email=only_with_email, filters=filters)
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marketing_clubs.csv"})
