"""Meta Marketing API client + recommendation logic for the Meta Ads HQ dashboard.

Reads BetterCricket's own ad account (platform-level, not club data) — the
"BC_AU_Traffic_ClubHistory_Jul2026" early-bird campaign. No SDK, plain httpx
against the Graph API. Every call is wrapped so a bad/expired token or a Meta
outage surfaces as a typed error on the HQ page instead of a 500.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = 20.0

# Ad -> destination map (§1 of the spec). Stable IDs; the live API response's
# ad_name/ad_id are preferred where available, this is the fallback label.
AD_DESTINATIONS = {
    "120249237210730121": {"name": "Ad1_EntireClubHistory", "destination": "betterat.cricket/applecross", "utm_content": "entire_club_history"},
    "120249238467140121": {"name": "Ad2_PlayerStory", "destination": "betterat.cricket/applecross", "utm_content": "every_player_story"},
    "120249238467150121": {"name": "Ad3_Analysis", "destination": "betterat.cricket/ (homepage)", "utm_content": "cricket_analysis"},
    "120249238467160121": {"name": "Ad4_Legacy", "destination": "betterat.cricket/ (homepage)", "utm_content": "club_legacy"},
}

_LEAD_ACTION_TYPES = {"lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead"}


class MetaAdsError(Exception):
    """Typed error so the router/page can show a specific message."""

    def __init__(self, kind: str, message: str):
        self.kind = kind  # "not_configured" | "invalid_token" | "rate_limited" | "other"
        self.message = message
        super().__init__(message)


def _base_url() -> str:
    return f"https://graph.facebook.com/{settings.meta_api_version}"


def _require_configured() -> None:
    if not settings.meta_ads_configured:
        raise MetaAdsError("not_configured", "Meta access token is not configured.")


async def _get(path: str, params: dict) -> dict:
    _require_configured()
    params = {**params, "access_token": settings.meta_access_token}
    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params=params)
    except httpx.HTTPError as e:
        raise MetaAdsError("other", f"Could not reach Meta: {e}") from e

    body: dict = {}
    try:
        body = resp.json()
    except ValueError:
        pass

    if resp.status_code != 200 or "error" in body:
        err = body.get("error", {})
        code = err.get("code")
        message = err.get("message") or f"HTTP {resp.status_code}"
        if resp.status_code == 401 or code in (190,):
            raise MetaAdsError("invalid_token", f"Meta token is invalid or expired: {message}")
        if code in (4, 17, 32, 613) or resp.status_code == 429:
            raise MetaAdsError("rate_limited", f"Meta API rate-limited: {message}")
        raise MetaAdsError("other", f"Meta API error: {message}")

    return body


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _action_value(actions: list | None, action_types: set[str]) -> float:
    if not actions:
        return 0.0
    total = 0.0
    for a in actions:
        if a.get("action_type") in action_types:
            total += _num(a.get("value"))
    return total


def _parse_row(row: dict) -> dict:
    """Normalise one Graph API insights row (campaign or ad level) into our shape."""
    actions = row.get("actions") or []
    cost_per_action = row.get("cost_per_action_type") or []

    spend = _num(row.get("spend"))
    impressions = _num(row.get("impressions"))
    link_clicks = _num(row.get("inline_link_clicks"))
    link_ctr = _num(row.get("inline_link_click_ctr"))
    lpv = _action_value(actions, {"landing_page_view"})
    leads = _action_value(actions, _LEAD_ACTION_TYPES)

    cost_per_lpv = None
    for c in cost_per_action:
        if c.get("action_type") == "landing_page_view":
            cost_per_lpv = _num(c.get("value"))
            break
    if cost_per_lpv is None and lpv > 0:
        cost_per_lpv = spend / lpv

    return {
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name"),
        "date_start": row.get("date_start"),
        "date_stop": row.get("date_stop"),
        "spend": round(spend, 2),
        "impressions": impressions,
        "link_clicks": link_clicks,
        "link_ctr": round(link_ctr, 4),
        "landing_page_views": lpv,
        "cost_per_lpv": round(cost_per_lpv, 2) if cost_per_lpv is not None else None,
        "leads": leads,
    }


async def fetch_campaign_totals() -> dict:
    """Campaign-level totals for the whole lifetime of the campaign."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "campaign",
        "fields": "spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{settings.meta_campaign_id}"]}}]',
        "date_preset": "maximum",
    })
    data = body.get("data") or []
    if not data:
        return _parse_row({})
    return _parse_row(data[0])


