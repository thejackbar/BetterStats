"""Internal self-serve club trial registration (Super Admin-only in this phase).

See docs/self-serve-trial-onboarding-plan.md. Everything here sits behind the
``self_serve_registration_enabled`` platform flag (off by default) as well as
``require_super_admin`` — the flag hides the feature, it is not itself an
authorization boundary. This module currently only carries the modal-shell status
check; club search, registration and submission land in later phases.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.routers.auth import require_super_admin, require_self_serve_registration_enabled
from app.services import platform_settings as ps

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
