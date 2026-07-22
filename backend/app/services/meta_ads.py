"""Meta Marketing API client + recommendation logic for the Meta Ads HQ dashboard.

Reads BetterCricket's own ad account (platform-level, not club data) — the
campaign in settings.meta_campaign_id (currently "BC_AU_SelfServe_Aug2026",
the self-serve trial campaign; the Jul 2026 early-bird was the first). No SDK, plain httpx
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
# `campaign_id` lets get_registration_count() work out which utm_content tags
# belong to the CURRENT campaign (settings.meta_campaign_id) without a second
# round-trip — see that function.
AD_DESTINATIONS = {
    # BC_AU_SelfServe_Aug2026 — every ad lands on /trial; utm_content is the
    # same tag the ad-signups report groups by (see routers/meta_ads.py).
    "120249908493850121": {"campaign_id": "120249890918010121", "name": "Ad1_SelfServe_StaticShowcase", "destination": "betterat.cricket/trial", "utm_content": "static_showcase_full"},
    "120249908396070121": {"campaign_id": "120249890918010121", "name": "Ad2_SelfServe_SimpleCTA", "destination": "betterat.cricket/trial", "utm_content": "static_simple_cta"},
    "120249892616050121": {"campaign_id": "120249890918010121", "name": "Ad3_SelfServe_StaticShowcase_RTG", "destination": "betterat.cricket/trial", "utm_content": "static_showcase_rtg"},
    "120249892619080121": {"campaign_id": "120249890918010121", "name": "Ad4_SelfServe_SimpleCTA_RTG", "destination": "betterat.cricket/trial", "utm_content": "static_simple_rtg"},
    # BC_AU_Traffic_ClubHistory_Jul2026 (finished) — kept so old snapshots still label.
    "120249237210730121": {"campaign_id": "120249237210710121", "name": "Ad1_EntireClubHistory", "destination": "betterat.cricket/applecross", "utm_content": "entire_club_history"},
    "120249238467140121": {"campaign_id": "120249237210710121", "name": "Ad2_PlayerStory", "destination": "betterat.cricket/applecross", "utm_content": "every_player_story"},
    "120249238467150121": {"campaign_id": "120249237210710121", "name": "Ad3_Analysis", "destination": "betterat.cricket/ (homepage)", "utm_content": "cricket_analysis"},
    "120249238467160121": {"campaign_id": "120249237210710121", "name": "Ad4_Legacy", "destination": "betterat.cricket/ (homepage)", "utm_content": "club_legacy"},
}

# The self-serve campaign optimises for CompleteRegistration (a finished
# trial signup), so registrations count as conversions alongside classic
# leads — one indicative Meta-side number. It's kept only as a reference
# figure now (campaign["leads"]) — the authoritative "did someone actually
# register for the trial" count is get_registration_count() below, which
# reads our own ad-signups ground truth (organisations.signup_attribution)
# instead of trusting Meta's action-type rollup, which conflates reaching
# the trial form (a Lead) with actually finishing it (a CompleteRegistration).
_LEAD_ACTION_TYPES = {
    "lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead",
    "complete_registration", "offsite_conversion.fb_pixel_complete_registration",
}

# Single source of truth for pacing/insights maths — the dashboard reads
# these back from get_latest_summary() rather than the frontend hardcoding
# its own copy (that drifted once already, see the campaign-budget line on
# the KPI card before this file owned it).
CAMPAIGN_BUDGET_AUD = 520.0
CAMPAIGN_LENGTH_DAYS = 30


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


async def fetch_ad_daily_trend(days: int = 30) -> list[dict]:
    """One row per ad per day (level=ad, time_increment=1) — TRUE daily
    breakdowns from Meta, not the cumulative-to-date totals fetch_per_ad
    returns. Powers the per-ad drill-down trend chart (get_ad_history)."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "ad",
        "fields": "ad_id,ad_name,spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{settings.meta_campaign_id}"]}}]',
        "date_preset": "maximum",
        "time_increment": 1,
    })
    rows = [_parse_row(r) for r in (body.get("data") or [])]
    rows.sort(key=lambda r: (r.get("date_start") or "", r.get("ad_id") or ""))
    if days:
        keep_dates = set(sorted({r.get("date_start") for r in rows if r.get("date_start")})[-days:])
        rows = [r for r in rows if r.get("date_start") in keep_dates]
    return rows


