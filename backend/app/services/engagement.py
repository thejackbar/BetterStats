"""How engaged a club is, scored from our own data.

The one definition of a club's engagement score and tier, plus the club
resolution the CRM and the Clubs Directory share. Everything here is a local
read/compute over our own tables (``usage_events``, ``email_events``,
``club_onboarding_requests``, the club's subscriptions); nothing in this module
calls anything outside BetterCricket.

``_engagement`` caches its result onto the club row itself
(``marketing_clubs.engagement_score`` / ``.engagement_tier`` /
``.engagement_scored_at`` — see ``_apply_engagement_cache``), and that cached
number is what the Club Directory, BetterComms Contacts/Lists/Segments, the CRM
board and the Sales Workspace all read. ``crm.recalc_all_engagement`` is the
platform-wide sweep (nightly, and the Directory's own Refresh button); a single
club is rescored inline wherever a real signal already has a session and a club
in hand.

HISTORY: this was ``services/twenty_sync.py``, and the scoring engine lived
inside the Twenty CRM exporter purely because that is where it was first
needed. Twenty was retired in Sep 2026 and its I/O deleted; the engine it had
grown around is what remains, under a name that says what it does. Nothing
about the scoring changed in that move.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MarketingClub, MarketingClubContact, Organisation
from app.services import engagement_params, platform_settings, trial_engagement
from app.services.club_directory import _PATH_CODE, _RESOLVED_CID

# A club's engagement score at or above this crosses from "worth watching" to
# "start the deal". Kept as the published threshold the pipeline reads; the
# external CRM lane that once auto-created an Opportunity at it is retired.
OPPORTUNITY_AUTO_THRESHOLD = engagement_params.DEFAULTS["OPPORTUNITY_AUTO_THRESHOLD"]

# --- Engagement scoring weights -------------------------------------------------
# EVERY NUMBER BELOW IS NOW A SUPER-ADMIN EDITABLE PARAMETER. The catalogue, the
# defaults, validation and the stored overrides all live in
# services/engagement_params.py; these module constants are just its defaults
# re-exported under the names the rest of the codebase already greps for.
#
# Read them ONLY as a fallback for a code path with no session in hand. Anything
# that actually scores a club takes a resolved ``params`` dict and reads from
# that, or it will keep using the defaults after a Super Admin has changed them.
# Resolve once per call chain (engagement_params.get_params) and pass it down —
# never per club inside a sweep.
#
# Per-event decay: each web/email event is scored by ITS OWN age and the scores
# are summed. Ages beyond the last tier score 0 — the ``d90`` tier plus the
# ``ELSE 0`` gives every sum an outer 90-day window, so a club's years of history
# can't quietly peg the depth curve (the sum is otherwise unbounded in age).
_D = engagement_params.DEFAULTS


def _curve(base: str, params: "Optional[dict]" = None) -> dict:
    """The five age tiers of one decay curve, as the ``{"d7": ...}`` shape the
    SQL builders read, pulled from a resolved params dict (or the defaults)."""
    src = params or _D
    return {tier.lower(): src[f"{base}_{tier}"]
            for tier in ("D7", "D14", "D21", "D28", "D90")}


WEB_DECAY = _curve("WEB_DECAY")
AD_DECAY = _curve("AD_DECAY")
EMAIL_CLICK_DECAY = _curve("EMAIL_CLICK_DECAY")
EMAIL_OPEN_DECAY = _curve("EMAIL_OPEN_DECAY")

REACH_PER_VISITOR = _D["REACH_PER_VISITOR"]
DEPTH_SCALE = _D["DEPTH_SCALE"]
RECENCY_FULL = _D["RECENCY_FULL"]
RECENCY_HALFLIFE_DAYS = _D["RECENCY_HALFLIFE_DAYS"]

BONUS_REQUESTED_TRIAL = _D["BONUS_REQUESTED_TRIAL"]
BONUS_IN_TRIAL = _D["BONUS_IN_TRIAL"]
BONUS_ONBOARDING = _D["BONUS_ONBOARDING"]
BONUS_CONTACT_PAGE = _D["BONUS_CONTACT_PAGE"]
BONUS_VISIT_TRIAL = _D["BONUS_VISIT_TRIAL"]
BONUS_AD_SIGNUP = _D["BONUS_AD_SIGNUP"]

CUSTOMER_BASE = _D["CUSTOMER_BASE"]
CUSTOMER_UPSELL_BONUS = _D["CUSTOMER_UPSELL_BONUS"]
CUSTOMER_ONBOARDING_BONUS = _D["CUSTOMER_ONBOARDING_BONUS"]

TIER_WARM_MIN = _D["TIER_WARM_MIN"]
TIER_HOT_MIN = _D["TIER_HOT_MIN"]
DIRECT_ENQUIRY_SCORE = _D["DIRECT_ENQUIRY_SCORE"]

# Meta / paid-click detection for a usage_events row: a Meta ad click lands with
# an fbclid (Facebook) or igshid (Instagram) in the URL, which record_event stores
# verbatim in ``path`` (query string included). Detected off ``path`` alone —
# usage_events has no dedicated click_source column in production, so the URL is
# the reliable, always-present signal (the same one routers/usage.py reads).
_META_CLICK = "(ue.path ~* '(fbclid|igshid)=')"

# Perth / Western Australia is AWST (UTC+8) year-round — no daylight saving —
# so a fixed +08:00 offset is exact. Used for the engagement up/down arrow's
# day-over-day ("yesterday vs today") boundary, which is a Perth calendar day.
_PERTH_TZ = datetime.timezone(datetime.timedelta(hours=8))


def _tier_for(score: float, params: "Optional[dict]" = None) -> str:
    src = params or _D
    return ("COLD" if score < src["TIER_WARM_MIN"]
            else "WARM" if score < src["TIER_HOT_MIN"] else "HOT")


logger = logging.getLogger(__name__)


# Modules are counted at the BILLABLE level: BetterAdmin is ONE module, so its
# members (fees/comms/merch — never sold or trialed on their own) collapse into
# 'admin'. Anything unrecognised is dropped. Result set: core / select / socials
# / admin / iq / fantasy.
_ADMIN_MEMBERS = frozenset({"fees", "comms", "merch"})
_BILLABLE_KEYS = frozenset({"core", "select", "socials", "iq", "fantasy"})


def _billing_modules(keys) -> set:
    """Module keys (entitlement or billing) -> the set of billable module values
    (lowercase). fees/comms/merch -> admin; unknown dropped. core (BetterStats) is a
    billable module now, so it passes through."""
    out: set = set()
    for k in (keys or []):
        kk = str(k).lower().strip()
        if kk in _ADMIN_MEMBERS or kk == "admin":
            out.add("admin")
        elif kk in _BILLABLE_KEYS:
            out.add(kk)
        # anything unrecognised is dropped (not a billable module)
    return out


def _module_labels(keys) -> list:
    """The uppercase billable-module list, as the engagement rollup reports it."""
    return sorted(k.upper() for k in _billing_modules(keys))


def _lifecycle(club: MarketingClub, is_paying: bool = False, all_unsub: bool = False) -> str:
    # Must be one of the Company lifecycleStage options (Target / Prospect /
    # Engaged / Trial / Customer / Churned / Suppressed). "Contacted" is an
    # Opportunity pipeline stage, NOT a company lifecycle value, so a contacted
    # club maps to Prospect here.
    #
    # ``is_paying`` = the linked org actually holds at least one PAID module
    # (``_module_split``'s ``paid`` list is non-empty) — NOT just "an
    # organisations row exists". Onboarding/syncing a club only pulls its CA
    # data in; it doesn't make them a customer, so a synced-but-not-yet-paying
    # club is a Prospect (it has a live deal on the pipeline), never
    # Customer.
    s = (club.status or "").lower()
    if is_paying or (club.demo_status or "") == "customer":
        return "CUSTOMER"
    # Every named-email officer has opted out — a marketing-suppression state
    # that overrides everything except an actual paying customer.
    if all_unsub:
        return "SUPPRESSED"
    if (club.demo_status or "") == "in_trial":
        return "TRIAL"
    # Requested a trial, or we've synced the club (an organisations row exists,
    # even without a paid module yet) — Prospect, not Customer.
    if club.existing_org_id or club.requested_trial_modules:
        return "PROSPECT"
    if s == "suppressed" or club.excluded:
        return "SUPPRESSED"
    if s == "contacted" or club.emailed_at:
        return "PROSPECT"
    return "TARGET"


def _recency_pts(last, params: "Optional[dict]" = None):
    """Recency points from a last-touch timestamp: a smooth exponential decay
    (RECENCY_FULL at 0 days, halving every RECENCY_HALFLIFE_DAYS), 0 if never.
    Continuous, so there are no step jumps at day boundaries. Deliberately modest
    so recency alone can't reach HOT — real frequency (repeat visits) or an
    explicit intent signal (trial request, contact form) has to carry a club
    over the line."""
    if not last:
        return 0.0
    src = params or _D
    days = max(0, (datetime.datetime.now(datetime.timezone.utc) - last).days)
    half_life = src["RECENCY_HALFLIFE_DAYS"] or 1
    return src["RECENCY_FULL"] * (0.5 ** (days / half_life))


async def _onboarding_signal(session, club: MarketingClub, utm: "Optional[str]",
                              org_slug: "Optional[str]" = None):
    """Has anyone asked, on the public site, for this club to be onboarded? Covers
    both the "Get your club on BetterCricket" quick modal and the full /contact
    "Request access" form — both post to the SAME ``club_onboarding_requests`` row
    (``routers/public_contact.py``), which carries no FK back to ``marketing_clubs``,
    so it's attributed here the same way email engagement is: by matching the
    submitter's email against a known officer of this club, OR (for a submitter who
    isn't yet a listed officer — the common case for a brand-new enquiry) by the
    anonymous visitor having arrived via this club's outreach UTM code OR this
    club's marketing-page path (``_PATH_CODE`` — a visitor who lands on
    /{club-slug}/... with no UTM param at all, then later submits Contact, needs
    attributing the same way ``_engagement``'s own web query does), OR an exact
    club-name match as a last resort. Returns (count, last_at)."""
    row = (await session.execute(text(f"""
        SELECT COUNT(*), MAX(cor.created_at)
        FROM club_onboarding_requests cor
        WHERE (cor.email IS NOT NULL AND cor.email <> '' AND lower(cor.email) IN (
                 SELECT lower(email) FROM marketing_club_contacts
                 WHERE marketing_club_id = :cid AND email IS NOT NULL AND email <> ''))
           OR (cor.visitor_id IS NOT NULL AND cor.visitor_id IN (
                 SELECT DISTINCT ue.visitor_id::text FROM usage_events ue
                 WHERE ue.visitor_id IS NOT NULL
                   AND ((CAST(:utm AS text) IS NOT NULL
                         AND (ue.utm_id = CAST(:utm AS text) OR ue.utm_source = CAST(:utm AS text)
                              OR {_PATH_CODE} = CAST(:utm AS text))
                         AND ue.user_id IS NULL
                         AND split_part(ue.path, '?', 1) !~* '^/admin')
                     OR (CAST(:org_slug AS text) IS NOT NULL AND {_PATH_CODE} = CAST(:org_slug AS text)))))
           OR (cor.club IS NOT NULL AND lower(cor.club) = lower(:name))
    """), {"cid": str(club.id), "utm": utm, "org_slug": org_slug, "name": club.name or ""})).first()
    return (row[0] or 0, row[1]) if row else (0, None)


def _apply_engagement_cache(club: MarketingClub, fields: dict,
                            keep_prev: bool = False) -> None:
    """Every _engagement() call caches its result onto the club row itself —
    marketing_clubs.engagement_score/.engagement_tier/.engagement_scored_at —
    regardless of what triggered the computation (the nightly rescore, the
    Directory's own Refresh button, a BetterComms send, or any single-club
    signal event), so the Club Directory / BetterComms Contacts+Lists /
    Segments can filter on a real number without recomputing this per-club
    scan themselves. Just sets attributes on the already-session-attached ORM
    object — the caller's own commit (every call site has one) persists it."""
    now = datetime.datetime.now(datetime.timezone.utc)
    # Day-over-day baseline for the CRM pipeline's engagement up/down arrow
    # (migration 192). The FIRST write on a new calendar day rolls the value
    # this club last held on an earlier day into _prev — so (current vs _prev)
    # is the day-over-day direction. A second (or later) write the same day
    # leaves _prev alone, so it keeps pointing at the previous day's last value
    # rather than being overwritten with today's own earlier reading. "Calendar
    # day" is Perth / Western Australia time (AWST, UTC+8, no DST) so the
    # boundary is Perth midnight, not UTC midnight (which is 8am in Perth).
    #
    # ``keep_prev`` suppresses that roll for a sweep triggered by a PARAMETER
    # CHANGE rather than by real activity. Without it, the first recalc after a
    # weight change is that first-write-of-the-day, so every club on the board
    # sprouts a large up or down arrow describing the parameter edit and not any
    # movement by the club — and the morning after a tuning session the board is
    # unreadable.
    prev_at = club.engagement_scored_at
    prev_day = prev_at.astimezone(_PERTH_TZ).date() if prev_at is not None else None
    if (not keep_prev and club.engagement_score is not None and prev_day is not None
            and prev_day < now.astimezone(_PERTH_TZ).date()):
        club.engagement_score_prev = club.engagement_score
        club.engagement_score_prev_date = prev_day
    club.engagement_score = fields.get("engagementScore")
    club.engagement_tier = fields.get("engagementTier")
    club.engagement_scored_at = now


