"""Public Contact-form intake (unauthenticated).

The marketing Contact form (betterat.cricket/contact) posts here on submit so
every prospective-club enquiry is stored in BetterStats, alongside the Formspree
email the form still sends. Unauthenticated by design: the sender is a prospect
with no club and no login, so this is NOT wrapped in require_module / auth.
Stored rows are read back in the super-admin area
(GET /club-admin/super/onboarding-requests).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import ClubOnboardingRequest, get_db
from app.routers import self_serve_trial as sst
from app.services import meta_capi, rate_limit
from app.services.crm import sync_deal_for_enquiry
from app.services.login_audit import client_ip
from app.services.twenty_sync import mark_contact_source, push_onboarding_enquiry
from app.services.usage_tracker import record_event_bg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/contact", tags=["public-contact"])

# Every search keystroke reaches the Cricket Australia club-search API, so this
# is capped per IP the same way the public self-serve wrapper caps its own copy.
# Sized for a club committee sharing one connection while several people fill
# the form in, not for scraping.
SEARCH_LIMIT, SEARCH_WINDOW = 120, 3600


@router.get("/club-search")
async def club_search(q: str = "", request: Request = None, db: AsyncSession = Depends(get_db)):
    """Club lookup for the Contact form's Club name field.

    Reuses the self-serve registration wizard's own search
    (``self_serve_trial.search_clubs`` -> the authoritative Grassroots/PlayHQ
    club list) so both forms resolve a club the same way. Deliberately NOT
    routed through /public/self-serve: that whole router sits behind the
    ``self_serve_registration_enabled`` platform flag, and the Contact form
    has to keep working whether or not self-serve registration is switched on.

    Only the fields the form needs come back. The self-serve search also
    returns the existing club's public slug and its Primary Admin's first name
    + last initial, for the "this club is already registered, talk to your
    admin" card - an enquiry has no use for either, and a marketing page is no
    place to serve them, so they are dropped here. ``already_registered`` is
    kept: it is worth showing on the result row, and an already-registered club
    is still perfectly entitled to get in touch.
    """
    rate_limit.enforce(
        f"pubcontact:search:{client_ip(request)}", SEARCH_LIMIT, SEARCH_WINDOW,
        detail="Too many searches. Slow down and try again shortly.",
    )
    results = await sst.search_clubs(q=q, db=db)
    return [
        {
            "id": org.get("id"),
            "name": org.get("name"),
            "shortName": org.get("shortName"),
            "suburb": org.get("suburb"),
            "stateName": org.get("stateName"),
            "already_registered": bool(org.get("already_registered")),
        }
        for org in results
    ]


class ContactMeta(BaseModel):
    """Meta Pixel / Conversions API dedup context — see docs/meta-conversions-api.md.
    `eventId` must be the exact id the browser pixel's Lead fired with, so Meta
    dedupes the browser + server copy into one event instead of double-counting."""
    eventId: Optional[str] = None
    eventSourceUrl: Optional[str] = None
    fbp: Optional[str] = None
    fbc: Optional[str] = None


class ContactIn(BaseModel):
    name: str = ""
    club: str = ""
    # Which club the enquirer picked from the club search, and how they got
    # there: 'search' (picked from the Cricket Australia list, so clubOrgId is
    # its real organisation guid) or 'manual' (typed in - a club the list
    # doesn't carry, e.g. one outside Australia). Both optional: the short CTA
    # modal still posts a bare club name.
    clubOrgId: Optional[str] = None
    clubSource: Optional[str] = None
    email: str = ""
    phone: Optional[str] = None
    association: Optional[str] = None
    grades: Optional[str] = None
    storage: Optional[str] = None
    timeline: Optional[str] = None
    clubUrl: Optional[str] = None
    message: Optional[str] = None
    # Extra onboarding questions (mirrored from the old Google Form).
    role: Optional[str] = None
    founded: Optional[str] = None
    playhq: Optional[str] = None
    historical: Optional[str] = None
    interests: Optional[str] = None
    heard: Optional[str] = None
    contactMethod: Optional[str] = None
    # First-party visitor id (localStorage UUID) so the enquiry links back to the
    # anonymous browsing journey behind it on the super-admin Usage page.
    visitorId: Optional[str] = None
    # Distinguishes the short CTA-modal capture (club + email only) from the full
    # 17-field /contact form, so staff know what to expect before they follow up.
    source: Optional[str] = None
    # Meta Pixel dedup context, forwarded so the server-side Lead event (below)
    # matches the browser pixel's Lead. Absent = CAPI event is skipped (see
    # meta_capi.send_lead_event), the browser pixel still fires either way.
    meta: Optional[ContactMeta] = None


def _clip(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if value else None


@router.post("")
async def submit_contact(
    payload: ContactIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Store one club onboarding enquiry.

    Required fields are validated client-side too; we re-check club and email
    (the two the short CTA-modal form collects) and clip every field so a bad or
    oversized post can't bloat the table. Name is optional here since the quick
    form doesn't ask for it — the full /contact form still requires it client-side.
    Formspree is the primary delivery, so the frontend treats a non-200 here as
    non-fatal.
    """
    name = (payload.name or "").strip()
    club = (payload.club or "").strip()
    email = (payload.email or "").strip().lower()
    if not club or not email:
        raise HTTPException(status_code=422, detail="Club and email are required.")

    # A guid is only meaningful alongside a club actually picked from the
    # search — a typed-in club name has nothing to key on, and letting a
    # 'manual' row carry an id would put a guessed identity on the record.
    club_source = _clip(payload.clubSource, 20)
    club_source = club_source if club_source in ("search", "manual") else None
    club_org_id = _clip(payload.clubOrgId, 64) if club_source == "search" else None

    row = ClubOnboardingRequest(
        name=name[:200],
        club=club[:200],
        email=email[:320],
        phone=_clip(payload.phone, 50),
        association=_clip(payload.association, 200),
        grades=_clip(payload.grades, 50),
        storage=_clip(payload.storage, 100),
        timeline=_clip(payload.timeline, 100),
        club_url=_clip(payload.clubUrl, 500),
        message=_clip(payload.message, 4000),
        role=_clip(payload.role, 120),
        founded_year=_clip(payload.founded, 20),
        playhq_status=_clip(payload.playhq, 50),
        has_historical=_clip(payload.historical, 50),
        interests=_clip(payload.interests, 400),
        heard_about=_clip(payload.heard, 200),
        contact_method=_clip(payload.contactMethod, 20),
        source=_clip(payload.source, 50) or "contact_form",
        user_agent=_clip(request.headers.get("user-agent"), 500),
        visitor_id=_clip(payload.visitorId, 64),
        club_org_id=club_org_id,
        club_source=club_source,
    )
    db.add(row)
    await db.commit()
    # If this enquirer is already a Person in the CRM, record that they made
    # contact via the website. Runs after the response so a CRM hiccup can't slow
    # or fail the form (Formspree is the primary delivery either way).
    background.add_task(mark_contact_source, email, "WEBSITE")
    # A direct "onboard my club" enquiry — from either this short CTA-modal form
    # or the full Contact page (both post here) — is the strongest buying signal
    # a prospect can give, so the club is immediately upserted into Twenty as a
    # Company + Lead at a forced Hot (100) engagement score, regardless of
    # whether it was already exported. Backgrounded; never raises.
    # ``org_id`` is what stops one club arriving as two: a picked club keys the
    # directory row on its real CA guid instead of a synthetic one derived from
    # however the name was spelled.
    background.add_task(push_onboarding_enquiry, club_name=club, contact_name=name,
                        email=email, phone=payload.phone, org_id=club_org_id)
    # Same enquiry, the local CRM pipeline's equivalent of the Twenty push
    # above — ensures a New Lead deal exists (or advances an existing one) so
    # the pipeline stays in step with the same trigger. Best-effort.
    background.add_task(sync_deal_for_enquiry, club_name=club, contact_name=name,
                        email=email, phone=payload.phone, org_id=club_org_id)
    # Server-side Lead event (Meta Conversions API), sharing the browser pixel's
    # event_id so Meta dedupes the pair. Best-effort + backgrounded — a CAPI
    # hiccup never affects this response (see meta_capi.send_lead_event).
    meta = payload.meta
    background.add_task(
        meta_capi.send_lead_event,
        event_id=meta.eventId if meta else None,
        event_source_url=meta.eventSourceUrl if meta else None,
        email=email,
        phone=payload.phone,
        name=name or None,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        fbp=meta.fbp if meta else None,
        fbc=meta.fbc if meta else None,
    )
    # Drop a breadcrumb for the conversion itself, so it shows up inline with
    # this visitor's page-view journey on the super-admin Usage page instead of
    # only existing as a row in the onboarding table. Fire-and-forget, never
    # raises (see usage_tracker.record_event).
    record_event_bg(
        event_type="conversion",
        method="POST",
        path="/public/contact",
        route="/public/contact",
        status=200,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
        visitor_id=payload.visitorId,
        metadata={"club": club, "source": row.source},
    )
    return {"ok": True}
