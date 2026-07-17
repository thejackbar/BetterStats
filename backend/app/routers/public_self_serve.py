"""Public self-serve club trial registration (unauthenticated).

The public face of routers/self_serve_trial.py — the ad-campaign landing page
(/trial) drives visitors here to register their own club and start a trial
with no credit card and no human in the loop. The business logic is NOT
duplicated: the internal router's step handlers are plain coroutines (their
auth gates live on that router's constructor, not the functions), so this
router re-registers the untouched handlers for the steps where public
behaviour is identical, and hand-wraps only the steps where it differs:

- rate limiting per IP (the internal flow only limits per email — a public
  attacker could burn a victim email's OTP quota or lock it out without an
  IP dimension),
- a honeypot field + minimum-fill-time check on submit (light bot guardrails
  per the agreed "auto-approve" posture; the email OTP the flow already
  requires is the main gate),
- generic error messages where the internal route deliberately shows raw
  provider errors to its super-admin operator (the "TIGHTEN BEFORE PUBLIC
  LAUNCH" note in self_serve_trial.py — this router is that public launch),
- auto-login on successful submit (the session-minting primitive
  self_serve_trial.py's login-as endpoint already documents as "what a
  future public flow will call automatically"),
- first-touch ad attribution stored onto the new org (migration 160), and a
  server-side Meta CompleteRegistration event deduped against the browser
  pixel's copy — the conversion the ad campaign optimises toward.

Known, accepted public-surface trade-offs (reviewed): GET
/verify-email/status reveals whether an email is mid-verification (low
value to an attacker — it doesn't reveal account existence, only an
in-flight signup); the submit 500 includes an opaque org_id/user_id support
reference a stuck registrant must be able to quote (not an enumeration
surface). Everything here still sits behind the
``self_serve_registration_enabled`` platform flag — the whole router 404s
until a super admin flips it on, so this can merge ahead of the campaign.
"""
import logging
import time
import uuid as _uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, get_db
from app.routers.auth import (
    create_session_token, require_self_serve_registration_enabled, set_session_cookie,
)
from app.routers import self_serve_trial as sst
from app.services import meta_capi
from app.services import platform_settings as ps
from app.services import rate_limit
from app.services.login_audit import client_ip
from app.services.usage_tracker import record_event_bg

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/self-serve",
    tags=["public-self-serve"],
    dependencies=[Depends(require_self_serve_registration_enabled)],
)

# Per-IP caps, layered on top of the per-email limits the shared handlers
# already enforce internally. Sized for one household/club committee sharing
# an IP while several people poke at the form, not for scraping.
SEARCH_LIMIT, SEARCH_WINDOW = 120, 3600      # club-search keystrokes hit CA's API
PREPARE_LIMIT, PREPARE_WINDOW = 15, 3600
SEND_LIMIT, SEND_WINDOW = 10, 3600           # OTP emails — internal adds 5/hour/email
CHECK_LIMIT, CHECK_WINDOW = 30, 900          # OTP guesses — internal adds 5-fail/email lockout
SUBMIT_LIMIT, SUBMIT_WINDOW = 5, 3600
# A real registrant can't finish 5 steps INCLUDING an email OTP round trip in
# under this many milliseconds; a form-filler bot can.
MIN_FILL_MS = 4000

# ─── Pass-throughs: public behaviour is identical, re-register the internal
#     handlers untouched (FastAPI resolves their Depends normally). ──────────
router.add_api_route("/validate-admin", sst.validate_admin, methods=["POST"])
router.add_api_route("/verify-email/status", sst.verification_status, methods=["GET"])
router.add_api_route("/acknowledge", sst.acknowledge, methods=["POST"])


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    """What the registration wizard needs before any step-specific work: the
    flag is on (the router dependency already 404'd otherwise) and the trial
    length for the modal title. Public counterpart of the internal /status."""
    return {
        "enabled": True,
        "default_trial_days": await ps.get_default_trial_days(db),
    }


@router.get("/search")
async def search_clubs(q: str = "", request: Request = None, db: AsyncSession = Depends(get_db)):
    """Public wrapper around the shared club search (closes the "public,
    unauthenticated wrapper around club search" item on the go-public
    checklist in docs/self-serve-trial-onboarding-plan.md). Rate-limited per
    IP because every call hits the Cricket Australia search API."""
    rate_limit.enforce(
        f"pubss:search:{client_ip(request)}", SEARCH_LIMIT, SEARCH_WINDOW,
        detail="Too many searches. Slow down and try again shortly.",
    )
    return await sst.search_clubs(q=q, db=db)


