"""Super-admin Meta Ads dashboard — BetterCricket's own ad spend/performance.

Cross-platform tooling (not club data), so gated by ``require_super_admin``,
same posture as the marketing club directory / KlubPro migration routers.
Reads a daily snapshot table by default (fast, no Meta round-trip on page
load); ``/refresh`` does a live pull and updates it on demand.
"""
from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

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


@router.get("/campaigns")
async def campaigns(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """List the ad account's campaigns for the picker, plus which one is active.
    The whole dashboard scopes to `active_campaign_id`; a super admin switches it
    via POST /campaign — stored in platform_settings, no .env edit or redeploy."""
    from app.services import platform_settings
    active = await platform_settings.get_active_meta_campaign_id(db)
    if not settings.meta_ads_configured:
        return {"campaigns": [], "active_campaign_id": active, "token_configured": False}
    try:
        camps = await meta_ads.list_campaigns()
    except MetaAdsError as e:
        return {"error": {"kind": e.kind, "message": e.message},
                "campaigns": [], "active_campaign_id": active, "token_configured": True}
    return {"campaigns": camps, "active_campaign_id": active, "token_configured": True}


class ActiveCampaignIn(BaseModel):
    campaign_id: str


@router.post("/campaign")
async def set_active_campaign(
    body: ActiveCampaignIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Point the dashboard at a different campaign. Stores the choice in
    platform_settings and returns the fresh summary for the newly-selected one."""
    from app.services import platform_settings
    try:
        await platform_settings.set_active_meta_campaign_id(db, body.campaign_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    data = await meta_ads.get_latest_summary(db)
    data["token_configured"] = settings.meta_ads_configured
    return data


class CountingSinceIn(BaseModel):
    since: str | None = None  # ISO 8601 datetime, or None/omitted to clear


@router.get("/counting-since")
async def counting_since(db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)):
    """The current "counting since" cutoff (platform_settings.
    meta_ads_counting_since) — data from before it is excluded from the
    on-site funnel/table numbers and Meta's own campaign insights (never
    from the "Free trial registrations" KPI, which always counts every real
    completed registration). Null means no cutoff (the default: lifetime
    numbers)."""
    from app.services import platform_settings
    return {"since": await platform_settings.get_meta_ads_since(db)}


@router.post("/counting-since")
async def set_counting_since(
    body: CountingSinceIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Set (or clear, by omitting `since`) the cutoff, then immediately
    re-pull Meta's own insights with the new date range (like Refresh now)
    so the KPI numbers reflect it right away instead of waiting for the next
    scheduled snapshot. A Meta pull failure here is non-fatal — the on-site
    funnel/table numbers (computed live on every page load) already respect
    the new cutoff regardless."""
    from app.services import platform_settings
    try:
        await platform_settings.set_meta_ads_since(db, body.since)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if settings.meta_ads_configured:
        try:
            await meta_ads.run_snapshot(db)
        except MetaAdsError:
            logger.exception("Meta Ads: snapshot re-pull after counting-since change failed")
    data = await meta_ads.get_latest_summary(db)
    data["token_configured"] = settings.meta_ads_configured
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


class HideSelectionIn(BaseModel):
    name: str


@router.post("/selected-clubs/hide")
async def hide_selected_club(
    body: HideSelectionIn,
    days: int = Query(meta_ads.CAMPAIGN_LENGTH_DAYS, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Flag a wizard-selected club as test noise, hiding it from the table
    above. A display-only tidy-up (stored in platform_settings, keyed by the
    normalised club name) — it never touches the Sales Pipeline; a Terms-step
    lead that already flowed into the pipeline stays there. Returns the fresh
    selected-clubs payload."""
    from app.services import platform_settings
    try:
        await platform_settings.hide_meta_selection(db, body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await meta_ads.get_selected_clubs(db, days)


@router.post("/selected-clubs/unhide")
async def unhide_selected_club(
    body: HideSelectionIn,
    days: int = Query(meta_ads.CAMPAIGN_LENGTH_DAYS, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Restore a club previously flagged as test noise. Returns the fresh
    selected-clubs payload."""
    from app.services import platform_settings
    await platform_settings.unhide_meta_selection(db, body.name)
    return await meta_ads.get_selected_clubs(db, days)


@router.get("/searched-clubs")
async def searched_clubs(
    days: int = Query(meta_ads.CAMPAIGN_LENGTH_DAYS, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Names the clubs visitors TYPED into the search box (whose search returned
    results) — the step before a club is clicked/selected. Surfaces the
    interest the "Clubs selected" table misses: a club searched but never
    selected. Each row flags whether it went on to be selected. See
    meta_ads.get_searched_clubs."""
    return await meta_ads.get_searched_clubs(db, days)


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
    registrations" number: signup_attribution has to match the CURRENT
    campaign via meta_ads._attribution_matches_campaign() (by utm_content or
    utm_campaign). Without this an EDM-driven signup would show up on the
    Meta Ads page as if an ad produced it.

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

    await meta_ads._use_active_campaign(db)

    orgs = (await db.execute(
        select(Organisation, MarketingClub.engagement_score, MarketingClub.engagement_scored_at)
        .outerjoin(MarketingClub, MarketingClub.existing_org_id == Organisation.id)
        .where(Organisation.signup_source.isnot(None), Organisation.archived_at.is_(None))
        .options(selectinload(Organisation.module_subscriptions))
    )).all()
    orgs = [
        (org, score, scored_at) for org, score, scored_at in orgs
        if meta_ads._attribution_matches_campaign(org.signup_attribution)
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
