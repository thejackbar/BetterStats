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


# ── Conversion streams ───────────────────────────────────────────────────────
# ONE Meta campaign now sells TWO DIFFERENT THINGS, and that is the single fact
# this whole module has to be read through since the 8-9 Sep 2026 restructure.
#
# Both landing pages fire the SAME pixel event, CompleteRegistration, on the
# same dataset, told apart only by `content_category`: /trial sends
# 'self_serve_trial' (and carries a value of 399 AUD), /demo sends 'webinar'
# (and carries none). A trial signup is a prospective paying club; a webinar
# registration is somebody who watched a form. They are not the same result and
# their costs differ by a lot, so NOTHING here reports a conversion count or a
# cost per result without saying which stream it belongs to — a combined
# "registrations" number would be arithmetic performed on two different units.
STREAM_TRIAL = "trial"
STREAM_WEBINAR = "webinar"
STREAMS = (STREAM_TRIAL, STREAM_WEBINAR)

STREAM_LABELS = {
    STREAM_TRIAL: "Free trial signups",
    STREAM_WEBINAR: "Webinar registrations",
}
# The pixel `content_category` each stream fires — the parameter that is the
# ONLY thing separating the two events on Meta's side. Mirrored from
# frontend/src/pages/marketing/{Trial,Demo}.jsx and services/meta_capi.py.
STREAM_CONTENT_CATEGORIES = {
    STREAM_TRIAL: "self_serve_trial",
    STREAM_WEBINAR: "webinar",
}
# Only the trial event carries a monetary value. Any revenue/ROAS arithmetic
# must read this rather than assuming every conversion is worth something —
# valuing a webinar registration at the trial's 399 would inflate return by the
# whole webinar volume.
STREAM_VALUE_AUD = {
    STREAM_TRIAL: 399.0,
    STREAM_WEBINAR: 0.0,
}


# Ad -> destination map (§1 of the spec). Stable IDs; the live API response's
# ad_name/ad_id are preferred where available, this is the fallback label.
# `campaign_id` lets get_registration_count() work out which utm_content tags
# belong to the CURRENT campaign (settings.meta_campaign_id) without a second
# round-trip — see that function.
#
# `stream` is the entry's own answer to "which product is this ad selling".
# It is NOT the only source — `stream_for_ad()` falls back to the ad NAME, so
# an ad built in Ads Manager tomorrow is classified correctly without anyone
# editing this file. The map exists to be exact where we can be, not to be the
# gate.
#
# `ends_on` marks an ad that stops being relevant on a known date (the webinar
# is a dated event). Used to report a stream as finished rather than leaving it
# reading as a live campaign with a collapsing result rate.
AD_DESTINATIONS = {
    # ── BC_AU_Trials_CBO_Aug2026 (current), restructured 8-9 Sep 2026 ────────
    # The webinar ad — the whole reason conversions had to be split. Its
    # primary text also carries a PLAIN-TEXT link with no UTMs (it had to match
    # a line on the artwork), so a minority of its registrations arrive
    # untagged and read as direct traffic. That shortfall is reported, never
    # papered over — see get_webinar_registration_counts().
    "120251267760560121": {"campaign_id": "120250149119070121", "name": "Ad_Webinar_LiveDemo_21Sep2026_v2", "destination": "betterat.cricket/demo", "utm_content": "live_demo_hero", "utm_campaign": "webinar_21sep2026", "stream": STREAM_WEBINAR, "ends_on": "2026-09-21"},
    "120251267750770121": {"campaign_id": "120250149119070121", "name": "ZZ_SUPERSEDED_Ad_Webinar_LiveDemo_21Sep2026_v1", "destination": "betterat.cricket/demo", "utm_content": "live_demo_hero", "utm_campaign": "webinar_21sep2026", "stream": STREAM_WEBINAR, "ends_on": "2026-09-21"},
    # The evergreen trial ad — paused, live from 22 Sep (the day after the
    # webinar), so it legitimately reads as zero-spend until then.
    "120251268385660121": {"campaign_id": "120250149119070121", "name": "Ad_Trial_Spreadsheet_Sep2026", "destination": "betterat.cricket/trial", "utm_content": "spreadsheet_hero", "utm_campaign": "trial_evergreen_sep2026", "stream": STREAM_TRIAL},
    "120250237123350121": {"campaign_id": "120250149119070121", "name": "Ad_CheckOutYourClub_v2", "destination": "betterat.cricket/trial", "stream": STREAM_TRIAL},
    "120250237122840121": {"campaign_id": "120250149119070121", "name": "Ad_CheckOutYourClub_v1", "destination": "betterat.cricket/trial", "stream": STREAM_TRIAL},
    # club-history hero → /trial. The utm_content here must match the tag on
    # the ad's own destination URL for get_registration_count() to tie a real
    # signup back to this campaign.
    "120250150859240121": {"campaign_id": "120250149119070121", "name": "Ad_ClubHistory_Trial_Hero_v3", "destination": "betterat.cricket/trial", "utm_content": "club_history_hero", "stream": STREAM_TRIAL},
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

# Every `utm_campaign` value a Meta campaign's ads tag their destination URLs
# with — a SET per campaign, not one value, and that plurality is the point.
#
# The convention used to be one tag per campaign, the exact Ads Manager name
# (docs/meta-ad-campaign-self-serve.md §4). The 8-9 Sep restructure broke that:
# BC_AU_Trials_CBO_Aug2026 now runs two products under two taxonomies
# (`webinar_21sep2026`, `trial_evergreen_sep2026`) and neither is the campaign's
# own name. A single-valued map would have quietly stopped recognising every
# registration through the new ads — failing CLOSED, which reads as "the ads
# produced nothing" rather than as a bug.
#
# This is still the resilient half of attribution (alongside AD_DESTINATIONS'
# per-ad utm_content): a new creative built off one of these destination-URL
# templates is recognised the moment it goes live, with no code change.
CAMPAIGN_UTM_CAMPAIGNS: dict[str, set[str]] = {
    "120250149119070121": {
        "BC_AU_Trials_CBO_Aug2026",   # pre-restructure ads
        "webinar_21sep2026",
        "trial_evergreen_sep2026",
    },
    "120249890918010121": {"BC_AU_SelfServe_Aug2026"},
    "120249237210710121": {"BC_AU_Traffic_ClubHistory_Jul2026"},
}

# Which stream a `utm_campaign` tag belongs to. Derived from the taxonomy
# rather than the ad id, so a registration is attributed to the right product
# even when the ad that produced it has since been deleted.
STREAM_BY_UTM_CAMPAIGN = {
    "webinar_21sep2026": STREAM_WEBINAR,
    "trial_evergreen_sep2026": STREAM_TRIAL,
}


def stream_for_ad(ad_id: str | None, ad_name: str | None = None) -> str:
    """Which product an ad is selling — the map first, then the ad's own NAME.

    Deliberately name-derived as the fallback rather than requiring every ad
    to be listed above: the ad set is where creatives get added and renamed in
    Ads Manager, and a classification that needs a code change to keep up would
    silently mis-file the next webinar ad as a trial one. Naming convention is
    `Ad_Webinar_*` / `ZZ_SUPERSEDED_Ad_Webinar_*`; anything that does not
    announce itself as a webinar ad sells the trial, which is what every ad in
    this account did before the restructure.

    NOT derived from the ad SET name — `AS_Cold_Broad_AU_LPV` says "cold
    broad" and "LPV" and is now wrong about both, so nothing here reads it.
    """
    entry = AD_DESTINATIONS.get(ad_id or "") or {}
    if entry.get("stream"):
        return entry["stream"]
    name = (ad_name or entry.get("name") or "").lower()
    return STREAM_WEBINAR if "webinar" in name else STREAM_TRIAL


def stream_for_attribution(attribution: dict | None) -> str | None:
    """Which stream a stored registration's own UTM tags point at, or None
    when they say nothing. The utm_campaign taxonomy is checked first (it is
    set per destination and survives an ad being deleted), then the creative
    tag. Used to attribute a CREATIVE's results — never to decide what KIND of
    result a row is, which is settled by the table it lives in."""
    if not attribution:
        return None
    campaign_tag = (attribution.get("utm_campaign") or "").strip().lower()
    for tag, stream in STREAM_BY_UTM_CAMPAIGN.items():
        if campaign_tag == tag.lower():
            return stream
    content_tag = (attribution.get("utm_content") or "").strip()
    for entry in AD_DESTINATIONS.values():
        if entry.get("utm_content") == content_tag and entry.get("stream"):
            return entry["stream"]
    return None

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
    # BC_AU_Trials_CBO_Aug2026 — A$30/day CBO since the 8 Sep restructure (was
    # A$50/day). 30 x 30 = 900 over the pacing window. Pacing is measured from
    # the most recent change (see build_insights), not across it, so this is
    # the plan the campaign is actually running to rather than a blend of two.
    "120250149119070121": (900.0, 30),
    "120249890918010121": (500.0, 30),  # BC_AU_SelfServe_Aug2026
    "120249237210710121": (500.0, 30),  # BC_AU_Traffic_ClubHistory_Jul2026 (finished)
}

