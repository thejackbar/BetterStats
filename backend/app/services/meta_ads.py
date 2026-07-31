"""Meta Marketing API client + recommendation logic for the Meta Ads HQ dashboard.

Reads BetterCricket's own ad account (platform-level, not club data) — the
campaign in settings.meta_campaign_id (currently "BC_AU_Trials_CBO_Aug2026",
the broad cold trials campaign to /trial; BC_AU_SelfServe_Aug2026 and the Jul
2026 early-bird came before it). No SDK, plain httpx
against the Graph API. Every call is wrapped so a bad/expired token or a Meta
outage surfaces as a typed error on the HQ page instead of a 500.
"""
from __future__ import annotations

import contextvars
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings

logger = logging.getLogger(__name__)

TIMEOUT = 20.0


# The active Meta campaign the dashboard is scoped to. A super admin selects it
# from the HQ page and it's stored in platform_settings; this ContextVar carries
# the resolved id for the current request so the many no-`db` fetch/helper
# functions below don't each need it threaded in. Defaults to the env seed
# (settings.meta_campaign_id) until a request resolves one, so a background call
# that never resolved one is still correct rather than empty.
_active_campaign: "contextvars.ContextVar[str | None]" = contextvars.ContextVar(
    "meta_active_campaign", default=None)

# A super-admin-set "counting since" cutoff (platform_settings.get_meta_ads_since)
# — data from before it is excluded from the on-site funnel/table numbers and
# Meta's own campaign insights, so a noisy launch period or old test traffic
# doesn't skew a fresh read. None (the default) means no cutoff — unchanged
# lifetime behaviour. Resolved alongside the active campaign since almost every
# caller of _use_active_campaign wants both.
_counting_since: "contextvars.ContextVar[datetime | None]" = contextvars.ContextVar(
    "meta_counting_since", default=None)


def _campaign_id() -> str:
    return _active_campaign.get() or settings.meta_campaign_id


def _since() -> datetime | None:
    return _counting_since.get()


async def _use_active_campaign(db: "AsyncSession") -> str:
    """Resolve the super-admin-selected active campaign AND counting-since
    cutoff from platform_settings, pinning both for the current request. Call
    at the top of every public entry point that scopes by campaign. Lazy
    import dodges a services import cycle."""
    from app.services import platform_settings
    cid = await platform_settings.get_active_meta_campaign_id(db)
    _active_campaign.set(cid)
    since_iso = await platform_settings.get_meta_ads_since(db)
    since_dt = None
    if since_iso:
        try:
            since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None
    _counting_since.set(since_dt)
    return cid


def _date_range_params() -> dict:
    """The date-scoping params for a Graph API insights call: the ordinary
    lifetime `date_preset: maximum` (unchanged default behaviour), or —
    when a counting-since cutoff is set (_since()) — a `time_range` from
    that date through today, so Meta's own campaign/ad totals reset the
    same way the on-site funnel numbers do. Meta's time_range is date-only
    (no hour precision), so an exact "6am" cutoff only applies to our own
    usage_events-derived numbers (_SINCE_LOWER_BOUND); this rounds down to
    the whole day it falls on."""
    since = _since()
    if not since:
        return {"date_preset": "maximum"}
    return {"time_range": json.dumps({
        "since": since.date().isoformat(),
        "until": date.today().isoformat(),
    })}