# Age tiers, shared by every decay curve. Kept beside the SQL builder so the
# tier boundaries and the curve values can never be edited apart.
_DECAY_TIER_DAYS = (("d7", 7), ("d14", 14), ("d21", 21), ("d28", 28), ("d90", 90))


def _decay_arms(curve: dict, ts: str, extra_pred: str = "") -> str:
    """The CASE arms scoring one event by its own age, for one decay curve.

    ONE builder for what used to be four hand-written copies of the same
    ladder (the per-club web and email queries in ``_engagement``, and their
    single-pass equivalents in ``batch_web_stats``/``batch_email_stats``). Two
    copies of a curve is how a live single-club rescore and the nightly sweep
    start disagreeing, which only ``recalc_engagement --verify`` would ever
    catch.

    Every value is coerced with ``float()`` before it is interpolated, so a
    stored parameter cannot carry anything but a number into the query."""
    pre = f"{extra_pred} AND " if extra_pred else ""
    return "\n                   ".join(
        f"WHEN {pre}{ts} > NOW() - INTERVAL '{days} days' THEN {float(curve[key])}"
        for key, days in _DECAY_TIER_DAYS)


def _non_page_view_arm(params: "Optional[dict]", alias: str = "") -> str:
    """With "count page views only" on, anything that is not a page view scores
    nothing. Off (the original behaviour) every recorded event counts, including
    the dwell-time event fired when a page view ends, server-side API rows, and
    the heartbeat the site sends every ~25 seconds while a page is open."""
    if not (params or _D).get("COUNT_ONLY_PAGE_VIEWS"):
        return ""
    return f"WHEN {alias}event_type <> 'page_view' THEN 0.0\n                   "