async def fetch_per_ad() -> list[dict]:
    """Per-ad totals (level=ad) for the campaign."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "ad",
        "fields": "ad_id,ad_name,spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{settings.meta_campaign_id}"]}}]',
        "date_preset": "maximum",
    })
    rows = [_parse_row(r) for r in (body.get("data") or [])]
    for r in rows:
        meta = AD_DESTINATIONS.get(r["ad_id"], {})
        r["name"] = r.get("ad_name") or meta.get("name") or r["ad_id"]
        r["destination"] = meta.get("destination")
        r["utm_content"] = meta.get("utm_content")
    return rows


async def fetch_daily_trend(days: int = 14) -> list[dict]:
    """One row per day, campaign level, for the trend charts."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "campaign",
        "fields": "spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{settings.meta_campaign_id}"]}}]',
        "date_preset": "maximum",
        "time_increment": 1,
    })
    rows = [_parse_row(r) for r in (body.get("data") or [])]
    rows.sort(key=lambda r: r.get("date_start") or "")
    if days:
        rows = rows[-days:]
    return rows


def compute_recommendation(campaign: dict) -> tuple[str, str]:
    """§6 recommendation rules. Returns (status, reason_text)."""
    spend = campaign.get("spend") or 0.0
    ctr = campaign.get("link_ctr") or 0.0  # already a percentage, e.g. 1.46
    cost_per_lpv = campaign.get("cost_per_lpv")

    if cost_per_lpv is None:
        return "watch", (
            "No landing page views recorded yet, so cost per LPV can't be judged. "
            "Too early to tell — let it run and check back after it starts delivering."
        )

    if ctr >= 1.2 and cost_per_lpv <= 1.50:
        if ctr >= 2.0 or cost_per_lpv <= 1.00:
            return "keep_going", (
                f"Link CTR is {ctr:.2f}% and cost per LPV is A${cost_per_lpv:.2f} — performing well, "
                "great territory. Keep going, nothing to change."
            )
        return "keep_going", (
            f"Link CTR is {ctr:.2f}% and cost per LPV is A${cost_per_lpv:.2f} — both healthy. "
            "Keep going, nothing to change."
        )

    if spend < 60:
        return "watch", (
            f"Link CTR is {ctr:.2f}% and cost per LPV is A${cost_per_lpv:.2f} — middling, but only "
            f"A${spend:.2f} has been spent so far. Too early to judge — let it run."
        )

    if ctr < 0.7 or cost_per_lpv > 1.50:
        return "action_needed", (
            f"After A${spend:.2f} spent, link CTR is {ctr:.2f}% and cost per LPV is A${cost_per_lpv:.2f} — "
            "underperforming. Review the creative and targeting."
        )

    return "watch", (
        f"Link CTR is {ctr:.2f}% and cost per LPV is A${cost_per_lpv:.2f} — middling. Keep watching "
        "as spend builds before making a call."
    )