# Ad -> destination map (§1 of the spec). Stable IDs; the live API response's
# ad_name/ad_id are preferred where available, this is the fallback label.
# `campaign_id` lets get_registration_count() work out which utm_content tags
# belong to the CURRENT campaign (settings.meta_campaign_id) without a second
# round-trip — see that function.
AD_DESTINATIONS = {
    # BC_AU_Trials_CBO_Aug2026 (current) — club-history hero → /trial. The
    # utm_content here must match the tag on the ad's own destination URL for
    # get_registration_count() to tie a real signup back to this campaign.
    "120250150859240121": {"campaign_id": "120250149119070121", "name": "Ad_ClubHistory_Trial_Hero_v3", "destination": "betterat.cricket/trial", "utm_content": "club_history_hero"},
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

# Canonical `utm_campaign` value per Meta campaign this dashboard has ever
# tracked — per docs/meta-ad-campaign-self-serve.md §4, every ad's
# destination URL sets utm_campaign to the exact Ads Manager campaign name,
# identical across every ad in it. That makes it a second, more resilient
# way (alongside AD_DESTINATIONS' per-ad utm_content) to tie a real signup
# back to a campaign: a new ad/creative added in Ads Manager needs its
# utm_content added to AD_DESTINATIONS by hand before a signup through it
# counts, but its utm_campaign was already right from the moment it was
# built off this campaign's own destination-URL template — no code change
# needed. See _attribution_matches_campaign().
CAMPAIGN_UTM_NAMES = {
    "120250149119070121": "BC_AU_Trials_CBO_Aug2026",
    "120249890918010121": "BC_AU_SelfServe_Aug2026",
    "120249237210710121": "BC_AU_Traffic_ClubHistory_Jul2026",
}

# campaign["leads"] (shown as "Started registering (Meta-reported)", the
# funnel stage right after "Club selected") counts ONLY the genuine Meta Lead
# action — fired the moment a prospect picks a club, step 1 of the wizard.
# Deliberately does NOT also sum complete_registration/
# offsite_conversion.fb_pixel_complete_registration: an earlier version of
# this set blended BOTH action types together, which conflates two DIFFERENT
# funnel stages into one number (everyone who picked a club PLUS everyone who
# ALSO went on to finish, double-counting every completer) — the reason this
# figure used to read higher than our own real "Club selected" count even
# once both were scoped to the same date window. CompleteRegistration is
# tracked as its own, more trustworthy figure via get_registration_count()
# below (our own DB ground truth, organisations.signup_attribution) — never
# blended back into this one.
_LEAD_ACTION_TYPES = {
    "lead", "onsite_conversion.lead_grouped", "offsite_conversion.fb_pixel_lead",
}

# Single source of truth for pacing/insights maths — the dashboard reads
# these back from get_latest_summary() rather than the frontend hardcoding
# its own copy (that drifted once already, see the campaign-budget line on
# the KPI card before this file owned it). Also the default "how many days
# back" window for the report endpoints below (registration funnel, selected/
# searched clubs) — a plain lookback size, not itself a per-campaign figure.
CAMPAIGN_BUDGET_AUD = 750.0  # A$25/day CBO over the ~30-day pacing window — current campaign's plan, and the fallback for one not in CAMPAIGN_PLANS
CAMPAIGN_LENGTH_DAYS = 30

# Real budget/length plan PER campaign (docs/meta-ad-campaign-self-serve.md;
# the July and August campaigns ran to different budgets). Without this,
# switching the dashboard's campaign picker (§ header) to an old/finished
# campaign judged its pacing — "Overspending the budget pace" / "Under-
# pacing", the "Spend $X of $750" KPI line, the "~30 days from launch"
# header text — against the CURRENT campaign's own $750/30-day plan
# regardless of what that older campaign's real plan was. get_latest_summary
# resolves the active campaign's own plan via _campaign_plan() so those
# notes only ever describe the campaign actually on screen.
CAMPAIGN_PLANS: dict[str, tuple[float, int]] = {
    "120250149119070121": (750.0, 30),  # BC_AU_Trials_CBO_Aug2026 — A$25/day CBO
    "120249890918010121": (500.0, 30),  # BC_AU_SelfServe_Aug2026
    "120249237210710121": (500.0, 30),  # BC_AU_Traffic_ClubHistory_Jul2026 (finished)
}


def _campaign_plan() -> tuple[float, int]:
    """(budget_aud, length_days) for the CURRENT campaign — falls back to
    CAMPAIGN_BUDGET_AUD/CAMPAIGN_LENGTH_DAYS for a campaign not yet added to
    CAMPAIGN_PLANS (e.g. a brand new one just switched to)."""
    return CAMPAIGN_PLANS.get(_campaign_id(), (CAMPAIGN_BUDGET_AUD, CAMPAIGN_LENGTH_DAYS))


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
    """Campaign-level totals for the whole lifetime of the campaign, or since
    the counting-since cutoff when one is set (see _date_range_params)."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "campaign",
        "fields": "spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{_campaign_id()}"]}}]',
        **_date_range_params(),
    })
    data = body.get("data") or []
    if not data:
        return _parse_row({})
    return _parse_row(data[0])


async def fetch_ad_delivery_statuses() -> dict[str, str]:
    """Current Meta-side `effective_status` (ACTIVE/PAUSED/ADSET_PAUSED/
    CAMPAIGN_PAUSED/ARCHIVED/DELETED/...) per ad in the campaign. Insights
    rows never carry this — it's a separate, lightweight call against the
    ads edge (no date range, no metrics). Best-effort: returns {} on any
    Meta error so a transient failure here only means the dashboard falls
    back to pure performance-based badges, same as before this existed,
    rather than breaking the whole per-ad fetch."""
    try:
        body = await _get(f"/act_{settings.meta_ad_account_id}/ads", {
            "fields": "id,effective_status",
            "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{_campaign_id()}"]}}]',
            "limit": 200,
        })
    except MetaAdsError:
        logger.exception("Meta Ads: could not fetch per-ad delivery status")
        return {}
    return {row["id"]: row.get("effective_status") for row in (body.get("data") or []) if row.get("id")}


async def fetch_per_ad() -> list[dict]:
    """Per-ad totals (level=ad) for the campaign, or since the counting-since
    cutoff when one is set."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "ad",
        "fields": "ad_id,ad_name,spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{_campaign_id()}"]}}]',
        **_date_range_params(),
    })
    rows = [_parse_row(r) for r in (body.get("data") or [])]
    delivery_statuses = await fetch_ad_delivery_statuses()
    for r in rows:
        meta = AD_DESTINATIONS.get(r["ad_id"], {})
        r["name"] = r.get("ad_name") or meta.get("name") or r["ad_id"]
        r["destination"] = meta.get("destination")
        r["utm_content"] = meta.get("utm_content")
        r["delivery_status"] = delivery_statuses.get(r["ad_id"])
    return rows