def _parse_insights_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def ad_note(ad: dict, all_ads: list[dict]) -> str:
    """One-line, plain-English explanation for an ad's status chip — so a
    reader never has to reverse-engineer *why* a badge says what it says."""
    spend = ad.get("spend") or 0.0
    status = ad.get("status")
    cost_per_lpv = ad.get("cost_per_lpv")
    lpv = ad.get("landing_page_views") or 0.0

    if spend < 3:
        return "Too little spend yet to judge. Give it more time before acting on it."

    if status == "winner":
        if cost_per_lpv:
            return f"Best landing-page reach for its spend so far (${cost_per_lpv:.2f} per view). Keep it running."
        return "Getting the most landing page views of the set so far. Keep it running."

    if status == "laggard":
        others = [a for a in all_ads if a.get("ad_id") != ad.get("ad_id") and a.get("cost_per_lpv")]
        if others and cost_per_lpv:
            best = min(others, key=lambda a: a["cost_per_lpv"])
            mult = cost_per_lpv / best["cost_per_lpv"] if best["cost_per_lpv"] else None
            if mult and mult > 1.1:
                return (
                    f"Costing {mult:.1f}x more per landing page view than {best.get('name', 'your best ad')}. "
                    "Consider pausing it or refreshing the creative."
                )
        return "Click-through rate is well behind the rest of the set. Worth a look."

    if lpv == 0 and spend >= 3:
        return "Spending but nobody has reached the landing page yet. Check the creative and targeting."

    return "Performing in line with the rest of the campaign. No action needed."


def compute_funnel(campaign: dict) -> list[dict]:
    """Ordered funnel stages, impressions through to a completed trial
    registration, each carrying what % of the top and of the PREVIOUS stage
    it represents — the numbers the KPI cards show individually, laid out so
    the drop-off at each step is visible without anyone computing a ratio."""
    stages_raw = [
        ("impressions", "Impressions", campaign.get("impressions") or 0),
        ("link_clicks", "Link clicks", campaign.get("link_clicks") or 0),
        ("landing_page_views", "Landing page views", campaign.get("landing_page_views") or 0),
        ("leads", "Started registering (Meta-reported)", campaign.get("leads") or 0),
        ("registrations", "Completed registrations", campaign.get("registrations") or 0),
    ]
    top = stages_raw[0][2] or 0
    stages: list[dict] = []
    prev: float | None = None
    for key, label, value in stages_raw:
        pct_of_top = round(100 * value / top, 1) if top else 0.0
        pct_of_prev = 100.0 if prev is None else (round(100 * value / prev, 1) if prev else 0.0)
        stages.append({
            "key": key, "label": label, "value": value,
            "pct_of_top": pct_of_top, "pct_of_prev": pct_of_prev,
        })
        prev = value
    return stages


# Ordered checkpoints the public registration wizard beacons through (see
# routers/public_self_serve.py FUNNEL_STEPS, which this must stay in sync
# with — each key here must also be in that allowlist or its beacon 422s).
REGISTRATION_STEP_ORDER = [
    ("club_prepared", "Club selected"),
    ("admin_details_completed", "Admin details completed"),
    ("email_code_sent", "Verification code sent"),
    ("email_verified", "Email verified"),
    ("acknowledgements_accepted", "Terms & privacy accepted"),
    ("submit_attempted", "Submit attempted"),
    ("registration_completed", "Registration completed"),
]