class PublicSubmitMeta(BaseModel):
    """Meta Pixel dedup context — same shape/purpose as public_contact.py's
    ContactMeta: the browser fires its pixel event with this eventId and the
    server-side copy must carry the same id so Meta counts one event."""
    eventId: Optional[str] = None
    eventSourceUrl: Optional[str] = None
    fbp: Optional[str] = None
    fbc: Optional[str] = None


class PublicPrepareRequest(sst.PrepareClubRequest):
    # Honeypot: hidden in the real form, so only a form-filler bot fills it.
    website: str = ""
    # Pixel dedup context for the server-side Lead event fired on success.
    meta: Optional[PublicSubmitMeta] = None


@router.post("/prepare")
async def prepare_club(
    data: PublicPrepareRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    rate_limit.enforce(
        f"pubss:prepare:{client_ip(request)}", PREPARE_LIMIT, PREPARE_WINDOW,
        detail="Too many attempts — try again later.",
    )
    if (data.website or "").strip():
        # Bot caught by the honeypot: return a plausible fake success so the
        # bot never learns it was detected. Nothing was checked or created —
        # a fabricated slug preview is all it gets.
        return {
            "org_id": data.org_id,
            "name": (data.name or "").strip(),
            "short_name": (data.short_name or "").strip(),
            "slug": sst._slugify(data.name),
        }
    result = await sst.prepare_club(data=data, db=db)
    # A visitor who picked their real club out of the CA register is a
    # genuine lead even if they stall later — server-side Lead (Meta CAPI),
    # deduped against the browser pixel's copy via the shared eventId. Same
    # semantics as the Contact form's Lead. Backgrounded, never blocks.
    meta = data.meta
    background_tasks.add_task(
        meta_capi.send_lead_event,
        event_id=meta.eventId if meta else None,
        event_source_url=meta.eventSourceUrl if meta else None,
        client_ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        fbp=meta.fbp if meta else None,
        fbc=meta.fbc if meta else None,
        content_name="Self-serve trial started",
        content_category="self_serve_trial",
    )
    return result


@router.post("/verify-email/send")
async def send_verification_code(data: sst.SendCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    rate_limit.enforce(
        f"pubss:send:{client_ip(request)}", SEND_LIMIT, SEND_WINDOW,
        detail="Too many verification codes requested — try again later.",
    )
    try:
        return await sst.send_verification_code(data=data, db=db)
    except HTTPException as e:
        if e.status_code == 502:
            # The internal route deliberately shows the raw provider error to
            # its super-admin operator; a public visitor gets a generic
            # message (the "TIGHTEN BEFORE PUBLIC LAUNCH" note this router
            # exists to honour). The real error is already logged server-side.
            logger.error("public self-serve: verification email send failed: %s", e.detail)
            raise HTTPException(
                status_code=502,
                detail="We couldn't send the verification email just now. Please try again in a minute.",
            )
        raise


@router.post("/verify-email/check")
async def check_verification_code(data: sst.CheckCodeRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Per-IP cap on ALL check calls (the shared handler's lockout keys on the
    # email only, so without this an attacker rotating target emails gets
    # unlimited guesses from one IP).
    rate_limit.enforce(
        f"pubss:check:{client_ip(request)}", CHECK_LIMIT, CHECK_WINDOW,
        detail="Too many attempts — try again later.",
    )
    return await sst.check_verification_code(data=data, db=db)


class PublicSubmitRequest(sst.SubmitRequest):
    # Honeypot (see PublicPrepareRequest).
    website: str = ""
    # Client epoch-ms when the wizard was opened, for the minimum-fill-time
    # check. Optional: a storage-blocked browser may not send it, and the OTP
    # + honeypot gates stand on their own.
    form_started_at: Optional[int] = None
    # First-touch acquisition record, verbatim from visitor.js getAttribution().
    attribution: Optional[dict] = None
    # First-party visitor id (localStorage UUID) so the registration links back
    # to the anonymous browsing journey on the super-admin Usage page — same
    # field the Contact form sends.
    visitorId: Optional[str] = None
    # Pixel dedup context for the server-side CompleteRegistration event.
    meta: Optional[PublicSubmitMeta] = None


_ATTRIBUTION_KEYS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_content",
    "click_id", "click_source", "landing_path", "landing_referrer", "has_signal",
)


def _clean_attribution(raw: Optional[dict]) -> Optional[dict]:
    """Keep only the known getAttribution() keys, clipped — stored verbatim
    otherwise, but never an arbitrary client-controlled blob."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k in _ATTRIBUTION_KEYS:
        v = raw.get(k)
        if isinstance(v, str):
            out[k] = v[:300]
        elif isinstance(v, bool):
            out[k] = v
    return out or None


@router.post("/submit")
async def submit(
    data: PublicSubmitRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    rate_limit.enforce(
        f"pubss:submit:{client_ip(request)}", SUBMIT_LIMIT, SUBMIT_WINDOW,
        detail="Too many attempts — try again later.",
    )

    if (data.website or "").strip():
        # Honeypot: plausible fake success, nothing created (see /prepare).
        return {
            "status": "completed",
            "org_id": str(_uuid.uuid4()),
            "user_id": str(_uuid.uuid4()),
            "replayed": False,
        }

    if data.form_started_at is not None:
        elapsed_ms = int(time.time() * 1000) - data.form_started_at
        # Only reject a positive, implausibly-small elapsed time — a clock
        # far ahead of ours goes negative and is ignored rather than
        # false-rejecting a real registrant over clock skew. A human can't
        # finish five steps plus an email OTP round trip in under 4 seconds.
        if 0 <= elapsed_ms < MIN_FILL_MS:
            raise HTTPException(status_code=422, detail="Something went wrong. Please try again.")

    result = await sst.submit(data=data, background_tasks=background_tasks, db=db)

    # ─── Public-only follow-through, all after the registration is durably
    #     committed by the shared handler. ─────────────────────────────────────

    # First-touch ad attribution onto the new org (migration 160) — the join
    # key for the ad-signups report (routers/meta_ads.py). Best-effort: an
    # attribution hiccup must never look like a failed registration.
    try:
        attribution = _clean_attribution(data.attribution)
        org = await db.get(Organisation, _uuid.UUID(result["org_id"])) if result.get("org_id") else None
        if org is not None and org.signup_source is None:
            org.signup_source = (
                "self_serve_ad" if (attribution or {}).get("has_signal") else "self_serve_organic"
            )
            org.signup_attribution = attribution
            await db.commit()
    except Exception:
        logger.exception("public self-serve: storing signup attribution failed for %s", result.get("org_id"))

    # Auto-login: the whole point of self-serve is landing in your own live
    # dashboard, not on a login form. Same primitive login-as uses; replayed
    # idempotent submits re-login the same registrant, which is what a
    # double-click deserves.
    if result.get("user_id"):
        set_session_cookie(response, create_session_token(result["user_id"]))

    if result.get("status") == "completed" and not result.get("replayed"):
        # Server-side CompleteRegistration (Meta CAPI), deduped against the
        # browser pixel's copy via the shared eventId — the ad campaign's
        # optimisation conversion. Backgrounded, never affects the response.
        meta = data.meta
        background_tasks.add_task(
            meta_capi.send_complete_registration_event,
            event_id=meta.eventId if meta else None,
            event_source_url=meta.eventSourceUrl if meta else None,
            email=(data.email or "").strip().lower() or None,
            phone=(data.mobile_number or "").strip() or None,
            name=f"{data.first_name} {data.last_name}".strip() or None,
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            fbp=meta.fbp if meta else None,
            fbc=meta.fbc if meta else None,
        )
        # Conversion breadcrumb for the super-admin Usage page, same as the
        # Contact form's — the registration shows inline with the visitor's
        # browsing journey. Fire-and-forget.
        record_event_bg(
            event_type="conversion",
            method="POST",
            path="/public/self-serve/submit",
            route="/public/self-serve/submit",
            status=200,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            visitor_id=(data.visitorId or "").strip()[:64] or None,
            org_id=result.get("org_id"),
            metadata={"club": result.get("name"), "org_id": result.get("org_id")},
        )

    # The frontend follows this straight into the new admin's live dashboard.
    return {**result, "redirect": "/admin"}
