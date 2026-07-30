"""BetterCricket CRM — engagement scoring engine.

Computes each targeted club's engagement rollup (a 0–100 score + a Cold / Warm /
Hot tier) from BetterCricket's own signals — website ``usage_events`` (attributed
by outreach UTM code or org id), ``email_events`` opens/clicks, direct "onboard my
club" enquiries, and real per-module trial depth — and caches the result on the
``marketing_clubs`` row (``engagement_score`` / ``engagement_tier`` /
``engagement_scored_at``). The BetterCricket CRM pipeline (``services/crm.py``)
reads that cache to score, sort and auto-promote deals.

Lifecycle-aware: a PROSPECT is scored on lead heat (recency + frequency of web +
email + buying intent); a CUSTOMER (a linked, paying org) is scored on account
health + expansion, and is never Cold.

``_engagement`` is a pure local read/compute over our own tables — it calls no
external service — so a single-club recompute (``crm.sync_engagement_promotion``)
and a full-table sweep (``scripts/recalc_engagement.py``) both work with nothing
to configure. This module also owns ``_resolve_onboarding_club`` /
``_resolve_self_serve_club``, the find-or-create helpers the CRM's enquiry and
self-serve deal hooks use.
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Optional

from sqlalchemy import func, select, text

from app.models.db import MarketingClub, MarketingClubContact, Organisation
from app.services import platform_settings, trial_engagement
from app.services.club_directory import _PATH_CODE, _RESOLVED_CID

# --- Engagement scoring weights -------------------------------------------------
# One place to tune every number in _engagement(). Mirrors the engagement-scoring
# workbook shared with the team; see docs there for the rationale behind each.
#
# Per-event decay: each web/email event is scored by ITS OWN age and the scores
# are summed. Ages beyond the last tier here score 0 — the ``d90`` tier plus the
# ``ELSE 0`` gives every sum an outer 90-day window, so a club's years of history
# can't quietly peg the depth curve (the sum is otherwise unbounded in age).
WEB_DECAY = {"d7": 2.0, "d14": 1.5, "d21": 1.0, "d28": 0.5, "d90": 0.25}
# A Meta / paid ad-click landing is a higher-intent arrival than an organic page
# view, so it gets its own richer curve instead of the flat WEB_DECAY rate.
AD_DECAY = {"d7": 5.0, "d14": 3.5, "d21": 2.0, "d28": 1.0, "d90": 0.5}
EMAIL_CLICK_DECAY = {"d7": 10.0, "d14": 7.5, "d21": 5.0, "d28": 2.0, "d90": 1.0}
EMAIL_OPEN_DECAY = {"d7": 4.0, "d14": 3.0, "d21": 2.0, "d28": 1.0, "d90": 1.0}

# Frequency = reach (distinct visitors) + depth (the summed per-event decay
# points), each a LINEAR function of real activity. The old saturating caps
# existed to stop a bot/crawler running the score away; outreach goes straight
# to real clubs, so there's no bot traffic to defend against, and the caps were
# the main thing compressing genuine clubs into a lump and creating the cliff.
# The only ceiling now is the final min(100) clamp. These two scale factors are
# the knobs to tune against the distribution (recalc_engagement prints a
# histogram): points per distinct 30-day visitor, and a multiplier on the summed
# per-event decay points.
REACH_PER_VISITOR = 2.5
DEPTH_SCALE = 0.6

# Recency of the single most-recent touch of any kind (web / email / enquiry),
# a SMOOTH exponential decay rather than hard day-buckets — so two clubs a day
# either side of a boundary don't sit points apart for no real difference.
# RECENCY_FULL at 0 days old, halving every RECENCY_HALFLIFE_DAYS; 0 if never.
RECENCY_FULL = 10.0
RECENCY_HALFLIFE_DAYS = 21.0

# Prospect intent bonuses, added on top of recency + frequency.
BONUS_REQUESTED_TRIAL = 12
BONUS_IN_TRIAL = 10
BONUS_ONBOARDING = 20
# A visit to the BetterCricket contact page — a real "get in touch" intent
# signal, worth more than plain browsing (a club that only browsed stays cooler).
BONUS_CONTACT_PAGE = 10
# A visit to the /trial signup page — the strongest pre-enquiry buying intent
# (someone actively looking to start), so it's scored higher than a contact-page
# visit. Both stack: a prospect who hit both pages earns both.
BONUS_VISIT_TRIAL = 20
# A club whose org was born from a Meta/paid ad (organisations.signup_source ==
# 'self_serve_ad') converted a paid click all the way to a registration — score
# that intent on top of the trial-depth registration credit it already earns.
BONUS_AD_SIGNUP = 10

# Customer account-health branch (floored, never Cold).
CUSTOMER_BASE = 60
CUSTOMER_UPSELL_BONUS = 15
CUSTOMER_ONBOARDING_BONUS = 10

# Tier bands: COLD < WARM_MIN, WARM up to < HOT_MIN, HOT at/above HOT_MIN.
TIER_WARM_MIN = 30
TIER_HOT_MIN = 60

# A direct "onboard my club" enquiry pins a prospect to this flat score/HOT for
# the super-admin-configured window (platform_settings.get_direct_enquiry_hot_days).
DIRECT_ENQUIRY_SCORE = 80

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


def _tier_for(score: float) -> str:
    return ("COLD" if score < TIER_WARM_MIN
            else "WARM" if score < TIER_HOT_MIN else "HOT")


logger = logging.getLogger(__name__)


# Modules are collapsed to the BILLABLE level: BetterAdmin is ONE module, so its
# members (fees/comms/merch — never sold or trialed on their own) collapse into
# 'admin'. core (always-on) passes through; anything unrecognised is dropped.
# Result set: core / select / socials / admin / iq / fantasy.
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


def _billable_module_values(keys) -> list:
    """The uppercase billable-module list (e.g. the club's upsell modules)."""
    return sorted(k.upper() for k in _billing_modules(keys))


def _recency_pts(last):
    """Recency points from a last-touch timestamp: a smooth exponential decay
    (RECENCY_FULL at 0 days, halving every RECENCY_HALFLIFE_DAYS), 0 if never.
    Continuous, so there are no step jumps at day boundaries. Deliberately modest
    so recency alone can't reach HOT — real frequency (repeat visits) or an
    explicit intent signal (trial request, contact form) has to carry a club
    over the line."""
    if not last:
        return 0.0
    days = max(0, (datetime.datetime.now(datetime.timezone.utc) - last).days)
    return RECENCY_FULL * (0.5 ** (days / RECENCY_HALFLIFE_DAYS))


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


def _apply_engagement_cache(club: MarketingClub, fields: dict) -> None:
    """Every _engagement() call caches its result onto the club row itself —
    marketing_clubs.engagement_score/.engagement_tier/.engagement_scored_at —
    regardless of which call site triggered the computation (a single-club
    recompute on a live signal, or the full-table recalc sweep), so the CRM
    pipeline / Club Directory / BetterComms Contacts+Lists / Segments can filter
    on a real number without recomputing this per-club scan themselves. Just sets
    attributes on the already-session-attached ORM object — the caller's own
    commit (every call site has one) persists it."""
    now = datetime.datetime.now(datetime.timezone.utc)
    # Day-over-day baseline for the CRM pipeline's engagement up/down arrow
    # (migration 192). The FIRST write on a new calendar day rolls the value
    # this club last held on an earlier day into _prev — so (current vs _prev)
    # is the day-over-day direction. A second (or later) write the same day
    # leaves _prev alone, so it keeps pointing at the previous day's last value
    # rather than being overwritten with today's own earlier reading. "Calendar
    # day" is Perth / Western Australia time (AWST, UTC+8, no DST) so the
    # boundary is Perth midnight, not UTC midnight (which is 8am in Perth).
    prev_at = club.engagement_scored_at
    prev_day = prev_at.astimezone(_PERTH_TZ).date() if prev_at is not None else None
    if (club.engagement_score is not None and prev_day is not None
            and prev_day < now.astimezone(_PERTH_TZ).date()):
        club.engagement_score_prev = club.engagement_score
        club.engagement_score_prev_date = prev_day
    club.engagement_score = fields.get("engagementScore")
    club.engagement_tier = fields.get("engagementTier")
    club.engagement_scored_at = now


async def batch_web_stats(session) -> dict:
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
    rows = (await session.execute(text(f"""
        WITH ev AS MATERIALIZED (
            SELECT ue.id AS eid, ue.created_at, ue.org_id, ue.user_id,
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
            SELECT rcid AS club_id, eid, created_at, ipk, is_meta, is_contact, is_trial
            FROM ev
            WHERE rcid IS NOT NULL
          UNION
            -- Customer product use: the club's own (non-archived) org traffic,
            -- never a super admin's acting-as activity.
            SELECT mc.id::text AS club_id, ev.eid, ev.created_at, ev.ipk,
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
                   WHEN is_meta THEN 0.0
                   WHEN created_at > NOW() - INTERVAL '7 days' THEN {WEB_DECAY['d7']}
                   WHEN created_at > NOW() - INTERVAL '14 days' THEN {WEB_DECAY['d14']}
                   WHEN created_at > NOW() - INTERVAL '21 days' THEN {WEB_DECAY['d21']}
                   WHEN created_at > NOW() - INTERVAL '28 days' THEN {WEB_DECAY['d28']}
                   WHEN created_at > NOW() - INTERVAL '90 days' THEN {WEB_DECAY['d90']}
                   ELSE 0.0
               END), 0.0)::float AS web_decay_pts,
               COALESCE(SUM(CASE
                   WHEN NOT is_meta THEN 0.0
                   WHEN created_at > NOW() - INTERVAL '7 days' THEN {AD_DECAY['d7']}
                   WHEN created_at > NOW() - INTERVAL '14 days' THEN {AD_DECAY['d14']}
                   WHEN created_at > NOW() - INTERVAL '21 days' THEN {AD_DECAY['d21']}
                   WHEN created_at > NOW() - INTERVAL '28 days' THEN {AD_DECAY['d28']}
                   WHEN created_at > NOW() - INTERVAL '90 days' THEN {AD_DECAY['d90']}
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


async def batch_email_stats(session) -> dict:
    """Single-pass equivalent of ``_engagement``'s per-club ``em`` (email
    engagement) query, for every club at once — the same idea as
    ``batch_web_stats``. Attributes each ``email_events`` row to a club by the
    club's own contact email OR its (non-archived) org id, ``UNION``-ed and
    deduped by event id so the two branches don't double-count, matching the
    per-club query's ``OR``. Returns ``{club_id_text: {...}}`` with the exact
    fields the per-club query yields."""
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
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '7 days' THEN {EMAIL_CLICK_DECAY['d7']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '14 days' THEN {EMAIL_CLICK_DECAY['d14']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '21 days' THEN {EMAIL_CLICK_DECAY['d21']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '28 days' THEN {EMAIL_CLICK_DECAY['d28']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '90 days' THEN {EMAIL_CLICK_DECAY['d90']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '7 days' THEN {EMAIL_OPEN_DECAY['d7']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '14 days' THEN {EMAIL_OPEN_DECAY['d14']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '21 days' THEN {EMAIL_OPEN_DECAY['d21']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '28 days' THEN {EMAIL_OPEN_DECAY['d28']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '90 days' THEN {EMAIL_OPEN_DECAY['d90']}
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
                      fast_web: bool = False) -> dict:
    """A per-club engagement rollup cached on the marketing_clubs row so the CRM can
    score and sort without holding raw events. Signal sources, all attributed to the club: web
    breadcrumbs (``usage_events`` by outreach UTM code or org id, both distinct-visitor
    reach AND raw page-view/API volume), email engagement (``email_events`` opens/
    clicks), a direct "onboard my club" website enquiry, and — for a customer — real
    per-module trial subscriptions (not just the marketing directory's aspirational
    trial-interest field).

    Lifecycle-aware: a PROSPECT is scored on lead heat (recency + frequency of web +
    email + buying intent); a CUSTOMER (linked org) is scored on account health +
    expansion, never Cold, with the modules they want-but-don't-pay-for surfaced as an
    upsell opportunity so a customer mid-sales-cycle is tracked, not buried at zero."""
    # "Not interested" is a manual disposition that overrides the computed heat, so it
    # isn't recomputed away on the next refresh — set it in the Club Directory.
    if getattr(club, "not_interested", False):
        result = {"engagementScore": 0, "engagementTier": "NOT_INTERESTED",
                  "sessions30d": 0, "emailEngaged30d": 0,
                  "upsellModules": [], "inSalesCycle": False}
        _apply_engagement_cache(club, result)
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
                   WHEN {_META_CLICK} THEN 0.0
                   WHEN ue.created_at > NOW() - INTERVAL '7 days' THEN {WEB_DECAY['d7']}
                   WHEN ue.created_at > NOW() - INTERVAL '14 days' THEN {WEB_DECAY['d14']}
                   WHEN ue.created_at > NOW() - INTERVAL '21 days' THEN {WEB_DECAY['d21']}
                   WHEN ue.created_at > NOW() - INTERVAL '28 days' THEN {WEB_DECAY['d28']}
                   WHEN ue.created_at > NOW() - INTERVAL '90 days' THEN {WEB_DECAY['d90']}
                   ELSE 0.0
               END), 0.0)::float AS web_decay_pts,
               -- Meta / paid ad-click landings, on the richer AD_DECAY curve.
               COALESCE(SUM(CASE
                   WHEN NOT {_META_CLICK} THEN 0.0
                   WHEN ue.created_at > NOW() - INTERVAL '7 days' THEN {AD_DECAY['d7']}
                   WHEN ue.created_at > NOW() - INTERVAL '14 days' THEN {AD_DECAY['d14']}
                   WHEN ue.created_at > NOW() - INTERVAL '21 days' THEN {AD_DECAY['d21']}
                   WHEN ue.created_at > NOW() - INTERVAL '28 days' THEN {AD_DECAY['d28']}
                   WHEN ue.created_at > NOW() - INTERVAL '90 days' THEN {AD_DECAY['d90']}
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
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '7 days' THEN {EMAIL_CLICK_DECAY['d7']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '14 days' THEN {EMAIL_CLICK_DECAY['d14']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '21 days' THEN {EMAIL_CLICK_DECAY['d21']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '28 days' THEN {EMAIL_CLICK_DECAY['d28']}
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '90 days' THEN {EMAIL_CLICK_DECAY['d90']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '7 days' THEN {EMAIL_OPEN_DECAY['d7']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '14 days' THEN {EMAIL_OPEN_DECAY['d14']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '21 days' THEN {EMAIL_OPEN_DECAY['d21']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '28 days' THEN {EMAIL_OPEN_DECAY['d28']}
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '90 days' THEN {EMAIL_OPEN_DECAY['d90']}
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
    reach_pts = REACH_PER_VISITOR * sessions
    depth_pts = DEPTH_SCALE * (email_decay_pts + web_decay_pts + ad_decay_pts)
    freq_pts = reach_pts + depth_pts
    recency = _recency_pts(last_touch)

    # A prospect whose org was born from a paid ad (self_serve_ad). Only meaningful
    # for a linked org; a bare directory row has no signup_source.
    ad_signup = (not is_customer and org is not None
                 and getattr(org, "signup_source", None) == "self_serve_ad")

    # Tier bands: see TIER_WARM_MIN / TIER_HOT_MIN.
    trial_depth = None
    if is_customer:
        # Account health + expansion. A paying account starts engaged, gains for
        # recent product use, and for an active expansion opportunity; floored at Warm.
        score = CUSTOMER_BASE + int(recency * 0.5) + min(int(freq_pts * 0.5), 20)
        if upsell:
            score += CUSTOMER_UPSELL_BONUS
        if onboarding_count:
            score += CUSTOMER_ONBOARDING_BONUS   # e.g. asking to onboard a second team/ground
        score = min(score, 100)
        tier = "HOT" if (score > TIER_HOT_MIN or upsell) else "WARM"
    else:
        # Prospect lead heat: recency + frequency of any touch + buying intent.
        score = recency + freq_pts
        if club.requested_trial_modules:
            score += BONUS_REQUESTED_TRIAL
        if (club.demo_status or "") == "in_trial":
            score += BONUS_IN_TRIAL
        if visited_contact:
            # Hit the contact page — a real "get in touch" signal, not just browsing.
            score += BONUS_CONTACT_PAGE
        if visited_trial:
            # Hit the /trial signup page — the strongest pre-enquiry buying intent.
            score += BONUS_VISIT_TRIAL
        if ad_signup:
            # Converted a paid ad click all the way to a self-serve registration.
            score += BONUS_AD_SIGNUP
        if onboarding_count:
            # A direct "onboard my club" enquiry is the strongest signal a prospect
            # can give — heavier than the admin-set requested_trial_modules flag.
            score += BONUS_ONBOARDING
        score = min(score, 100)
        tier = _tier_for(score)

        # Trial-depth floor: a self-serve/onboarded prospect's own product-setup
        # effort (registration, historical import, merges, module trial usage —
        # see services/trial_engagement.py) can outscore the web/email recency+
        # frequency formula above, especially in the first hours after signup
        # before any usage_events/email_events have had time to accumulate. Only
        # a floor (never lowers a score the ordinary formula already earned) and
        # only for a club that's actually been onboarded — a bare marketing-
        # directory row with no linked Organisation has nothing to be deep in.
        if org is not None:
            trial_depth = await trial_engagement.trial_depth_score(session, org)
            if trial_depth["score"] > score:
                score = trial_depth["score"]
                tier = _tier_for(score)

    # freq_pts sums fractional per-event decay points (the 21-28 day web-view tier
    # is worth 0.5), so score can come out fractional here — round once, at the
    # very end, so the tier-band comparisons above run on the precise value but the
    # cached score reads as a whole number.
    score = int(round(score))

    # A direct "onboard my club" enquiry (Contact page or the quick CTA modal)
    # holds a prospect at a flat Hot DIRECT_ENQUIRY_SCORE for a super-admin-
    # configured number of days (Club Directory > General Settings > Marketing)
    # — not just at the moment the enquiry lands, but on every later recompute
    # too (a full recalc sweep, or a BetterComms send), so it doesn't quietly
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
        score, tier = DIRECT_ENQUIRY_SCORE, "HOT"

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
        "upsellModules": _billable_module_values(upsell),
        "inSalesCycle": in_cycle,
        # Ever visited the public site (all-time, not the 30-day session count) so the
        # CRM can filter "has visited the site". `last_web` is MAX(created_at) of
        # web activity attributed by utm_id or org id — the primary attribution path.
        "hasVisitedSite": bool(last_web),
        # Whether a direct "onboard my club" enquiry is what's driving the heat, so
        # the CRM can source-label the deal "Contact us" rather than a generic bucket.
        "_onboardingRequested": bool(onboarding_count),
        # Internal-only score breakdown (underscore-prefixed) — lets a score be
        # explained rather than just observed.
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
    _apply_engagement_cache(club, fields)
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


async def _resolve_onboarding_club(session, *, club_name: str, contact_name: str,
                                   email: str, phone: "Optional[str]"):
    """Find-or-create the MarketingClub + MarketingClubContact a direct 'onboard
    my club' enquiry belongs to. Matching mirrors ``_onboarding_signal``'s own
    priority — the submitter's email against a known officer first (the
    strongest signal: this exact person is already on file for a specific
    club), then an exact club-name match, else a brand-new prospect club is
    created from what the form gave us, so a first-touch enquiry from a club
    the PlayHQ crawler hasn't found yet is never silently dropped. Commits
    nothing itself — the caller commits."""
    name = (club_name or "").strip()
    email_l = (email or "").strip().lower()

    club = None
    if email_l:
        club = (await session.execute(
            select(MarketingClub).join(
                MarketingClubContact, MarketingClubContact.marketing_club_id == MarketingClub.id)
            .where(func.lower(MarketingClubContact.email) == email_l)
            .limit(1)
        )).scalars().first()
    if club is None and name:
        club = (await session.execute(
            select(MarketingClub).where(func.lower(MarketingClub.name) == name.lower()).limit(1)
        )).scalars().first()
    if club is None:
        if not name:
            return None, None
        # No real PlayHQ GUID for a club that hasn't been crawled — a
        # deterministic synthetic one keyed on the name, so a second enquiry
        # from the same club (matched by name above) upserts the same row
        # rather than minting a duplicate.
        club = MarketingClub(
            grassroots_guid=f"manual:{uuid.uuid5(uuid.NAMESPACE_URL, name.lower())}",
            name=name[:200], kind="club", status="contacted", source="onboarding_form",
            contact_email=email_l or None, contact_phone=phone,
        )
        session.add(club)
        await session.flush()

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
                                   email: str, phone: "Optional[str]"):
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
    customer. Commits nothing itself — the caller commits."""
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
            status="contacted", source="self_serve_trial",
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
            source="self_serve_trial", subscribed=True, outreach_selected=True,
        )
        session.add(contact)
        await session.flush()
    elif not contact.outreach_selected:
        contact.outreach_selected = True

    return club, contact