async def get_registration_step_funnel(db: AsyncSession, days: int = CAMPAIGN_LENGTH_DAYS) -> list[dict]:
    """In-app breakdown of WHERE within the registration wizard visitors drop
    off — the detail Meta's own reporting can't give us, since it only ever
    sees a Lead (fired at the very first step) and a CompleteRegistration
    (fired only on a fully successful last step). Counts distinct visitors
    reaching each step (see public_self_serve.py's /track-step beacon and
    SelfServeTrialModal.jsx's trackFunnelStep calls), same
    key/label/value/pct_of_top/pct_of_prev shape as compute_funnel() so the
    frontend can reuse the same FunnelChart component."""
    rows = (await db.execute(text("""
        SELECT route, COUNT(DISTINCT visitor_id) AS n
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND visitor_id IS NOT NULL
        GROUP BY route
    """), {"days": days})).mappings().all()
    counts = {r["route"]: int(r["n"]) for r in rows}

    top = counts.get(REGISTRATION_STEP_ORDER[0][0], 0)
    stages: list[dict] = []
    prev: int | None = None
    for key, label in REGISTRATION_STEP_ORDER:
        value = counts.get(key, 0)
        pct_of_top = round(100 * value / top, 1) if top else 0.0
        pct_of_prev = 100.0 if prev is None else (round(100 * value / prev, 1) if prev else 0.0)
        stages.append({
            "key": key, "label": label, "value": value,
            "pct_of_top": pct_of_top, "pct_of_prev": pct_of_prev,
        })
        prev = value
    return stages


def build_insights(campaign: dict, ads: list[dict], daily_history: list[dict],
                    campaign_budget: float, campaign_length_days: int) -> list[dict]:
    """Short, severity-ordered headlines on how the campaign is actually
    going, so a reader never has to interpret the raw KPI numbers themselves.
    Deliberately terse (one line of detail, not a paragraph) and only fires
    on something worth a glance — nothing "always on" here, so an empty list
    is a valid, good result. Each item is {severity, title, detail}; severity
    is critical / warning / info / good, list returned sorted worst-first."""
    insights: list[dict] = []

    spend = campaign.get("spend") or 0.0
    impressions = campaign.get("impressions") or 0.0
    link_clicks = campaign.get("link_clicks") or 0.0
    lpv = campaign.get("landing_page_views") or 0.0
    leads = campaign.get("leads") or 0.0
    registrations = campaign.get("registrations") or 0

    # Budget pacing — from REAL daily spend (daily_history is the
    # level='campaign_daily' series), not the lifetime-to-date campaign
    # total, so a short burst of higher spend can't be misread as the
    # steady-state rate.
    spend_days = {d["date"] for d in daily_history if (d.get("spend") or 0) > 0}
    if campaign_budget and spend_days:
        daily_rate = spend / len(spend_days)
        projected = daily_rate * campaign_length_days
        if projected > campaign_budget * 1.15:
            over_pct = round((projected / campaign_budget - 1) * 100)
            insights.append({
                "severity": "warning",
                "title": "Overspending the budget pace",
                "detail": f"On track for ~${projected:.0f} of ${campaign_budget:.0f} by day {campaign_length_days} ({over_pct}% over). Trim spend or pause the weaker ads.",
            })
        elif projected < campaign_budget * 0.7 and len(spend_days) >= 2:
            insights.append({
                "severity": "info",
                "title": "Under-pacing the budget",
                "detail": f"On track for only ~${projected:.0f} of ${campaign_budget:.0f} by day {campaign_length_days}. Room to spend more if the ads below are working.",
            })

    # Funnel bottlenecks — where the drop-off actually hurts.
    if impressions >= 500 and link_clicks / impressions < 0.005:
        insights.append({
            "severity": "critical",
            "title": "Very few people are clicking through",
            "detail": f"Just {100 * link_clicks / impressions:.2f}% of impressions click ({link_clicks:.0f} of {impressions:.0f}). Try a different creative or narrow the audience.",
        })
    if link_clicks >= 10 and lpv / link_clicks < 0.5:
        insights.append({
            "severity": "warning",
            "title": "Clicks aren't reaching the landing page",
            "detail": f"Only {100 * lpv / link_clicks:.0f}% of link clicks become a landing page view. Check /trial loads fast on mobile.",
        })
    if lpv >= 5 and leads == 0:
        insights.append({
            "severity": "warning",
            "title": "Landing page traffic isn't converting",
            "detail": f"{lpv:.0f} people reached the trial page, nobody's picked a club yet. Check the call-to-action and club search.",
        })
    if leads >= 2 and registrations == 0 and spend >= 15:
        # Small sample by design: Meta's own Lead count here is already
        # flagged elsewhere as unstable at low volume, and the self-serve
        # flow (email OTP included) is proven working through other
        # channels, so don't jump to "the flow is broken" on a couple of
        # ad clicks. Only escalate to critical once there's enough volume
        # that a genuine block would actually show up as a pattern.
        small_sample = leads < 8
        insights.append({
            "severity": "warning" if small_sample else "critical",
            "title": "Leads aren't turning into registrations",
            "detail": (
                f"{leads:.0f} people picked a club, {registrations} finished registering. Too small a "
                "sample to call a problem yet, worth watching as it builds up."
                if small_sample else
                f"{leads:.0f} people picked a club, {registrations} finished registering. The flow works "
                "elsewhere, so try a real test signup from a Meta ad click to see where it drops off."
            ),
        })

    # Best vs worst spending ad.
    spending_ads = [a for a in ads if (a.get("spend") or 0) >= 3 and a.get("cost_per_lpv")]
    if len(spending_ads) >= 2:
        best = min(spending_ads, key=lambda a: a["cost_per_lpv"])
        worst = max(spending_ads, key=lambda a: a["cost_per_lpv"])
        if best["ad_id"] != worst["ad_id"] and worst["cost_per_lpv"] > best["cost_per_lpv"] * 1.8:
            insights.append({
                "severity": "info",
                "title": f"{best['name']} is your most efficient ad",
                "detail": f"${best['cost_per_lpv']:.2f} vs ${worst['cost_per_lpv']:.2f} per view for {worst['name']}. Consider shifting budget its way.",
            })

    severity_order = {"critical": 0, "warning": 1, "info": 2, "good": 3}
    insights.sort(key=lambda i: severity_order.get(i["severity"], 9))
    return insights