# Dated, deliberate changes to a campaign — rendered as a marker on every
# time-series chart and used to decide what is comparable with what.
#
# A campaign that changed materially is two campaigns wearing one name, and a
# chart that plots straight through the change invites a reading it cannot
# support: "down 40% week on week" printed over a deliberate 40% budget cut is
# worse than saying nothing. There WILL be more of these — add a row rather
# than reasoning about the discontinuity somewhere else.
CAMPAIGN_ANNOTATIONS: dict[str, list[dict]] = {
    "120250149119070121": [
        {
            "date": "2026-09-08",
            "label": "Campaign restructured",
            "detail": (
                "Budget A$50 → A$30/day; placements narrowed to Facebook Feed only "
                "(Instagram off); targeting went from broad with Advantage+ Audience to "
                "AU men 30-64 with a cricket interest; /demo added alongside /trial. "
                "Figures either side of this line describe two different campaigns."
            ),
        },
    ],
}

# Meta attributes a conversion to the date of the CLICK, on a 7-day window, so
# the most recent 7 days always under-report and fill in retrospectively. Every
# figure covering that stretch is provisional; nothing alerts off it.
ATTRIBUTION_WINDOW_DAYS = 7


def _campaign_plan() -> tuple[float, int]:
    """(budget_aud, length_days) for the CURRENT campaign — falls back to
    CAMPAIGN_BUDGET_AUD/CAMPAIGN_LENGTH_DAYS for a campaign not yet added to
    CAMPAIGN_PLANS (e.g. a brand new one just switched to)."""
    return CAMPAIGN_PLANS.get(_campaign_id(), (CAMPAIGN_BUDGET_AUD, CAMPAIGN_LENGTH_DAYS))


def campaign_annotations() -> list[dict]:
    """The CURRENT campaign's change markers, oldest first."""
    return sorted(CAMPAIGN_ANNOTATIONS.get(_campaign_id(), []), key=lambda a: a["date"])


def _provisional_from() -> date:
    """The first date whose figures are still settling — anything on or after
    it is inside Meta's 7-day click-attribution window."""
    return date.today() - timedelta(days=ATTRIBUTION_WINDOW_DAYS - 1)


def _last_change_date() -> date | None:
    """The most recent deliberate campaign change, or None. Anything before it
    is not comparable with anything after it."""
    dates = [_parse_insights_date(a["date"]) for a in campaign_annotations()]
    settled = [d for d in dates if d]
    return max(settled) if settled else None


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


# ─── Token health ──────────────────────────────────────────────────────────
# The Aug→Sep 2026 outage was a silent one: the ads_read token expired and the
# HQ page kept showing the last good snapshot for ten days before anyone opened
# it and saw the banner. And the CAPI token — which quietly stops sending
# server-side conversions when it lapses — has NO surface at all. So both tokens
# are checked proactively (a countdown, not a post-mortem) via Meta's own
# debug_token, and "expiring within TOKEN_WARN_WITHIN_DAYS" lights the sidebar
# badge so it's caught before the data goes stale. The real fix for recurrence
# is a never-expiring system-user token; this makes the 60-day one visible.
TOKEN_WARN_WITHIN_DAYS = 14