async def batch_web_stats(session, params: "Optional[dict]" = None) -> dict:
    """Single-pass equivalent of ``_engagement``'s per-club ``web`` query, for
    EVERY club at once.

    The per-club query filters ``usage_events`` on the computed ``_RESOLVED_CID``
    expression, which forces a full re-resolution of every page-view row for
    every club — O(events x clubs). Fine for one club; ~14h across the whole
    ``marketing_clubs`` table on a full recalc. This resolves each event to its
    club ONCE (the MATERIALIZED ``ev`` CTE) and aggregates per club in a single
    GROUP BY, turning that sweep from hours into minutes.

    Returns ``{club_id_text: {...}}`` carrying EXACTLY the fields the per-club
    query produces, so ``_engagement(..., web_stats=<this>)`` is equivalent to
    running the per-club query. The two attribution branches mirror the per-club
    query's ``OR``: the PROSPECT branch (an anonymous, non-admin visit that
    resolves to the club) and the CUSTOMER branch (the club's own org traffic).
    They're ``UNION``-ed (deduped by event id) so a visit matching both counts
    once, exactly as the row-level ``OR`` does. The customer branch drops
    archived orgs, matching ``_engagement``'s own ``org_archived`` handling
    (which sets ``org_id = None`` so a wound-up test club stops scoring on its
    staff/test logins)."""
    params = params or _D
    web_curve, ad_curve = _curve("WEB_DECAY", params), _curve("AD_DECAY", params)
    skip_non_pv = _non_page_view_arm(params)
    rows = (await session.execute(text(f"""
        WITH ev AS MATERIALIZED (
            SELECT ue.id AS eid, ue.created_at, ue.org_id, ue.user_id,
                   ue.event_type,
                   COALESCE(ue.ip_hash, ue.visitor_id::text) AS ipk,
                   ({_META_CLICK}) AS is_meta,
                   (split_part(ue.path, '?', 1) ~* '^/contact(/|$)') AS is_contact,
                   (split_part(ue.path, '?', 1) ~* '^/trial(/|$)') AS is_trial,
                   -- Only an anonymous, non-admin row can ever be prospect-attributed,
                   -- so only those need the (expensive, 7-subquery) _RESOLVED_CID
                   -- resolution — skipping it for the (majority) authenticated / api /
                   -- admin rows is most of the speedup. A CASE THEN is not evaluated
                   -- when its WHEN is false, so those rows never run the subqueries.
                   -- rcid NULL therefore means "not a prospect visit", which is
                   -- exactly the prospect-branch filter below.
                   CASE WHEN ue.user_id IS NULL
                             AND split_part(ue.path, '?', 1) !~* '^/admin'
                        THEN ({_RESOLVED_CID}) ELSE NULL END AS rcid
            FROM usage_events ue
        ),
        attributed AS (
            -- Prospect marketing traffic: anonymous, non-admin, resolves to a club
            -- (all three conditions are baked into a non-NULL rcid above).
            SELECT rcid AS club_id, eid, created_at, event_type, ipk, is_meta, is_contact, is_trial
            FROM ev
            WHERE rcid IS NOT NULL
          UNION
            -- Customer product use: the club's own (non-archived) org traffic,
            -- never a super admin's acting-as activity.
            SELECT mc.id::text AS club_id, ev.eid, ev.created_at, ev.event_type, ev.ipk,
                   ev.is_meta, ev.is_contact, ev.is_trial
            FROM ev
            JOIN marketing_clubs mc ON mc.existing_org_id = ev.org_id
            JOIN organisations o ON o.id = ev.org_id AND o.archived_at IS NULL
            WHERE ev.org_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM club_memberships cm
                              WHERE cm.user_id = ev.user_id AND cm.role = 'super_admin')
        )
        SELECT club_id,
               MAX(created_at) AS last_seen,
               COUNT(DISTINCT ipk) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS sessions_30d,
               COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS events_30d,
               COALESCE(SUM(CASE
                   {skip_non_pv}WHEN is_meta THEN 0.0
                   {_decay_arms(web_curve, 'created_at')}
                   ELSE 0.0
               END), 0.0)::float AS web_decay_pts,
               COALESCE(SUM(CASE
                   {skip_non_pv}WHEN NOT is_meta THEN 0.0
                   {_decay_arms(ad_curve, 'created_at')}
                   ELSE 0.0
               END), 0.0)::float AS ad_decay_pts,
               COUNT(*) FILTER (WHERE is_meta) AS ad_clicks,
               BOOL_OR(is_contact) AS visited_contact,
               BOOL_OR(is_trial) AS visited_trial
        FROM attributed
        GROUP BY club_id
    """))).all()
    out: dict = {}
    for r in rows:
        if r[0] is None:
            continue
        out[str(r[0])] = {
            "last_seen": r[1],
            "sessions_30d": r[2] or 0,
            "events_30d": r[3] or 0,
            "web_decay_pts": float(r[4] or 0.0),
            "ad_decay_pts": float(r[5] or 0.0),
            "ad_clicks": r[6] or 0,
            "visited_contact": bool(r[7]),
            "visited_trial": bool(r[8]),
        }
    return out