async def upsert_snapshot(db: AsyncSession, snapshot_date: date, level: str, row: dict,
                           recommendation: str | None = None, recommendation_status: str | None = None) -> None:
    """Stamped with the CURRENT settings.meta_campaign_id (migration 162) —
    the conflict target includes campaign_id, so a campaign switch on the
    same calendar day writes its own row instead of colliding with
    whatever the previous campaign already wrote for today."""
    await db.execute(text("""
        INSERT INTO meta_ad_snapshots
            (snapshot_date, level, ad_id, ad_name, campaign_id, spend, impressions, link_clicks,
             link_ctr, landing_page_views, cost_per_lpv, leads, recommendation, recommendation_status)
        VALUES
            (:snapshot_date, :level, :ad_id, :ad_name, :campaign_id, :spend, :impressions, :link_clicks,
             :link_ctr, :landing_page_views, :cost_per_lpv, :leads, :recommendation, :recommendation_status)
        ON CONFLICT (snapshot_date, level, COALESCE(ad_id, ''), COALESCE(campaign_id, ''))
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
        "campaign_id": settings.meta_campaign_id,
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

    # TRUE (non-cumulative) daily breakdowns, stored under their own levels
    # ('campaign'/'ad' above are lifetime-to-date-as-of-today totals, needed
    # for the KPI cards — plotting THOSE on a "per day" trend chart would
    # show a cumulative curve mislabeled as daily). Best-effort: a transient
    # failure here just leaves the trend charts one day stale, it shouldn't
    # fail a snapshot that otherwise succeeded.
    try:
        for row in await fetch_daily_trend(days=CAMPAIGN_LENGTH_DAYS + 5):
            d = _parse_insights_date(row.get("date_start"))
            if d:
                await upsert_snapshot(db, d, "campaign_daily", row)
        for row in await fetch_ad_daily_trend(days=CAMPAIGN_LENGTH_DAYS + 5):
            d = _parse_insights_date(row.get("date_start"))
            if d:
                await upsert_snapshot(db, d, "ad_daily", row)
    except MetaAdsError:
        logger.exception("Meta Ads: daily-trend snapshot pull failed")

    await db.commit()

    return {
        "campaign": campaign,
        "ads": ads,
        "recommendation": reason,
        "recommendation_status": status,
    }


async def get_leads_adjustment_total(db: AsyncSession) -> int:
    """Running sum of every manual reconciliation delta recorded against the
    CURRENT campaign (settings.meta_campaign_id) — scoped since migration 162
    so a correction made against a previous campaign can't keep inflating or
    deflating a later one's numbers forever."""
    total = (await db.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM meta_lead_adjustments WHERE campaign_id = :campaign_id"
    ), {"campaign_id": settings.meta_campaign_id})).scalar()
    return int(total or 0)