def ad_status(ad: dict, all_ads: list[dict]) -> str:
    """§6 per-ad status chip: winner / laggard / on_track."""
    spend = ad.get("spend") or 0.0
    ctr = ad.get("link_ctr") or 0.0
    lpv = ad.get("landing_page_views") or 0.0

    others = [a for a in all_ads if a.get("ad_id") != ad.get("ad_id")]
    max_lpv = max((a.get("landing_page_views") or 0.0 for a in all_ads), default=0.0)
    if max_lpv > 0 and lpv == max_lpv and lpv > 0:
        return "winner"

    if spend > 20 and others:
        avg_other_ctr = sum((a.get("link_ctr") or 0.0) for a in others) / len(others)
        if ctr < avg_other_ctr * 0.6:
            return "laggard"

    return "on_track"


async def upsert_snapshot(db: AsyncSession, snapshot_date: date, level: str, row: dict,
                           recommendation: str | None = None, recommendation_status: str | None = None) -> None:
    await db.execute(text("""
        INSERT INTO meta_ad_snapshots
            (snapshot_date, level, ad_id, ad_name, spend, impressions, link_clicks,
             link_ctr, landing_page_views, cost_per_lpv, leads, recommendation, recommendation_status)
        VALUES
            (:snapshot_date, :level, :ad_id, :ad_name, :spend, :impressions, :link_clicks,
             :link_ctr, :landing_page_views, :cost_per_lpv, :leads, :recommendation, :recommendation_status)
        ON CONFLICT (snapshot_date, level, COALESCE(ad_id, ''))
        DO UPDATE SET
            ad_name = EXCLUDED.ad_name,
            spend = EXCLUDED.spend,
            impressions = EXCLUDED.impressions,
            link_clicks = EXCLUDED.link_clicks,
            link_ctr = EXCLUDED.link_ctr,
            landing_page_views = EXCLUDED.landing_page_views,
            cost_per_lpv = EXCLUDED.cost_per_lpv,
            leads = EXCLUDED.leads,
            recommendation = COALESCE(EXCLUDED.recommendation, meta_ad_snapshots.recommendation),
            recommendation_status = COALESCE(EXCLUDED.recommendation_status, meta_ad_snapshots.recommendation_status)
    """), {
        "snapshot_date": snapshot_date,
        "level": level,
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name") or row.get("name"),
        "spend": row.get("spend") or 0,
        "impressions": row.get("impressions") or 0,
        "link_clicks": row.get("link_clicks") or 0,
        "link_ctr": row.get("link_ctr") or 0,
        "landing_page_views": row.get("landing_page_views") or 0,
        "cost_per_lpv": row.get("cost_per_lpv"),
        "leads": row.get("leads") or 0,
        "recommendation": recommendation,
        "recommendation_status": recommendation_status,
    })


async def run_snapshot(db: AsyncSession) -> dict:
    """Pull current totals from Meta, compute the recommendation, upsert today's
    snapshot rows (campaign + each ad). Raises MetaAdsError on failure — callers
    decide whether to log-and-skip (scheduled job) or surface it (manual refresh)."""
    campaign = await fetch_campaign_totals()
    ads = await fetch_per_ad()
    status, reason = compute_recommendation(campaign)

    today = date.today()
    await upsert_snapshot(db, today, "campaign", campaign, reason, status)
    for ad in ads:
        await upsert_snapshot(db, today, "ad", ad)
    await db.commit()

    return {
        "campaign": campaign,
        "ads": ads,
        "recommendation": reason,
        "recommendation_status": status,
    }


async def get_leads_adjustment_total(db: AsyncSession) -> int:
    """Running sum of every manual reconciliation delta ever recorded."""
    total = (await db.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM meta_lead_adjustments"
    ))).scalar()
    return int(total or 0)


async def add_lead_adjustment(db: AsyncSession, delta: int, note: str | None, created_by_email: str | None) -> int:
    """Record a manual +/- correction to the Meta-reported lead count. Returns
    the new running total (does not touch ``meta_ad_snapshots.leads`` itself,
    so the next snapshot pull can't silently wipe the correction)."""
    await db.execute(text("""
        INSERT INTO meta_lead_adjustments (delta, note, created_by_email)
        VALUES (:delta, :note, :created_by_email)
    """), {"delta": delta, "note": (note or None), "created_by_email": created_by_email})
    await db.commit()
    return await get_leads_adjustment_total(db)