async def batch_email_stats(session, params: "Optional[dict]" = None) -> dict:
    """Single-pass equivalent of ``_engagement``'s per-club ``em`` (email
    engagement) query, for every club at once — the same idea as
    ``batch_web_stats``. Attributes each ``email_events`` row to a club by the
    club's own contact email OR its (non-archived) org id, ``UNION``-ed and
    deduped by event id so the two branches don't double-count, matching the
    per-club query's ``OR``. Returns ``{club_id_text: {...}}`` with the exact
    fields the per-club query yields."""
    params = params or _D
    click_curve = _curve("EMAIL_CLICK_DECAY", params)
    open_curve = _curve("EMAIL_OPEN_DECAY", params)
    rows = (await session.execute(text(f"""
        WITH att AS (
            -- By the club's own contact email.
            SELECT mcc.marketing_club_id::text AS club_id, ee.id AS eid,
                   ee.created_at, ee.event_type
            FROM email_events ee
            JOIN marketing_club_contacts mcc ON lower(mcc.email) = lower(ee.email)
            WHERE ee.email IS NOT NULL AND ee.email <> ''
              AND mcc.email IS NOT NULL AND mcc.email <> ''
          UNION
            -- By the club's own (non-archived) org id.
            SELECT mc.id::text AS club_id, ee.id AS eid, ee.created_at, ee.event_type
            FROM email_events ee
            JOIN marketing_clubs mc ON mc.existing_org_id = ee.organisation_id
            JOIN organisations o ON o.id = ee.organisation_id AND o.archived_at IS NULL
            WHERE ee.organisation_id IS NOT NULL
        )
        SELECT club_id,
               MAX(created_at) FILTER (WHERE event_type IN ('open','click')) AS last_eng,
               COUNT(*) FILTER (WHERE event_type IN ('open','click')
                                AND created_at > NOW() - INTERVAL '30 days') AS eng_30d,
               COALESCE(SUM(CASE
                   {_decay_arms(click_curve, 'created_at', "event_type = 'click'")}
                   {_decay_arms(open_curve, 'created_at', "event_type = 'open'")}
                   ELSE 0.0
               END), 0.0)::float AS email_decay_pts
        FROM att
        GROUP BY club_id
    """))).all()
    out: dict = {}
    for r in rows:
        if r[0] is None:
            continue
        out[str(r[0])] = {
            "last_eng": r[1],
            "eng_30d": r[2] or 0,
            "email_decay_pts": float(r[3] or 0.0),
        }
    return out