async def fetch_daily_trend(days: int = 14) -> list[dict]:
    """One row per day, campaign level, for the trend charts. Since the
    counting-since cutoff when one is set — a shorter range than `days`
    just means fewer rows come back, the trailing rows[-days:] trim below
    still applies harmlessly."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/insights", {
        "level": "campaign",
        "fields": "spend,impressions,inline_link_clicks,inline_link_click_ctr,actions,cost_per_action_type",
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{_campaign_id()}"]}}]',
        **_date_range_params(),
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
        "filtering": f'[{{"field":"campaign.id","operator":"IN","value":["{_campaign_id()}"]}}]',
        **_date_range_params(),
        "time_increment": 1,
    })
    rows = [_parse_row(r) for r in (body.get("data") or [])]
    rows.sort(key=lambda r: (r.get("date_start") or "", r.get("ad_id") or ""))
    if days:
        keep_dates = set(sorted({r.get("date_start") for r in rows if r.get("date_start")})[-days:])
        rows = [r for r in rows if r.get("date_start") in keep_dates]
    return rows


async def list_campaigns() -> list[dict]:
    """All campaigns in the ad account (id, name, status, created_time), newest
    first — powers the HQ campaign picker so a super admin switches which
    campaign the dashboard tracks without a .env edit. Raises MetaAdsError on a
    Meta failure, like the other fetches."""
    body = await _get(f"/act_{settings.meta_ad_account_id}/campaigns", {
        "fields": "id,name,status,effective_status,created_time",
        "limit": 200,
    })
    rows = body.get("data") or []
    rows.sort(key=lambda r: r.get("created_time") or "", reverse=True)
    return [{
        "id": r.get("id"),
        "name": r.get("name"),
        "status": r.get("status"),
        "effective_status": r.get("effective_status"),
        "created_time": r.get("created_time"),
    } for r in rows if r.get("id")]


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
    """§6 per-ad status chip: paused / winner / laggard / on_track.

    A real Meta-side pause (or the parent ad set/campaign being paused)
    takes priority over every performance label — an ad that's stopped
    spending shouldn't keep reading as a live "Winner"/"Laggard"/"On track"
    verdict, which is only meaningful while it's still delivering."""
    if ad.get("delivery_status") and ad["delivery_status"] != "ACTIVE":
        return "paused"

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

    if status == "paused":
        label = {
            "PAUSED": "Paused",
            "ADSET_PAUSED": "Paused (its ad set is paused)",
            "CAMPAIGN_PAUSED": "Paused (the campaign is paused)",
            "ARCHIVED": "Archived",
            "DELETED": "Deleted",
        }.get(ad.get("delivery_status"), "No longer active")
        return f"{label} — not spending any more. Figures shown are its lifetime-to-date totals."

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


def compute_funnel(campaign: dict, club_selected: float = 0) -> list[dict]:
    """Ordered funnel stages, impressions through to a completed trial
    registration, each carrying what % of the top and of the PREVIOUS stage
    it represents — the numbers the KPI cards show individually, laid out so
    the drop-off at each step is visible without anyone computing a ratio.

    Every stage except "Club selected" is Meta's own ad-account number
    (impressions/clicks/LPV/leads from Insights). "Club selected" is ours —
    a real count of distinct Meta-driven visitors who picked a club in the
    wizard (get_club_selected_count), regardless of whether they went on to
    finish. It sits between landing_page_views and leads because that's
    exactly where it happens in the wizard, and it's a genuine buying signal
    worth tracking on its own — Meta's own "leads" reports the same moment
    but is self-reported and can drift (see the leads_effective note)."""
    stages_raw = [
        ("impressions", "Impressions", campaign.get("impressions") or 0),
        ("link_clicks", "Link clicks", campaign.get("link_clicks") or 0),
        ("landing_page_views", "Landing page views", campaign.get("landing_page_views") or 0),
        ("club_selected", "Club selected", club_selected or 0),
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
    ("club_searched", "Club searched"),
    ("club_prepared", "Club selected"),
    ("admin_details_completed", "Admin details completed"),
    ("email_code_sent", "Verification code sent"),
    ("email_verified", "Email verified"),
    ("acknowledgements_accepted", "Terms & privacy accepted"),
    ("submit_attempted", "Submit attempted"),
    ("registration_completed", "Registration completed"),
]


# The lower bound every windowed usage_events query below uses: the ordinary
# rolling "last :days days", but never earlier than a super-admin-set
# counting-since cutoff (platform_settings.get_meta_ads_since / _since()) when
# one is set — GREATEST(...) picks whichever bound is LATER (more recent), so
# a cutoff only ever narrows the window, never widens it past the requested
# `days`. :since is NULL (no cutoff) by default, in which case COALESCE falls
# back to '-infinity' and this is exactly the old "last :days days" behaviour.
_SINCE_LOWER_BOUND = "GREATEST(NOW() - (:days * INTERVAL '1 day'), COALESCE(:since, '-infinity'::timestamptz))"

