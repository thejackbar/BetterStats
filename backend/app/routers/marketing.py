"""Super-admin API over the marketing club directory (BetterCricket outreach).

Cross-club platform tooling, so gated by ``require_super_admin`` (not a per-club
capability), same posture as the KlubPro migration router. Lets staff watch the
crawl, search/filter the collected clubs, export the selection into a BetterComms
campaign (the existing send pipeline), and download a CSV.
"""
from __future__ import annotations

from datetime import datetime, timezone
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


# The tri-state directory filters (off / include / exclude). Same keys front to
# back (SuperMarketing.jsx sends them, club_directory.filter_mode_conditions reads
# them).
FILTER_MODE_FIELDS = cd.FILTER_MODE_KEYS


def _norm_modes(raw: dict | None) -> dict:
    """Keep only the known filter keys whose value is include/exclude."""
    out = {}
    for key in FILTER_MODE_FIELDS:
        v = str((raw or {}).get(key) or "").strip().lower()
        if v in ("include", "exclude"):
            out[key] = v
    return out


def _modes_from(obj) -> dict:
    """Read the tri-state filter modes off a request body (attributes) or dict."""
    getter = obj.get if isinstance(obj, dict) else (lambda k, d=None: getattr(obj, k, d))
    return _norm_modes({k: getter(k) for k in FILTER_MODE_FIELDS})