async def _engagement(session, club: MarketingClub,
                      org: "Optional[Organisation]" = None,
                      web_stats: "Optional[dict]" = None,
                      email_stats: "Optional[dict]" = None,
                      fast_web: bool = False,
                      params: "Optional[dict]" = None,
                      keep_prev: bool = False) -> dict:
    """A per-club engagement rollup pushed onto the Company so the CRM can score and
    sort without holding raw events. Signal sources, all attributed to the club: web
    breadcrumbs (``usage_events`` by outreach UTM code or org id, both distinct-visitor
    reach AND raw page-view/API volume), email engagement (``email_events`` opens/
    clicks), a direct "onboard my club" website enquiry, and — for a customer — real
    per-module trial subscriptions (not just the marketing directory's aspirational
    trial-interest field).

    Lifecycle-aware: a PROSPECT is scored on lead heat (recency + frequency of web +
    email + buying intent); a CUSTOMER (linked org) is scored on account health +
    expansion, never Cold, with the modules they want-but-don't-pay-for surfaced as an
    upsell opportunity so a customer mid-sales-cycle is tracked, not buried at zero."""
    # Every weight in this function is a Super Admin parameter
    # (services/engagement_params.py). A caller scoring MANY clubs must resolve
    # once and pass ``params`` in, both to avoid a settings read per club and so
    # that every club in one sweep is scored with the same values even if
    # someone saves a change halfway through.
    if params is None:
        params = await engagement_params.get_params(session)
    web_curve = _curve("WEB_DECAY", params)
    ad_curve = _curve("AD_DECAY", params)
    click_curve = _curve("EMAIL_CLICK_DECAY", params)
    open_curve = _curve("EMAIL_OPEN_DECAY", params)
    skip_non_pv = _non_page_view_arm(params, "ue.")

    # "Not interested" is a manual disposition that overrides the computed heat, so it
    # isn't recomputed away on the next refresh — set it in the Club Directory.
    if getattr(club, "not_interested", False):
        result = {"engagementScore": 0, "engagementTier": "NOT_INTERESTED",
                  "sessions30d": 0, "emailEngaged30d": 0,
                  "upsellModules": [], "inSalesCycle": False}
        _apply_engagement_cache(club, result, keep_prev)
        return result
    # An ARCHIVED org (soft-deleted — gone from All Clubs, e.g. a wound-up test
    # trial) must stop scoring on its own product use. Its remaining activity is
    # staff/test logins (super admins are already excluded; a "fake admin" test
    # account resolves only via the org-id branch), so drop the org entirely:
    # the club then scores as a bare prospect on genuine outreach/email only,
    # which for a test club is nothing — so it decays to 0 and leaves the
    # pipeline, instead of holding a score off staff activity forever.
    org_archived = org is not None and getattr(org, "archived_at", None) is not None
    if org_archived:
        org = None
    utm = club.utm_code
    # org_id is what the customer/product-use web branch keys on; drop it too for
    # an archived org so its own staff/test logins stop counting.
    org_id = str(club.existing_org_id) if (club.existing_org_id and not org_archived) else None
    paid, trial_mods, _renewals = _module_split(org) if org is not None else ([], [], [])
    # A synced-but-not-yet-paying org (e.g. a demo synced ahead of a sale) is scored
    # as a Prospect's lead heat, not a Customer's account health — "we sync the club"
    # doesn't itself make them a customer (see _lifecycle).
    is_customer = bool(paid) or (club.demo_status or "") == "customer"

    # Web activity (usage_events) by UTM code (prospect) or org id (customer/trial).
    # Counts BOTH distinct-visitor reach (sessions) and raw event volume (page views
    # + API calls) — a club whose one visitor browses 50 pages is more engaged than
    # one who bounces after a single view, which distinct-visitor count alone can't
    # tell apart.
    #
    # Matches BOTH utm_id and utm_source against the club's code — a campaign
    # template can carry the code in either param (utm_id is auto-appended by
    # comms.py's _apply_utm; utm_source is also available as a merge var an
    # operator can hand-place in a link), and club_directory.py's own visit-stats
    # panel (_RESOLVED_VISITS) already matches both. Checking only utm_id silently
    # missed every click from a utm_source-tagged link (confirmed: a club with 54
    # visitors on its Directory "site visits" panel scored 0 sessions here).
    #
    # Also matches the club's marketing-page PATH itself (``_PATH_CODE``, the same
    # first-path-segment extraction _RESOLVED_VISITS uses) against the utm_code, and
    # — for a customer — against the org's own slug. A visitor who lands on
    # /{club-slug}/... straight from Google or a shared link (no UTM query param at
    # all) still needs attributing; without this a customer's own site traffic (path
    # keyed on the org slug, which need not even equal the club's stored utm_code —
    # confirmed for West Coburg St Andrews CC and Geelong Over 50s CC, both showing
    # real Directory "site visits" via path-only hits) scored zero sessions here.
    org_slug = getattr(org, "slug", None) if org is not None else None
    # ``web_decay_pts`` scores EACH matched page-view/API event by its own age (not
    # just the newest one) and sums them — a burst of 8 pages this week outscores 8
    # pages trickled over the full window, and the sum itself differentiates a quiet
    # club from a busy one far more than a flat 30-day count capped at 20 ever could
    # (many genuinely-different clubs were converging on the same capped value).
    # Prospect attribution. Normally the 7-subquery _RESOLVED_CID resolution over
    # the whole table (correct for any row, incl. ones not yet materialised — the
    # batch recalc / breakdown path). ``fast_web`` swaps it for the pre-stamped
    # usage_events.resolved_marketing_club_id column (an indexed equality), which
    # turns a single-club recompute from ~6s into milliseconds so it's safe to
    # fire on every live signal. Requires the column to be backfilled for the
    # scoring window (app/scripts/backfill_resolved_club.py) to be equivalent —
    # see recalc_engagement --verify-fast.
    prospect_match = ("ue.resolved_marketing_club_id = CAST(:cid AS uuid)"
                      if fast_web else f"({_RESOLVED_CID}) = CAST(:cid AS text)")
    if web_stats is None:
      web = (await session.execute(text(f"""
        SELECT MAX(ue.created_at) AS last_seen,
               -- Distinct visitors deduped by IP FIRST, then visitor_id. The
               -- client-side visitor_id can churn (a bot/crawler or a privacy
               -- browser gets a fresh id per page view), so counting raw
               -- visitor_id inflated reach — e.g. 18 "visitors" from 2 IPs.
               -- ip_hash is the robust unit and matches the Website analytics
               -- panel's "unique IPs"; visitor_id is only the fallback when a
               -- row has no ip_hash.
               COUNT(DISTINCT COALESCE(ue.ip_hash, ue.visitor_id::text))
                 FILTER (WHERE ue.created_at > NOW() - INTERVAL '30 days') AS sessions_30d,
               COUNT(*) FILTER (WHERE ue.created_at > NOW() - INTERVAL '30 days') AS events_30d,
               -- Organic page views / API calls (everything that is NOT a paid
               -- ad-click landing), age-decayed and summed, bounded to 90 days.
               COALESCE(SUM(CASE
                   {skip_non_pv}WHEN {_META_CLICK} THEN 0.0
                   {_decay_arms(web_curve, 'ue.created_at')}
                   ELSE 0.0
               END), 0.0)::float AS web_decay_pts,
               -- Meta / paid ad-click landings, on the richer AD_DECAY curve.
               COALESCE(SUM(CASE
                   {skip_non_pv}WHEN NOT {_META_CLICK} THEN 0.0
                   {_decay_arms(ad_curve, 'ue.created_at')}
                   ELSE 0.0
               END), 0.0)::float AS ad_decay_pts,
               -- All-time count of matched Meta/paid ad-click landings (for the
               -- diagnostic breakdown and the in-sales-cycle signal).
               COUNT(*) FILTER (WHERE {_META_CLICK}) AS ad_clicks,
               -- Did an attributed visit hit the BetterCricket contact page? A
               -- high-intent action ("I want to get in touch"), unlike plain
               -- browsing — this is what should earn HOT, not page volume.
               BOOL_OR(split_part(ue.path, '?', 1) ~* '^/contact(/|$)') AS visited_contact,
               -- Did an attributed visit hit the /trial signup page? The strongest
               -- pre-enquiry buying intent — someone actively looking to start.
               BOOL_OR(split_part(ue.path, '?', 1) ~* '^/trial(/|$)') AS visited_trial
        FROM usage_events ue
        WHERE (
                -- Prospect marketing traffic: resolve EACH visit to the ONE club it
                -- belongs to (the same priority resolution the Website analytics
                -- panel uses — _RESOLVED_CID: alias → utm_code in utm_id/utm_source
                -- → utm_code = path → onboarded slug = path), and only count it here
                -- if it resolves to THIS club. This replaces the old any-overlap
                -- match, which credited a visit to every club whose utm_code merely
                -- collided with the path/UTM — so a club with no page of its own
                -- could inherit another same-named club's visitors. Anonymous +
                -- non-/admin (a stale UTM riding a staff member's admin browsing
                -- must not attribute). ``prospect_match`` is either the bulk
                -- _RESOLVED_CID resolution or the pre-stamped column (fast_web).
                ({prospect_match}
                 AND ue.user_id IS NULL
                 AND split_part(ue.path, '?', 1) !~* '^/admin')
                -- A customer's own product use: their org's own traffic, keyed on
                -- the precise org id (no collision possible). Deliberately NOT
                -- guarded against logged-in use — an admin working in their own
                -- club's backend IS the product-use signal for a real customer.
                OR (CAST(:org AS text) IS NOT NULL AND ue.org_id::text = CAST(:org AS text))
              )
          -- Never credit a BetterCricket Super Admin's activity to a club (a
          -- staff member acting-as inflates the club's own engagement). A
          -- super admin's home membership role stays 'super_admin' regardless
          -- of which club they're currently acting as. Anonymous rows
          -- (user_id NULL) find no match here and are kept.
          AND NOT EXISTS (
                SELECT 1 FROM club_memberships cm
                WHERE cm.user_id = ue.user_id AND cm.role = 'super_admin'
          )
    """), {"org": org_id, "cid": str(club.id)})).first()
      last_web = web[0] if web else None
      sessions = (web[1] or 0) if web else 0
      events_30d = (web[2] or 0) if web else 0
      web_decay_pts = float(web[3] or 0.0) if web else 0.0
      ad_decay_pts = float(web[4] or 0.0) if web else 0.0
      ad_clicks = (web[5] or 0) if web else 0
      visited_contact = bool(web[6]) if web else False
      visited_trial = bool(web[7]) if web else False
    else:
      # Batch-precomputed by batch_web_stats() — identical fields, resolved once
      # for the whole table instead of a per-club scan (the full-recalc fast path).
      ws = web_stats.get(str(club.id)) or {}
      last_web = ws.get("last_seen")
      sessions = ws.get("sessions_30d") or 0
      events_30d = ws.get("events_30d") or 0
      web_decay_pts = float(ws.get("web_decay_pts") or 0.0)
      ad_decay_pts = float(ws.get("ad_decay_pts") or 0.0)
      ad_clicks = ws.get("ad_clicks") or 0
      visited_contact = bool(ws.get("visited_contact"))
      visited_trial = bool(ws.get("visited_trial"))

    # Email engagement (email_events opens/clicks) for this club's contact emails, or
    # org-scoped for a customer. Opens+clicks are real engagement; sends are not.
    #
    # ``email_decay_pts`` mirrors a marketing-automation "score every time" rule
    # (e.g. HubSpot): each open/click is scored on ITS OWN age against a tiered
    # schedule and every qualifying event is summed, rather than folding every touch
    # into one flat 30-day count. A click is weighted double an open (a real click
    # is stronger buying intent than a pixel-fired open, which Apple Mail Privacy
    # Protection can trigger without the recipient ever looking). Requires AWS SES
    # "Open and click tracking" enabled on the configuration set — if that's off,
    # email_events never gets open/click rows and this is always 0 (see
    # app/scripts/email_opens.py to check).
    if email_stats is None:
      em = (await session.execute(text(f"""
        SELECT MAX(created_at) FILTER (WHERE event_type IN ('open','click')) AS last_eng,
               COUNT(*) FILTER (WHERE event_type IN ('open','click')
                                AND created_at > NOW() - INTERVAL '30 days') AS eng_30d,
               COALESCE(SUM(CASE
                   {_decay_arms(click_curve, 'created_at', "event_type = 'click'")}
                   {_decay_arms(open_curve, 'created_at', "event_type = 'open'")}
                   ELSE 0.0
               END), 0.0)::float AS email_decay_pts
        FROM email_events
        WHERE lower(email) IN (
                SELECT lower(email) FROM marketing_club_contacts
                WHERE marketing_club_id = :cid AND email IS NOT NULL AND email <> '')
           OR (CAST(:org AS text) IS NOT NULL AND organisation_id::text = CAST(:org AS text))
    """), {"cid": str(club.id), "org": org_id})).first()
      last_email = em[0] if em else None
      eng_30d = (em[1] or 0) if em else 0
      email_decay_pts = float(em[2] or 0.0) if em else 0.0
    else:
      # Batch-precomputed by batch_email_stats() — the full-recalc fast path.
      es = email_stats.get(str(club.id)) or {}
      last_email = es.get("last_eng")
      eng_30d = es.get("eng_30d") or 0
      email_decay_pts = float(es.get("email_decay_pts") or 0.0)

    onboarding_count, onboarding_last = await _onboarding_signal(session, club, utm, org_slug)

    last_touch = max([d for d in (last_web, last_email, onboarding_last) if d], default=None)

    # Modules the club wants but isn't paying for = the open opportunity (a prospect's
    # interest, or a customer's expansion / trialing-extra). ``trial_mods`` is the
    # REAL per-module trial subscriptions a super admin actually started
    # (org_module_subscriptions status='trial') — not just the marketing directory's
    # aspirational trial_modules field, so initiating a real trial always registers
    # even if nobody separately flags it in the Club Directory.
    paid_keys = _billing_modules(paid)
    wanted = (_billing_modules(club.requested_trial_modules or [])
              | _billing_modules(club.trial_modules or [])
              | _billing_modules(trial_mods))
    upsell = sorted(wanted - paid_keys)

    # Frequency = reach + depth, both LINEAR in real activity (no saturating cap;
    # see the constants block for why the caps were removed). Reach rewards how
    # many distinct people visited in 30 days; depth folds together the three
    # per-event age-decayed sums (organic web views, email opens/clicks, and the
    # richer-weighted Meta/paid ad-click landings). The only ceiling is the final
    # min(100) clamp below, so genuinely busy clubs now climb the whole range
    # instead of bunching under an artificial wall.
    reach_pts = params["REACH_PER_VISITOR"] * sessions
    depth_pts = params["DEPTH_SCALE"] * (email_decay_pts + web_decay_pts + ad_decay_pts)
    # Depth is linear in raw event COUNT, which is what makes it vulnerable to
    # any repeated-request source: an open tab sending a heartbeat every 25
    # seconds, or a mail-security scanner prefetching every link in an outreach
    # email. Capping it bounds that without having to identify the source, and
    # leaves the club's total still linear in how many distinct visitors it had,
    # which is the quantity worth measuring. 0 keeps the original behaviour.
    depth_cap = params.get("DEPTH_PER_VISITOR_CAP") or 0
    if depth_cap:
        depth_pts = min(depth_pts, float(depth_cap))
    freq_pts = reach_pts + depth_pts
    recency = _recency_pts(last_touch, params)

    # A prospect whose org was born from a paid ad (self_serve_ad). Only meaningful
    # for a linked org; a bare directory row has no signup_source.
    ad_signup = (not is_customer and org is not None
                 and getattr(org, "signup_source", None) == "self_serve_ad")

    # Tier bands: see TIER_WARM_MIN / TIER_HOT_MIN.
    trial_depth = None
    if is_customer:
        # Account health + expansion. A paying account starts engaged, gains for
        # recent product use, and for an active expansion opportunity; floored at Warm.
        score = (params["CUSTOMER_BASE"]
                 + int(recency * params["CUSTOMER_RECENCY_SCALE"])
                 + min(int(freq_pts * params["CUSTOMER_FREQ_SCALE"]),
                       params["CUSTOMER_FREQ_CAP"]))
        if upsell:
            score += params["CUSTOMER_UPSELL_BONUS"]
        if onboarding_count:
            score += params["CUSTOMER_ONBOARDING_BONUS"]  # e.g. onboard a second team/ground
        score = min(score, 100)
        tier = "HOT" if (score > params["TIER_HOT_MIN"] or upsell) else "WARM"
    else:
        # Prospect lead heat: recency + frequency of any touch + buying intent.
        score = recency + freq_pts
        if club.requested_trial_modules:
            score += params["BONUS_REQUESTED_TRIAL"]
        if (club.demo_status or "") == "in_trial":
            score += params["BONUS_IN_TRIAL"]
        if visited_contact:
            # Hit the contact page — a real "get in touch" signal, not just browsing.
            score += params["BONUS_CONTACT_PAGE"]
        if visited_trial:
            # Hit the /trial signup page — the strongest pre-enquiry buying intent.
            score += params["BONUS_VISIT_TRIAL"]
        if ad_signup:
            # Converted a paid ad click all the way to a self-serve registration.
            score += params["BONUS_AD_SIGNUP"]
        if onboarding_count:
            # A direct "onboard my club" enquiry is the strongest signal a prospect
            # can give — heavier than the admin-set requested_trial_modules flag.
            score += params["BONUS_ONBOARDING"]
        score = min(score, 100)
        tier = _tier_for(score, params)

        # Trial-depth floor: a self-serve/onboarded prospect's own product-setup
        # effort (registration, historical import, merges, module trial usage —
        # see services/trial_engagement.py) can outscore the web/email recency+
        # frequency formula above, especially in the first hours after signup
        # before any usage_events/email_events have had time to accumulate. Only
        # a floor (never lowers a score the ordinary formula already earned) and
        # only for a club that's actually been onboarded — a bare marketing-
        # directory row with no linked Organisation has nothing to be deep in.
        if org is not None:
            trial_depth = await trial_engagement.trial_depth_score(session, org, params)
            if trial_depth["score"] > score:
                score = trial_depth["score"]
                tier = _tier_for(score, params)

    # freq_pts sums fractional per-event decay points (the 21-28 day web-view tier
    # is worth 0.5), so score can come out fractional here — round once, at the
    # very end, so the tier-band comparisons above run on the precise value but the
    # cached field reads as a whole number.
    score = int(round(score))

    # A direct "onboard my club" enquiry (Contact page or the quick CTA modal)
    # holds a prospect at a flat Hot DIRECT_ENQUIRY_SCORE for a super-admin-
    # configured number of days (Club Directory > General Settings > Marketing)
    # — not just the
    # one-off push push_onboarding_enquiry() makes the moment the enquiry
    # lands, but on every later recompute too (the nightly refresh, a
    # BetterComms send, a manual rescore), so it doesn't quietly
    # decay back to the ordinary recency/frequency score overnight. Ends the
    # moment the deal is "won" (the club becomes a paying customer — is_customer
    # switches it to the account-health formula above instead) or "lost"
    # (``not_interested``, handled by the early return at the top of this
    # function), whichever comes first.
    hot_days = await platform_settings.get_direct_enquiry_hot_days(session)
    direct_enquiry_hot = (
        not is_customer and onboarding_last is not None
        and (datetime.datetime.now(datetime.timezone.utc) - onboarding_last).days <= hot_days
    )
    if direct_enquiry_hot:
        enquiry_score = params["DIRECT_ENQUIRY_SCORE"]
        if params.get("ENQUIRY_OVERRIDE_IS_FLOOR"):
            # A FLOOR: raise a club that would otherwise decay below it, never
            # lower one that has independently earned more. The paragraph above
            # describes only the first of those, but as an outright assignment
            # this also did the second — a busy prospect on 100 dropped to 80 by
            # filling in the contact form, so the most engaged prospects were the
            # ones it penalised. Off by default so no club's score moves on
            # deploy; turn it on from the parameters page with the preview open.
            if enquiry_score > score:
                score, tier = enquiry_score, _tier_for(enquiry_score, params)
        else:
            score, tier = enquiry_score, "HOT"

    # In an active sales cycle: a customer expanding, or a prospect showing intent or
    # RECENT engagement (so it's a deal to work, not just a name on a list). Uses
    # ``sessions``/``eng_30d`` (both 30-day-windowed), not the all-time ``last_touch``
    # — a single click years ago shouldn't keep a club permanently flagged in-cycle
    # long after its score has decayed back to Cold.
    in_cycle = bool(upsell or onboarding_count) if is_customer else bool(
        club.requested_trial_modules or (club.demo_status or "") == "in_trial"
        or onboarding_count or sessions or eng_30d or ad_signup or visited_contact
        or visited_trial or (trial_depth and trial_depth["score"] >= 70))

    fields = {
        "engagementScore": score,
        "engagementTier": tier,
        "sessions30d": sessions,
        "emailEngaged30d": eng_30d,
        "upsellModules": _module_labels(upsell),
        "inSalesCycle": in_cycle,
        # Ever visited the public site (all-time, not the 30-day session count) so a
        # CRM View can filter "has visited the site". `last_web` is MAX(created_at) of
        # web activity attributed by utm_id or org id — the primary attribution path.
        "hasVisitedSite": bool(last_web),
        # Exposed so a caller can source-label a lead
        # raised off a direct enquiry as "Contact us" rather than a generic bucket.
        "_onboardingRequested": bool(onboarding_count),
        # Internal-only score breakdown (underscore-prefixed, stripped by _public()
        # stripped before the result is stored) — for diagnose_club_lead.py, so a score
        # can actually be explained rather than just observed.
        "_recencyPts": round(recency, 1),
        "_emailDecayPts": round(email_decay_pts, 1),
        "_webDecayPts": round(web_decay_pts, 1),
        "_adDecayPts": round(ad_decay_pts, 1),
        "_adClicks": ad_clicks,
        "_adSignup": ad_signup,
        "_visitedContact": visited_contact,
        "_visitedTrial": visited_trial,
        "_freqPts": round(freq_pts, 1),
        "_directEnquiryHot": direct_enquiry_hot,
        "_trialDepth": trial_depth,
    }
    if last_touch:
        fields["lastSeenAt"] = last_touch.isoformat()
    if last_web:
        fields["lastWebVisitAt"] = last_web.isoformat()
    if last_email:
        fields["lastEmailAt"] = last_email.isoformat()
    _apply_engagement_cache(club, fields, keep_prev)
    return fields