# debug_token is a live Meta call and the badge fetch fires on every super-admin
# page mount, so cache it briefly — an expiry date doesn't change minute to
# minute. Busted after a successful /refresh so a just-fixed token confirms
# straight away rather than waiting out the TTL.
_TOKEN_HEALTH_TTL = timedelta(minutes=30)
_token_health_cache: dict[str, Any] = {"at": None, "value": None}


def bust_token_health_cache() -> None:
    _token_health_cache["at"] = None
    _token_health_cache["value"] = None


async def _debug_token(token: str) -> dict:
    """Ask Meta about one token, using the token itself as the caller (no app
    secret needed). Returns validity + expiry. Best-effort — never raises; a
    check that couldn't run reports ``checked=False``. An expired token used as
    its own caller comes back as a top-level 190 error, which reads here as
    ``valid=False`` (the actionable signal), so we don't get an expiry date for
    one that's already dead — that's fine, "it's dead" is the whole message."""
    out: dict[str, Any] = {
        "configured": bool(token), "checked": False, "valid": None,
        "expires_at": None, "days_left": None, "never": False,
        "type": None, "scopes": [], "error": None,
    }
    if not token:
        return out
    url = f"https://graph.facebook.com/{settings.meta_api_version}/debug_token"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, params={"input_token": token, "access_token": token})
        body = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError) as e:
        out["error"] = f"Could not reach Meta: {e}"
        return out

    out["checked"] = True
    err = body.get("error") if isinstance(body, dict) else None
    if resp.status_code != 200 or err:
        out["valid"] = False
        out["error"] = (err or {}).get("message") or f"HTTP {resp.status_code}"
        return out

    data = (body.get("data") or {}) if isinstance(body, dict) else {}
    out["valid"] = bool(data.get("is_valid"))
    out["type"] = data.get("type")
    out["scopes"] = data.get("scopes") or []
    if not out["valid"]:
        out["error"] = (data.get("error") or {}).get("message") or "Token reports not valid."
    exp = data.get("expires_at")
    if exp == 0:
        out["never"] = True  # 0 = never expires (a properly-issued system-user token)
    elif exp:
        dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        out["expires_at"] = dt.isoformat()
        out["days_left"] = (dt - datetime.now(timezone.utc)).days
    return out


def _token_needs_attention(t: dict) -> bool:
    """A configured token that is failing, or expiring within the warn window.
    A blank token is NOT attention — an unset CAPI token is a deliberate
    "server-side events off" state, and an unset ads token has its own big
    empty-state on the page already."""
    if not t["configured"] or not t["checked"]:
        return False
    if t["valid"] is False:
        return True
    return t["days_left"] is not None and t["days_left"] <= TOKEN_WARN_WITHIN_DAYS


async def token_health(*, force: bool = False) -> dict:
    """Health of both Meta tokens — the ads_read dashboard token
    (settings.meta_access_token) and the CAPI write token
    (settings.meta_capi_access_token). ``attention`` is the one boolean the
    sidebar badge and the daily scheduler check read: True when either
    configured token is invalid/expired or within the warn window. Cached for
    _TOKEN_HEALTH_TTL. Never raises."""
    now = datetime.now(timezone.utc)
    cached = _token_health_cache["value"]
    if not force and cached is not None and _token_health_cache["at"] \
            and now - _token_health_cache["at"] < _TOKEN_HEALTH_TTL:
        return cached

    ads = await _debug_token(settings.meta_access_token)
    ads["purpose"] = "ads_read"
    capi = await _debug_token(settings.meta_capi_access_token)
    capi["purpose"] = "capi"
    result = {
        "ads": ads,
        "capi": capi,
        "attention": _token_needs_attention(ads) or _token_needs_attention(capi),
        "warn_within_days": TOKEN_WARN_WITHIN_DAYS,
    }
    _token_health_cache["at"] = now
    _token_health_cache["value"] = result
    return result


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
        r["utm_campaign"] = meta.get("utm_campaign")
        r["stream"] = stream_for_ad(r["ad_id"], r.get("ad_name"))
        r["ends_on"] = meta.get("ends_on")
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


