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

from app.models.db import Organisation, get_db
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