def _module_split(org):
    """Split a club's held modules into genuinely-paid vs trial, with the per-module
    renewal dates of the paid ones. Reads the per-module rows when loaded; falls back
    to the legacy org-wide ``module_overrides`` + ``subscription_status``. The org-level
    master switch (paused/cancelled) means nothing is live."""
    from app.auth.modules import (
        org_subscription_active, sub_is_live, PAID_STATUSES, STATUS_TRIAL, ALL_MODULES,
        MANAGED_MODULES,
    )
    if not org_subscription_active(org):
        return [], [], []
    subs = None
    try:
        from sqlalchemy import inspect as _sa_inspect
        if "module_subscriptions" not in _sa_inspect(org).unloaded:
            subs = list(org.module_subscriptions or [])
    except Exception:
        subs = None
    if subs is None:
        # Legacy fallback: the whole club is paid, or (status trial) all-on-trial.
        held = [m for m in (org.module_overrides or []) if m in ALL_MODULES]
        if (org.subscription_status or "").lower() == STATUS_TRIAL:
            return [], held, []
        return held, [], []
    paid, trial, renewals = [], [], []
    for s in subs:
        if s.module_key not in MANAGED_MODULES or not sub_is_live(s):  # MANAGED includes core
            continue
        if s.status in PAID_STATUSES:
            paid.append(s.module_key)
            if s.renewal_date:
                renewals.append(s.renewal_date)
        elif s.status == STATUS_TRIAL:
            trial.append(s.module_key)
    return paid, trial, renewals