def _filter_kwargs(q, state, association, status, postcode_from, postcode_to, contact,
                   person=None, modes=None, associations=None, visited=False,
                   countries=None, engagement_score_gte=None, engagement_score_lte=None,
                   existing_org_id=None):
    """Normalise the directory filter query-params into club_filters kwargs."""
    return {
        "q": q, "state": state, "association": association, "status": status,
        "postcode_from": postcode_from, "postcode_to": postcode_to,
        "contact_filter": contact if contact in cd.CONTACT_FILTERS else None,
        "person": person,
        "modes": _norm_modes(modes),
        "visited": bool(visited),
        "associations": [a for a in (associations or []) if a],
        "countries": [c for c in (countries or []) if c],
        "engagement_score_gte": engagement_score_gte,
        "engagement_score_lte": engagement_score_lte,
        "existing_org_id": existing_org_id,
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


@router.get("/clubs/quick-search")
async def quick_search_clubs(
    q: str,
    limit: int = Query(8, ge=1, le=20),
    kind: Optional[str] = "club",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """Cheap club-name typeahead — deliberately NOT ``list_clubs`` below.

    The CRM's New Deal club search was reusing ``GET /clubs`` (this file's
    full directory list) for live-as-you-type search, and it was unacceptably
    slow next to the public self-serve trial registration's own club search
    (which just hits PlayHQ's external org-search API, no local aggregation
    at all). The actual cost wasn't the name match itself (a plain LIKE over
    marketing_clubs, a few thousand rows) — it was that ``list_clubs`` ALSO
    always computes a ``COUNT(*)`` over the filtered set and calls
    ``club_visit_stats``/``club_login_intent_stats`` for the returned page,
    both of which resolve EVERY ``usage_events`` page_view row through
    ``_RESOLVED_VISITS``'s per-row COALESCE of correlated subqueries before
    filtering down to the requested club ids — an O(all page views ever
    recorded) scan on every keystroke, for data the New Deal modal doesn't
    even display (per-club website analytics are fetched separately, one
    club at a time, only once a club is actually selected — see
    ``GET /clubs/{id}/visits``). This endpoint only ever does a name match +
    a contacts batch for the handful of returned rows, nothing else."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"clubs": []}
    stmt = select(MarketingClub).where(
        MarketingClub.detail_fetched_at.isnot(None),
        func.lower(MarketingClub.name).like(f"%{q.lower()}%"),
    )
    if kind:
        stmt = stmt.where(MarketingClub.kind == kind)
    stmt = stmt.order_by(func.lower(MarketingClub.name)).limit(limit)
    clubs = (await db.execute(stmt)).scalars().all()

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

    return {"clubs": [{
        "id": str(c.id), "name": c.name,
        "suburb": c.suburb, "state": c.state, "postcode": c.postcode, "address_line1": c.address_line1,
        "is_customer": c.existing_org_id is not None,
        "contacts": [{
            "id": str(ct.id), "full_name": ct.full_name, "role": ct.role,
            "email": ct.email, "mobile": ct.mobile,
        } for ct in contacts_by_club.get(c.id, [])],
    } for c in clubs]}


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
    # Tri-state directory filters: each 'off' | 'include' | 'exclude'.
    junior: str = "off",
    carnival: str = "off",
    school: str = "off",
    rep: str = "off",
    cricket_au: str = "off",
    emailed: str = "off",
    exported: str = "off",
    suppressed: str = "off",
    excluded: str = "off",
    visited: bool = False,
    kind: Optional[str] = "club",
    group_by_association: bool = False,
    assoc_sort: str = "asc",
    club_sort: str = "asc",
    limit: int = Query(100, le=500),
    offset: int = 0,
    # "Top N of what's currently filtered" — ranks by the cached page-view /
    # distinct-visitor count (see club_directory.top_clubs_by_visits) and
    # supersedes normal pagination while active, same as `visited` is a plain
    # toggle rather than something that composes with page size.
    top_n: Optional[int] = Query(None, ge=1, le=1000),
    top_n_metric: str = Query("views", pattern="^(views|visitors)$"),
    engagement_score_gte: Optional[int] = None,
    engagement_score_lte: Optional[int] = None,
    existing_org_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    stmt = select(MarketingClub).where(MarketingClub.detail_fetched_at.isnot(None))
    if kind:
        stmt = stmt.where(MarketingClub.kind == kind)
    modes = {"junior": junior, "carnival": carnival, "school": school, "rep": rep,
             "cricket_au": cricket_au, "emailed": emailed, "exported": exported,
             "suppressed": suppressed, "excluded": excluded}
    kw = await cd.expand_shortcode(db, _filter_kwargs(
        q, state, association, status, postcode_from, postcode_to, contact,
        person, modes=modes, associations=associations, visited=visited,
        countries=countries, engagement_score_gte=engagement_score_gte,
        engagement_score_lte=engagement_score_lte, existing_org_id=existing_org_id))
    for cond in cd.club_filters(**kw):
        stmt = stmt.where(cond)

    if top_n:
        # Resolve the candidate set from every OTHER active filter (no order/
        # limit/offset yet), then rank just that set — "top N of what's
        # filtered", not top N of the whole directory regardless of filters.
        candidate_ids = (await db.execute(stmt.with_only_columns(MarketingClub.id))).scalars().all()
        ranked = await cd.top_clubs_by_visits(db, top_n_metric, top_n, candidate_ids=candidate_ids)
        ranked_ids = [r["id"] for r in ranked]
        total = len(ranked_ids)
        clubs = []
        if ranked_ids:
            by_id = {str(c.id): c for c in (await db.execute(
                select(MarketingClub).where(MarketingClub.id.in_(ranked_ids)))).scalars().all()}
            clubs = [by_id[rid] for rid in ranked_ids if rid in by_id]
    else:
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
    # Visitors who browsed a club's pages then hit /login — a lead signal,
    # strongest for a club with no existing_org_id (nothing to log into yet).
    login_intent_stats = await cd.club_login_intent_stats(db, [c.id for c in clubs])

    out = []
    for c in clubs:
        out.append({
            "id": str(c.id), "name": c.name, "playhq_id": c.playhq_id,
            "grassroots_guid": c.grassroots_guid, "association_name": c.association_name,
            "association_guid": c.association_guid, "associations": c.associations,
            "suburb": c.suburb, "state": c.state,
            "postcode": c.postcode, "address_line1": c.address_line1,
            "latitude": float(c.latitude) if c.latitude is not None else None,
            "longitude": float(c.longitude) if c.longitude is not None else None,
            "website_url": c.website_url, "status": c.status,
            "is_customer": c.existing_org_id is not None,
            "emailed_at": c.emailed_at.isoformat() if c.emailed_at else None,
            "emailed_via": c.emailed_via, "emailed_note": c.emailed_note,
            "excluded": c.excluded,
            "utm_code": c.utm_code or cd._default_utm(c.name),
            "visits": visit_stats.get(str(c.id)),
            "login_intent": login_intent_stats.get(str(c.id)),
            "trial_modules": c.trial_modules or [],
            "requested_trial_modules": c.requested_trial_modules or [],
            "demo_status": c.demo_status,
            "not_interested": bool(c.not_interested),
            # Cached at the last _engagement() computation (any trigger — see
            # twenty_sync.py) — can lag reality up to however long since this
            # club was last (re)computed; engagement_scored_at says how stale.
            "engagement_score": c.engagement_score,
            "engagement_tier": c.engagement_tier,
            "engagement_scored_at": c.engagement_scored_at.isoformat() if c.engagement_scored_at else None,
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


class DirFilterFields(BaseModel):
    """The directory filter fields every filtered action shares, so the export /
    CSV / bulk endpoints act on exactly the list the page shows. The tri-state
    filters (junior … suppressed) are each 'off' | 'include' | 'exclude'."""
    q: Optional[str] = None
    state: Optional[str] = None
    association: Optional[str] = None
    status: Optional[str] = None
    postcode_from: Optional[str] = None
    postcode_to: Optional[str] = None
    contact: Optional[str] = None
    person: Optional[str] = None
    junior: str = "off"
    carnival: str = "off"
    school: str = "off"
    rep: str = "off"
    cricket_au: str = "off"
    emailed: str = "off"
    exported: str = "off"
    suppressed: str = "off"
    excluded: str = "off"
    visited: bool = False
    associations: Optional[List[str]] = None
    countries: Optional[List[str]] = None


class ExportBody(DirFilterFields):
    organisation_id: Optional[str] = None
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
        body.postcode_to, body.contact, body.person, modes=_modes_from(body),
        associations=body.associations, visited=body.visited, countries=body.countries))
    return await cd.export_to_comms(
        db, organisation_id=body.organisation_id, selected_only=body.selected_only,
        filters=filters)


class ExportTwentyBody(DirFilterFields):
    # all | named | pst — which officers of each matched club to push.
    contact_scope: str = "all"
    # Honour the per-officer outreach tick (de-selected officers are skipped).
    selected_only: bool = True
    # Optional cap on clubs per run (None = all matched).
    limit: Optional[int] = None


# A Twenty export against the CRM's 100/min rate limit takes minutes for a big
# filter — far longer than the nginx proxy timeout — so it runs in the background and
# the UI polls /export-twenty/status. One at a time (overlapping runs compounded the
# rate-limiting). State is in-process: a worker restart mid-run loses it, so a run
# older than this is treated as stale and a new one is allowed.
_EXPORT_STALE_SECS = 30 * 60
_twenty_export: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "result": None, "error": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settle_bg(state: dict, res):
    """Store a background job's result, translating the services' documented
    "never raises, returns {'error': ...} instead" convention into the state
    dict's own error field — so the UI poller's ``if (s.error)`` branch catches
    a soft failure (e.g. "Twenty is not configured") the same way it catches a
    hard exception, instead of trying to format an error dict as a success
    result."""
    if isinstance(res, dict) and res.get("error"):
        state["result"], state["error"] = None, str(res["error"])
    else:
        state["result"], state["error"] = res, None


def _bg_stale(state: dict) -> bool:
    """True if a background job's ``state`` dict claims to still be running but
    started long enough ago that it's more likely a worker restart lost track of
    it — shared by the Twenty export, engagement refresh and leads/tasks refresh
    runners below, all of which use the same running/started_at/finished_at/
    result/error shape."""
    if not state["running"] or not state["started_at"]:
        return False
    try:
        started = datetime.fromisoformat(state["started_at"])
        return (datetime.now(timezone.utc) - started).total_seconds() > _EXPORT_STALE_SECS
    except Exception:
        return True


async def _export_twenty_bg(filters: dict, scope: str, selected_only: bool, limit):
    try:
        res = await twenty_sync.export_to_twenty(
            filters=filters, contact_scope=scope, selected_only=selected_only, limit=limit)
        _settle_bg(_twenty_export, res)
    except Exception as e:  # noqa: BLE001 — never let a CRM error wedge the runner
        _twenty_export["result"], _twenty_export["error"] = None, str(e)
    finally:
        _twenty_export["running"] = False
        _twenty_export["finished_at"] = _now_iso()


@router.post("/export-twenty")
async def export_twenty(body: ExportTwentyBody, background: BackgroundTasks,
                        db: AsyncSession = Depends(get_db),
                        _=Depends(require_super_admin)):
    """Kick off pushing the currently-filtered directory subset into Twenty CRM
    (Companies + Associations + People) in the background and return immediately;
    poll /export-twenty/status for progress + the result. Idempotent — re-running
    upserts and skips unchanged records. Excluded clubs are always skipped."""
    if _twenty_export["running"] and not _bg_stale(_twenty_export):
        return {"status": "already_running", "started_at": _twenty_export["started_at"]}
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, modes=_modes_from(body),
        associations=body.associations, visited=body.visited, countries=body.countries))
    scope = body.contact_scope if body.contact_scope in ("all", "named", "pst") else "all"
    _twenty_export.update(running=True, started_at=_now_iso(), finished_at=None,
                          result=None, error=None)
    background.add_task(_export_twenty_bg, filters, scope, body.selected_only, body.limit)
    return {"status": "started"}


@router.get("/export-twenty/status")
async def export_twenty_status(_=Depends(require_super_admin)):
    """Current/last Twenty export state for the UI poller."""
    return dict(_twenty_export)


class PushToCrmBody(DirFilterFields):
    # Where a pushed club lands — 'Manually Added' by default (see
    # services/crm.py PLATFORM_DEFAULT_STAGES), but any existing platform
    # stage key works.
    stage_key: str = "manually_added"
    limit: Optional[int] = None


_crm_push: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "result": None, "error": None,
}


async def _push_to_crm_bg(filters: dict, stage_key: str, limit):
    try:
        async with async_session_maker() as session:
            res = await cd.push_clubs_to_crm(session, filters, stage_key=stage_key, limit=limit)
        _settle_bg(_crm_push, res)
    except Exception as e:  # noqa: BLE001 — never let a CRM error wedge the runner
        _crm_push["result"], _crm_push["error"] = None, str(e)
    finally:
        _crm_push["running"] = False
        _crm_push["finished_at"] = _now_iso()


@router.post("/push-to-crm")
async def push_to_crm(body: PushToCrmBody, background: BackgroundTasks,
                      db: AsyncSession = Depends(get_db),
                      _=Depends(require_super_admin)):
    """Upsert every club in the currently-filtered Club Directory result set
    directly into BetterCricket's OWN platform CRM pipeline (not Twenty) at
    ``stage_key`` (default 'Manually Added') — a super admin explicitly
    deciding these clubs belong in the sales pipeline right now, distinct
    from the enquiry/trial/webhook signals that create a deal automatically.
    Runs in the background (same pattern as /export-twenty) since a large
    filtered set means many individual upserts; poll /push-to-crm/status."""
    if _crm_push["running"] and not _bg_stale(_crm_push):
        return {"status": "already_running", "started_at": _crm_push["started_at"]}
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, modes=_modes_from(body),
        associations=body.associations, visited=body.visited, countries=body.countries))
    _crm_push.update(running=True, started_at=_now_iso(), finished_at=None, result=None, error=None)
    background.add_task(_push_to_crm_bg, filters, body.stage_key, body.limit)
    return {"status": "started"}


@router.get("/push-to-crm/status")
async def push_to_crm_status(_=Depends(require_super_admin)):
    """Current/last BetterCricket-CRM push state for the UI poller."""
    return dict(_crm_push)


_twenty_engagement_refresh: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "result": None, "error": None,
}
_twenty_leads_refresh: dict = {
    "running": False, "started_at": None, "finished_at": None,
    "result": None, "error": None,
}


async def _refresh_engagement_bg():
    try:
        res = await twenty_sync.refresh_engagement()
        _settle_bg(_twenty_engagement_refresh, res)
    except Exception as e:  # noqa: BLE001 — never let a CRM error wedge the runner
        _twenty_engagement_refresh["result"], _twenty_engagement_refresh["error"] = None, str(e)
    finally:
        _twenty_engagement_refresh["running"] = False
        _twenty_engagement_refresh["finished_at"] = _now_iso()


async def _refresh_leads_tasks_bg():
    from app.services import twenty_leads_tasks
    try:
        res = await twenty_leads_tasks.refresh_leads_and_tasks()
        _settle_bg(_twenty_leads_refresh, res)
    except Exception as e:  # noqa: BLE001 — never let a CRM error wedge the runner
        _twenty_leads_refresh["result"], _twenty_leads_refresh["error"] = None, str(e)
    finally:
        _twenty_leads_refresh["running"] = False
        _twenty_leads_refresh["finished_at"] = _now_iso()


@router.post("/refresh-twenty-engagement")
async def refresh_twenty_engagement(background: BackgroundTasks, _=Depends(require_super_admin)):
    """Recompute the engagement rollup (score / tier / 30-day sessions / last seen)
    for every club already in Twenty and PATCH it onto its Company. Runs daily on a
    schedule too; this is the on-demand trigger. Only touches already-exported
    clubs — it never pulls a new club into the CRM.

    Same reasoning as /export-twenty: a PATCH per exported club against Twenty's
    rate limit can comfortably exceed the nginx proxy timeout once there are more
    than a few dozen exported clubs, so this runs in the background and the UI
    polls /refresh-twenty-engagement/status."""
    if _twenty_engagement_refresh["running"] and not _bg_stale(_twenty_engagement_refresh):
        return {"status": "already_running", "started_at": _twenty_engagement_refresh["started_at"]}
    _twenty_engagement_refresh.update(running=True, started_at=_now_iso(), finished_at=None,
                                      result=None, error=None)
    background.add_task(_refresh_engagement_bg)
    return {"status": "started"}


@router.get("/refresh-twenty-engagement/status")
async def refresh_twenty_engagement_status(_=Depends(require_super_admin)):
    """Current/last engagement-refresh state for the UI poller."""
    return dict(_twenty_engagement_refresh)


@router.post("/refresh-twenty-leads-tasks")
async def refresh_twenty_leads_tasks(background: BackgroundTasks, _=Depends(require_super_admin)):
    """Seed/refresh Leads from telemetry and raise follow-up Tasks for outstanding
    module requests, expiring trials and upcoming renewals. Runs daily on a schedule
    too; this is the on-demand trigger. Idempotent — the first run backfills whatever
    already qualifies, later runs only add what's new. Only touches clubs already in
    the CRM (a twenty_links row).

    Same reasoning as /export-twenty: this walks every exported club and can make
    several Twenty calls each, comfortably exceeding the nginx proxy timeout once
    there's a meaningful number of exported clubs — runs in the background, poll
    /refresh-twenty-leads-tasks/status."""
    if _twenty_leads_refresh["running"] and not _bg_stale(_twenty_leads_refresh):
        return {"status": "already_running", "started_at": _twenty_leads_refresh["started_at"]}
    _twenty_leads_refresh.update(running=True, started_at=_now_iso(), finished_at=None,
                                 result=None, error=None)
    background.add_task(_refresh_leads_tasks_bg)
    return {"status": "started"}


@router.get("/refresh-twenty-leads-tasks/status")
async def refresh_twenty_leads_tasks_status(_=Depends(require_super_admin)):
    """Current/last leads/tasks-refresh state for the UI poller."""
    return dict(_twenty_leads_refresh)


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


class BulkActionBody(DirFilterFields):
    value: bool  # the new emailed / excluded state to apply
    note: Optional[str] = None


async def _bulk_filters(db: AsyncSession, body: BulkActionBody) -> dict:
    return await cd.expand_shortcode(db, _filter_kwargs(
        body.q, body.state, body.association, body.status, body.postcode_from,
        body.postcode_to, body.contact, body.person, modes=_modes_from(body),
        associations=body.associations, visited=body.visited, countries=body.countries))


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


@router.get("/clubs/{club_id}/engagement-breakdown")
async def club_engagement_breakdown(club_id: str, db: AsyncSession = Depends(get_db),
                                    _=Depends(require_super_admin)):
    """Explain a club's engagement score: which signals produced it (recency,
    web page views, email opens vs clicks, Meta ad clicks) and which flags fired
    (a direct enquiry, a trial request/in-trial, an ad-sourced signup, product
    setup depth). Recomputes _engagement live for the breakdown fields, then rolls
    back — read-only, nothing is persisted. Powers the deal-detail panel so a
    score like 70 with no web activity is self-explaining (e.g. the trial-depth
    registration floor) instead of a mystery number."""
    from sqlalchemy.orm import selectinload
    from app.models.db import Organisation

    club = await db.get(MarketingClub, club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    org = None
    if club.existing_org_id:
        org = await db.get(Organisation, club.existing_org_id,
                           options=[selectinload(Organisation.module_subscriptions)])
    eng = await twenty_sync._engagement(db, club, org)
    await db.rollback()  # read-only: don't persist this recompute

    # Build a plain-English list of contributions, biggest first, so the panel
    # can just render them in order.
    contributions = []
    def add(label, points, detail=""):
        if points:
            contributions.append({"label": label, "points": round(float(points), 1), "detail": detail})

    recency = eng.get("_recencyPts") or 0
    web = eng.get("_webDecayPts") or 0
    email = eng.get("_emailDecayPts") or 0
    ad = eng.get("_adDecayPts") or 0
    td = eng.get("_trialDepth") or None
    is_linked = bool(club.existing_org_id)

    if eng.get("_directEnquiryHot"):
        contributions.append({"label": "Direct 'onboard my club' enquiry (recent)",
                              "points": eng.get("engagementScore"),
                              "detail": "Pinned to a flat Hot score for a set window after the enquiry."})
    else:
        add("Recency of last activity", recency, "Most recent web/email/enquiry touch, decaying over time.")
        add("Web page views", web, f"{eng.get('sessions30d', 0)} distinct visitor(s) in 30 days.")
        add("Email opens & clicks", email, f"{eng.get('emailEngaged30d', 0)} open/click(s) in 30 days.")
        add("Meta ad clicks", ad, f"{eng.get('_adClicks', 0)} ad-click landing(s).")
        if eng.get("_onboardingRequested"):
            add("Onboarding enquiry bonus", twenty_sync.BONUS_ONBOARDING)
        if club.requested_trial_modules:
            add("Requested a trial", twenty_sync.BONUS_REQUESTED_TRIAL)
        if (club.demo_status or "") == "in_trial":
            add("Currently in a trial", twenty_sync.BONUS_IN_TRIAL)
        if eng.get("_adSignup"):
            add("Signed up from a paid ad", twenty_sync.BONUS_AD_SIGNUP)
        if td and td.get("score"):
            add("Product setup depth (registered/imported/merged)", td.get("score"),
                "Onboarded club: floors the score on real setup effort, not web activity."
                + ("" if td.get("hasPrimaryAdmin") else " Staff-performed, so discounted."))

    return {
        "score": eng.get("engagementScore"),
        "tier": eng.get("engagementTier"),
        "is_customer": is_linked,
        "in_sales_cycle": eng.get("inSalesCycle"),
        "signals": {
            "sessions_30d": eng.get("sessions30d", 0),
            "email_engaged_30d": eng.get("emailEngaged30d", 0),
            "ad_clicks": eng.get("_adClicks", 0),
            "recency_pts": round(float(recency), 1),
            "web_pts": round(float(web), 1),
            "email_pts": round(float(email), 1),
            "ad_pts": round(float(ad), 1),
            "freq_pts": eng.get("_freqPts", 0),
        },
        "trial_depth": td,
        "contributions": contributions,
        "last_web_visit_at": eng.get("lastWebVisitAt"),
        "last_email_at": eng.get("lastEmailAt"),
    }


@router.get("/clubs/{club_id}/login-intent")
async def club_login_intent(club_id: str, db: AsyncSession = Depends(get_db),
                             _=Depends(require_super_admin)):
    """Visitors who browsed this club's pages then hit /login — totals and a
    recent trail, for the directory's expanded-row panel."""
    club = await db.get(MarketingClub, club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found")
    return await cd.club_login_intent_detail(db, club.id)


@router.get("/clubs/{club_id}/boundary")
async def club_boundary(club_id: str, db: AsyncSession = Depends(get_db),
                        _=Depends(require_super_admin)):
    """A club's suburb boundary polygon (GeoJSON), fetched from OpenStreetMap on
    first request and cached forever after — the free-tier stand-in for a real
    postcode-area shape. `geojson: null` when nothing was found."""
    geo = await cd.get_or_fetch_boundary(db, club_id)
    return {"geojson": geo}


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
    not_interested: Optional[bool] = None


@router.patch("/clubs/{club_id}/sales")
async def set_club_sales(club_id: str, body: SalesBody, db: AsyncSession = Depends(get_db),
                         _=Depends(require_super_admin)):
    """Set a prospect's sales-pipeline state: which modules it's trialing / has
    requested a trial for, its demo follow-on state, and the not-interested
    disposition. Only fields supplied are changed (demo_status only when set_demo is
    true, so it can be cleared)."""
    res = await cd.set_sales_state(
        db, club_id,
        trial_modules=body.trial_modules,
        requested_trial_modules=body.requested_trial_modules,
        demo_status=(body.demo_status if body.set_demo else ...),
        not_interested=body.not_interested,
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
    junior: str = "off",
    carnival: str = "off",
    school: str = "off",
    rep: str = "off",
    cricket_au: str = "off",
    emailed: str = "off",
    exported: str = "off",
    suppressed: str = "off",
    excluded: str = "off",
    visited: bool = False,
    associations: Optional[List[str]] = Query(None),
    countries: Optional[List[str]] = Query(None),
    only_with_email: bool = True,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_super_admin),
):
    """CSV of the currently-filtered directory (one row per club+contact)."""
    modes = {"junior": junior, "carnival": carnival, "school": school, "rep": rep,
             "cricket_au": cricket_au, "emailed": emailed, "exported": exported,
             "suppressed": suppressed, "excluded": excluded}
    filters = await cd.expand_shortcode(db, _filter_kwargs(
        q, state, association, status, postcode_from, postcode_to, contact, person,
        modes=modes, associations=associations, visited=visited, countries=countries))
    csv_text = await cd.clubs_to_csv(db, only_with_email=only_with_email, filters=filters)
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=marketing_clubs.csv"})
