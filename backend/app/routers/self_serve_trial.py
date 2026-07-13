"""Internal self-serve club trial registration (Super Admin-only in this phase).

See docs/self-serve-trial-onboarding-plan.md. Everything here sits behind the
``self_serve_registration_enabled`` platform flag (off by default) as well as
``require_super_admin`` — the flag hides the feature, it is not itself an
authorization boundary. Registration and submission land in later phases.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
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