# ── link table ────────────────────────────────────────────────────────────────


def _club_assocs(club: MarketingClub):
    """Every association the club belongs to as (guid, name, is_primary), deduped.
    Combines the primary association_name/guid with the full associations JSONB
    array; is_primary marks the one PlayHQ lists as primary."""
    out, seen = [], set()
    items = []
    if club.association_name:
        items.append((club.association_guid, club.association_name))
    for a in (club.associations or []):
        if isinstance(a, dict) and a.get("name"):
            items.append((a.get("id"), a.get("name")))
    for guid, name in items:
        key = guid or ("name:" + name)
        if key in seen:
            continue
        seen.add(key)
        is_primary = (guid is not None and guid == club.association_guid) or \
                     (guid is None and name == club.association_name)
        out.append((guid, name, is_primary))
    return out


# ── club-level suppression (all officers opted out) ────────────────────────────

async def _all_contacts_unsubscribed(session, club_id) -> bool:
    """True when the club has at least one named-email officer and every one of
    them has unsubscribed/bounced/complained. A club with zero email contacts is
    NOT "all unsubscribed" — there's nothing to suppress on."""
    row = (await session.execute(text("""
        SELECT COUNT(*) FILTER (WHERE subscribed) AS subscribed_n, COUNT(*) AS total_n
        FROM marketing_club_contacts
        WHERE marketing_club_id = :cid AND email IS NOT NULL AND email <> ''
    """), {"cid": str(club_id)})).first()
    if not row or not row[1]:
        return False
    return row[0] == 0