# A visitor counts as "Meta-driven" if any of their events in the window
# carries a Meta signal — the same detection the Usage page uses for its FB/IG
# split (a fb/ig/meta utm_source, an fbclid/igshid on the URL, or a resolved
# facebook/instagram traffic_source). Keeps the wizard funnel and the
# selected-clubs table to Meta traffic only, so an organic or EDM signup that
# reached /trial some other way never shows on the Meta Ads dashboard.
def _meta_visitor_subquery(created_at_bound: str) -> str:
    return f"""
        visitor_id IN (
            SELECT DISTINCT visitor_id FROM usage_events
            WHERE created_at >= {created_at_bound}
              AND visitor_id IS NOT NULL
              AND (
                traffic_source IN ('facebook', 'instagram')
                OR lower(COALESCE(NULLIF(utm_source, ''),
                         substring(path from 'utm_source=([^&]+)')))
                    IN ('fb', 'facebook', 'meta', 'ig', 'instagram')
                OR path ~* 'fbclid=' OR path ~* 'igshid='
              )
        )
"""


# Since-aware — for the funnel STAT counts (get_club_selected_count), which
# reset with the counting-since cutoff.
_META_VISITOR_SUBQUERY = _meta_visitor_subquery(_SINCE_LOWER_BOUND)
# Plain days-only, unaffected by the cutoff — for the "Clubs selected"/"Clubs
# searched" TABLES (get_selected_clubs/get_searched_clubs), which stay a full
# follow-up/lead-management list regardless of the funnel reset.
_META_VISITOR_SUBQUERY_PLAIN = _meta_visitor_subquery("NOW() - (:days * INTERVAL '1 day')")


async def get_club_selected_count(db: AsyncSession, days: int = CAMPAIGN_LENGTH_DAYS) -> int:
    """Real count of distinct Meta-driven visitors who picked a club in the
    wizard (the `club_prepared` beacon), whether or not they ever went on to
    finish registering — a genuine buying signal in its own right, tracked
    as its own stage in compute_funnel() between landing_page_views and
    leads. Scoped to Meta traffic only (the same signal get_selected_clubs
    and get_searched_clubs use), so it lines up with the Meta-account
    numbers on either side of it in that funnel rather than including
    selections from organic/EDM/other traffic."""
    count = (await db.execute(text(f"""
        SELECT COUNT(DISTINCT visitor_id) FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND created_at >= {_SINCE_LOWER_BOUND}
          AND visitor_id IS NOT NULL
          AND {_META_VISITOR_SUBQUERY}
    """), {"days": days, "since": _since()})).scalar()
    return int(count or 0)


async def get_registration_step_funnel(db: AsyncSession, days: int = CAMPAIGN_LENGTH_DAYS) -> list[dict]:
    """In-app breakdown of WHERE within the registration wizard visitors drop
    off — the detail Meta's own reporting can't give us, since it only ever
    sees a Lead (fired at the very first step) and a CompleteRegistration
    (fired only on a fully successful last step). Counts distinct visitors
    reaching each step (see public_self_serve.py's /track-step beacon and
    SelfServeTrialModal.jsx's trackFunnelStep calls), same
    key/label/value/pct_of_top/pct_of_prev shape as compute_funnel() so the
    frontend can reuse the same FunnelChart component."""
    await _use_active_campaign(db)  # resolves the counting-since cutoff, see _since()
    rows = (await db.execute(text(f"""
        SELECT route, COUNT(DISTINCT visitor_id) AS n
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND created_at >= {_SINCE_LOWER_BOUND}
          AND visitor_id IS NOT NULL
        GROUP BY route
    """), {"days": days, "since": _since()})).mappings().all()
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


# Furthest step a selected club is known to have reached, strongest last. The
# funnel above counts anonymous visitors; this names the clubs behind the
# "Club selected" count wherever we can identify one.
_SELECTED_STEP_RANK = {"selected": 1, "terms": 2, "completed": 3}
_SELECTED_STEP_LABEL = {
    1: "Club selected",
    2: "Reached Terms & privacy",
    3: "Registration completed",
}


