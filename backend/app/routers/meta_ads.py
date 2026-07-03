"""Super-admin Meta Ads dashboard — BetterCricket's own ad spend/performance.

Cross-platform tooling (not club data), so gated by ``require_super_admin``,
same posture as the marketing club directory / KlubPro migration routers.
Reads a daily snapshot table by default (fast, no Meta round-trip on page
load); ``/refresh`` does a live pull and updates it on demand.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.config.settings import settings
from app.services import meta_ads
from app.services.meta_ads import MetaAdsError

router = APIRouter(prefix="/club-admin/meta-ads", tags=["meta-ads"])


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """Latest stored snapshot: campaign totals, per-ad rows, current recommendation."""
    data = await meta_ads.get_latest_summary(db)
    data["token_configured"] = settings.meta_ads_configured
    return data


@router.get("/history")
async def history(
    days: int = Query(14, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Daily series for the trend charts."""
    return {"days": await meta_ads.get_history(db, days), "token_configured": settings.meta_ads_configured}


@router.post("/refresh")
async def refresh(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """Run the snapshot pull now (Refresh now button) and return the fresh summary."""
    if not settings.meta_ads_configured:
        return {"error": {"kind": "not_configured", "message": "Meta access token is not configured."},
                "token_configured": False}
    try:
        await meta_ads.run_snapshot(db)
    except MetaAdsError as e:
        return {"error": {"kind": e.kind, "message": e.message}, "token_configured": True}
    data = await meta_ads.get_latest_summary(db)
    data["token_configured"] = True
    return data