async def _resolve_onboarding_club(session, *, club_name: str, contact_name: str,
                                   email: str, phone: "Optional[str]",
                                   org_id: "Optional[str]" = None):
    """Find-or-create the MarketingClub + MarketingClubContact a direct 'onboard
    my club' enquiry belongs to. Matching mirrors ``_onboarding_signal``'s own
    priority — the submitter's email against a known officer first (the
    strongest signal: this exact person is already on file for a specific
    club) — then, when the Contact form's club search gave us one, the club's
    real CA organisation guid, then an exact club-name match, else a brand-new
    prospect club is created from what the form gave us, so a first-touch
    enquiry from a club the PlayHQ crawler hasn't found yet is never silently
    dropped. Commits nothing itself — the caller commits.

    ``org_id`` is the whole point of the search field: a name a person typed
    matches only itself, so "Applecross CC" and "Applecross Cricket Club" used
    to become two prospect rows. A guid matches the club the crawler already
    knows, whatever either of them called it.
    """
    name = (club_name or "").strip()
    email_l = (email or "").strip().lower()
    guid = (org_id or "").strip() or None

    club = None
    if email_l:
        club = (await session.execute(
            select(MarketingClub).join(
                MarketingClubContact, MarketingClubContact.marketing_club_id == MarketingClub.id)
            .where(func.lower(MarketingClubContact.email) == email_l)
            .limit(1)
        )).scalars().first()
    if club is None and guid:
        club = await session.scalar(
            select(MarketingClub).where(MarketingClub.grassroots_guid == guid))
    if club is None and name:
        club = (await session.execute(
            select(MarketingClub).where(func.lower(MarketingClub.name) == name.lower()).limit(1)
        )).scalars().first()
    if club is None:
        if not name:
            return None, None
        # A picked club is keyed on its real CA guid — the same one the PlayHQ
        # crawler uses — so a row created here and a row the crawler finds
        # later are the same row. With no guid (a club typed in by hand, i.e.
        # one the CA list doesn't carry) fall back to a deterministic synthetic
        # guid keyed on the name, so a second enquiry from the same club
        # (matched by name above) upserts the same row rather than minting a
        # duplicate.
        club = MarketingClub(
            grassroots_guid=guid or f"manual:{uuid.uuid5(uuid.NAMESPACE_URL, name.lower())}",
            name=name[:200], kind="club", status="contacted", source="onboarding_form",
            contact_email=email_l or None, contact_phone=phone,
        )
        session.add(club)
        await session.flush()
    elif guid and str(club.grassroots_guid or "").startswith("manual:"):
        # Matched a row an earlier free-text enquiry created, and this time we
        # know the club's real guid. Upgrading it is what lets the crawler's own
        # row for this club find it later instead of sitting alongside it —
        # unless some other row already holds that guid, in which case the two
        # are genuine duplicates and merging them is a decision for a person,
        # not a silent write from a background task. (grassroots_guid is
        # unique, so the check is also what keeps this from raising.)
        taken = await session.scalar(
            select(MarketingClub.id).where(
                MarketingClub.grassroots_guid == guid, MarketingClub.id != club.id))
        if taken is None:
            club.grassroots_guid = guid

    contact = None
    if email_l:
        contact = (await session.execute(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id,
                func.lower(MarketingClubContact.email) == email_l)
        )).scalars().first()
    if contact is None:
        contact = MarketingClubContact(
            marketing_club_id=club.id, full_name=(contact_name or "").strip()[:200] or None,
            email=email_l or None, mobile=phone, role="Enquirer", role_rank=1,
            source="website", subscribed=True, outreach_selected=True,
        )
        session.add(contact)
        await session.flush()
    elif not contact.outreach_selected:
        contact.outreach_selected = True

    return club, contact


async def _resolve_self_serve_club(session, *, org_id, org_name: str, contact_name: str,
                                   email: str, phone: "Optional[str]",
                                   source: str = "self_serve_trial"):
    """Find-or-create the MarketingClub + registering-admin MarketingClubContact
    a self-serve trial registration (routers/self_serve_trial.py) belongs to.
    Checked in order: (1) a directory row already linked to this exact org —
    ``_onboard_club_core`` (organisations.py), which always runs first as part
    of the same registration, may already have matched-and-linked one by
    playhq_id or name; reusing it here is what stops this function minting a
    duplicate row for a club the directory already knows; (2) a row keyed on
    the same CA org id the directory crawler would itself have used had it
    found this club (``_link_existing_org``'s own fallback: BetterStats
    ``Organisation.id`` == the grassroots org guid for a grassroots-sourced
    club) — covers a retried registration whose earlier attempt already
    created this row; (3) an exact name match; (4) create fresh. Unlike
    ``_resolve_onboarding_club`` (a bare contact-form enquiry with no real CA
    identifier at all, so it mints a synthetic ``manual:`` guid), a self-serve
    registration always has a real org to key (2) on. Always (re-)stamps
    ``existing_org_id`` — the row is now definitely a real BetterCricket
    customer. Commits nothing itself — the caller commits.

    ``source`` is what a newly-created directory row / contact records about
    where it came from. Super Admin → New Club (routers/club_admin.py::
    create_club) reuses this whole resolution — a staff-registered club needs
    exactly the same find-or-create — and passes 'super_admin_trial' so the
    row doesn't claim the club signed itself up."""
    guid = str(org_id)
    club = await session.scalar(
        select(MarketingClub).where(MarketingClub.existing_org_id == org_id))
    if club is None:
        club = await session.scalar(
            select(MarketingClub).where(MarketingClub.grassroots_guid == guid))
    if club is None:
        club = await session.scalar(
            select(MarketingClub).where(func.lower(MarketingClub.name) == org_name.lower()))
    email_l = (email or "").strip().lower()
    if club is None:
        club = MarketingClub(
            grassroots_guid=guid, name=org_name[:200], kind="club",
            status="contacted", source=source,
            contact_email=email_l or None, contact_phone=phone,
        )
        session.add(club)
        await session.flush()
    club.existing_org_id = org_id

    contact = None
    if email_l:
        contact = (await session.execute(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id,
                func.lower(MarketingClubContact.email) == email_l)
        )).scalars().first()
    if contact is None:
        contact = MarketingClubContact(
            marketing_club_id=club.id, full_name=(contact_name or "").strip()[:200] or None,
            email=email_l or None, mobile=phone, role="Club Admin", role_rank=1,
            source=source, subscribed=True, outreach_selected=True,
        )
        session.add(contact)
        await session.flush()
    elif not contact.outreach_selected:
        contact.outreach_selected = True

    return club, contact