async def get_selected_clubs(db: AsyncSession, days: int = CAMPAIGN_LENGTH_DAYS) -> dict:
    """Name the clubs behind the registration wizard's "Club selected" count.

    The step funnel (get_registration_step_funnel) only counts anonymous
    visitor_ids per step — it can't say WHICH club a dropped-off visitor picked.
    This fills that in from three sources, merged by normalised club name and
    reporting the furthest step each one reached:

      1. the `club_prepared` beacon's own metadata — the club captured at
         selection time (public_self_serve.py track_step, from Jul 2026 on);
      2. self_serve_acknowledgements.club_name — anyone who reached the Terms
         step, recoverable even for selections made before (1) existed;
      3. organisations.signup_source — anyone who completed registration.

    Selections made before the beacon captured the club AND that never reached
    the Terms step are unidentifiable; those are returned only as an
    `anonymous` count so the total still reconciles with the funnel."""
    # Every started club stays in this list — it's the follow-up tool for hot
    # leads who didn't finish, so a non-Meta start is never hidden. Instead each
    # club is TAGGED (`via_meta`) with whether it came through the ad: completed
    # registrations by utm_content (the current campaign's own tags, same as the
    # KPI card + ad-signups) or a fb/ig/meta utm_source; beacon selections by
    # whether any of the club's visitors carried a Meta signal. The COUNTED "Meta
    # leads" numbers stay Meta-scoped elsewhere; this list is deliberately
    # all-source so no lead is lost.
    #
    # Deliberately NOT windowed by the counting-since cutoff (_since()) —
    # unlike the funnel STAT counts above it on the dashboard, this table is a
    # follow-up/lead-management tool ("who do we chase up") and a super admin
    # asking to reset the funnel to a clean baseline still wants every past
    # lead listed here, not to have them drop out of view.
    await _use_active_campaign(db)
    window = {"days": days}
    utm_contents = set(_current_campaign_utm_contents())
    _META_SOURCES = _META_ATTRIBUTION_SOURCES  # same set _attribution_matches_campaign uses

    # (1) Beacon rows that carry a club name (going forward), each tagged with
    # whether any of its visitors was Meta-driven. Plus a count of the ones that
    # carry no club name — selections we genuinely can't attribute.
    beacon_rows = (await db.execute(text(f"""
        SELECT metadata->>'club_name'   AS club_name,
               metadata->>'club_org_id' AS org_id,
               MIN(created_at)          AS first_at,
               MAX(created_at)          AS last_at,
               COUNT(DISTINCT visitor_id) AS visitors,
               bool_or({_META_VISITOR_SUBQUERY_PLAIN}) AS via_meta
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NOT NULL
        GROUP BY 1, 2
    """), window)).mappings().all()

    anon = (await db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) AS n
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND visitor_id IS NOT NULL
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NULL
    """), window)).scalar() or 0

    # (2) Terms-step acknowledgements — carry the club name and an email.
    ack_rows = (await db.execute(text("""
        SELECT club_name, MIN(email) AS email,
               MIN(accepted_at) AS first_at, MAX(accepted_at) AS last_at
        FROM self_serve_acknowledgements
        WHERE accepted_at >= NOW() - (:days * INTERVAL '1 day')
        GROUP BY club_name
    """), window)).mappings().all()

    # (3) Completed self-serve registrations — the org plus when it was created
    # (orgs carry no created_at; the idempotency key holds the timestamp).
    # All completions are listed; utm_content / utm_source come back so each one
    # can be tagged Meta-or-not in Python below.
    done_rows = (await db.execute(text("""
        SELECT o.name AS club_name, o.slug, o.id::text AS org_id,
               MIN(k.created_at) AS at,
               MIN(o.signup_attribution->>'utm_content') AS utm_content,
               MIN(o.signup_attribution->>'utm_source')  AS utm_source
        FROM organisations o
        JOIN self_serve_idempotency_keys k ON k.org_id = o.id
        WHERE o.signup_source IS NOT NULL
          AND k.created_at >= NOW() - (:days * INTERVAL '1 day')
        GROUP BY o.name, o.slug, o.id
    """), window)).mappings().all()

    clubs: dict[str, dict] = {}

    def _upsert(name, rank, *, first_at=None, last_at=None, org_id=None,
                slug=None, email=None, visitors=0, via_meta=False):
        key = (name or "").strip().lower()
        if not key:
            return
        c = clubs.setdefault(key, {
            "name": (name or "").strip(), "furthest_rank": 0, "furthest_step": "",
            "first_at": None, "last_at": None, "org_id": None, "slug": None,
            "email": None, "visitors": 0, "via_meta": False,
        })
        if via_meta:
            c["via_meta"] = True
        if rank > c["furthest_rank"]:
            c["furthest_rank"] = rank
            c["furthest_step"] = _SELECTED_STEP_LABEL[rank]
        for field, val in (("first_at", first_at), ("last_at", last_at)):
            if val is not None:
                cur = c[field]
                if cur is None or (val < cur if field == "first_at" else val > cur):
                    c[field] = val
        if org_id and not c["org_id"]:
            c["org_id"] = org_id
        if slug and not c["slug"]:
            c["slug"] = slug
        if email and not c["email"]:
            c["email"] = email
        c["visitors"] = max(c["visitors"], visitors or 0)

    for r in beacon_rows:
        _upsert(r["club_name"], _SELECTED_STEP_RANK["selected"],
                first_at=r["first_at"], last_at=r["last_at"],
                org_id=r["org_id"], visitors=int(r["visitors"] or 0),
                via_meta=bool(r["via_meta"]))
    # Terms-step acknowledgements carry no Meta signal of their own, so they
    # enrich the furthest step (and email) of whatever club they name without
    # changing its source tag.
    for r in ack_rows:
        _upsert(r["club_name"], _SELECTED_STEP_RANK["terms"],
                first_at=r["first_at"], last_at=r["last_at"], email=r["email"])
    for r in done_rows:
        _upsert(r["club_name"], _SELECTED_STEP_RANK["completed"],
                first_at=r["at"], last_at=r["at"], org_id=r["org_id"], slug=r["slug"],
                via_meta=((r["utm_content"] in utm_contents)
                          or ((r["utm_source"] or "").strip().lower() in _META_SOURCES)))

    # Newest selection first; a club with no timestamp (shouldn't happen — every
    # source supplies one) sinks to the bottom without tripping the aware/naive
    # datetime comparison.
    _floor = datetime.min.replace(tzinfo=timezone.utc)
    rows = sorted(clubs.values(), key=lambda c: c["last_at"] or _floor, reverse=True)
    for c in rows:
        # The normalised name is exactly the dict key get_selected_clubs grouped
        # by (name is already .strip()'d in _upsert) — hide/unhide is keyed on it.
        c["key"] = (c["name"] or "").strip().lower()
        c["first_at"] = c["first_at"].isoformat() if c["first_at"] else None
        c["last_at"] = c["last_at"].isoformat() if c["last_at"] else None
        c.pop("furthest_rank", None)

    # A super admin flags test noise (e.g. their own stripetest run) as hidden —
    # a display-only tidy-up of this table, never touching the Sales Pipeline.
    from app.services import platform_settings
    hidden_keys = await platform_settings.get_hidden_meta_selections(db)
    visible = [c for c in rows if c["key"] not in hidden_keys]
    hidden = [c for c in rows if c["key"] in hidden_keys]

    return {
        "clubs": visible,
        "hidden_clubs": hidden,
        "identified": len(visible),
        "hidden_count": len(hidden),
        "anonymous": int(anon),
    }


async def get_searched_clubs(db: AsyncSession, days: int = CAMPAIGN_LENGTH_DAYS) -> dict:
    """Name the clubs visitors TYPED into the search box — the step before a
    club is actually clicked/selected.

    The `/trial` search box (and the wizard's own) fire a `club_searched`
    beacon whenever a search returns results, carrying the top-matching club
    and the raw text typed (public_self_serve.py track_step). This surfaces the
    interest-without-commitment those beacons capture: a club whose name got
    searched but which was never selected is a warm prospect the "Clubs
    selected" table would otherwise miss entirely.

    Each row reports the top-matched club, how many distinct visitors searched
    it, a sample of the literal search terms, whether the search came through a
    Meta ad, and — the point of the table — whether it was ever `selected`
    (clicked into the wizard). Test noise flagged on the selected-clubs table is
    hidden here too, keyed on the same normalised club name.

    Deliberately NOT windowed by the counting-since cutoff (_since()) — same
    reasoning as get_selected_clubs: this is a follow-up/lead-management
    list, not a funnel stat, so a reset shouldn't drop past leads from view."""
    await _use_active_campaign(db)
    window = {"days": days}

    # Clubs typed into the search box, grouped by the top result the search
    # returned, tagged Meta-or-not, with a sample of the literal search terms.
    search_rows = (await db.execute(text(f"""
        SELECT metadata->>'club_name'   AS club_name,
               metadata->>'club_org_id' AS org_id,
               MIN(created_at)          AS first_at,
               MAX(created_at)          AS last_at,
               COUNT(DISTINCT visitor_id) AS visitors,
               COUNT(*)                   AS searches,
               bool_or({_META_VISITOR_SUBQUERY_PLAIN}) AS via_meta,
               (array_agg(DISTINCT NULLIF(TRIM(metadata->>'search_query'), ''))
                  FILTER (WHERE NULLIF(TRIM(metadata->>'search_query'), '') IS NOT NULL)
               )[1:5] AS queries
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_searched'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NOT NULL
        GROUP BY 1, 2
    """), window)).mappings().all()

    # The set of clubs that went on to actually be SELECTED (clicked into the
    # wizard) in the same window — a searched club present here converted, the
    # rest are searched-only. Keyed by normalised name, so it lines up with the
    # search rows' own grouping regardless of which org_id each side captured.
    selected_keys = set((await db.execute(text("""
        SELECT DISTINCT lower(TRIM(metadata->>'club_name')) AS k
        FROM usage_events
        WHERE event_type = 'self_serve_step'
          AND route = 'club_prepared'
          AND created_at >= NOW() - (:days * INTERVAL '1 day')
          AND NULLIF(TRIM(metadata->>'club_name'), '') IS NOT NULL
    """), window)).scalars().all())

    rows: list[dict] = []
    for r in search_rows:
        name = (r["club_name"] or "").strip()
        if not name:
            continue
        key = name.lower()
        rows.append({
            "name": name,
            "key": key,
            "org_id": r["org_id"],
            "visitors": int(r["visitors"] or 0),
            "searches": int(r["searches"] or 0),
            "queries": list(r["queries"] or []),
            "via_meta": bool(r["via_meta"]),
            "selected": key in selected_keys,
            "first_at": r["first_at"].isoformat() if r["first_at"] else None,
            "last_at": r["last_at"].isoformat() if r["last_at"] else None,
        })

    _floor = datetime.min.replace(tzinfo=timezone.utc)
    rows.sort(key=lambda c: c["last_at"] or _floor.isoformat(), reverse=True)

    # Reuse the selected-clubs hidden list — a club flagged as test noise there
    # is test noise here too (same normalised-name key).
    from app.services import platform_settings
    hidden_keys = await platform_settings.get_hidden_meta_selections(db)
    visible = [c for c in rows if c["key"] not in hidden_keys]
    hidden = [c for c in rows if c["key"] in hidden_keys]

    searched_only = [c for c in visible if not c["selected"]]
    return {
        "clubs": visible,
        "hidden_clubs": hidden,
        "identified": len(visible),
        "hidden_count": len(hidden),
        "searched_only_count": len(searched_only),
        "converted_count": len(visible) - len(searched_only),
    }


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
             link_ctr, landing_page_views, cost_per_lpv, leads, recommendation, recommendation_status,
             delivery_status, updated_at)
        VALUES
            (:snapshot_date, :level, :ad_id, :ad_name, :campaign_id, :spend, :impressions, :link_clicks,
             :link_ctr, :landing_page_views, :cost_per_lpv, :leads, :recommendation, :recommendation_status,
             :delivery_status, NOW())
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
            recommendation_status = COALESCE(EXCLUDED.recommendation_status, meta_ad_snapshots.recommendation_status),
            delivery_status = EXCLUDED.delivery_status,
            updated_at = NOW()
    """), {
        "snapshot_date": snapshot_date,
        "level": level,
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name") or row.get("name"),
        "campaign_id": _campaign_id(),
        "spend": row.get("spend") or 0,
        "impressions": row.get("impressions") or 0,
        "link_clicks": row.get("link_clicks") or 0,
        "link_ctr": row.get("link_ctr") or 0,
        "landing_page_views": row.get("landing_page_views") or 0,
        "cost_per_lpv": row.get("cost_per_lpv"),
        "leads": row.get("leads") or 0,
        "recommendation": recommendation,
        "recommendation_status": recommendation_status,
        "delivery_status": row.get("delivery_status"),
    })


async def run_snapshot(db: AsyncSession) -> dict:
    """Pull current totals from Meta, compute the recommendation, upsert today's
    snapshot rows (campaign + each ad). Raises MetaAdsError on failure — callers
    decide whether to log-and-skip (scheduled job) or surface it (manual refresh)."""
    await _use_active_campaign(db)
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
    await _use_active_campaign(db)
    total = (await db.execute(text(
        "SELECT COALESCE(SUM(delta), 0) FROM meta_lead_adjustments WHERE campaign_id = :campaign_id"
    ), {"campaign_id": _campaign_id()})).scalar()
    return int(total or 0)


async def add_lead_adjustment(db: AsyncSession, delta: int, note: str | None, created_by_email: str | None) -> int:
    """Record a manual +/- correction to the Meta-reported lead count, tagged
    to the current campaign. Returns the new running total (does not touch
    ``meta_ad_snapshots.leads`` itself, so the next snapshot pull can't
    silently wipe the correction)."""
    await _use_active_campaign(db)
    await db.execute(text("""
        INSERT INTO meta_lead_adjustments (delta, note, created_by_email, campaign_id)
        VALUES (:delta, :note, :created_by_email, :campaign_id)
    """), {"delta": delta, "note": (note or None), "created_by_email": created_by_email,
           "campaign_id": _campaign_id()})
    await db.commit()
    return await get_leads_adjustment_total(db)


async def get_lead_adjustments(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Recent manual reconciliation entries for the CURRENT campaign, newest
    first — the audit trail behind the effective lead count."""
    await _use_active_campaign(db)
    rows = (await db.execute(text("""
        SELECT delta, note, created_by_email, created_at
        FROM meta_lead_adjustments
        WHERE campaign_id = :campaign_id
        ORDER BY created_at DESC
        LIMIT :limit
    """), {"campaign_id": _campaign_id(), "limit": limit})).mappings().all()
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
        if meta.get("campaign_id") == _campaign_id() and meta.get("utm_content")
    }


