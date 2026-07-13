"""Internal self-serve club trial registration (Super Admin-only in this phase).

See docs/self-serve-trial-onboarding-plan.md. Everything here sits behind the
``self_serve_registration_enabled`` platform flag (off by default) as well as
``require_super_admin`` — the flag hides the feature, it is not itself an
authorization boundary. Registration and submission land in later phases.
"""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, User, get_db
from app.routers.auth import require_super_admin, require_self_serve_registration_enabled
from app.services import platform_settings as ps
from app.services import playhq_client
from app.services.sync import _parse_uuid, find_matching_organisation

# Both guards apply to every route in this router, present and future: the flag
# check alone is not an authorization boundary (see require_self_serve_registration_
# enabled's docstring), so it always travels paired with require_super_admin.
router = APIRouter(
    prefix="/self-serve-trial",
    tags=["self-serve-trial"],
    dependencies=[Depends(require_super_admin), Depends(require_self_serve_registration_enabled)],
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


@router.get("/search")
async def search_clubs(q: str = "", db: AsyncSession = Depends(get_db)):
    """Club search for step 1 of the registration modal. Reuses the same
    authoritative Grassroots/PlayHQ lookup the existing Super Admin "New Club"
    search calls (playhq_client.search_organisations) — same minimum-length and
    empty-query handling as GET /organisations/search.

    Each result is annotated with ``already_registered``, using the same
    three-layer id/playhq_id/name match already used to guard club creation
    against duplicates (find_matching_organisation), so an operator can see a
    club is taken before attempting to register it — without exposing anything
    about the existing club beyond that fact (no admin/contact details)."""
    if not q or len(q.strip()) < 2:
        return []
    results = await playhq_client.search_organisations(q.strip())
    out = []
    for org in results:
        org_id = _parse_uuid(str(org.get("id") or ""))
        existing = await find_matching_organisation(db, org_id, org.get("name") or "")
        out.append({**org, "already_registered": existing is not None})
    return out


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
        raise HTTPException(status_code=422, detail="Invalid club id — pick a club from the search results")

    name = (data.name or "").strip()
    existing = await find_matching_organisation(db, org_id, name)
    if existing:
        raise HTTPException(status_code=409, detail="This club has already been registered in BetterCricket.")

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

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# AU mobile: 04xxxxxxxx, +614xxxxxxxx or 614xxxxxxxx, spaces/dashes ignored.
_AU_MOBILE_RE = re.compile(r"^(\+?61|0)4\d{8}$")
# Generic international fallback: a leading + and 8-15 digits — the codebase
# has no phone-validation library anywhere (Player.phone is stored as free text,
# see routers/availability.py's phone_last4), so this is a light sanity check,
# not a claim of full E.164 validation.
_INTL_MOBILE_RE = re.compile(r"^\+\d{8,15}$")


def _mobile_valid(raw: str) -> bool:
    compact = re.sub(r"[\s-]", "", raw or "")
    return bool(_AU_MOBILE_RE.match(compact) or _INTL_MOBILE_RE.match(compact))


class ValidateAdminRequest(BaseModel):
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    username: str = ""
    email: str = ""
    mobile_number: str = ""


@router.post("/validate-admin")
async def validate_admin(data: ValidateAdminRequest, db: AsyncSession = Depends(get_db)):
    """Validate-as-you-type for the admin-details step. Reuses the exact
    username rules (lowercase, 3-32 chars, uniqueness) the existing
    POST /super/users already enforces.

    Email: format-checked, then checked against existing users and BLOCKED if
    already taken (Phase 5, see docs/self-serve-trial-onboarding-plan.md Decision
    14). The source document wanted this to link an existing admin to a second
    club instead — but club_memberships.uq_membership_one_per_user (a user can
    have at most one membership, ever) and the global uniqueness of users.email
    make that a schema change, not a form feature. Building it properly needs a
    club-switcher for ordinary club admins (mirroring the super-admin-only
    active_club_id pattern) and a re-audit of every route that assumes one
    membership per user — explicitly out of scope here. This blocks rather than
    silently allowing a broken multi-club state, and does not reveal which
    club(s) the existing account holds (no verification has happened yet)."""
    errors = {}

    if not (data.first_name or "").strip():
        errors["first_name"] = "First name is required"
    if not (data.last_name or "").strip():
        errors["last_name"] = "Last name is required"
    if not (data.display_name or "").strip():
        errors["display_name"] = "Preferred display name is required"

    username = (data.username or "").strip().lower()
    if not username or len(username) < 3 or len(username) > 32:
        errors["username"] = "Username must be 3-32 characters"
    else:
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            errors["username"] = "Username already taken"

    email = (data.email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        errors["email"] = "Enter a valid email address"
    else:
        existing_user = await db.execute(select(User).where(User.email == email))
        if existing_user.scalar_one_or_none():
            errors["email"] = (
                "This email already belongs to a BetterCricket account. Self-serve "
                "registration doesn't yet support adding an existing admin to a "
                "second club — email cricket@bettersports.com.au for help."
            )

    mobile = (data.mobile_number or "").strip()
    if not mobile or not _mobile_valid(mobile):
        errors["mobile_number"] = "Enter a valid Australian mobile number, or an international number starting with +"

    return {
        "valid": not errors,
        "errors": errors,
        "normalised": {"username": username, "email": email},
    }
