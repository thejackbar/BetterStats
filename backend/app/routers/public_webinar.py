"""Public webinar registration (unauthenticated).

WHY THIS PAGE EXISTS AT ALL, since it decides everything about the shape of it:
the Meta ad set optimises for the `CompleteRegistration` pixel event, and a
pixel cannot fire on a third-party domain. Pointing the ad straight at
StreamYard would hand Meta zero conversion signal and delivery would degrade
within days. So the registration happens on betterat.cricket, fires the pixel
on confirmed success, and hands the viewing link over afterwards.

Unauthenticated by necessity — the registrant is a prospect with no club and no
login, the same posture `public_contact.py` takes. Deliberately NOT behind the
`self_serve_registration_enabled` flag either: that flag gates trial signup,
and a paid campaign pointing at this page must keep working whether or not
self-serve registration happens to be switched on.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import meta_capi, platform_settings, rate_limit, webinar
from app.services.login_audit import client_ip
from app.services.usage_tracker import record_event_bg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/webinar", tags=["public-webinar"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The shortest and longest run of digits that can be a real phone number. An
# Australian landline with no area code is 8 digits and a mobile is 10; an
# international number with a country code runs to 15 (E.164's own ceiling).
#
# THE FIELD ITSELF IS OPTIONAL. It shipped required for one release and that
# was the wrong call on cold paid traffic — a mandatory phone number is the
# highest-friction field on the form, and it reads as a promise to ring, which
# contradicts the "no sales call" line on /trial. A blank one is accepted; this
# range only governs a number somebody actually typed.
#
# DELIBERATELY NOT `admin_identity.mobile_valid`, which is the right rule for a
# club admin's account and the wrong one here: it refuses anything that is not
# an Australian mobile, and the clubroom landline a secretary writes down is a
# perfectly good number to ring them on. This checks that what was typed COULD
# be a phone number, and nothing more — the value is stored exactly as typed.
PHONE_MIN_DIGITS, PHONE_MAX_DIGITS = 8, 15

# Sized for a club committee filling the form in from one connection, not for
# scraping. Every submission is a database write and a transactional email.
REGISTER_LIMIT, REGISTER_WINDOW = 20, 3600

# The shortest a real person plausibly takes to read the hero and fill in three
# fields. Under it, this is a bot that filled the form the moment it loaded.
MIN_FILL_SECONDS = 3


class WebinarMeta(BaseModel):
    """Meta Pixel / Conversions API dedup context — see docs/meta-conversions-api.md.
    `eventId` must be the exact id the browser pixel's CompleteRegistration
    fired with, so Meta counts the browser and server copies as one event."""
    eventId: Optional[str] = None
    eventSourceUrl: Optional[str] = None
    fbp: Optional[str] = None
    fbc: Optional[str] = None


class RegisterIn(BaseModel):
    name: str = ""
    email: str = ""
    club: str = ""
    phone: str = ""
    role: Optional[str] = None
    # First-touch UTM/click-id blob from lib/visitor.js `getAttribution()` — the
    # same capture every other public form on the site uses, rather than a
    # second one built for this page.
    attribution: Optional[dict[str, Any]] = None
    visitorId: Optional[str] = None
    meta: Optional[WebinarMeta] = None
    # Honeypot. A real browser never fills this in (it is off-screen and
    # aria-hidden); a form-filling bot fills every field it finds.
    website: Optional[str] = None
    # Epoch ms of when the form first rendered, for the minimum-fill-time check.
    formStartedAt: Optional[int] = None


def _event_payload(recording_url: Optional[str]) -> dict:
    event = webinar.EVENT
    is_past = event.is_past()
    return {
        "key": event.key,
        "title": event.title,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat(),
        "date_label": event.date_label,
        "time_label": event.time_label,
        "is_past": is_past,
        # After the event this is the recording if a super admin has pasted one
        # in, and nothing at all if they haven't — never the dead live link.
        "watch_url": (recording_url if is_past else event.watch_url),
        "recording_available": bool(is_past and recording_url),
        "google_calendar_url": webinar.google_calendar_url(
            recording_url=recording_url if is_past else None
        ),
        "roles": webinar.ROLES,
    }


@router.get("")
async def webinar_details(db: AsyncSession = Depends(get_db)):
    """What the page needs that it cannot know for itself: whether a recording
    has been published yet. The date and the labels are here too, but the page
    renders those from its own mirrored constant so the headline paints without
    waiting on this — the ad's traffic is mobile, and a request in front of the
    H1 is a request in front of LCP."""
    return _event_payload(await platform_settings.get_webinar_recording_url(db))


@router.get("/calendar.ics")
async def calendar_file(db: AsyncSession = Depends(get_db)):
    """The calendar file, served as a real URL rather than a browser-built blob
    — that is what lets the confirmation email link to it too, and a link works
    in every mail client where an attachment needs five different provider
    APIs (see webinar.send_confirmation)."""
    recording_url = await platform_settings.get_webinar_recording_url(db)
    body = webinar.build_ics(recording_url=recording_url if webinar.EVENT.is_past() else None)
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bettercricket-demo.ics"'},
    )


@router.post("/register")
async def register(
    payload: RegisterIn,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Register one person, then hand back everything the success state needs.

    The response carries `created`, and the page fires the conversion pixel
    only when it is true. A resubmission from an address already registered is
    the same lead, not a second registration — counting it would teach the ad
    set to optimise toward people who fill the form in twice. It still gets the
    link and the calendar, because from the registrant's side nothing has gone
    wrong.
    """
    name = (payload.name or "").strip()
    email = (payload.email or "").strip().lower()
    club = (payload.club or "").strip()
    phone = (payload.phone or "").strip()

    # A filled honeypot is a bot. Answer as though it worked — telling it
    # otherwise only teaches whoever wrote it to leave the field alone. Nothing
    # is stored and no email is sent.
    if (payload.website or "").strip():
        logger.info("webinar: honeypot filled, ignoring submission")
        return _fake_success(await platform_settings.get_webinar_recording_url(db))

    started = payload.formStartedAt
    if isinstance(started, int) and started > 0:
        elapsed = (datetime.now(timezone.utc).timestamp() * 1000) - started
        # A negative delta is clock skew on the visitor's device, not a bot —
        # ignored rather than treated as an instant submission.
        if 0 <= elapsed < MIN_FILL_SECONDS * 1000:
            raise HTTPException(status_code=422, detail="That was too quick — please try again.")

    if not name:
        raise HTTPException(status_code=422, detail="Enter your name.")
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if not club:
        raise HTTPException(status_code=422, detail="Enter your club.")
    # OPTIONAL — a blank phone is a complete registration, not a refusal. See
    # PHONE_MIN_DIGITS above for why, and why the check on a number that IS
    # given is this loose.
    if phone:
        digits = re.sub(r"\D", "", phone)
        if not (PHONE_MIN_DIGITS <= len(digits) <= PHONE_MAX_DIGITS):
            raise HTTPException(status_code=422, detail="Enter a valid phone number.")

    rate_limit.enforce(
        f"webinar:register:{client_ip(request)}", REGISTER_LIMIT, REGISTER_WINDOW,
        detail="Too many registrations from this connection. Try again shortly.",
    )

    result = await webinar.register(
        db,
        name=name, email=email, club=club, phone=phone, role=payload.role,
        attribution=payload.attribution or {},
        visitor_id=payload.visitorId,
        user_agent=request.headers.get("user-agent"),
    )

    recording_url = await platform_settings.get_webinar_recording_url(db)

    # The confirmation email runs after the response so a provider hiccup never
    # slows or fails the registration — the page has already handed over the
    # link and the calendar, which is the real delivery.
    background.add_task(
        _send_confirmation_bg,
        registration_id=result["id"], name=name, email=email,
        recording_url=recording_url if webinar.EVENT.is_past() else None,
    )

    # ONE FORM, TWO LISTS. StreamYard's own registration asks for exactly what
    # this form already collected, so the registrant is pushed into their list
    # from here instead of being asked again on their domain. Backgrounded and
    # best-effort for the same reason the email is: the registration is already
    # written and the link already handed over, so an undocumented third-party
    # API must not be able to slow or fail either. Never for a past event —
    # there is nothing left to register for.
    if not webinar.EVENT.is_past():
        background.add_task(
            _push_streamyard_bg,
            registration_id=result["id"], name=name, email=email, phone=phone,
        )

    if result["created"]:
        # Server-side CompleteRegistration, sharing the browser pixel's own
        # event_id so Meta dedupes the pair into one conversion rather than
        # counting it twice. Best-effort and backgrounded (see meta_capi).
        #
        # The phone rides along BECAUSE it is a second hashed identifier for
        # the same person: Meta matches a conversion to whoever saw the ad, and
        # a registration carrying an email AND a phone matches more often than
        # one carrying an email alone. `meta_capi._hash_phone` does the
        # digits-only normalisation and hashing — the raw number never leaves.
        meta = payload.meta
        background.add_task(
            meta_capi.send_complete_registration_event,
            event_id=meta.eventId if meta else None,
            event_source_url=meta.eventSourceUrl if meta else None,
            email=email,
            phone=phone,
            name=name,
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            fbp=meta.fbp if meta else None,
            fbc=meta.fbc if meta else None,
            # THE SAME THREE VALUES THE BROWSER PIXEL SENDS (Demo.jsx), and
            # they have to be passed rather than defaulted: the two halves of
            # one deduped conversion must not describe two different products.
            # A webinar registration carries NO value — it is a form fill, not
            # a club buying anything, and inheriting the trial's A$399 default
            # invented revenue on every one of them.
            value=0,
            content_name=f"Webinar Registration - {webinar.EVENT.date_label} 2026",
            content_category="webinar",
        )
        # A breadcrumb on this visitor's own journey, so a registration shows
        # up inline on the Usage page rather than only as a row in its table.
        record_event_bg(
            event_type="conversion",
            method="POST",
            path="/public/webinar/register",
            route="/public/webinar/register",
            status=200,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            visitor_id=payload.visitorId,
            metadata={"club": club, "source": "webinar", "event": webinar.EVENT.key},
        )

    return {
        "ok": True,
        "created": result["created"],
        **_event_payload(recording_url),
    }


def _fake_success(recording_url: Optional[str]) -> dict:
    return {"ok": True, "created": False, **_event_payload(recording_url)}


async def _send_confirmation_bg(*, registration_id: str, name: str, email: str,
                                recording_url: Optional[str]) -> None:
    """Own session — a background task must never borrow the request's, which
    is closed by the time this runs. Never raises."""
    from app.models.db import async_session_maker

    try:
        async with async_session_maker() as session:
            await webinar.send_confirmation(
                session, registration_id=registration_id, name=name,
                email=email, recording_url=recording_url,
            )
    except Exception:
        logger.exception("webinar: confirmation task failed for %s", email)


async def _push_streamyard_bg(*, registration_id: str, name: str, email: str,
                              phone: Optional[str]) -> None:
    """Own session — a background task must never borrow the request's, which is
    closed by the time this runs. Never raises."""
    from app.models.db import async_session_maker

    try:
        async with async_session_maker() as session:
            await webinar.push_to_streamyard(
                session, registration_id=registration_id, name=name,
                email=email, phone=phone,
            )
    except Exception:
        logger.exception("webinar: StreamYard push task failed for %s", email)