# Same "was this click Meta at all" signal get_selected_clubs/get_searched_clubs/
# _META_VISITOR_SUBQUERY already use elsewhere on this dashboard — the loosest
# (and last-resort) of _attribution_matches_campaign's three checks.
_META_ATTRIBUTION_SOURCES = {"fb", "facebook", "meta", "ig", "instagram"}


def _attribution_matches_campaign(attribution: dict | None) -> bool:
    """True if a stored signup_attribution counts as a registration for the
    CURRENT campaign (_campaign_id()), checked three independent ways — any
    one is enough:
    1. its utm_content is one AD_DESTINATIONS maps to this campaign;
    2. its utm_campaign matches this campaign's own canonical name in
       CAMPAIGN_UTM_NAMES (more resilient than (1) — doesn't need
       AD_DESTINATIONS kept in sync with every new ad);
    3. it otherwise carries a plain Meta click signal (a fb/ig/meta
       utm_source, or a facebook/instagram click_source) — the loosest
       check, but a genuine Meta-driven registration shouldn't silently
       vanish from the count just because its UTM tags don't exactly match
       a hand-maintained mapping. In practice only one campaign has ever
       been live at a time, so "a Meta click happened" is a good enough
       stand-in for "it was THIS campaign" when the more precise checks
       above come up empty.
    Used by get_registration_count() and the ad-signups report
    (routers/meta_ads.py) so the two can never disagree."""
    if not attribution:
        return False
    utm_content = (attribution.get("utm_content") or "").strip()
    if utm_content and utm_content in _current_campaign_utm_contents():
        return True
    utm_campaign_name = CAMPAIGN_UTM_NAMES.get(_campaign_id())
    if utm_campaign_name and (attribution.get("utm_campaign") or "").strip().lower() == utm_campaign_name.lower():
        return True
    utm_source = (attribution.get("utm_source") or "").strip().lower()
    if utm_source in _META_ATTRIBUTION_SOURCES:
        return True
    click_source = (attribution.get("click_source") or "").strip().lower()
    return click_source in {"facebook", "instagram"}