async def add_lead_adjustment(db: AsyncSession, delta: int, note: str | None, created_by_email: str | None) -> int:
    """Record a manual +/- correction to the Meta-reported lead count, tagged
    to the current campaign. Returns the new running total (does not touch
    ``meta_ad_snapshots.leads`` itself, so the next snapshot pull can't
    silently wipe the correction)."""
    await db.execute(text("""
        INSERT INTO meta_lead_adjustments (delta, note, created_by_email, campaign_id)
        VALUES (:delta, :note, :created_by_email, :campaign_id)
    """), {"delta": delta, "note": (note or None), "created_by_email": created_by_email,
           "campaign_id": settings.meta_campaign_id})
    await db.commit()
    return await get_leads_adjustment_total(db)


async def get_lead_adjustments(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Recent manual reconciliation entries for the CURRENT campaign, newest
    first — the audit trail behind the effective lead count."""
    rows = (await db.execute(text("""
        SELECT delta, note, created_by_email, created_at
        FROM meta_lead_adjustments
        WHERE campaign_id = :campaign_id
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"campaign_id": settings.meta_campaign_id, "limit": limit})).mappings().all()
    return [
        {
            "delta": int(r["delta"]),
            "note": r["note"],
            "created_by_email": r["created_by_email"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


def _current_campaign_utm_contents() -> set[str]:
    """utm_content tags of every ad AD_DESTINATIONS maps to the CURRENT
    campaign (settings.meta_campaign_id) — how get_registration_count() ties
    a real signup back to this specific Meta campaign rather than any other
    campaign (an EDM send, organic, a past campaign) that also happens to
    carry a utm_campaign tag."""
    return {
        meta["utm_content"]
        for meta in AD_DESTINATIONS.values()
        if meta.get("campaign_id") == settings.meta_campaign_id and meta.get("utm_content")
    }


async def get_registration_count(db: AsyncSession) -> int:
    """Real, completed free-trial registrations attributed to the CURRENT
    Meta campaign — ground truth from our own DB (organisations.
    signup_attribution, migration 161), not Meta's self-reported Lead/
    CompleteRegistration action counts. Those actions fire the moment a
    prospect reaches the trial form (a Lead) or completes it (a
    CompleteRegistration) and can double-count across the pixel/CAPI
    action-type split (see the "2 conversions" investigation) — they also
    can't tell a Meta-driven signup apart from one that came in through a
    different campaign (an EDM send, a "national-launch" push, organic
    traffic) that happens to carry its own utm tags. A club only counts here
    if its own signup_attribution.utm_content matches one of THIS campaign's
    ads, archived test signups are excluded (same default as the ad-signups
    report and the main Club Directory)."""
    utm_contents = _current_campaign_utm_contents()
    if not utm_contents:
        return 0
    count = (await db.execute(text("""
        SELECT COUNT(*) FROM organisations
        WHERE signup_source IS NOT NULL
          AND archived_at IS NULL
          AND signup_attribution->>'utm_content' = ANY(:utm_contents)
    """), {"utm_contents": list(utm_contents)})).scalar()
    return int(count or 0)


async def get_latest_summary(db: AsyncSession) -> dict:
    """Read back the most recent snapshot set for the CURRENT campaign (used
    for the fast page-load path, as opposed to /refresh which does a live
    pull). Scoped by campaign_id since migration 162 — without it, the most
    recent row could belong to a previous campaign's last snapshot before it
    was switched off, or (worse) a stale row for today under the old
    campaign could shadow the new one's."""
    campaign_row = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign' AND campaign_id = :campaign_id
        ORDER BY snapshot_date DESC, created_at DESC
        LIMIT 1
    """), {"campaign_id": settings.meta_campaign_id})).mappings().first()

    adjustment = await get_leads_adjustment_total(db)

    if not campaign_row:
        return {"campaign": None, "ads": [], "recommendation": None,
                "recommendation_status": None, "last_updated": None,
                "leads_adjustment": adjustment, "campaign_budget": CAMPAIGN_BUDGET_AUD,
                "campaign_length_days": CAMPAIGN_LENGTH_DAYS, "insights": []}

    latest_date = campaign_row["snapshot_date"]
    ad_rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'ad' AND campaign_id = :campaign_id AND snapshot_date = :d
        ORDER BY spend DESC
    """), {"campaign_id": settings.meta_campaign_id, "d": latest_date})).mappings().all()

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

    registrations = await get_registration_count(db)

    campaign = _row_to_dict(campaign_row)
    campaign["leads_adjustment"] = adjustment
    campaign["registrations"] = registrations
    campaign["leads_effective"] = max(0.0, registrations + adjustment)
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
        ad["note"] = ad_note(ad, ads)

    # Used for both the funnel/pacing insights below AND the default trend
    # chart window — a fixed lookback covering the whole campaign length so
    # pacing maths isn't skewed by whatever `days` window the trend charts
    # happen to be showing at the time.
    daily_history = await get_history(db, days=CAMPAIGN_LENGTH_DAYS + 5)

    campaign["funnel"] = compute_funnel(campaign)
    insights = build_insights(campaign, ads, daily_history, CAMPAIGN_BUDGET_AUD, CAMPAIGN_LENGTH_DAYS)

    return {
        "campaign": campaign,
        "ads": ads,
        "recommendation": campaign_row["recommendation"],
        "recommendation_status": campaign_row["recommendation_status"],
        "last_updated": campaign_row["created_at"].isoformat() if campaign_row["created_at"] else None,
        "leads_adjustment": adjustment,
        "campaign_budget": CAMPAIGN_BUDGET_AUD,
        "campaign_length_days": CAMPAIGN_LENGTH_DAYS,
        "insights": insights,
    }


async def get_history(db: AsyncSession, days: int = 14) -> list[dict]:
    """TRUE daily campaign-level series for the trend charts (level=
    'campaign_daily' — see run_snapshot), scoped to the CURRENT campaign
    (migration 162). These are each day's OWN spend/clicks/etc from Meta's
    time_increment=1 breakdown — NOT the level='campaign' rows, which are
    cumulative-to-date totals as of that day's snapshot pull and would plot
    as an ever-rising curve mislabeled as "per day" if used here."""
    since = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign_daily' AND campaign_id = :campaign_id AND snapshot_date >= :since
        ORDER BY snapshot_date ASC
    """), {"campaign_id": settings.meta_campaign_id, "since": since})).mappings().all()
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


async def get_ad_history(db: AsyncSession, ad_id: str, days: int = 30) -> list[dict]:
    """TRUE daily per-ad series (level='ad_daily') for the drill-down trend
    chart when a super admin clicks into one ad — same shape as get_history."""
    since = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'ad_daily' AND campaign_id = :campaign_id AND ad_id = :ad_id AND snapshot_date >= :since
        ORDER BY snapshot_date ASC
    """), {"campaign_id": settings.meta_campaign_id, "ad_id": ad_id, "since": since})).mappings().all()
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