# A single campaign-wide funnel USED TO LIVE HERE (compute_funnel) and was
# removed in the 8-9 Sep restructure rather than relabelled. It put
# campaign-wide impressions, clicks and landing page views above a "Completed
# registrations" figure that only ever counted TRIAL signups — fine while the
# campaign sold one thing, and a mixed-unit chart the moment the webinar ad
# started spending: the drop at the bottom read as a conversion collapse when
# it was really two products sharing one column. compute_stream_funnel() builds
# one funnel per stream instead, each ending in its own result.


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
    as its own stage in the trial funnel (compute_stream_funnel) between
    landing_page_views and leads. Scoped to Meta traffic only (the same signal get_selected_clubs
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
    key/label/value/pct_of_top/pct_of_prev shape as compute_stream_funnel() so the
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
                    campaign_budget: float, campaign_length_days: int,
                    streams: list[dict] | None = None) -> list[dict]:
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
    #
    # MEASURED FROM THE LAST DELIBERATE CHANGE, NEVER ACROSS IT. The 8 Sep
    # restructure cut the daily budget from A$50 to A$30, so a rate averaged
    # over both halves describes a campaign that no longer exists and would
    # read as "overspending" for weeks after a deliberate cut.
    #
    # SPEND IS NOT SUBJECT TO THE 7-DAY ATTRIBUTION WINDOW and this block does
    # not pretend it is. Meta attributes a CONVERSION to the date of the click
    # and back-fills it for 7 days; money spent on a given day is settled that
    # day. So pacing excludes only today, which is a part-day, and the
    # provisional-window guard below applies to the conversion insights it
    # genuinely bites on. (An earlier cut gated pacing on the attribution
    # window too, which made it unanswerable for a week after every change —
    # the two conditions are contradictory the day a change lands.)
    change_date = _last_change_date()
    today = date.today()
    pacing_days = [
        d for d in daily_history
        if (d.get("spend") or 0) > 0
        and (not change_date or (_parse_insights_date(d.get("date")) or date.min) >= change_date)
        and (_parse_insights_date(d.get("date")) or date.min) < today
    ]
    if campaign_budget and len(pacing_days) >= 2:
        window_spend = sum(d.get("spend") or 0.0 for d in pacing_days)
        daily_rate = window_spend / len(pacing_days)
        projected = daily_rate * campaign_length_days
        since = f" (measured since the {change_date.strftime('%-d %b')} change)" if change_date else ""
        if projected > campaign_budget * 1.15:
            over_pct = round((projected / campaign_budget - 1) * 100)
            insights.append({
                "severity": "warning",
                "title": "Overspending the budget pace",
                "detail": f"On track for ~${projected:.0f} of ${campaign_budget:.0f} by day {campaign_length_days} ({over_pct}% over){since}. Trim spend or pause the weaker ads.",
            })
        elif projected < campaign_budget * 0.7:
            insights.append({
                "severity": "info",
                "title": "Under-pacing the budget",
                "detail": f"On track for only ~${projected:.0f} of ${campaign_budget:.0f} by day {campaign_length_days}{since}. Room to spend more if the ads below are working.",
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

    # Per-stream cost, stated separately and never averaged. Two ads selling
    # two different things at very different prices is the ordinary state of
    # this campaign now, so this reports the pair rather than flagging the gap
    # between them as a fault.
    priced = [s for s in (streams or []) if s.get("cost_per_result") and s.get("spend", 0) >= 5]
    if len(priced) >= 2:
        cheapest = min(priced, key=lambda s: s["cost_per_result"])
        dearest = max(priced, key=lambda s: s["cost_per_result"])
        if cheapest["stream"] != dearest["stream"]:
            insights.append({
                "severity": "info",
                "title": "Two results at two prices",
                "detail": (
                    f"{cheapest['label']} cost ${cheapest['cost_per_result']:.2f} each, "
                    f"{dearest['label']} ${dearest['cost_per_result']:.2f}. Different things at "
                    "different prices — worth comparing each against what it's worth, not against each other."
                ),
            })
    # A change younger than the attribution window means every conversion
    # figure describing the period after it is still filling in. Say so once,
    # and hold back the conversion-shortfall warnings below rather than
    # reporting a stream as failing when its results simply haven't landed yet.
    settling = bool(change_date and (today - change_date).days < ATTRIBUTION_WINDOW_DAYS)
    if settling:
        insights.append({
            "severity": "info",
            "title": "Results since the change are still settling",
            "detail": (
                f"The campaign changed on {change_date.strftime('%-d %b')} and Meta attributes "
                f"conversions to the click date over {ATTRIBUTION_WINDOW_DAYS} days, so anything "
                "after it will keep filling in. Spend is settled; results are not."
            ),
        })

    for stream in (streams or []):
        # An ad that has ended stops being a live performance question. Say so
        # once rather than letting it read as a stream that stopped converting.
        if stream.get("ended"):
            insights.append({
                "severity": "info",
                "title": f"{stream['label']} has finished",
                "detail": (
                    f"The ads behind it ended on {stream['ends_on']}. "
                    f"${stream['spend']:.0f} spent, {stream['results']} registered"
                    + (f" (${stream['cost_per_result']:.2f} each)." if stream.get("cost_per_result") else ".")
                ),
            })
        elif (not settling and stream.get("spend", 0) >= 20 and stream.get("results") == 0
              and stream.get("landing_page_views", 0) >= 10):
            insights.append({
                "severity": "warning",
                "title": f"No {stream['label'].lower()} yet",
                "detail": (
                    f"${stream['spend']:.0f} spent and {stream['landing_page_views']:.0f} landing page views, "
                    "with nothing registered. Check the form on that page works from a real ad click."
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


def _all_known_utm_contents() -> frozenset[str]:
    """Every utm_content tag ANY campaign's ads use (AD_DESTINATIONS), across
    all campaigns. A signup carrying one of these is tied to a specific
    campaign, so — once it has failed the current-campaign checks — it must NOT
    be swept in by the generic Meta-click fallback: it demonstrably belongs to
    a different campaign. Case-sensitive, matching the current-campaign check."""
    return frozenset(
        meta["utm_content"] for meta in AD_DESTINATIONS.values() if meta.get("utm_content")
    )


def _all_known_utm_campaigns() -> frozenset[str]:
    """Every utm_campaign tag ANY campaign's ads use (CAMPAIGN_UTM_CAMPAIGNS),
    lowercased to match the current-campaign check. Same purpose as
    _all_known_utm_contents: a recognised tag names a campaign, so it can't fall
    through to the campaign-agnostic fallback."""
    return frozenset(
        name.lower() for names in CAMPAIGN_UTM_CAMPAIGNS.values() for name in names
    )


def _attribution_matches_campaign(attribution: dict | None) -> bool:
    """True if a stored signup_attribution counts as a registration for the
    CURRENT campaign (_campaign_id()), checked three independent ways — any
    one is enough:
    1. its utm_content is one AD_DESTINATIONS maps to this campaign;
    2. its utm_campaign is one of the tags this campaign's ads use
       (CAMPAIGN_UTM_CAMPAIGNS — a SET since the 8-9 Sep restructure, when one
       campaign started running two destination taxonomies). More resilient
       than (1): doesn't need AD_DESTINATIONS kept in sync with every new ad;
    3. it otherwise carries a plain Meta click signal (a fb/ig/meta
       utm_source, or a facebook/instagram click_source) AND carries no UTM
       tag that names a DIFFERENT known campaign — the loosest check, a safety
       net so a genuine Meta-driven registration doesn't vanish from the count
       just because its exact utm_content/utm_campaign isn't in the maps yet.

       That last guard is what makes this campaign-SPECIFIC. Before it, the
       Meta-click fallback fired for every Meta-sourced signup regardless of
       which campaign it belonged to — so with more than one campaign in
       history the tile read the all-time tracked total against WHICHEVER
       campaign the dropdown had selected (spend/LPV filter by campaign_id, but
       a signup carries only its UTM tags, so this is the equivalent filter).
       A signup whose utm_content or utm_campaign is a recognised tag has
       already been tested against THIS campaign in checks 1-2; if neither
       fired, the tag names another campaign and the registration is not ours,
       however it clicked in. Only a signup with no campaign-identifying tag at
       all (or one tagged for a campaign not yet in the maps) reaches the
       generic fallback.
    Used by get_registration_count() and the ad-signups report
    (routers/meta_ads.py) so the two can never disagree."""
    if not attribution:
        return False
    utm_content = (attribution.get("utm_content") or "").strip()
    if utm_content and utm_content in _current_campaign_utm_contents():
        return True
    utm_campaign = (attribution.get("utm_campaign") or "").strip().lower()
    known = CAMPAIGN_UTM_CAMPAIGNS.get(_campaign_id()) or set()
    if utm_campaign and utm_campaign in {name.lower() for name in known}:
        return True
    # The tag names a different known campaign → this registration is that
    # campaign's, not the selected one. Don't let the generic fallback claim it.
    if utm_content and utm_content in _all_known_utm_contents():
        return False
    if utm_campaign and utm_campaign in _all_known_utm_campaigns():
        return False
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


async def get_registration_count_since(db: AsyncSession, since: date) -> dict:
    """Completed trial registrations attributed to the current campaign that
    happened on or after `since`.

    Shares `_attribution_matches_campaign` with get_registration_count above,
    so the windowed and lifetime figures can never disagree about what counts
    as a registration — only about when it happened.

    Orgs carry no created_at; the signup timestamp is the earliest
    `self_serve_idempotency_keys` row, the same source the ad-signups report
    uses. An attributed org with NO key row has no knowable signup date, so it
    cannot be placed in the window at all — it is counted as `undated` rather
    than dropped quietly or swept in, either of which would move a
    cost-per-result figure without saying so.

    The comparison is made in Postgres against a date, so the boundary is
    midnight in the database's own timezone. Meta's daily figures are in the ad
    account's timezone, so a few hours either side of a change date cannot be
    reconciled exactly by anything here — immaterial for "before or after the
    restructure", and not worth implying a precision we do not have.
    """
    await _use_active_campaign(db)
    rows = (await db.execute(text("""
        SELECT o.signup_attribution AS attribution,
               MIN(k.created_at) AS signed_up_at
          FROM organisations o
          LEFT JOIN self_serve_idempotency_keys k ON k.org_id = o.id
         WHERE o.signup_source IS NOT NULL
           AND o.archived_at IS NULL
           AND o.signup_attribution IS NOT NULL
         GROUP BY o.id, o.signup_attribution
    """))).mappings().all()

    count = 0
    undated = 0
    for row in rows:
        if not _attribution_matches_campaign(row["attribution"]):
            continue
        at = row["signed_up_at"]
        if at is None:
            undated += 1
        elif at.date() >= since:
            count += 1
    return {"count": count, "undated": undated}


async def get_webinar_registration_counts(db: AsyncSession) -> dict:
    """Webinar registrations (`webinar_registrations`, migration 296) split by
    whether they can be attributed to the CURRENT Meta campaign.

    THE UNATTRIBUTED COUNT IS REPORTED, NOT ABSORBED, and that is deliberate.
    The webinar ad's primary text carries a plain-text link (betterat.cricket/demo)
    with no UTMs on it — it had to match a line printed on the artwork — so a
    minority of genuinely ad-driven registrations arrive carrying no campaign
    signal at all and are indistinguishable from an organic one. Counting them
    as ours would inflate the ad's result; hiding them would make the shortfall
    look like a tracking fault. So the cost-per-result figure is computed on
    the attributed count alone (which reads HIGH, the safe direction) and the
    unattributed count rides alongside so a reader knows the true figure sits
    somewhere between.

    Scoped to the event, not to a date window: a registration for the 21 Sep
    webinar is a result of this campaign whenever it happened."""
    await _use_active_campaign(db)
    from app.services import webinar

    rows = (await db.execute(text("""
        SELECT utm_source, utm_campaign, utm_content, click_source
          FROM webinar_registrations
         WHERE event_key = :event_key
    """), {"event_key": webinar.EVENT.key})).mappings().all()

    attributed = 0
    unattributed = 0
    for row in rows:
        if _attribution_matches_campaign(dict(row)):
            attributed += 1
        elif not any((row["utm_source"], row["utm_campaign"],
                      row["utm_content"], row["click_source"])):
            # No campaign signal of ANY kind — the untagged in-ad link, or a
            # genuinely organic registration. The two cannot be told apart.
            unattributed += 1
    return {
        "attributed": attributed,
        "unattributed": unattributed,
        "total": len(rows),
        "event_key": webinar.EVENT.key,
        "event_date": webinar.EVENT.starts_at.date().isoformat(),
        "is_past": webinar.EVENT.is_past(),
    }


async def get_webinar_registration_count_since(db: AsyncSession, since: date) -> int:
    """Attributed webinar registrations received on or after `since`.

    The lifetime count above is deliberately scoped to the EVENT rather than to
    a date — a registration for the 21 Sep webinar is a result of this campaign
    whenever it arrived. This one exists only for the since-the-change block,
    where both streams have to be measured over the same stretch of calendar or
    their cost-per-result figures are not comparable. The webinar ad started at
    the restructure, so today the two counts are the same; they stop being the
    same at the next change.

    Attributed only, per the lifetime rule: the untagged in-ad link means a
    minority of genuine registrations carry no campaign signal, and counting
    those would inflate the ad's result."""
    await _use_active_campaign(db)
    from app.services import webinar

    rows = (await db.execute(text("""
        SELECT utm_source, utm_campaign, utm_content, click_source
          FROM webinar_registrations
         WHERE event_key = :event_key AND created_at >= :since
    """), {"event_key": webinar.EVENT.key, "since": since})).mappings().all()
    return sum(1 for row in rows if _attribution_matches_campaign(dict(row)))


def stream_totals(ads: list[dict]) -> dict[str, dict]:
    """Meta's own delivery figures summed PER STREAM from the per-ad rows.

    Spend has to be split this way or every cost-per-result on the page is
    wrong: the campaign-level spend now covers both products, so dividing it by
    trial signups charges the trial with the webinar's spend, and vice versa.
    Ad-level is the finest split Meta gives us and the streams are cleanly
    separable there (see stream_for_ad), so this is exact rather than
    apportioned."""
    totals = {
        stream: {
            "stream": stream,
            "label": STREAM_LABELS[stream],
            "spend": 0.0, "impressions": 0.0, "link_clicks": 0.0,
            "landing_page_views": 0.0, "leads": 0.0,
            "ad_count": 0, "active_ad_count": 0,
        }
        for stream in STREAMS
    }
    for ad in ads:
        stream = ad.get("stream") or stream_for_ad(ad.get("ad_id"), ad.get("ad_name"))
        bucket = totals.get(stream)
        if bucket is None:
            continue
        for key in ("spend", "impressions", "link_clicks", "landing_page_views", "leads"):
            bucket[key] += ad.get(key) or 0.0
        bucket["ad_count"] += 1
        if (ad.get("delivery_status") or "ACTIVE") == "ACTIVE":
            bucket["active_ad_count"] += 1
    for bucket in totals.values():
        bucket["spend"] = round(bucket["spend"], 2)
        bucket["cost_per_lpv"] = (
            round(bucket["spend"] / bucket["landing_page_views"], 2)
            if bucket["landing_page_views"] > 0 else None
        )
    return totals


async def stream_totals_since(db: AsyncSession, since: date) -> dict:
    """Per-stream delivery figures summed from the TRUE daily per-ad rows
    (level='ad_daily') on or after `since`.

    stream_totals() above reads the level='ad' rows, which are LIFETIME totals.
    Right for "what has this campaign cost in all", wrong for "what are we
    paying now": the trial's lifetime spend is mostly the regime that ran
    BEFORE the 8 Sep restructure (A$50/day, broad targeting, all placements,
    Instagram on), while the webinar stream has no pre-change history at all.
    So the two lifetime cost-per-result figures describe two different
    campaigns and must never be read against each other.

    `covers_from` is the earliest daily row actually held. A window that starts
    after `since` is missing spend, which reads LOW and would UNDERSTATE cost
    per result — the direction that flatters the campaign — so it is reported
    and the caller withholds the division rather than printing a wrong number.
    """
    await _use_active_campaign(db)
    rows = (await db.execute(text("""
        SELECT ad_id, ad_name, spend, impressions, link_clicks,
               landing_page_views, leads
          FROM meta_ad_snapshots
         WHERE level = 'ad_daily' AND campaign_id = :campaign_id
           AND snapshot_date >= :since
    """), {"campaign_id": _campaign_id(), "since": since})).mappings().all()

    earliest = (await db.execute(text("""
        SELECT MIN(snapshot_date) FROM meta_ad_snapshots
         WHERE level = 'ad_daily' AND campaign_id = :campaign_id
    """), {"campaign_id": _campaign_id()})).scalar()

    totals = {
        stream: {"spend": 0.0, "impressions": 0.0, "link_clicks": 0.0,
                 "landing_page_views": 0.0, "leads": 0.0}
        for stream in STREAMS
    }
    for r in rows:
        stream = stream_for_ad(r["ad_id"], r["ad_name"])
        bucket = totals.get(stream)
        if bucket is None:
            continue
        bucket["spend"] += float(r["spend"] or 0)
        bucket["impressions"] += float(r["impressions"] or 0)
        bucket["link_clicks"] += float(r["link_clicks"] or 0)
        bucket["landing_page_views"] += float(r["landing_page_views"] or 0)
        bucket["leads"] += float(r["leads"] or 0)
    for bucket in totals.values():
        bucket["spend"] = round(bucket["spend"], 2)

    return {
        "totals": totals,
        "covers_from": earliest,
        # Held data starts after the date asked for, so the sum is short of the
        # real spend since the change.
        "partial": bool(earliest and earliest > since),
    }


def _since_change_block(stream: str, since_change: dict | None) -> dict | None:
    """One stream's figures since the last deliberate campaign change, or None
    when there has been no change to measure from.

    THE WHOLE POINT IS COMPARABILITY. Lifetime, the trial carries months of
    pre-restructure spend and the webinar carries none, so the two cost-per-
    result figures are not answering the same question. Measured from the
    change, both describe the campaign as it runs today.

    Three things are deliberately withheld rather than guessed at:

    * A PARTIAL WINDOW yields no cost per result. If the daily rows we hold
      start after the change, the spend is short of what was really spent, so
      the division would UNDERSTATE the cost — the direction that makes the
      campaign look better than it is.
    * NO RESULTS YET yields no cost per result, the same rule the lifetime
      figure keeps. An ad set that has not converted is not an infinitely
      expensive one.
    * SPEND IS SETTLED, RESULTS ARE NOT. Meta credits a conversion to the date
      of the click and back-fills for 7 days, so a cost per result computed
      inside that window is a ceiling that will come down. It is marked
      provisional and nothing alerts off it.
    """
    if not since_change:
        return None
    since = since_change["since"]
    totals = (since_change.get("totals") or {}).get(stream) or {}
    results = int((since_change.get("results") or {}).get(stream) or 0)
    spend = round(float(totals.get("spend") or 0.0), 2)
    partial = bool(since_change.get("partial"))
    today = date.today()
    days = max(0, (today - since).days)
    # Inside the attribution window the results behind this figure are still
    # arriving, so the cost reads HIGH and will fall.
    provisional = days < ATTRIBUTION_WINDOW_DAYS

    block = {
        "since": since.isoformat(),
        "days": days,
        "spend": spend,
        "results": results,
        "impressions": round(float(totals.get("impressions") or 0.0)),
        "link_clicks": round(float(totals.get("link_clicks") or 0.0)),
        "landing_page_views": round(float(totals.get("landing_page_views") or 0.0)),
        "leads": round(float(totals.get("leads") or 0.0)),
        "partial": partial,
        "provisional": provisional,
        "cost_per_result": None,
        "withheld_reason": None,
    }
    if partial:
        block["withheld_reason"] = "partial_window"
    elif results <= 0:
        block["withheld_reason"] = "no_results_yet"
    elif spend <= 0:
        block["withheld_reason"] = "no_spend_yet"
    else:
        block["cost_per_result"] = round(spend / results, 2)
    return block


def build_streams(ads: list[dict], campaign: dict, *, trial_results: int,
                  webinar_counts: dict, club_selected: float = 0,
                  since_change: dict | None = None) -> list[dict]:
    """The two streams as the page reads them: delivery figures, the result
    that stream actually produced, its own cost per result, and its own funnel.

    `trial_results` and the webinar counts come from OUR OWN database — a real
    completed registration — never from Meta's self-reported action counts,
    which cannot tell the two CompleteRegistration events apart at all without
    a breakdown we don't fetch. Meta's `leads` is kept alongside as the
    self-reported comparison, clearly labelled as that."""
    totals = stream_totals(ads)
    webinar_results = webinar_counts.get("attributed", 0)
    results_by_stream = {STREAM_TRIAL: trial_results, STREAM_WEBINAR: webinar_results}

    out: list[dict] = []
    for stream in STREAMS:
        bucket = dict(totals[stream])
        results = results_by_stream.get(stream, 0)
        bucket["results"] = results
        bucket["result_label"] = STREAM_LABELS[stream]
        bucket["content_category"] = STREAM_CONTENT_CATEGORIES[stream]
        # Divide only when there is something to divide by — an ad set that has
        # not converted yet, and one whose ads have ended, both land here.
        bucket["cost_per_result"] = (
            round(bucket["spend"] / results, 2) if results > 0 and bucket["spend"] > 0 else None
        )
        # ONLY the trial carries a value. A webinar registration is worth
        # nothing on the books, so it contributes nothing here — folding it in
        # at the trial's 399 would invent revenue out of form fills.
        unit_value = STREAM_VALUE_AUD[stream]
        bucket["unit_value_aud"] = unit_value
        bucket["attributed_value_aud"] = round(results * unit_value, 2) if unit_value else 0.0
        bucket["carries_value"] = unit_value > 0
        bucket["roas"] = (
            round(bucket["attributed_value_aud"] / bucket["spend"], 2)
            if unit_value and bucket["spend"] > 0 else None
        )
        # An ad that has ended stops the stream reading as a live campaign
        # whose result rate is collapsing.
        ends = [
            _parse_insights_date((AD_DESTINATIONS.get(a.get("ad_id") or "") or {}).get("ends_on"))
            for a in ads
            if (a.get("stream") or stream_for_ad(a.get("ad_id"), a.get("ad_name"))) == stream
        ]
        ends = [d for d in ends if d]
        bucket["ends_on"] = max(ends).isoformat() if ends else None
        bucket["ended"] = bool(ends) and max(ends) < date.today()
        bucket["funnel"] = compute_stream_funnel(
            bucket, results,
            club_selected=club_selected if stream == STREAM_TRIAL else None,
        )
        if stream == STREAM_WEBINAR:
            bucket["unattributed_results"] = webinar_counts.get("unattributed", 0)
            bucket["total_registrations"] = webinar_counts.get("total", 0)
        bucket["since_change"] = _since_change_block(stream, since_change)
        out.append(bucket)

    # Whatever the campaign spent that no ad row accounts for (a deleted ad, a
    # rounding gap). Surfaced rather than silently folded into one stream —
    # a cost-per-result quietly carrying someone else's spend is the bug this
    # whole split exists to remove.
    attributed_spend = round(sum(s["spend"] for s in out), 2)
    campaign_spend = round(campaign.get("spend") or 0.0, 2)
    return out, round(campaign_spend - attributed_spend, 2)


def compute_stream_funnel(bucket: dict, results: int, club_selected: float | None = None) -> list[dict]:
    """One stream's own funnel, impressions through to its own result.

    Built per stream rather than campaign-wide because the campaign-wide
    version mixed units the moment the webinar ad started spending: its
    impressions and clicks sat above a "completed registrations" figure that
    only ever counted trial signups, so the drop-off at the bottom read as a
    conversion collapse when it was two products in one column.

    "Club selected" only exists on the trial path (it is a step in the
    registration wizard), so the webinar funnel goes straight from a landing
    page view to a registration — which is what that page actually asks for."""
    stages_raw = [
        ("impressions", "Impressions", bucket.get("impressions") or 0),
        ("link_clicks", "Link clicks", bucket.get("link_clicks") or 0),
        ("landing_page_views", "Landing page views", bucket.get("landing_page_views") or 0),
    ]
    if club_selected is not None:
        stages_raw.append(("club_selected", "Club selected", club_selected or 0))
        stages_raw.append(("leads", "Started registering (Meta-reported)", bucket.get("leads") or 0))
    stages_raw.append(("results", bucket.get("result_label") or "Results", results or 0))

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


async def get_creative_performance(db: AsyncSession, ads: list[dict]) -> list[dict]:
    """Per-creative results, keyed on `utm_content` — the identifier that
    outlives the ad it was built on, so a creative's performance can be
    compared across campaigns and across a rebuild in Ads Manager.

    Spend comes from Meta (per ad, mapped to its creative tag); the results
    come from our own tables. A creative's results are counted by the tag on
    the registration, so a webinar-ad click that went on to start a trial is
    credited to the webinar creative as a TRIAL result — which is what
    happened, and worth seeing."""
    await _use_active_campaign(db)
    from app.services import webinar

    trial_tags = (await db.execute(text("""
        SELECT signup_attribution FROM organisations
         WHERE signup_source IS NOT NULL
           AND archived_at IS NULL
           AND signup_attribution IS NOT NULL
    """))).scalars().all()
    webinar_tags = (await db.execute(text("""
        SELECT utm_source, utm_campaign, utm_content, click_source
          FROM webinar_registrations
         WHERE event_key = :event_key
    """), {"event_key": webinar.EVENT.key})).mappings().all()

    rows: dict[str, dict] = {}

    def _bucket(tag: str | None, stream: str) -> dict:
        key = (tag or "").strip() or "(untagged)"
        return rows.setdefault(key, {
            "utm_content": key, "stream": stream, "ad_name": None,
            "spend": 0.0, "trial_signups": 0, "webinar_registrations": 0,
            "impressions": 0.0, "link_clicks": 0.0, "landing_page_views": 0.0,
        })

    for ad in ads:
        stream = ad.get("stream") or stream_for_ad(ad.get("ad_id"), ad.get("ad_name"))
        bucket = _bucket(ad.get("utm_content"), stream)
        bucket["ad_name"] = bucket["ad_name"] or ad.get("name")
        bucket["stream"] = stream
        for key in ("spend", "impressions", "link_clicks", "landing_page_views"):
            bucket[key] += ad.get(key) or 0.0

    for attribution in trial_tags:
        if _attribution_matches_campaign(attribution):
            tag = (attribution or {}).get("utm_content")
            _bucket(tag, stream_for_attribution(attribution) or STREAM_TRIAL)["trial_signups"] += 1
    for row in webinar_tags:
        if _attribution_matches_campaign(dict(row)):
            _bucket(row["utm_content"], STREAM_WEBINAR)["webinar_registrations"] += 1

    out = []
    for bucket in rows.values():
        bucket["spend"] = round(bucket["spend"], 2)
        results = bucket["trial_signups"] + bucket["webinar_registrations"]
        bucket["results"] = results
        bucket["cost_per_result"] = (
            round(bucket["spend"] / results, 2) if results > 0 and bucket["spend"] > 0 else None
        )
        bucket["cost_per_lpv"] = (
            round(bucket["spend"] / bucket["landing_page_views"], 2)
            if bucket["landing_page_views"] > 0 else None
        )
        # A creative's results are one stream's or the other's, never a sum of
        # both presented as one figure — the row carries each separately and
        # the total is only ever used to rank.
        out.append(bucket)
    out.sort(key=lambda b: (-b["results"], -b["spend"]))
    return out


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
                "streams": [], "creatives": [], "unattributed_spend": 0.0,
                "annotations": campaign_annotations(),
                "attribution_window_days": ATTRIBUTION_WINDOW_DAYS,
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
    webinar_counts = await get_webinar_registration_counts(db)

    campaign = _row_to_dict(campaign_row)
    campaign["leads_adjustment"] = adjustment
    # THE TRIAL'S OWN RESULT COUNT, and it is named that way on purpose. This
    # reads `organisations`, so it has only ever counted trial signups — the
    # danger was never that it double-counted, it was that the SPEND it used
    # to be divided by covers both products (see cost_per_result below).
    campaign["registrations"] = registrations
    campaign["leads_effective"] = max(0.0, registrations + adjustment)
    campaign["webinar_registrations"] = webinar_counts

    ads = [_row_to_dict(r) for r in ad_rows]
    for ad in ads:
        meta = AD_DESTINATIONS.get(ad["ad_id"], {})
        ad["name"] = ad.get("ad_name") or meta.get("name") or ad["ad_id"]
        ad["destination"] = meta.get("destination")
        ad["utm_content"] = meta.get("utm_content")
        ad["utm_campaign"] = meta.get("utm_campaign")
        ad["stream"] = stream_for_ad(ad["ad_id"], ad.get("ad_name"))
        ad["ends_on"] = meta.get("ends_on")
        ad["status"] = ad_status(ad, ads)
        ad["cost_per_lead"] = round(ad["spend"] / ad["leads"], 2) if ad["leads"] > 0 else None
        ad["note"] = ad_note(ad, ads)

    # Used for both the funnel/pacing insights below AND the default trend
    # chart window — a fixed lookback covering the whole campaign length so
    # pacing maths isn't skewed by whatever `days` window the trend charts
    # happen to be showing at the time.
    daily_history = await get_history(db, days=campaign_length_days + 5)
    club_selected = await get_club_selected_count(db)

    # SINCE THE LAST DELIBERATE CHANGE, alongside the lifetime figures.
    # Lifetime, the trial carries months of pre-restructure spend and the
    # webinar carries none, so reading one cost per result against the other
    # compares two different campaigns. Measured from the change, both describe
    # the campaign as it runs now — which is the question the page is actually
    # asked. The manual leads adjustment is NOT applied here: it is a lifetime
    # correction and may well relate to a signup from before the change.
    change_date = _last_change_date()
    since_change = None
    if change_date:
        spend_since = await stream_totals_since(db, change_date)
        trial_since = await get_registration_count_since(db, change_date)
        since_change = {
            "since": change_date,
            "totals": spend_since["totals"],
            "partial": spend_since["partial"],
            "results": {
                STREAM_TRIAL: trial_since["count"],
                STREAM_WEBINAR: await get_webinar_registration_count_since(db, change_date),
            },
            "undated_trial_results": trial_since["undated"],
        }

    streams, unattributed_spend = build_streams(
        ads, campaign,
        trial_results=int(campaign["leads_effective"]),
        webinar_counts=webinar_counts,
        club_selected=club_selected,
        since_change=since_change,
    )
    by_stream = {s["stream"]: s for s in streams}

    # `cost_per_lead` is kept under its old name for anything still reading it,
    # but is now the TRIAL's own cost per signup — trial spend over trial
    # signups. It used to be whole-campaign spend over trial signups, which
    # charged the trial with the webinar's spend from the moment both ran in
    # one campaign, and would have gone on quietly overstating it.
    campaign["cost_per_lead"] = by_stream[STREAM_TRIAL]["cost_per_result"]
    campaign["cost_per_trial_signup"] = by_stream[STREAM_TRIAL]["cost_per_result"]
    campaign["cost_per_webinar_registration"] = by_stream[STREAM_WEBINAR]["cost_per_result"]

    insights = build_insights(campaign, ads, daily_history, campaign_budget,
                              campaign_length_days, streams=streams)

    return {
        "campaign": campaign,
        "ads": ads,
        "streams": streams,
        "creatives": await get_creative_performance(db, ads),
        "unattributed_spend": unattributed_spend,
        "annotations": campaign_annotations(),
        "attribution_window_days": ATTRIBUTION_WINDOW_DAYS,
        # An attributed trial signup we hold no timestamp for can't be placed
        # either side of the change, so it counts lifetime and not since.
        # Reported so a short since-the-change count reads as a known gap
        # rather than as the ads having stopped working.
        "undated_trial_results": (since_change or {}).get("undated_trial_results", 0),
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
    # Meta attributes a conversion to the date of the CLICK on a 7-day window,
    # so the most recent 7 days always under-report and fill in retrospectively.
    # Flagged rather than hidden: the days are real, they are just not finished.
    # The charts draw them differently and nothing alerts off them.
    provisional_from = _provisional_from()
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
            "provisional": r["snapshot_date"] >= provisional_from,
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
    # Meta attributes a conversion to the date of the CLICK on a 7-day window,
    # so the most recent 7 days always under-report and fill in retrospectively.
    # Flagged rather than hidden: the days are real, they are just not finished.
    # The charts draw them differently and nothing alerts off them.
    provisional_from = _provisional_from()
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
            "provisional": r["snapshot_date"] >= provisional_from,
        }
        for r in rows
    ]