async def get_registration_count(db: AsyncSession) -> int:
    """Real, completed free-trial registrations attributed to the CURRENT
    Meta campaign — ground truth from our own DB (organisations.
    signup_attribution, migration 161), not Meta's self-reported Lead/
    CompleteRegistration action counts. Those actions fire the moment a
    prospect reaches the trial form (a Lead) or completes it (a
    CompleteRegistration) and can double-count across the pixel/CAPI
    action-type split (see the "2 conversions" investigation) — they also
    can't tell a Meta-driven signup apart from one that came in through a
    different (non-Meta) channel (an EDM send, organic traffic) that happens
    to carry its own utm tags. A club only counts here if its
    signup_attribution matches (_attribution_matches_campaign — by
    utm_content, utm_campaign, or a plain Meta click signal), archived test
    signups are excluded (same default as the ad-signups report and the main
    Club Directory). Deliberately NOT windowed by the counting-since cutoff
    (_since()) that scopes the funnel/table numbers above it on the
    dashboard — a genuine completed registration always counts, however long
    ago it happened. Filtered in Python rather than SQL — self-serve signup
    volume is small, and it keeps this in lockstep with ad_signups()'s own
    filtering instead of two hand-matched queries."""
    await _use_active_campaign(db)
    rows = (await db.execute(text("""
        SELECT signup_attribution FROM organisations
        WHERE signup_source IS NOT NULL AND archived_at IS NULL AND signup_attribution IS NOT NULL
    """))).scalars().all()
    return sum(1 for attribution in rows if _attribution_matches_campaign(attribution))


