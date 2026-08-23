"""Internal self-serve club trial registration — Super Admin menu item.

See docs/self-serve-trial-onboarding-plan.md. Reachable from the Super Admin
"Self-Serve Trial (Internal)" page (``require_super_admin``) ONLY — this is
NOT gated by the ``self_serve_registration_enabled`` platform flag. That flag
controls the *public* self-serve surface only (routers/public_self_serve.py,
the /trial ad-campaign landing page), and must not also hide this internal
tool from a super admin who needs it regardless of whether the public flow
is switched on.
"""
import logging
import re
import uuid as _uuid
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.modules import BILLABLE_MODULES, MODULE_CORE
from app.models.db import (
    ClubMembership, DiscountCouponRedemption, ModuleActionRequest, Organisation,
    SelfServeAcknowledgement, SelfServeIdempotencyKey, User, get_db,
)
from app.routers.auth import require_super_admin
from app.services import module_subscriptions as mod_subs
from app.services import admin_identity
from app.services import password_policy
from app.services import platform_settings as ps
from app.services import playhq_client
from app.services import rate_limit
from app.services import self_serve_verification as verification
from app.services.login_audit import client_ip
from app.services.memberships import ensure_primary_admin
from app.services.sync import _parse_uuid, find_matching_organisation
from app.services.usage_tracker import hash_ip

# The optional add-on modules a trial can select (BetterStats/Core is always
# on, not a choice — handled via mod_subs.ensure_core_subscription, not a
# trial). Same set routers/club_admin.py's SuperClubs module editor manages.
_SELECTABLE_MODULES = tuple(k for k in BILLABLE_MODULES if k != MODULE_CORE)

logger = logging.getLogger(__name__)

