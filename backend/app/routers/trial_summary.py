"""Better HQ > Reporting > Trial Summary. Super admins only, read only.
See services/trial_summary.py for who is listed and how each figure is read."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import trial_summary

router = APIRouter(prefix="/club-admin", tags=["trial-summary"])


@router.get("/super/trial-summary")
async def get_trial_summary(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every club that signed up or went on a trial: sign-up date and channel, modules on
    trial or paid, when the trial ends, and its own people's activity."""
    return await trial_summary.build_summary(db)
