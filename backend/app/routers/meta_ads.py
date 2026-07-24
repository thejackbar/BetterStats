"""Super-admin Meta Ads dashboard — BetterCricket's own ad spend/performance.

Cross-platform tooling (not club data), so gated by ``require_super_admin``,
same posture as the marketing club directory / KlubPro migration routers.
Reads a daily snapshot table by default (fast, no Meta round-trip on page
load); ``/refresh`` does a live pull and updates it on demand.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, SelfServeIdempotencyKey, User, get_db
from app.routers.auth import require_super_admin
from app.config.settings import settings
from app.services import meta_ads
from app.services.meta_ads import MetaAdsError

router = APIRouter(prefix="/club-admin/meta-ads", tags=["meta-ads"])


class LeadAdjustmentIn(BaseModel):
    delta: int = Field(..., ge=-100000, le=100000)
    note: str | None = None


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


@router.get("/ad-history/{ad_id}")
async def ad_history(
    ad_id: str,
    days: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Per-ad daily trend for the drill-down chart when an ad is selected."""
    return {"days": await meta_ads.get_ad_history(db, ad_id, days), "token_configured": settings.meta_ads_configured}


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


@router.post("/leads/adjust")
async def adjust_leads(
    body: LeadAdjustmentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_super_admin),
):
    """Manually correct the Meta-reported lead count (+/-). Meta's own number
    is indicative only, so this is stored as a standalone delta and layered on
    top of the latest snapshot rather than overwriting it — see meta_ads.py."""
    if body.delta == 0:
        raise HTTPException(400, "delta must be non-zero")
    await meta_ads.add_lead_adjustment(db, body.delta, body.note, user.email)
    data = await meta_ads.get_latest_summary(db)
    data["token_configured"] = settings.meta_ads_configured
    return data


@router.get("/leads/adjustments")
async def leads_adjustments(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """Audit trail of manual lead-count corrections, newest first."""
    return {"adjustments": await meta_ads.get_lead_adjustments(db)}


@router.get("/registration-funnel")
async def registration_funnel(
    days: int = Query(meta_ads.CAMPAIGN_LENGTH_DAYS, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Step-by-step breakdown of the registration wizard itself (club
    selected → admin details → email verified → acknowledgements → submit →
    completed), filling in the gap between Meta's own Lead and
    CompleteRegistration events."""
    return {"funnel": await meta_ads.get_registration_step_funnel(db, days)}


@router.get("/selected-clubs")
async def selected_clubs(
    days: int = Query(meta_ads.CAMPAIGN_LENGTH_DAYS, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Names the clubs behind the registration wizard's "Club selected" count —
    the detail the step funnel (which only counts anonymous visitors) can't
    give. Merges the club captured on the selection beacon with the Terms-step
    acknowledgements and completed registrations, reporting the furthest step
    each club reached. See meta_ads.get_selected_clubs."""
    return await meta_ads.get_selected_clubs(db, days)


@router.get("/ad-signups")
async def ad_signups(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """Every club that registered itself through the public self-serve flow
    AND is attributed to one of THIS Meta campaign's own ads, joined with
    what it's since done (trial/paid modules) and its cached Twenty
    engagement score — "which ads produced our hottest leads" in one table.

    `signup_source == 'self_serve_ad'` on its own is NOT specific to Meta —
    it's set whenever getAttribution() saw ANY click signal, which an EDM
    (email) send's own UTM-tagged link also carries. Scoped the same way
    get_registration_count() scopes the KPI card's own "actual
    registrations" number: signup_attribution.utm_content has to match one
    of settings.meta_campaign_id's own ads, via
    meta_ads._current_campaign_utm_contents(). Without this an EDM-driven
    signup would show up on the Meta Ads page as if an ad produced it.

    The engagement score is the cached marketing_clubs value from the daily
    refresh (via the existing_org_id link), NOT a live _engagement() scan per
    row — and an ad signup can legitimately have no MarketingClub row at all
    (Twenty wasn't configured at registration time), so both club and score
    are nullable here and the UI shows "not yet scored".

    Archived clubs are excluded — same default as the main Club Directory
    (GET /club-admin/super/clubs). A super admin's own test signups get
    archived after verifying the flow works (the documented cleanup step),
    and this report exists to show real prospects, not test data."""
    from app.services.twenty_sync import _module_split

    utm_contents = meta_ads._current_campaign_utm_contents()

    orgs = (await db.execute(
        select(Organisation, MarketingClub.engagement_score, MarketingClub.engagement_scored_at)
        .outerjoin(MarketingClub, MarketingClub.existing_org_id == Organisation.id)
        .where(Organisation.signup_source.isnot(None), Organisation.archived_at.is_(None))
        .options(selectinload(Organisation.module_subscriptions))
    )).all()
    orgs = [
        (org, score, scored_at) for org, score, scored_at in orgs
        if (org.signup_attribution or {}).get("utm_content") in utm_contents
    ]

    # Registration timestamps come from the self-serve idempotency keys (the
    # org rows themselves carry no created_at).
    org_ids = [org.id for org, _s, _at in orgs]
    signed_up_at = {}
    if org_ids:
        for oid, ts in (await db.execute(
            select(SelfServeIdempotencyKey.org_id, func.min(SelfServeIdempotencyKey.created_at))
            .where(SelfServeIdempotencyKey.org_id.in_(org_ids))
            .group_by(SelfServeIdempotencyKey.org_id)
        )).all():
            signed_up_at[oid] = ts

    rows = []
    for org, score, scored_at in orgs:
        paid, trial, _renewals = _module_split(org)
        attribution = org.signup_attribution or {}
        ts = signed_up_at.get(org.id)
        rows.append({
            "org_id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "signed_up_at": ts.isoformat() if ts else None,
            "signup_source": org.signup_source,
            "utm_campaign": attribution.get("utm_campaign"),
            "utm_content": attribution.get("utm_content"),
            "utm_source": attribution.get("utm_source"),
            "click_source": attribution.get("click_source"),
            "landing_path": attribution.get("landing_path"),
            "trial_modules": trial,
            "paid_modules": paid,
            "converted_to_paid": bool(paid),
            "engagement_score": score,
            "engagement_scored_at": scored_at.isoformat() if scored_at else None,
        })

    # Hottest first; unscored rows sink below scored ones, newest signup wins ties.
    rows.sort(key=lambda r: (r["engagement_score"] is None, -(r["engagement_score"] or 0),
                             r["signed_up_at"] or ""), reverse=False)

    # Per-campaign rollup so the UI can put cost-per-signup next to the spend
    # figures the dashboard already holds (matched by campaign/source name).
    by_campaign: dict = {}
    for r in rows:
        key = r["utm_campaign"] or r["click_source"] or r["signup_source"]
        agg = by_campaign.setdefault(key, {"campaign": key, "signups": 0, "converted": 0, "scores": []})
        agg["signups"] += 1
        agg["converted"] += 1 if r["converted_to_paid"] else 0
        if r["engagement_score"] is not None:
            agg["scores"].append(r["engagement_score"])
    campaigns = [{
        "campaign": a["campaign"],
        "signups": a["signups"],
        "converted": a["converted"],
        "avg_engagement": round(sum(a["scores"]) / len(a["scores"])) if a["scores"] else None,
    } for a in by_campaign.values()]
    campaigns.sort(key=lambda c: -c["signups"])

    return {"rows": rows, "campaigns": campaigns}