async def get_latest_summary(db: AsyncSession) -> dict:
    """Read back the most recent snapshot set for the CURRENT campaign (used
    for the fast page-load path, as opposed to /refresh which does a live
    pull). Scoped by campaign_id since migration 162 — without it, the most
    recent row could belong to a previous campaign's last snapshot before it
    was switched off, or (worse) a stale row for today under the old
    campaign could shadow the new one's."""
    await _use_active_campaign(db)
    campaign_budget, campaign_length_days = _campaign_plan()
    campaign_row = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign' AND campaign_id = :campaign_id
        ORDER BY snapshot_date DESC, created_at DESC
        LIMIT 1
    """), {"campaign_id": _campaign_id()})).mappings().first()

    adjustment = await get_leads_adjustment_total(db)

    if not campaign_row:
        return {"campaign": None, "ads": [], "recommendation": None,
                "recommendation_status": None, "last_updated": None,
                "leads_adjustment": adjustment, "campaign_budget": campaign_budget,
                "campaign_length_days": campaign_length_days, "insights": [],
                "counting_since": _since().isoformat() if _since() else None}

    latest_date = campaign_row["snapshot_date"]
    ad_rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'ad' AND campaign_id = :campaign_id AND snapshot_date = :d
        ORDER BY spend DESC
    """), {"campaign_id": _campaign_id(), "d": latest_date})).mappings().all()

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
            "delivery_status": r["delivery_status"],
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
    daily_history = await get_history(db, days=campaign_length_days + 5)
    club_selected = await get_club_selected_count(db)

    campaign["funnel"] = compute_funnel(campaign, club_selected)
    insights = build_insights(campaign, ads, daily_history, campaign_budget, campaign_length_days)

    return {
        "campaign": campaign,
        "ads": ads,
        "recommendation": campaign_row["recommendation"],
        "recommendation_status": campaign_row["recommendation_status"],
        "last_updated": (campaign_row["updated_at"] or campaign_row["created_at"]).isoformat()
            if (campaign_row["updated_at"] or campaign_row["created_at"]) else None,
        "leads_adjustment": adjustment,
        "campaign_budget": campaign_budget,
        "campaign_length_days": campaign_length_days,
        "insights": insights,
        "counting_since": _since().isoformat() if _since() else None,
    }


async def get_history(db: AsyncSession, days: int = 14) -> list[dict]:
    """TRUE daily campaign-level series for the trend charts (level=
    'campaign_daily' — see run_snapshot), scoped to the CURRENT campaign
    (migration 162). These are each day's OWN spend/clicks/etc from Meta's
    time_increment=1 breakdown — NOT the level='campaign' rows, which are
    cumulative-to-date totals as of that day's snapshot pull and would plot
    as an ever-rising curve mislabeled as "per day" if used here."""
    await _use_active_campaign(db)
    since = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'campaign_daily' AND campaign_id = :campaign_id AND snapshot_date >= :since
        ORDER BY snapshot_date ASC
    """), {"campaign_id": _campaign_id(), "since": since})).mappings().all()
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
    await _use_active_campaign(db)
    since = date.today() - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT * FROM meta_ad_snapshots
        WHERE level = 'ad_daily' AND campaign_id = :campaign_id AND ad_id = :ad_id AND snapshot_date >= :since
        ORDER BY snapshot_date ASC
    """), {"campaign_id": _campaign_id(), "ad_id": ad_id, "since": since})).mappings().all()
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
