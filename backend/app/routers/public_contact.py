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
from app.services import meta_capi
from app.services.crm import sync_deal_for_enquiry
from app.services.login_audit import client_ip
from app.services.usage_tracker import record_event_bg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/contact", tags=["public-contact"])


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
    )
    db.add(row)
    await db.commit()
    # A direct "onboard my club" enquiry — from either this short CTA-modal form
    # or the full Contact page (both post here) — is the strongest buying signal
    # a prospect can give, so it ensures a platform deal exists (or advances an
    # existing one) in the BetterCricket CRM pipeline and recomputes the club's
    # engagement score. Runs after the response so a CRM hiccup can't slow or
    # fail the form (Formspree is the primary delivery either way).
    background.add_task(sync_deal_for_enquiry, club_name=club, contact_name=name,
                        email=email, phone=payload.phone)
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