async def get_lead_adjustments(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Recent manual reconciliation entries, newest first — the audit trail
    behind the effective lead count."""
    rows = (await db.execute(text("""
        SELECT delta, note, created_by_email, created_at
        FROM meta_lead_adjustments
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"limit": limit})).mappings().all()
    return [
        {
            "delta": int(r["delta"]),
            "note": r["note"],
            "created_by_email": r["created_by_email"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def get_latest_summary(db: AsyncSession) -> dict:
    """Read back the most recent snapshot set (used for the fast page-load path,
    as opposed to /refresh which does a live pull)."""
    campaign_row = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign'
        ORDER BY snapshot_date DESC, created_at DESC
        LIMIT 1
    """))).mappings().first()

    adjustment = await get_leads_adjustment_total(db)

    if not campaign_row:
        return {"campaign": None, "ads": [], "recommendation": None,
                "recommendation_status": None, "last_updated": None,
                "leads_adjustment": adjustment}

    latest_date = campaign_row["snapshot_date"]
    ad_rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'ad' AND snapshot_date = :d
        ORDER BY spend DESC
    """), {"d": latest_date})).mappings().all()

    def _row_to_dict(r) -> dict:
        return {
            "ad_id": r["ad_id"],
            "ad_name": r["ad_name"],
            "spend": float(r["spend"]),
            "impressions": float(r["impressions"]),
            "link_clicks": float(r["link_clicks"]),
            "link_ctr": float(r["link_ctr"]),
            "landing_page_views": float(r["landing_page_views"]),
            "cost_per_lpv": float(r["cost_per_lpv"]) if r["cost_per_lpv"] is not None else None,
            "leads": float(r["leads"]),
        }

    campaign = _row_to_dict(campaign_row)
    campaign["leads_adjustment"] = adjustment
    campaign["leads_effective"] = max(0.0, campaign["leads"] + adjustment)
    campaign["cost_per_lead"] = (
        round(campaign["spend"] / campaign["leads_effective"], 2) if campaign["leads_effective"] > 0 else None
    )

    ads = [_row_to_dict(r) for r in ad_rows]
    for ad in ads:
        meta = AD_DESTINATIONS.get(ad["ad_id"], {})
        ad["name"] = ad.get("ad_name") or meta.get("name") or ad["ad_id"]
        ad["destination"] = meta.get("destination")
        ad["utm_content"] = meta.get("utm_content")
        ad["status"] = ad_status(ad, ads)
        ad["cost_per_lead"] = round(ad["spend"] / ad["leads"], 2) if ad["leads"] > 0 else None

    return {
        "campaign": campaign,
        "ads": ads,
        "recommendation": campaign_row["recommendation"],
        "recommendation_status": campaign_row["recommendation_status"],
        "last_updated": campaign_row["created_at"].isoformat() if campaign_row["created_at"] else None,
        "leads_adjustment": adjustment,
    }


async def get_history(db: AsyncSession, days: int = 14) -> list[dict]:
    """Daily campaign-level series for the trend charts, from stored snapshots."""
    since = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign' AND snapshot_date >= :since
        ORDER BY snapshot_date ASC
    """), {"since": since})).mappings().all()
    return [
        {
            "date": r["snapshot_date"].isoformat(),
            "spend": float(r["spend"]),
            "impressions": float(r["impressions"]),
            "link_clicks": float(r["link_clicks"]),
            "link_ctr": float(r["link_ctr"]),
            "landing_page_views": float(r["landing_page_views"]),
            "cost_per_lpv": float(r["cost_per_lpv"]) if r["cost_per_lpv"] is not None else None,
            "leads": float(r["leads"]),
        }
        for r in rows
    ]