# require_super_admin only — no flag dependency. This router always works
# for a super admin, checkbox or no checkbox (see module docstring).
router = APIRouter(
    prefix="/self-serve-trial",
    tags=["self-serve-trial"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/status")
async def get_status(db: AsyncSession = Depends(get_db)):
    """Data the registration modal shell needs before any step-specific work
    exists: confirmation the flow is enabled (redundant with the 404 the router
    dependency already gives, but explicit for the frontend) and the configured
    trial length for the modal's title."""
    return {
        "enabled": True,
        "default_trial_days": await ps.get_default_trial_days(db),
    }


def _duplicate_club_message(name: str, admin_label: str | None, slug: str | None = None) -> str:
    """Shared wording for the "already registered" 409 — matches the search
    step's own duplicate message in SelfServeTrialModal.jsx so the same
    condition reads the same way wherever it's surfaced. This is the
    plain-text fallback for callers that can only show a flat string (e.g. the
    final submit step's error, a race-condition edge case); structured callers
    (search_clubs, the 409 detail dicts below) also return the raw ``slug``
    and ``admin_label`` so the frontend can render the club name and its
    public page as a real clickable link instead of the parenthetical slug
    used here.

    ``admin_label`` already ends in an ellipsis (see ``_primary_admin_label``)
    when it carries a truncated last name, so a space (not a bare "…;") is
    inserted before the semicolon that follows it — otherwise the two collide
    into a stray "…;" that reads like a typo."""
    see = f" - see {name}'s public page on BetterCricket ({slug})." if slug else "."
    admin = f" {admin_label} ;" if admin_label else ";"
    return (
        f"{name} has already been registered in BetterCricket{see} "
        f"Please either (a) contact your club's administrator{admin} or (b) email us at "
        "support@bettersports.com.au if you think your club has been incorrectly registered."
    )


async def _primary_admin_label(db: AsyncSession, club_id) -> str | None:
    """First name + last-initial for the club's Primary Club Admin (falling
    back to the longest-standing club admin if no primary is set), so the
    "already registered" message can point at a real person to contact
    without exposing a full name or any contact details.

    ``User.first_name``/``last_name`` were only ever populated by the
    self-serve trial registration form itself (migration 135) — every admin
    created any other way (the ordinary Super Admin "New Club" flow, which is
    how almost every existing club's admin account exists) has those columns
    NULL and only ``display_name`` set. Reading first/last name alone made
    this return None for nearly every real club, which is the bug this
    docstring used to paper over. Falls back to splitting ``display_name`` on
    whitespace (first word + last word's initial) so a "Chris Mackinnon"
    account still resolves to "Chris M…"."""
    row = (await db.execute(
        select(User.first_name, User.last_name, User.display_name)
        .join(ClubMembership, ClubMembership.user_id == User.id)
        .where(ClubMembership.club_id == club_id)
        .order_by(ClubMembership.is_primary_admin.desc(), ClubMembership.created_at.asc())
        .limit(1)
    )).first()
    if row is None:
        return None
    if (row.first_name or "").strip():
        first = row.first_name.strip()
        last = (row.last_name or "").strip()
        return f"{first} {last[0]}…" if last else first
    parts = (row.display_name or "").strip().split()
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}…"


@router.get("/search")
async def search_clubs(q: str = "", db: AsyncSession = Depends(get_db)):
    """Club search for step 1 of the registration modal. Reuses the same
    authoritative Grassroots/PlayHQ lookup the existing Super Admin "New Club"
    search calls (playhq_client.search_organisations) — same minimum-length and
    empty-query handling as GET /organisations/search.

    Each result is annotated with ``already_registered``, using the same
    three-layer id/playhq_id/name match already used to guard club creation
    against duplicates (find_matching_organisation), so an operator can see a
    club is taken before attempting to register it. A registered club also
    carries ``already_registered_by`` — the Primary Club Admin's first name +
    last initial only (e.g. "Jack B…") — so the duplicate message can point at
    a real person without exposing a full name, its length, or any contact
    details — and ``already_registered_slug``, the existing club's public page
    slug, so the frontend can link straight to it."""
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    out = []
    for org in results:
        org_id = _parse_uuid(str(org.get("id") or ""))
        existing = await find_matching_organisation(db, org_id, org.get("name") or "", include_archived=False)
        admin_label = await _primary_admin_label(db, existing.id) if existing else None
        out.append({
            **org,
            "already_registered": existing is not None,
            "already_registered_by": admin_label,
            "already_registered_slug": existing.slug if existing else None,
        })
    return out


async def _resolve_club_address(db: AsyncSession, *, org_id: str, name: str) -> dict | None:
    """The club's real street address, for the Stripe Customer created at its
    first checkout — automatic tax calculation needs one (see
    stripe_client._ensure_customer). Two sources, tried in order:

    1. A live PlayHQ public-directory search for this club by name, matched
       back to the exact org GUID (the search is name-fuzzy, not a direct
       GUID lookup, so results are filtered). ``delay=(0, 0.5)`` overrides
       the client's default 15-40s *background-crawl* politeness delay —
       this is one interactive lookup during a registration a person is
       sitting in front of, not a bulk crawl.
    2. Club Directory (marketing_clubs) — already-crawled data for this same
       GUID, if the live search found nothing (offline, name mismatch, or
       the club isn't in PlayHQ's public search for some other reason).

    Returns None (not raised) on any failure — an unresolved address isn't
    fatal to registration; create_checkout_session's own
    ``customer_update: {"address": "auto"}`` covers the gap by saving
    whatever the payer enters at checkout instead."""
    from app.models.db import MarketingClub
    from app.services import playhq_directory_client as phq

    try:
        results, _total = await phq.search_organisations("CLUB", name, page=1, limit=25, delay=(0, 0.5))
    except Exception:
        results = None
    for r in (results or []):
        if str(r.get("id") or "").lower() == str(org_id).lower():
            addr = r.get("address") or {}
            if addr.get("line1") or addr.get("suburb"):
                return {
                    "line1": addr.get("line1") or None,
                    "suburb": addr.get("suburb") or None,
                    "state": addr.get("state") or None,
                    "postcode": addr.get("postcode") or None,
                    "country": addr.get("country") or None,
                }
            break

    club = (await db.execute(
        select(MarketingClub).where(MarketingClub.grassroots_guid == str(org_id))
    )).scalar_one_or_none()
    if club and (club.address_line1 or club.suburb):
        return {
            "line1": club.address_line1, "suburb": club.suburb,
            "state": club.state, "postcode": club.postcode, "country": club.country,
        }
    return None


def _slugify(name: str) -> str:
    """Same algorithm SuperClubs.jsx's selectOrg uses to auto-fill a slug from a
    club name (lowercase, collapse non-alphanumeric runs to one dash, trim),
    ported here because this step generates the slug server-side rather than
    trusting an editable client field — the operator can't edit it in this flow."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """The existing manual "New Club" flow leaves a slug collision for the
    operator to notice (409) and retype by hand — there's no auto-suffix
    algorithm to reuse, because until now a human was always in the loop. Here
    the slug isn't editable, so a collision needs to resolve to *something*:
    append -2, -3, ... until free. Minimal extension of the existing slugify,
    not a competing algorithm."""
    base = base or "club"
    slug = base
    n = 2
    while True:
        existing = await db.execute(select(Organisation).where(Organisation.slug == slug))
        if not existing.scalar_one_or_none():
            return slug
        slug = f"{base}-{n}"
        n += 1


class PrepareClubRequest(BaseModel):
    org_id: str
    name: str
    short_name: str = ""


@router.post("/prepare")
async def prepare_club(data: PrepareClubRequest, db: AsyncSession = Depends(get_db)):
    """Step 1 -> step 2 handoff: prepare the club identity fields (name, short
    name, slug, source id) the way the existing "New Club" creation already
    derives them, so later steps can display them read-only. No club is created
    here — this only prepares and previews.

    No club logo, association, state/territory or location fields: none of
    these exist anywhere in the current data model or club-creation flow (the
    Grassroots/PlayHQ APIs this reuses don't return them either), so there's
    nothing existing to reuse for them. A club's logo is uploaded later, in the
    onboarding wizard's own step for it."""
    org_id = _parse_uuid(data.org_id)
    if not org_id:
        raise HTTPException(status_code=422, detail="Invalid club id: pick a club from the search results")

    name = (data.name or "").strip()
    existing = await find_matching_organisation(db, org_id, name, include_archived=False)
    if existing:
        admin_label = await _primary_admin_label(db, existing.id)
        raise HTTPException(status_code=409, detail={
            "message": _duplicate_club_message(name, admin_label, existing.slug),
            "name": name,
            "slug": existing.slug,
            "admin_label": admin_label,
        })

    org_data = await playhq_client.get_organisation(str(org_id))
    if not org_data:
        raise HTTPException(status_code=404, detail="Club not found in the Cricket Australia data source")

    slug = await _unique_slug(db, _slugify(name))
    return {
        "org_id": str(org_id),
        "name": name,
        "short_name": (data.short_name or "").strip(),
        "slug": slug,
    }


# ─── Step 2: Primary Club Admin details (Phase 4) ────────────────────────────
# Password isn't collected here — deliberately deferred to immediately before
# final submission (a later phase) so a plaintext password spends less time
# sitting in client state across email verification and acknowledgements.

# The field rules themselves live in services/admin_identity.py — shared with
# Super Admin → All Clubs → New Club, which creates the same kind of account
# (a club's Primary Club Admin) and must judge it by the same rules.
_EMAIL_RE = admin_identity.EMAIL_RE


class ValidateAdminRequest(BaseModel):
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    username: str = ""
    email: str = ""
    mobile_number: str = ""


async def _validate_admin_fields(db: AsyncSession, data: ValidateAdminRequest) -> dict:
    """The admin-details field checks, shared by the as-you-type validator
    below and the final /submit revalidation (Phase 8) — one set of rules,
    not two copies that could drift. The rules live in
    services/admin_identity.py so Super Admin → New Club (which creates the
    same kind of account) applies exactly the same ones; a mobile number is
    mandatory on this flow, since the registrant is the club's own admin and
    is being asked for their own number."""
    return await admin_identity.validate_admin_fields(
        db,
        first_name=data.first_name, last_name=data.last_name,
        display_name=data.display_name, username=data.username,
        email=data.email, mobile_number=data.mobile_number,
        require_mobile=True,
    )


@router.post("/validate-admin")
async def validate_admin(data: ValidateAdminRequest, db: AsyncSession = Depends(get_db)):
    """Validate-as-you-type for the admin-details step."""
    errors = await _validate_admin_fields(db, data)
    return {
        "valid": not errors,
        "errors": errors,
        "normalised": {
            "username": (data.username or "").strip().lower(),
            "email": (data.email or "").strip().lower(),
        },
    }


# ─── Step 3: email verification (Phase 6) ────────────────────────────────────
# Full OTP flow, not a stub — built now so a future public launch only needs UI
# wiring (see docs/self-serve-trial-onboarding-plan.md, Decision 5).

SEND_LIMIT = 5
SEND_WINDOW_SECONDS = 3600  # 1 hour — code generation + resend share this cap
VERIFY_MAX_FAILURES = 5
VERIFY_LOCKOUT_SECONDS = 15 * 60  # same threshold as the BetterSelect PIN check


class SendCodeRequest(BaseModel):
    email: str


@router.post("/verify-email/send")
async def send_verification_code(data: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """Send (or resend) a verification code. The same endpoint covers both —
    a resend and a "restart after changing email" are the same operation
    (issue a fresh code, superseding whatever was active for that email)."""
    email = (data.email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    rate_limit.enforce(
        f"ssvr:send:{email}", SEND_LIMIT, SEND_WINDOW_SECONDS,
        detail="Too many verification codes requested for this email. Try again later.",
    )

    try:
        await verification.start_verification(db, email)
    except RuntimeError as e:
        # This router is Super Admin-gated in this phase, so the caller is
        # already a trusted operator, not a public visitor — showing the real
        # provider error here is a diagnostic aid, not an information leak.
        # TIGHTEN BEFORE PUBLIC LAUNCH (see docs/self-serve-trial-onboarding-plan.md,
        # "go public" checklist): swap back to a generic message once this is
        # reachable by anyone other than a super admin.
        raise HTTPException(status_code=502, detail=f"Could not send the verification email: {e}")

    return {"sent": True}


class CheckCodeRequest(BaseModel):
    email: str
    code: str


@router.post("/verify-email/check")
async def check_verification_code(data: CheckCodeRequest, db: AsyncSession = Depends(get_db)):
    email = (data.email or "").strip().lower()
    code = (data.code or "").strip()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    lock_key = f"ssvr:verify:{email}"
    rate_limit.assert_not_locked(
        lock_key, VERIFY_MAX_FAILURES, VERIFY_LOCKOUT_SECONDS,
        detail="Too many incorrect attempts. Try again later or request a new code.",
    )

    outcome = await verification.check_code(db, email, code)

    if outcome in (verification.VerifyOutcome.OK, verification.VerifyOutcome.ALREADY_VERIFIED):
        rate_limit.clear_failures(lock_key)
        return {"verified": True}

    if outcome == verification.VerifyOutcome.EXPIRED:
        # About the caller's own code, not another account — safe to be specific.
        raise HTTPException(status_code=422, detail="This code has expired. Request a new one.")

    # NO_ACTIVE_CODE and INCORRECT get the same generic message — don't reveal
    # whether this email ever had a code issued (non-enumerating, per the plan).
    rate_limit.record_failure(lock_key, VERIFY_LOCKOUT_SECONDS)
    raise HTTPException(status_code=422, detail="Incorrect code.")


@router.get("/verify-email/status")
async def verification_status(email: str = "", db: AsyncSession = Depends(get_db)):
    email = (email or "").strip().lower()
    if not email:
        return {"verified": False}
    return {"verified": await verification.is_verified(db, email)}


# ─── Step 4: acknowledgements (Phase 7) ──────────────────────────────────────
# Versions match the "Last updated" dates on the public Terms/Privacy pages
# (frontend/src/pages/marketing/Terms.jsx, Privacy.jsx) — there's no shared
# version source today (those pages just hardcode the date), so this constant
# has to be kept in sync by hand whenever those pages change. BetterComms-
# specific marketing terms aren't included: module selection (which modules,
# including BetterAdmin/comms) doesn't happen until a later phase, so there's
# nothing to condition a comms-specific acknowledgement on yet.
TERMS_VERSION = "2026-06-09"
PRIVACY_VERSION = "2026-06-09"


class AcknowledgeRequest(BaseModel):
    email: str
    club_name: str
    accept_terms: bool = False
    accept_privacy: bool = False


@router.post("/acknowledge")
async def acknowledge(data: AcknowledgeRequest, background_tasks: BackgroundTasks,
                      request: Request, db: AsyncSession = Depends(get_db)):
    """Records ToS + Privacy acceptance. Both are mandatory — this endpoint
    only succeeds once every box is ticked, matching the source document's
    "required acknowledgements" list. IP is stored hashed
    (services/usage_tracker.hash_ip), same privacy-conscious approach
    login_attempts already uses — never the raw address."""
    email = (data.email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")

    club_name = (data.club_name or "").strip()
    if not club_name:
        raise HTTPException(status_code=422, detail="Club name is required")

    missing = []
    if not data.accept_terms:
        missing.append("Terms of Service")
    if not data.accept_privacy:
        missing.append("Privacy Policy")
    if missing:
        raise HTTPException(status_code=422, detail=f"Please accept: {', '.join(missing)}")

    accepted_at = datetime.now(timezone.utc)
    row = SelfServeAcknowledgement(
        id=_uuid.uuid4(),
        email=email,
        club_name=club_name,
        terms_version=TERMS_VERSION,
        privacy_version=PRIVACY_VERSION,
        accepted_at=accepted_at,
        ip_hash=hash_ip(client_ip(request)),
        user_agent=(request.headers.get("user-agent") or "")[:300] or None,
    )
    db.add(row)
    await db.commit()

    # A prospect who reached the Terms step has supplied a club name AND an
    # email — a real, contactable lead even if they never finish the wizard.
    # Ensure they're on the Sales Pipeline so a salesperson can follow up, not
    # just visible in the Meta Ads wizard-selection table. Best-effort and
    # backgrounded (its own session); a CRM hiccup never fails the acceptance.
    from app.services import crm as crm_service
    background_tasks.add_task(
        crm_service.sync_deal_for_wizard_lead,
        club_name=club_name, email=email,
    )

    return {
        "accepted": True,
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
        "accepted_at": accepted_at.isoformat(),
    }


# ─── Step 5: final submission (Phases 8-9) ────────────────────────────────────
# Password is collected here, not in Phase 4's admin-details step — deliberately
# deferred to immediately before submission (see that router comment) so it
# spends less time sitting in client state.
#
# ATOMICITY CAVEAT (read before touching this): _onboard_club_core (in
# organisations.py) calls upsert_organisation, which commits internally —
# pre-existing behaviour, out of scope to change here since it's shared with
# the ordinary Super Admin "New Club" / authenticated-user onboarding paths.
# That commit durably commits the WHOLE session, including the User row this
# handler creates earlier in the same request. So club+user creation is
# effectively atomic with each other (both land in that one commit), but the
# ClubMembership + primary-admin + module-trial step that follows is NOT
# covered by it — if that narrow window fails (a genuine DB outage; no
# external calls happen in it), the club and user already exist with no
# membership or trials attached. That failure path returns a 500 naming the
# org_id/user_id and explicitly says not to retry, since a retry would just
# hit "club already registered" against the very club the failed attempt
# created — it needs a human to finish the rest manually via existing Super
# Admin tooling. Given this whole router requires super_admin already and the
# failure mode needs an actual infra fault to trigger, that's judged
# proportionate for this phase rather than building compensating-transaction
# machinery for it.

# Union of the existing rule (POST /super/users: >= 10 chars) and the source
# document's minimum (upper + digit + special) — "use existing rules where
# stronger" cuts both ways when neither is a strict superset of the other.
# Password rule lives in services/password_policy.py — shared with the club-
# user invite accept flow (routers/auth.py) so the two can't drift apart.


class SubmitRequest(BaseModel):
    idempotency_key: str
    org_id: str
    name: str
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    username: str = ""
    email: str = ""
    mobile_number: str = ""
    password: str = ""
    confirm_password: str = ""
    modules: list[str] = []
    # First-touch ad attribution (frontend/src/lib/visitor.js getAttribution()) —
    # only ever populated by the public flow (routers/public_self_serve.py's
    # PublicSubmitRequest extends this with the same field name, so it just
    # flows straight through); the internal super-admin testing flow has none
    # to give and leaves it None. Used to classify the new platform deal's
    # Lead Source — see crm.lead_source_from_attribution.
    attribution: "dict | None" = None


@router.post("/submit")
async def submit(data: SubmitRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    key = (data.idempotency_key or "").strip()
    if not key:
        raise HTTPException(status_code=422, detail="Missing idempotency key")

    # Idempotent replay: a key already seen returns its stored outcome instead
    # of reprocessing — the guarantee that makes a double-click, refresh, or
    # network retry provably safe rather than a second club/user.
    existing_key = await db.get(SelfServeIdempotencyKey, key)
    if existing_key is not None:
        return {
            "status": existing_key.status,
            "org_id": str(existing_key.org_id) if existing_key.org_id else None,
            "user_id": str(existing_key.user_id) if existing_key.user_id else None,
            "replayed": True,
        }

    email = (data.email or "").strip().lower()

    org_id = _parse_uuid(data.org_id)
    if not org_id:
        raise HTTPException(status_code=422, detail="Invalid club id: pick a club from the search results")
    dup = await find_matching_organisation(db, org_id, data.name, include_archived=False)
    if dup:
        admin_label = await _primary_admin_label(db, dup.id)
        raise HTTPException(status_code=409, detail={
            "message": _duplicate_club_message((data.name or "").strip(), admin_label, dup.slug),
            "name": (data.name or "").strip(),
            "slug": dup.slug,
            "admin_label": admin_label,
        })
    if not await playhq_client.get_organisation(str(org_id)):
        raise HTTPException(status_code=404, detail="Club not found in the Cricket Australia data source")

    admin_errors = await _validate_admin_fields(db, ValidateAdminRequest(
        first_name=data.first_name, last_name=data.last_name, display_name=data.display_name,
        username=data.username, email=data.email, mobile_number=data.mobile_number,
    ))
    if admin_errors:
        raise HTTPException(status_code=422, detail={"errors": list(admin_errors.values())})

    if not email or not await verification.is_verified(db, email):
        raise HTTPException(status_code=422, detail="Email is not verified")

    ack = await db.execute(
        select(SelfServeAcknowledgement).where(SelfServeAcknowledgement.email == email)
        .order_by(SelfServeAcknowledgement.accepted_at.desc()).limit(1)
    )
    if ack.scalar_one_or_none() is None:
        raise HTTPException(status_code=422, detail="Acknowledgements have not been accepted")

    password_errors = password_policy.password_errors(data.password, data.confirm_password)
    if password_errors:
        raise HTTPException(status_code=422, detail={"errors": password_errors})

    # Every check passed. Create the account first (flush only, not committed
    # yet — see the atomicity caveat above): if this races against a
    # concurrent signup for the same username/email despite the pre-check,
    # the unique-constraint violation surfaces here, cleanly, before anything
    # else exists.
    username = (data.username or "").strip().lower()
    user = User(
        username=username,
        email=email,
        password_hash=bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode(),
        display_name=(data.display_name or "").strip(),
        first_name=(data.first_name or "").strip(),
        last_name=(data.last_name or "").strip(),
        mobile_number=(data.mobile_number or "").strip(),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="That username or email was just taken. Try again.")

    # Club creation + sync kickoff + marketing-directory link: the same
    # underlying logic the existing authenticated-user "onboard" flow uses
    # (organisations.py), not a parallel implementation. Commits internally
    # (see the atomicity caveat above) — this also durably commits the user
    # row created just above.
    from app.routers.organisations import _onboard_club_core
    org, run_id, name = await _onboard_club_core(
        db, background_tasks, str(org_id), data.name, auto_yearbooks=True,
    )

    # That internal commit leaves module_subscriptions unloaded on this now-
    # persistent org — the exact trap club_admin.py's create_club comment
    # warns about ("accessing the collection after a flush ... raises
    # MissingGreenlet"). Explicit refresh before ensure_core_subscription /
    # start_trial_billing touch it (same idiom as club_admin.py's patch_club).
    await db.refresh(org, attribute_names=["module_subscriptions"])

    requested_modules = sorted({m for m in (data.modules or []) if m in _SELECTABLE_MODULES})

    try:
        # upsert_organisation (services/sync.py) — shared with the ordinary
        # authenticated "onboard" flow — never sets is_active or slug, so a
        # brand-new org otherwise lands inactive with no public URL. Setting
        # both HERE, scoped to self-serve only, rather than in the shared
        # helper: a self-serve trial is meant to go live immediately, but
        # that's a deliberate call for THIS flow specifically, not something
        # to silently change for the shared onboard path's existing behaviour.
        org.is_active = True
        # How this club came to exist, on the club row itself (migration 225) —
        # the CRM deal is stamped from it below, and both trial_engagement's
        # staff-vs-club scoring and the setup wizard's auto-open read it. Set
        # here rather than inferred later, since nothing else can tell a club
        # that registered itself apart from one a super admin created for it.
        org.onboarding_method = "self_serve_trial"
        if not org.slug:
            org.slug = await _unique_slug(db, _slugify(name))
        # Real street address, for the Stripe Customer this club's first
        # checkout creates — automatic tax calculation needs one on file (see
        # _resolve_club_address's own docstring). Never overwrites an address
        # already on the row (a super admin's manual edit, or one this same
        # resolution already found on an earlier registration attempt).
        if not org.address_line1:
            addr = await _resolve_club_address(db, org_id=str(org_id), name=name)
            if addr:
                org.address_line1 = addr["line1"]
                org.suburb = addr["suburb"]
                org.state = addr["state"]
                org.postcode = addr["postcode"]
                org.country = addr["country"]
        # Registering a previously-archived club (the duplicate-check above
        # deliberately ignores archived matches, see find_matching_organisation)
        # brings it back — un-archiving is what "available to register again"
        # actually means once submit reaches this point and reuses the row.
        org.archived_at = None
        # A previously-archived club can carry an entire real billing history
        # on this same row (same CA org id, reused rather than duplicated) —
        # a prior real Stripe subscription/cancellation, and the org-level
        # subscription_status/renewal_date/billing_cycle a super admin last
        # left it at. None of that belongs to THIS registration: it's a brand
        # new 14-day trial, not a continuation. Reset it to the same blank
        # state a genuinely new org starts at (start_trial_billing below
        # already re-trials every module cleanly either way — this is the
        # org-level state that isn't touched by a per-module trial start).
        org.stripe_customer_id = None
        org.stripe_subscription_id = None
        org.subscription_status = "active"
        org.renewal_date = None
        org.billing_cycle = None
        # Likewise, any outstanding subscribe/trial/cancel request from the
        # club's previous life is stale — it was never actioned before the
        # club was archived, and re-showing it now (e.g. "subscribe
        # requested" next to a module that just started a brand new trial)
        # misrepresents this as a continuation of the old club rather than a
        # fresh signup.
        stale_requests = (await db.execute(
            select(ModuleActionRequest).where(
                ModuleActionRequest.organisation_id == org.id,
                ModuleActionRequest.status == "outstanding",
            )
        )).scalars().all()
        for stale in stale_requests:
            stale.status = "dismissed"
            stale.completed_at = datetime.now(timezone.utc)
        # Same story for discount-coupon redemptions: the "one redemption per
        # club, ever" unique slot (discount_coupon_redemptions) is still held
        # by whatever this row redeemed in its previous life, so a genuinely
        # fresh signup would get "Your club has already used this code" for
        # a code it's never actually used. Revoking (not deleting) frees the
        # slot back up the same way a Super Admin's manual revoke does,
        # keeping the audit trail intact.
        stale_redemptions = (await db.execute(
            select(DiscountCouponRedemption).where(
                DiscountCouponRedemption.organisation_id == org.id,
                DiscountCouponRedemption.status != "revoked",
            )
        )).scalars().all()
        for stale in stale_redemptions:
            stale.status = "revoked"

        db.add(ClubMembership(club_id=org.id, user_id=user.id, role="club_admin"))
        await db.flush()
        await ensure_primary_admin(db, org.id)

        # BetterStats is mandatory (always on, never a choice), but on THIS
        # flow it's still part of the "14 Day Free Trial" the club is
        # signing up for — it starts trialling on the same schedule as every
        # other module, not immediately Active, so the whole plan reads as
        # one consistent trial (matches the ordinary Super Admin "New Club"
        # flow's ensure_core_subscription for a club onboarded directly as a
        # real, paying customer — deliberately different here).
        default_days = await ps.get_default_trial_days(db)
        mod_subs.start_trial_billing(org, MODULE_CORE, days=default_days)
        for module_key in requested_modules:
            mod_subs.start_trial_billing(org, module_key, days=default_days)

        db.add(SelfServeIdempotencyKey(
            idempotency_key=key, email=email, status="completed",
            org_id=org.id, user_id=user.id,
        ))
        await db.commit()

        # Best-effort, backgrounded: land the club + registering admin in
        # Twenty as a Company/Contact/Lead/Opportunity immediately (per the
        # user's explicit call — a self-serve registration is the strongest
        # buying signal there is, stronger even than a direct "onboard my
        # club" enquiry, so it doesn't wait on the nightly refresh or a human
        # flipping Twenty's own createOpportunity field). Never raises;
        # a CRM hiccup can't undo the registration that already committed.
        from app.services import twenty_sync
        background_tasks.add_task(
            twenty_sync.push_self_serve_registration,
            org_id=org.id, org_name=name, contact_name=user.display_name,
            email=email, phone=user.mobile_number or None, modules=list(requested_modules),
        )
        # Same signal, BetterCricket's own pipeline: pin the local platform
        # deal to Trial / Self-Serve Trial onboarding method / $399 base value
        # (see crm.sync_self_serve_trial_deal's own docstring for why value
        # stays at the Stats base rather than every trialled module's price).
        # Deliberately a SEPARATE background task from the Twenty push above,
        # not nested inside it — push_self_serve_registration no-ops entirely
        # when Twenty isn't configured, and this local sync must not inherit
        # that gate.
        from app.services import crm as crm_service
        background_tasks.add_task(
            crm_service.sync_self_serve_trial_registration,
            org_id=org.id, org_name=name, contact_name=user.display_name,
            email=email, phone=user.mobile_number or None, attribution=data.attribution,
        )
    except Exception:
        logger.error(
            "self-serve registration: club %s / user %s were created but "
            "membership/module-trial linking failed — needs manual completion "
            "via existing Super Admin tooling, do not retry this submission",
            org.id, user.id, exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The club and account were created, but finishing setup failed. "
                f"Contact support with reference {org.id}/{user.id}. Don't "
                "retry, this needs manual completion."
            ),
        )

    return {
        "status": "completed",
        "org_id": str(org.id),
        "user_id": str(user.id),
        "run_id": str(run_id),
        "name": name,
        "modules": [MODULE_CORE, *requested_modules],
        "replayed": False,
    }


@router.post("/login-as/{user_id}")
async def login_as_registered_admin(user_id: str, response: Response, db: AsyncSession = Depends(get_db)):
    """Internal-testing convenience: lets the Super Admin operator who just ran
    a self-serve registration actually see what the new club admin sees,
    without a second browser/incognito window. Deliberately NOT wired into
    `/submit` itself — auto-setting the session cookie there would silently
    swap the operator's own `bs_session` for the new admin's the instant they
    register a test club, ending their super-admin session without asking.
    This is an explicit, separate action instead (mirrors `switch-club` being
    an explicit, visible action rather than an automatic side effect).

    Scoped tightly to accounts THIS flow created — a `SelfServeIdempotencyKey`
    row must reference the exact user id — so it can never become a general
    impersonation backdoor for arbitrary users.

    This is also the real "establish a session" primitive a future public
    self-serve flow will call automatically and unconditionally right after
    account creation (Decision 5: build the complete thing now, so going
    public later is wiring, not new backend work) — only the caller and the
    "is this OK to do silently" judgement change, not the session-minting
    logic itself."""
    uid = _parse_uuid(user_id)
    if not uid:
        raise HTTPException(status_code=422, detail="Invalid user id")
    key_row = await db.scalar(
        select(SelfServeIdempotencyKey).where(SelfServeIdempotencyKey.user_id == uid))
    if key_row is None:
        raise HTTPException(status_code=404, detail="This user wasn't created by self-serve trial registration")
    user = await db.get(User, uid)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.routers.auth import _build_me, create_session_token, set_session_cookie
    token = create_session_token(str(user.id))
    set_session_cookie(response, token)
    return await _build_me(user, db)
