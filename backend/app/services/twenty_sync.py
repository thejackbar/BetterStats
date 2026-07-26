"""Export the targeted subset of the Clubs Directory into Twenty CRM.

``export_to_twenty`` mirrors ``club_directory.export_to_comms``: it runs the same
directory ``club_filters`` the page shows, then upserts the matched clubs, their
associations and their officers into Twenty as Companies / Associations / People.
Membership and idempotency are tracked in the ``twenty_links`` table (a row per
exported entity + a content hash so an unchanged record is a no-op on re-export).

Twenty holds only this exported subset, never the whole directory (a club enters
the CRM only when an operator exports it). See docs/twenty-crm-integration.md.
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

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.settings import settings
from app.models.db import (MarketingClub, MarketingClubContact, Organisation,
                           async_session_maker)
from app.services import platform_settings, trial_engagement
from app.services.club_directory import _PATH_CODE, club_filters
from app.services.twenty_client import (TwentyApiError, client, currency, emails_value,
                                        full_name, link, phone)

# A club's engagement score at or above this crosses from "worth watching" to
# "start the deal" — twenty_leads_tasks._seed_and_refresh_leads uses this to
# auto-create an Opportunity the moment a Lead's score reaches it, rather than
# waiting on a human to flip Twenty's own createOpportunity cascade field.
OPPORTUNITY_AUTO_THRESHOLD = 90

logger = logging.getLogger(__name__)

_ROLE_MAP = [
    ("vice president", "VICE_PRESIDENT"), ("vice-president", "VICE_PRESIDENT"),
    ("president", "PRESIDENT"), ("secretary", "SECRETARY"),
    ("treasurer", "TREASURER"), ("registrar", "REGISTRAR"),
    ("coordinator", "COORDINATOR"), ("club contact", "CLUB_CONTACT"),
    ("sponsor", "SPONSOR"),
]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _name_key(first, last) -> "str | None":
    """A normalised first+last key for matching a Contact. Twenty's Person duplicate
    criteria includes (firstName + lastName), so a shared officer whose junior-club
    record has a different/blank email still collides on name; this key is how we find
    and adopt that existing Contact. Both sides derive firstName/lastName via
    ``full_name``, so the key is consistent."""
    key = " ".join(((first or "") + " " + (last or "")).split()).lower()
    return key or None


def _hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def _clean(d: dict) -> dict:
    """Drop None (so we never clobber a Twenty field we have no value for); keep
    False / 0 / [] which are meaningful."""
    return {k: v for k, v in d.items() if v is not None}


def _modules(keys) -> list:
    return [str(k).upper() for k in (keys or []) if k]


# Twenty represents modules at the BILLABLE level: BetterAdmin is ONE module, so its
# members (fees/comms/merch — never sold or trialed on their own) collapse into
# 'admin'. core (always-on) and anything unrecognised are dropped. Result set:
# select / socials / admin / iq / fantasy (see bootstrap_twenty.MODULE_OPTS).
_ADMIN_MEMBERS = frozenset({"fees", "comms", "merch"})
_BILLABLE_KEYS = frozenset({"core", "select", "socials", "iq", "fantasy"})


def _billing_modules(keys) -> set:
    """Module keys (entitlement or billing) -> the set of Twenty billable module values
    (lowercase). fees/comms/merch -> admin; unknown dropped. core (BetterStats) is a
    billable module now, so it passes through."""
    out: set = set()
    for k in (keys or []):
        kk = str(k).lower().strip()
        if kk in _ADMIN_MEMBERS or kk == "admin":
            out.add("admin")
        elif kk in _BILLABLE_KEYS:
            out.add(kk)
        # anything unrecognised is dropped (not a Twenty paid/trial option)
    return out


def _twenty_modules(keys) -> list:
    """The MULTI_SELECT-safe, uppercase billable-module list for Twenty."""
    return sorted(k.upper() for k in _billing_modules(keys))


def _club_kind(name: Optional[str]) -> str:
    n = (name or "").lower()
    if "carnival" in n:
        return "CARNIVAL"
    if "school" in n:
        return "SCHOOL"
    if "junior" in n:
        return "JUNIOR"
    return "CLUB"


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
    # club is a Prospect (with a Lead raised — see twenty_leads_tasks), never
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


def _sub_status(club: MarketingClub) -> Optional[str]:
    d = (club.demo_status or "")
    if d == "in_trial":
        return "TRIAL"
    if d == "customer":
        return "ACTIVE"
    return None


def _role(role: Optional[str]) -> str:
    r = (role or "").lower().strip()
    for needle, val in _ROLE_MAP:
        if needle in r:
            return val
    return "OTHER"


# Public annual pricing (frontend/src/data/pricing.js): Core $399 + BetterSelect /
# BetterSocials / BetterAdmin $149 each + BetterIQ $249, with a bundle discount by
# priced add-on count. BetterAdmin is the fees+comms+merch umbrella. The $399 base is
# tied to Core being PAID — a club trialing/not-paying Core reads $0.
def _arr(module_keys) -> float:
    keys = _billing_modules(module_keys)  # collapse to billable (core/select/socials/admin/iq/...)
    total, priced = 0.0, 0
    if "core" in keys:
        total += 399                       # BetterStats base, only when paid
    if "select" in keys:
        total += 149; priced += 1
    if "socials" in keys:
        total += 149; priced += 1
    if "admin" in keys:
        total += 149; priced += 1          # BetterAdmin umbrella, charged once
    if "iq" in keys:
        total += 249; priced += 1
    return total - {0: 0, 1: 0, 2: 48, 3: 97, 4: 146}.get(priced, 146)


def _recency_pts(last, full=20):
    """Recency points from a last-touch timestamp: decays with age, a small floor
    for any touch ever, 0 if never.

    ``full`` was 40 — sitting almost exactly on the Hot cutoff (45) on its own, so
    a single page view this week already read Hot regardless of depth. Halved to
    20 so recency alone can't cross into Hot; real frequency (repeat visits, more
    than a couple of page views) or an explicit intent signal (trial request,
    contact form) has to contribute too. A few pages read this week now lands
    Warm, not Hot — sustained/repeat browsing still gets there via freq_pts."""
    if not last:
        return 0
    days = (datetime.datetime.now(datetime.timezone.utc) - last).days
    if days <= 7:
        return full
    if days <= 30:
        return int(full * 0.7)
    if days <= 90:
        return int(full * 0.35)
    return int(full * 0.1)


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
    regardless of which of the four call sites triggered the computation
    (manual export, bulk export, "Refresh Twenty scores", or "Refresh Twenty
    leads/tasks"), so the Club Directory / BetterComms Contacts+Lists /
    Segments can filter on a real number without recomputing this per-club
    scan themselves. Just sets attributes on the already-session-attached ORM
    object — the caller's own commit (every call site has one) persists it."""
    club.engagement_score = fields.get("engagementScore")
    club.engagement_tier = fields.get("engagementTier")
    club.engagement_scored_at = datetime.datetime.now(datetime.timezone.utc)


async def _engagement(session, club: MarketingClub,
                      org: "Optional[Organisation]" = None) -> dict:
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
    # "Not interested" is a manual disposition that overrides the computed heat, so it
    # isn't recomputed away on the next refresh — set it in the Club Directory.
    if getattr(club, "not_interested", False):
        result = {"engagementScore": 0, "engagementTier": "NOT_INTERESTED",
                  "sessions30d": 0, "emailEngaged30d": 0,
                  "upsellModules": [], "inSalesCycle": False}
        _apply_engagement_cache(club, result)
        return result
    utm = club.utm_code
    org_id = str(club.existing_org_id) if club.existing_org_id else None
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
    web = (await session.execute(text(f"""
        SELECT MAX(ue.created_at) AS last_seen,
               COUNT(DISTINCT ue.visitor_id)
                 FILTER (WHERE ue.created_at > NOW() - INTERVAL '30 days') AS sessions_30d,
               COUNT(*) FILTER (WHERE ue.created_at > NOW() - INTERVAL '30 days') AS events_30d,
               COALESCE(SUM(CASE
                   WHEN ue.created_at > NOW() - INTERVAL '7 days' THEN 3.0
                   WHEN ue.created_at > NOW() - INTERVAL '14 days' THEN 2.0
                   WHEN ue.created_at > NOW() - INTERVAL '21 days' THEN 1.0
                   WHEN ue.created_at > NOW() - INTERVAL '28 days' THEN 0.5
                   ELSE 0.0
               END), 0.0)::float AS web_decay_pts
        FROM usage_events ue
        WHERE (
                -- UTM-based attribution is for anonymous/prospect marketing traffic
                -- only. A UTM captured once in a browser tab (visitor.js
                -- getLinkCode()) keeps riding along on every later page view from
                -- that tab, including a staff member's own authenticated admin
                -- browsing — which has nothing to do with this club and would
                -- otherwise inflate its score. The org_id/org_slug branches below
                -- are deliberately NOT guarded the same way: for an actual
                -- customer, their own staff logging into their own club's admin
                -- IS the "product use" signal this score means to capture.
                (CAST(:utm AS text) IS NOT NULL
                 AND (ue.utm_id = CAST(:utm AS text) OR ue.utm_source = CAST(:utm AS text)
                      OR {_PATH_CODE} = CAST(:utm AS text))
                 AND ue.user_id IS NULL
                 AND split_part(ue.path, '?', 1) !~* '^/admin')
                OR (CAST(:org AS text) IS NOT NULL AND ue.org_id::text = CAST(:org AS text))
                OR (CAST(:org_slug AS text) IS NOT NULL AND {_PATH_CODE} = CAST(:org_slug AS text))
                OR (
                     EXISTS (
                          SELECT 1 FROM marketing_utm_aliases a
                          WHERE a.marketing_club_id = CAST(:cid AS uuid)
                            AND a.utm_value IN (ue.utm_id, ue.utm_source, {_PATH_CODE})
                     )
                     AND ue.user_id IS NULL
                     AND split_part(ue.path, '?', 1) !~* '^/admin'
                )
              )
    """), {"utm": utm, "org": org_id, "org_slug": org_slug, "cid": str(club.id)})).first()
    last_web = web[0] if web else None
    sessions = (web[1] or 0) if web else 0
    events_30d = (web[2] or 0) if web else 0
    web_decay_pts = float(web[3] or 0.0) if web else 0.0

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
    em = (await session.execute(text("""
        SELECT MAX(created_at) FILTER (WHERE event_type IN ('open','click')) AS last_eng,
               COUNT(*) FILTER (WHERE event_type IN ('open','click')
                                AND created_at > NOW() - INTERVAL '30 days') AS eng_30d,
               COALESCE(SUM(CASE
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '7 days' THEN 16.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '14 days' THEN 12.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '21 days' THEN 8.0
                   WHEN event_type = 'click' AND created_at > NOW() - INTERVAL '28 days' THEN 4.0
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '7 days' THEN 8.0
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '14 days' THEN 6.0
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '21 days' THEN 4.0
                   WHEN event_type = 'open' AND created_at > NOW() - INTERVAL '28 days' THEN 2.0
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

    # Reach (distinct visitors) and depth (the two per-event age-decayed sums) are
    # each squashed through a saturating curve (cap*raw/(raw+half)) — asymptotic
    # towards the cap but NEVER reaching it, so two different raw values can never
    # tie. A hard min(raw, cap) was tried first and genuinely broke on real data:
    # Tasmania Police CC (54 distinct visitors, 71 views) and Yarnteen CC (12
    # visitors, 20 views) both blew straight past a 24-point reach cap (hit at just
    # 4 sessions) and a 40-point depth cap (hit at ~14 recent page views), landing
    # on the exact same clipped freq_pts and the same final score (84) despite one
    # club having ~4x the other's real traffic. With a hard clip it doesn't matter
    # how far past the cap a club is — 10% over and 1000% over land on the same
    # number.
    # The curve keeps *some* headroom between any two real values all the way up
    # (diminishing returns, not a flat wall), while still bounding a crawler/bot's
    # score the same way a hard cap did. ``half`` (the raw value giving exactly
    # half the cap) is set equal to the cap itself — verified against real and
    # synthetic data to sit closest to the OLD hard-clip calibration for
    # low/typical volumes (a lone visitor's score barely moves) while still
    # clearly separating genuinely different high-volume clubs (Tasmania
    # Police's real 54-visitor/71-view case scores 76 vs Yarnteen's real
    # 12-visitor/20-view case at 62 — both previously clipped to an identical 84).
    def _saturate(raw: float, cap: float, half: float) -> float:
        return cap * raw / (raw + half) if raw > 0 else 0.0

    reach_pts = _saturate(sessions * 6, cap=24, half=24)
    depth_pts = _saturate(email_decay_pts + web_decay_pts, cap=40, half=40)
    freq_pts = reach_pts + depth_pts
    recency = _recency_pts(last_touch)

    # Tier bands: Cold < 30, Warm 30-45, Hot > 45 (open-ended at the top).
    trial_depth = None
    if is_customer:
        # Account health + expansion. A paying account starts engaged, gains for
        # recent product use, and for an active expansion opportunity; floored at Warm.
        score = 45 + int(recency * 0.5) + min(int(freq_pts * 0.5), 20)
        if upsell:
            score += 15
        if onboarding_count:
            score += 10   # e.g. asking to onboard a second team/ground
        score = min(score, 100)
        tier = "HOT" if (score > 45 or upsell) else "WARM"
    else:
        # Prospect lead heat: recency + frequency of any touch + buying intent.
        score = recency + freq_pts
        if club.requested_trial_modules:
            score += 12
        if (club.demo_status or "") == "in_trial":
            score += 8
        if onboarding_count:
            # A direct "onboard my club" enquiry is the strongest signal a prospect
            # can give — heavier than the admin-set requested_trial_modules flag.
            score += 20
        score = min(score, 100)
        tier = "COLD" if score < 30 else "WARM" if score <= 45 else "HOT"

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
                tier = "COLD" if score < 30 else "WARM" if score <= 45 else "HOT"

    # freq_pts sums fractional per-event decay points (the 21-28 day web-view tier
    # is worth 0.5), so score can come out fractional here — round once, at the
    # very end, so the tier-band comparisons above run on the precise value but the
    # field actually pushed to Twenty reads as a whole number.
    score = int(round(score))

    # A direct "onboard my club" enquiry (Contact page or the quick CTA modal)
    # holds a prospect at a flat Hot 100 for a super-admin-configured number of
    # days (Club Directory > General Settings > Marketing) — not just the
    # one-off push push_onboarding_enquiry() makes the moment the enquiry
    # lands, but on every later recompute too (the nightly refresh, a
    # BetterComms send, a manual "Refresh Twenty scores"), so it doesn't quietly
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
        score, tier = 100, "HOT"

    # In an active sales cycle: a customer expanding, or a prospect showing intent or
    # RECENT engagement (so it's a deal to work, not just a name on a list). Uses
    # ``sessions``/``eng_30d`` (both 30-day-windowed), not the all-time ``last_touch``
    # — a single click years ago shouldn't keep a club permanently flagged in-cycle
    # long after its score has decayed back to Cold.
    in_cycle = bool(upsell or onboarding_count) if is_customer else bool(
        club.requested_trial_modules or (club.demo_status or "") == "in_trial"
        or onboarding_count or sessions or eng_30d
        or (trial_depth and trial_depth["score"] >= 70))

    fields = {
        "engagementScore": score,
        "engagementTier": tier,
        "sessions30d": sessions,
        "emailEngaged30d": eng_30d,
        "upsellModules": _twenty_modules(upsell),
        "inSalesCycle": in_cycle,
        # Ever visited the public site (all-time, not the 30-day session count) so a
        # CRM View can filter "has visited the site". `last_web` is MAX(created_at) of
        # web activity attributed by utm_id or org id — the primary attribution path.
        "hasVisitedSite": bool(last_web),
        # Exposed for the Lead lane (twenty_leads_tasks) to source-label a Lead
        # raised off a direct enquiry as "Contact us" rather than a generic bucket.
        "_onboardingRequested": bool(onboarding_count),
        # Internal-only score breakdown (underscore-prefixed, stripped by _public()
        # before anything reaches Twenty) — for diagnose_club_lead.py, so a score
        # can actually be explained rather than just observed.
        "_recencyPts": recency,
        "_emailDecayPts": round(email_decay_pts, 1),
        "_webDecayPts": round(web_decay_pts, 1),
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


def _company_values(club: MarketingClub, org: "Optional[Organisation]" = None,
                    all_unsub: bool = False) -> dict:
    # Association membership is a separate many-to-many via the clubAssociation
    # junction (see _sync_memberships), each membership carrying an isPrimary flag —
    # so the primary association is recoverable from the relations and the company
    # holds no denormalised association field. Customer-side fields (paid modules,
    # subscription, renewal, billing, ARR) come from the linked Organisation when
    # the club is already onboarded.
    #
    # Per-module split (migration 118) resolved up front so lifecycleStage agrees
    # with paidModules/ARR below: a club only counts as CUSTOMER once it genuinely
    # holds a paid module, not merely because it's been synced.
    paid, trial, renewals = _module_split(org) if org is not None else ([], [], [])
    is_paying = bool(paid) or (club.demo_status or "") == "customer"
    vals = {
        "name": club.name,
        "bcClubId": club.grassroots_guid,
        "lifecycleStage": _lifecycle(club, is_paying, all_unsub),
        "subscriptionStatus": _sub_status(club),
        "trialModules": _twenty_modules(club.trial_modules),
        "interestedModules": _twenty_modules(club.requested_trial_modules),
        "clubKind": _club_kind(club.name),
        "clubState": club.state,
        "country": club.country,
        "postcode": club.postcode,
        "utmCode": club.utm_code,
        "dataSource": "PLAYHQ",
        "publicProfileUrl": link(club.website_url),
        "existingKpCustomer": "YES" if club.existing_org_id else "NO",
        "lastSyncedAt": _now_iso(),
        # Association membership as a read-only multi-value array (replaces the
        # clubAssociation junction): every association the club plays in, by name.
        "associations": [name for _g, name, _p in _club_assocs(club)],
    }
    if org is not None:
        status = (org.subscription_status or "").lower()
        vals["subscriptionStatus"] = status.upper() or None
        # The org-level status stays a master switch — paused/cancelled there means
        # nothing is live, so paidModules is empty and ARR is $0 (already reflected
        # in ``paid`` above, since _module_split zeroes out when the switch is off).
        vals["paidModules"] = _twenty_modules(paid)
        vals["arr"] = currency(_arr(paid))
        if trial:
            vals["trialModules"] = sorted(set(vals.get("trialModules") or []) | set(_twenty_modules(trial)))
        if org.billing_cycle:
            vals["billingCycle"] = org.billing_cycle.upper()
        # The next renewal across paid modules (each module now renews on its own
        # date); fall back to the legacy org-level renewal_date.
        renewal = min(renewals) if renewals else org.renewal_date
        if renewal:
            vals["renewalDate"] = renewal.isoformat() + "T00:00:00Z"
    return _clean(vals)


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


def _person_values(ct: MarketingClubContact, club_country: Optional[str] = None) -> dict:
    """The Person's STABLE IDENTITY only — safe to PATCH on every export, even for an
    officer who serves several clubs. Twenty enforces one Person per email, so a
    shared officer is a single Person; their per-club role/company live on the
    personClub junction (_officer_role_values), never here, so re-exporting from a
    second club can't overwrite the first club's role or steal the person to it."""
    vals = {
        "name": full_name(ct.full_name),
        "subscribed": bool(ct.subscribed),
        "bounced": bool(ct.bounced),
        "namedEmail": bool(ct.full_name and ct.email),
        "country": club_country,        # an officer inherits their club's country
    }
    ev = emails_value(ct.email)
    if ev:
        vals["emails"] = ev
    ph = phone(ct.mobile)
    if ph:
        vals["phones"] = ph
    return _clean(vals)


def _person_create_extra(ct: MarketingClubContact) -> dict:
    """Fields written ONCE, when the Person is first created by its introducing club:
    the native company + that club's role, plus the default contact source. Set-once
    (create_extra, never on update) so a later export from another club never steals
    the person onto itself — the full per-club picture is the personClub junction.
    ``companyId`` is injected at IO time once the club's Company id is known."""
    extra = {
        "bcContactId": str(ct.id),
        "clubRole": _role(ct.role),
        "roleRank": ct.role_rank,
        "outreachSelected": bool(ct.outreach_selected),
        # The directory export is not a real contact source — seed it to "No Contact
        # Source" and leave it operator-editable; real contact events set it later.
        "contactSource": "NO_CONTACT_SOURCE",
    }
    if ct.role:
        extra["jobTitle"] = ct.role          # the raw role into Twenty's standard Job title
    return _clean(extra)


def _officer_role_values(ct: MarketingClubContact, club_name: str) -> dict:
    """One personClub membership: this officer's role AT this club. Always PATCHed
    (kept fresh per club), so a shared officer shows under EVERY club they serve with
    the right role. ``personId`` / ``companyId`` are injected at IO time."""
    vals = {
        "name": f"{ct.full_name or 'Officer'} — {club_name}",
        "bcContactId": str(ct.id),
        "clubRole": _role(ct.role),
        "roleTitle": ct.role or None,
        "roleRank": ct.role_rank,
        "outreachSelected": bool(ct.outreach_selected),
    }
    # The per-club email + phone live on the junction so a club-specific contact
    # detail is kept even when it differs from the shared Contact's canonical one, and
    # so a club's "Officer roles" view shows role, email and mobile together.
    ev = emails_value(ct.email)
    if ev:
        vals["email"] = ev
    ph = phone(ct.mobile)
    if ph:
        vals["phone"] = ph
    return _clean(vals)


def _scoped(contacts, scope: str):
    out = []
    for ct in contacts:
        named = bool(ct.full_name and ct.email)
        if scope == "named" and not named:
            continue
        if scope == "pst" and not (named and _role(ct.role) in ("PRESIDENT", "SECRETARY", "TREASURER")):
            continue
        if scope == "all" and not (ct.full_name or ct.email):
            continue
        out.append(ct)
    return out


# ── link table ────────────────────────────────────────────────────────────────

async def _link_get(session: AsyncSession, entity_type: str, bc_id: str):
    row = (await session.execute(text(
        "SELECT twenty_id, content_hash FROM twenty_links "
        "WHERE entity_type = :e AND bc_id = :b"),
        {"e": entity_type, "b": bc_id})).first()
    return (row[0], row[1]) if row else None


async def _link_put(session: AsyncSession, entity_type: str, bc_id: str,
                    twenty_id: str, content_hash: str):
    await session.execute(text(
        "INSERT INTO twenty_links (entity_type, bc_id, twenty_id, content_hash, last_synced_at) "
        "VALUES (:e, :b, :t, :h, NOW()) "
        "ON CONFLICT (entity_type, bc_id) DO UPDATE SET "
        "twenty_id = EXCLUDED.twenty_id, content_hash = EXCLUDED.content_hash, "
        "last_synced_at = NOW()"),
        {"e": entity_type, "b": bc_id, "t": twenty_id, "h": content_hash})


async def _raise_task(session, http, ext_ref: str, title: str,
                      company_tid: "Optional[str]" = None, due_at=None) -> "Optional[str]":
    """Create one Twenty Task, deduped on ``ext_ref`` via ``twenty_links``
    (entity_type ``task``) — shared by the daily Lead/Task scan
    (twenty_leads_tasks) and any event-driven Task raise (a queued module trial
    request, a "sync this club first" prompt, …). Best-effort: logs and returns
    None on failure or when a Task for this ref already exists, never raises."""
    if await _link_get(session, "task", ext_ref):
        return None
    values: dict = {"title": title[:255], "status": "TODO"}
    if due_at is not None:
        values["dueAt"] = due_at.isoformat()
    if settings.twenty_task_assignee_id:
        values["assigneeId"] = settings.twenty_task_assignee_id
    try:
        task = await client.create(http, "tasks", values)
    except Exception:  # noqa: BLE001
        logger.exception("twenty task create failed (%s)", ext_ref)
        return None
    tid = task.get("id")
    if not tid:
        return None
    await _link_put(session, "task", ext_ref, tid, "")
    if company_tid:
        try:
            await client.create(http, "taskTargets", {"taskId": tid, "companyId": company_tid})
        except Exception:  # noqa: BLE001 - the task still exists unlinked
            logger.exception("twenty taskTarget link failed for task %s", tid)
    return tid


async def _index_people_pass(session, http, filter: "str | None") -> tuple:
    """Paginate ``GET /people`` (optionally filtered, e.g. to soft-deleted records)
    and index each into the email/name maps. Returns (count, completed) — completed is
    False if a request errored mid-scan, so the caller doesn't prematurely mark the
    backfill done."""
    cursor, seen, completed = None, 0, False
    for _ in range(200):  # cap 200 pages * 60 = 12k people
        try:
            payload = await client.list_page(http, "people", limit=60,
                                             starting_after=cursor, filter=filter)
        except Exception:  # noqa: BLE001
            logger.exception("twenty prewarm: listing people (filter=%r) failed", filter)
            break
        data = payload.get("data") if isinstance(payload, dict) else None
        people = data.get("people") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not people:
            completed = True
            break
        for p in people:
            pid = p.get("id")
            if not pid:
                continue
            email = ((p.get("emails") or {}).get("primaryEmail") or "").strip().lower()
            nm = p.get("name") or {}
            nkey = _name_key(nm.get("firstName"), nm.get("lastName"))
            if email:
                await _link_put(session, "person_email", email, pid, "")
            if nkey:
                await _link_put(session, "person_name", nkey, pid, "")
            if email or nkey:
                seen += 1
        page = (payload.get("pageInfo") or {}) if isinstance(payload, dict) else {}
        cursor = page.get("endCursor")
        # Stop on the last page. Fall back to the last record's id as a cursor if the
        # payload doesn't carry pageInfo but the page was full.
        if page.get("hasNextPage") is False:
            completed = True
            break
        if not cursor:
            if len(people) < 60:
                completed = True
                break
            cursor = people[-1].get("id")
            if not cursor:
                completed = True
                break
    return seen, completed


async def _prewarm_person_emails(session, http, force: bool = False) -> int:
    """ONE-TIME backfill of the email/name -> Person id map in twenty_links. The map is
    the permanent index used to adopt a shared officer (Twenty's own email filter
    doesn't reliably match an existing record on this version); it is maintained
    INCREMENTALLY on every person upsert, so the steady state costs nothing extra per
    export. This full scan only seeds contacts that already lived in Twenty before the
    map existed — so it runs once (guarded by a marker) and then never on the hot path.

    Two passes: active records, then SOFT-DELETED ones (Twenty hides those from a
    default list but still counts them in its uniqueness check, so a stale soft-deleted
    Contact blocks a create — indexing it lets us adopt and restore it via deletedAt
    null). Best-effort. Returns how many entries were indexed.

    Pass ``force=True`` to re-seed (e.g. after bulk manual edits in Twenty)."""
    # Marker is versioned: v3 also covers name + soft-deleted, so bumping it forces a
    # single re-scan on upgrade.
    if not force and await _link_get(session, "_meta", "person_index_v3_backfilled"):
        return 0
    active_n, active_done = await _index_people_pass(session, http, None)
    deleted_n, _deleted_done = await _index_people_pass(session, http, "deletedAt[is]:NOT_NULL")
    # Mark done on a clean ACTIVE pass; the soft-deleted pass is best-effort (the filter
    # may be unsupported), so it never blocks the marker or forces a re-scan every run.
    if active_done:
        await _link_put(session, "_meta", "person_index_v3_backfilled", "1", "")
    await session.commit()
    logger.info("twenty prewarm: indexed %d contact(s) by email+name (incl. %d soft-deleted)%s",
                active_n + deleted_n, deleted_n, "" if active_done else " (incomplete, will retry)")
    return active_n + deleted_n


def _link_keys_in(values: dict) -> list:
    """Which keys in ``values`` carry a Twenty LINKS-shaped value (detected by the
    ``primaryLinkUrl`` sub-key link() always sets), so a rejected link field can be
    identified and dropped generically regardless of which field it was."""
    return [k for k, v in values.items() if isinstance(v, dict) and "primaryLinkUrl" in v]


def _is_invalid_url_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "invalid_url" in msg or "url of the link is not valid" in msg


async def _update_resilient(http, plural, record_id, values):
    """PATCH, retrying once without any LINKS-shaped value if Twenty rejects one as
    invalid. A record already in Twenty shouldn't start failing every refresh just
    because a directory-scraped website field turned out messier than link()'s own
    cleanup in twenty_client.py could catch."""
    try:
        return await client.update(http, plural, record_id, values)
    except TwentyApiError as e:
        if not _is_invalid_url_error(e):
            raise
        link_keys = _link_keys_in(values)
        if not link_keys:
            raise
        logger.warning(
            "twenty: %s %s update rejected link field(s) %s (value=%r) — "
            "dropping and retrying without them",
            plural, record_id, link_keys, {k: values[k] for k in link_keys})
        return await client.update(
            http, plural, record_id, {k: v for k, v in values.items() if k not in link_keys})


async def _upsert(session, http, entity_type, bc_id, plural, ext_field, values,
                  create_extra=None, dedup=None, known_id=None):
    """Create-or-update a Twenty record, keyed on the local link table first, then
    the external-key field as a dedupe fallback. ``create_extra`` is merged only on
    creation (not on update), so fields an operator may edit in Twenty (e.g. a
    membership's isPrimary) are set once and never overwritten. The content hash is
    computed on ``values`` only, so create_extra never forces an update.

    ``known_id`` is a Twenty record id we already know maps to this entity (e.g. a
    shared Person resolved by email from our OWN link table). We can't trust Twenty's
    email filter to find a duplicate (it doesn't match on this version), so the local
    map is the reliable adopt target — used both as a direct adopt and to recover from
    a duplicate-create 400. Returns (twenty_id, action)."""
    h = _hash(values)
    link_row = await _link_get(session, entity_type, bc_id)
    if link_row:
        tid, _old_hash = link_row
        # Always PATCH — never trust a cached hash to mean "still present". A record
        # can be deleted in Twenty out-of-band, and only the update round-trip tells
        # us (404 -> recreate below). Skipping on a matching hash would leave a
        # deleted record gone forever.
        updated = await _update_resilient(http, plural, tid, values)
        if updated is not None:
            await _link_put(session, entity_type, bc_id, tid, h)
            return tid, "updated"
        # stale link: the record was deleted in Twenty — fall through to recreate.
    existing = await client.find_by(http, plural, ext_field, bc_id) if ext_field else None
    # Also look up by a Twenty-unique field (e.g. a person's email): two clubs can
    # share an officer, and Twenty rejects a second person with the same email as a
    # duplicate. Adopt the existing record instead of failing the create.
    if not existing and dedup:
        existing = await client.find_by(http, plural, dedup[0], dedup[1])
    adopt_id = (existing or {}).get("id") or known_id
    if adopt_id:
        if await _update_resilient(http, plural, adopt_id, values) is not None:
            await _link_put(session, entity_type, bc_id, adopt_id, h)
            return adopt_id, "adopted"
    try:
        rec = await client.create(http, plural, {**values, **(create_extra or {})})
    except TwentyApiError as e:
        # Twenty enforces uniqueness on some fields (notably a Person's email). On a
        # duplicate collision, adopt the record we already know is the duplicate
        # (known_id from our local email map) rather than dropping the officer. This
        # is what stops a shared officer silently vanishing.
        if known_id and "duplicate" in str(e).lower():
            if await client.update(http, plural, known_id, values) is not None:
                await _link_put(session, entity_type, bc_id, known_id, h)
                return known_id, "adopted"
            raise
        # A LINKS-type value (e.g. Company.publicProfileUrl) can still fail Twenty's
        # own stricter validation even after link()'s cleanup in twenty_client.py —
        # don't lose the whole record over one optional field. Drop whichever
        # LINKS-shaped value(s) are present and retry once; the log line records the
        # actual rejected value so a recurring shape can be added to link()'s cleanup.
        if not _is_invalid_url_error(e):
            raise
        link_keys = _link_keys_in(values)
        if not link_keys:
            raise
        logger.warning(
            "twenty: %s %s create rejected link field(s) %s (value=%r) — "
            "dropping and retrying without them",
            entity_type, bc_id, link_keys, {k: values[k] for k in link_keys})
        stripped = {k: v for k, v in values.items() if k not in link_keys}
        rec = await client.create(http, plural, {**stripped, **(create_extra or {})})
    tid = rec["id"]
    await _link_put(session, entity_type, bc_id, tid, h)
    return tid, "created"


async def _assoc_modal(session, guid: Optional[str], name: Optional[str],
                       col: str) -> Optional[str]:
    """Derive an association attribute (state / country) from the modal value
    among its member clubs (associations carry neither of their own). Matches
    members by the primary association_guid or the associations JSONB array,
    falling back to name. ``col`` is whitelisted, never client input."""
    assert col in ("state", "country")
    if guid:
        row = (await session.execute(text(
            f"SELECT {col} FROM marketing_clubs "
            f"WHERE {col} IS NOT NULL AND {col} <> '' "
            "AND (association_guid = :g OR associations @> CAST(:elem AS jsonb)) "
            f"GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 1"),
            {"g": guid, "elem": json.dumps([{"id": guid}])})).first()
        if row:
            return row[0]
    if name:
        row = (await session.execute(text(
            f"SELECT {col} FROM marketing_clubs "
            f"WHERE {col} IS NOT NULL AND {col} <> '' "
            "AND lower(association_name) = lower(:n) "
            f"GROUP BY {col} ORDER BY COUNT(*) DESC LIMIT 1"),
            {"n": name})).first()
        if row:
            return row[0]
    return None


async def _assoc_extra(session, guid: Optional[str], name: Optional[str]) -> dict:
    """Short code + linked-club count (from the association registry) + a state and
    country derived from the member clubs."""
    extra: dict = {}
    if guid:
        row = (await session.execute(text(
            "SELECT short_code, club_count FROM marketing_associations WHERE id = :id"),
            {"id": guid})).first()
        if row:
            extra["shortCode"] = row[0]
            extra["clubCount"] = row[1]
    extra["assocState"] = await _assoc_modal(session, guid, name, "state")
    extra["assocCountry"] = await _assoc_modal(session, guid, name, "country")
    return _clean(extra)


async def _ensure_assoc_by(session, http, guid: Optional[str], name: str,
                           cache: dict, stats) -> Optional[str]:
    """Upsert one association by (guid, name) and return its Twenty id."""
    bc_id = guid or ("name:" + name)
    if bc_id in cache:
        return cache[bc_id]
    values = _clean({"name": name, "bcAssociationId": bc_id,
                     **(await _assoc_extra(session, guid, name))})
    try:
        tid, act = await _upsert(session, http, "association", bc_id,
                                 "associations", "bcAssociationId", values)
        stats["assoc_" + act] += 1
        cache[bc_id] = tid
        return tid
    except Exception:  # noqa: BLE001 - association is best-effort
        logger.exception("twenty assoc upsert failed for %s", name)
        return None


def _club_assocs(club: MarketingClub):
    """Every association the club belongs to as (guid, name, is_primary), deduped.
    Combines the primary association_name/guid with the full associations JSONB
    array; is_primary marks the one PlayHQ lists as primary (editable in Twenty)."""
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


async def _sync_memberships(session, http, club_guid, club_name, assocs, company_tid,
                            cache, stats):
    """Upsert one clubAssociation (membership) per association the club plays in,
    so a club shows under every association and an association shows all its clubs.
    isPrimary is set on creation only, so an operator can re-point it in Twenty.
    ``assocs`` is the pre-snapshotted _club_assocs list (plain tuples)."""
    for guid, name, is_primary in assocs:
        assoc_tid = await _ensure_assoc_by(session, http, guid, name, cache, stats)
        if not assoc_tid:
            continue
        bc_id = f"{club_guid}:{guid or name}"
        values = _clean({"name": f"{club_name} — {name}",
                         "companyId": company_tid, "associationId": assoc_tid})
        _, act = await _upsert(session, http, "membership", bc_id, "clubAssociations",
                               None, values, create_extra={"isPrimary": bool(is_primary)})
        stats["memberships_" + act] += 1


# Company field -> Lead field, for whatever a Lead mirrors from its Company.
_LEAD_MIRROR_FIELDS = {
    "engagementScore": "engagementScore",
    "lifecycleStage": "lifecycleStage",
}


async def _sync_lead_from_company(session, http, club_guid: str, company_fields: dict) -> None:
    """Mirror onto a club's Lead (if any) whatever of the Company's fields the Lead
    also carries — engagementScore and lifecycleStage — the moment the Company is
    pushed, from ANY path that can change either: BetterCricket's own recompute
    (export_to_twenty, refresh_engagement, push_club_and_contacts) is what actually
    drives the value, so mirroring right after each of those pushes covers every
    source of change without waiting for the daily Lead seed/refresh
    (twenty_leads_tasks._lead_values sets both there too, for a brand-new Lead).
    No-op if the club has no Lead yet, or ``company_fields`` touches neither mirrored
    field; best-effort, never raises into the Company push."""
    mirrored = {lead_key: company_fields[co_key]
                for co_key, lead_key in _LEAD_MIRROR_FIELDS.items()
                if co_key in company_fields}
    if not mirrored:
        return
    try:
        lead_row = await _link_get(session, "lead", club_guid)
        if lead_row:
            await client.update(http, "leads", lead_row[0], mirrored)
    except Exception:  # noqa: BLE001 - a CRM hiccup must never fail the Company push
        logger.exception("twenty: failed to mirror company fields to lead for %s", club_guid)


async def update_person_by_email(email: str, fields: dict) -> None:
    """Best-effort update of a Person matched by their unique email with arbitrary
    Twenty fields (contact source, subscribed/bounced flags, last campaign, …).
    No-op if Twenty isn't configured or the person isn't in the CRM, and never
    raises into the caller — used from public/webhook paths that must not break."""
    if not client.configured or not email or not fields:
        return
    email = email.strip().lower()
    try:
        # Prefer our own email -> Person map (Twenty's email filter is unreliable on
        # this version); fall back to the filter for anyone not yet in the map.
        async with async_session_maker() as session:
            row = await _link_get(session, "person_email", email)
        tid = row[0] if row else None
        async with httpx.AsyncClient() as http:
            if not tid:
                person = await client.find_by(http, "people", "emails.primaryEmail", email)
                tid = person.get("id") if person else None
            if tid:
                await client.update(http, "people", tid, fields)
    except Exception:  # noqa: BLE001 - never let a CRM error affect the caller
        logger.exception("twenty update_person_by_email failed for %s", email)


async def mark_contact_source(email: str, source: str) -> None:
    """Set a Person's Contact source to ``source`` (WEBSITE / BETTERCOMMS_EMAIL /
    MANUAL_EMAIL). Most-recent-channel-wins, so it just writes the channel of the
    event that fired it (last write)."""
    await update_person_by_email(email, {"contactSource": source})


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


async def _downgrade_lead_and_opportunities(session, http, club_guid: str,
                                            company_tid: "Optional[str]") -> None:
    """A club whose every officer has opted out shouldn't sit in active sales
    triage: discard its Lead (if any) and mark any of its still-open Opportunities
    Lost / Dormant. Best-effort — the Opportunity relation-filter path
    (``company.id[eq]:``) is unverified against the live workspace, same caveat as
    the Task field paths in twenty_leads_tasks."""
    lead_row = await _link_get(session, "lead", club_guid)
    if lead_row:
        try:
            await client.update(http, "leads", lead_row[0], {"leadStatus": "DISCARDED"})
        except Exception:  # noqa: BLE001
            logger.exception("twenty: failed to discard lead for suppressed club %s", club_guid)
    if not company_tid:
        return
    try:
        payload = await client.list_page(http, "opportunities", limit=60,
                                         filter=f"company.id[eq]:{company_tid}")
        data = payload.get("data") if isinstance(payload, dict) else None
        opps = data.get("opportunities") if isinstance(data, dict) else None
        for opp in (opps or []):
            if (opp.get("stage") or "") in ("Won", "Lost / Dormant") or not opp.get("id"):
                continue
            await client.update(http, "opportunities", opp["id"], {"stage": "Lost / Dormant"})
    except Exception:  # noqa: BLE001 - opportunities aren't tracked in twenty_links; best-effort only
        logger.exception("twenty: failed to downgrade opportunities for suppressed club %s", club_guid)


async def enforce_club_suppression(session, club_id) -> dict:
    """Recompute whether every named-email officer of this club has opted out, and
    if so, mark its Company Suppressed (unless it's a genuinely paying customer)
    and downgrade any open Lead/Opportunity. Called right after a contact's
    subscribed flag flips false (unsubscribe link / SES bounce / complaint); the
    same check also runs inline for every linked club on each ``refresh_engagement``
    pass (nightly job + the one-time reconcile script), so it self-heals even
    without a real-time trigger. No-op and never raises — this must not affect the
    triggering request."""
    if not client.configured:
        return {"skipped": "not configured"}
    try:
        club = await session.get(MarketingClub, club_id)
        if club is None:
            return {"skipped": "no club"}
        if not await _all_contacts_unsubscribed(session, club.id):
            return {"skipped": "not all unsubscribed"}
        link_row = await _link_get(session, "club", club.grassroots_guid)
        if not link_row:
            return {"skipped": "club not in CRM"}
        company_tid = link_row[0]
        org = (await session.get(Organisation, club.existing_org_id)
               if club.existing_org_id else None)
        paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
        if paid or (club.demo_status or "") == "customer":
            return {"skipped": "paying customer"}
        async with httpx.AsyncClient() as http:
            await client.update(http, "companies", company_tid, {"lifecycleStage": "SUPPRESSED"})
            await _downgrade_lead_and_opportunities(session, http, club.grassroots_guid, company_tid)
        return {"ok": True, "club": club.name}
    except Exception as e:  # noqa: BLE001 - never let a CRM error affect the caller
        logger.exception("twenty enforce_club_suppression failed for %s", club_id)
        return {"error": str(e)}


async def handle_contact_opt_out(session, email: str) -> None:
    """After a contact's subscribed flag flips false (unsubscribe / bounce /
    complaint), check every marketing club they're an officer of and suppress the
    ones where every officer has now opted out. Best-effort, never raises."""
    if not client.configured or not email:
        return
    try:
        rows = (await session.execute(text(
            "SELECT DISTINCT marketing_club_id FROM marketing_club_contacts "
            "WHERE lower(email) = :e AND marketing_club_id IS NOT NULL"),
            {"e": email.strip().lower()})).all()
        for (cid,) in rows:
            await enforce_club_suppression(session, cid)
    except Exception:  # noqa: BLE001
        logger.exception("twenty handle_contact_opt_out failed for %s", email)


async def push_club_and_contacts(marketing_club_id, contact_ids: "list | None" = None,
                                 engagement_override: "Optional[dict]" = None,
                                 force_lead: bool = False,
                                 create_opportunity: bool = False,
                                 opportunity_modules: "Optional[list]" = None,
                                 lead_lifecycle_override: "Optional[str]" = None,
                                 opportunity_stage: "Optional[str]" = None) -> dict:
    """Best-effort: upsert ONE prospect club's Company + the given
    MarketingClubContact ids (People) into Twenty. This is the "every email sent
    should upsert a record" hook: sending a BetterComms campaign to a club's
    officer is itself the moment they enter the targeted CRM subset — no manual
    "export to Twenty" click required first. A club not yet in the CRM is created
    fresh, landing at its computed lifecycle stage (Target, for a first-ever send).

    ``contact_ids`` defaults to the club's outreach-selected officers when omitted.
    ``engagement_override`` merges over the normally-computed engagement rollup —
    used by ``push_onboarding_enquiry`` to force a direct "onboard my club"
    enquiry to score as an immediate Hot (100) lead rather than whatever the
    gradual recency/frequency formula would give a brand-new signal. When given,
    this ALSO upserts a real Lead (create-or-refresh) instead of only mirroring
    onto one that already exists, so a first-touch enquiry gets a Lead in Twenty
    right away rather than waiting for tomorrow's 07:00 refresh to notice it —
    ordinary callers (a campaign send) are unaffected, since Twenty's own "does
    this club currently qualify as a Lead" rule (``_lead_signal``) already gates
    against a routine send alone creating one.

    ``force_lead`` (without an ``engagement_override``) also upserts a real Lead
    immediately, using the NORMALLY-COMPUTED engagement rollup rather than a
    forced score — used by ``push_self_serve_registration``, where the
    registration itself is real news worth a Lead right away, but the actual
    score should still come from ``_engagement()`` (which now includes the
    trial-depth floor from services/trial_engagement.py) rather than a flat
    override the way a direct enquiry gets.

    ``create_opportunity`` additionally upserts an Opportunity right after the
    Lead, but ONLY once the engagement score (after any override) has actually
    reached ``OPPORTUNITY_AUTO_THRESHOLD`` — a brand-new self-serve signup is
    real interest, but not yet a deal to work; the Opportunity is earned by the
    club's own trial-depth score crossing the line, whether that happens at
    this exact call or a later refresh notices it (see
    twenty_leads_tasks._seed_and_refresh_leads for the recurring check).
    ``opportunity_modules`` scopes it; falls back to
    ``twenty_opportunity._default_modules(club)`` when omitted. Every other
    caller leaves both off and is unaffected.

    ``lead_lifecycle_override``/``opportunity_stage`` force the Lead's
    ``lifecycleStage`` and the Opportunity's ``stage`` at creation (via
    ``create_extra`` — see both functions' own docstrings for exactly how long
    each sticks). Used by ``push_self_serve_registration`` to open both at
    "Self-Serve Trial" instead of the normally-computed lifecycle / the default
    "Contacted" stage.

    Opens its own session + http client; never raises — a CRM hiccup must never
    break a send."""
    if not client.configured or not marketing_club_id:
        return {"skipped": "not configured"}
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False
            club = await session.get(MarketingClub, marketing_club_id)
            if club is None:
                return {"skipped": "no club"}
            org = (await session.get(
                        Organisation, club.existing_org_id,
                        options=[selectinload(Organisation.module_subscriptions)])
                   if club.existing_org_id else None)
            cq = select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id)
            if contact_ids:
                cq = cq.where(MarketingClubContact.id.in_(contact_ids))
            else:
                cq = cq.where(MarketingClubContact.outreach_selected.is_(True))
            contacts = (await session.execute(cq)).scalars().all()
            all_unsub = await _all_contacts_unsubscribed(session, club.id)
            engagement = await _engagement(session, club, org)
            if engagement_override:
                engagement = {**engagement, **engagement_override}
            # Local BetterCRM equivalent of Twenty's own OPPORTUNITY_AUTO_THRESHOLD
            # gate below — a club's score (forced-Hot override or the ordinary
            # formula) crossing 70 promotes its existing platform deal straight to
            # Engaged. See crm.maybe_promote_by_engagement_score's own docstring
            # for why it never creates a deal from nothing.
            from app.services import crm as crm_service
            club.engagement_score = engagement.get("engagementScore")
            await crm_service.maybe_promote_by_engagement_score(session, club)
            company = {**_company_values(club, org, all_unsub=all_unsub), **engagement}
            club_stage = company["lifecycleStage"]

            async with httpx.AsyncClient() as http:
                ctid, _cact = await _upsert(session, http, "club", club.grassroots_guid,
                                            "companies", "bcClubId", company)
                if engagement_override or force_lead:
                    from app.services import twenty_leads_tasks
                    await twenty_leads_tasks.upsert_lead_for_club(
                        session, http, club, org, ctid, engagement,
                        lifecycle_override=lead_lifecycle_override)
                else:
                    await _sync_lead_from_company(session, http, club.grassroots_guid, company)
                if create_opportunity and (engagement.get("engagementScore") or 0) >= OPPORTUNITY_AUTO_THRESHOLD:
                    from app.services import twenty_opportunity
                    modules = (opportunity_modules if opportunity_modules is not None
                               else twenty_opportunity._default_modules(club))
                    await twenty_opportunity._upsert_opportunity(
                        session, http, club, ctid, modules, stage=opportunity_stage)
                for ct in contacts:
                    try:
                        person_vals = {**_person_values(ct, club.country),
                                       "clubLifecycleStage": club_stage}
                        email = (person_vals.get("emails") or {}).get("primaryEmail")
                        dedup = ("emails.primaryEmail", email) if email else None
                        nm = person_vals.get("name") or {}
                        nkey = _name_key(nm.get("firstName"), nm.get("lastName"))
                        known_id, match_by = None, None
                        if email:
                            row = await _link_get(session, "person_email", email)
                            if row:
                                known_id, match_by = row[0], "email"
                        if not known_id and nkey:
                            row = await _link_get(session, "person_name", nkey)
                            if row:
                                known_id, match_by = row[0], "name"
                        if match_by == "name" and "emails" in person_vals:
                            person_vals = {k: v for k, v in person_vals.items() if k != "emails"}
                        pid, _pact = await _upsert(
                            session, http, "person", str(ct.id), "people", "bcContactId",
                            person_vals, dedup=dedup, known_id=known_id,
                            create_extra={**_person_create_extra(ct), "companyId": ctid})
                        if email:
                            await _link_put(session, "person_email", email, pid, "")
                        if nkey:
                            await _link_put(session, "person_name", nkey, pid, "")
                    except Exception:  # noqa: BLE001 - one bad officer must not drop the rest
                        logger.exception("twenty push_club_and_contacts: officer %s failed", ct.id)
                if all_unsub:
                    await _downgrade_lead_and_opportunities(session, http, club.grassroots_guid, ctid)
            await session.commit()
        return {"ok": True, "club": club.name, "company": ctid}
    except Exception as e:  # noqa: BLE001 - never let a CRM error affect the caller
        logger.exception("twenty push_club_and_contacts failed for club %s", marketing_club_id)
        return {"error": str(e)}


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


async def push_onboarding_enquiry(*, club_name: str, contact_name: str = "",
                                  email: str = "", phone: "Optional[str]" = None) -> dict:
    """A direct "onboard my club" / trial-request enquiry — from EITHER the short
    'Get your club on BetterCricket' CTA modal or the full Contact page, both of
    which post to the same ``/public/contact`` endpoint — is the single strongest
    buying signal a prospect can give. Rather than let it filter through as one
    input among several in the gradual engagement formula (and wait on a club
    already being in the CRM at all), this immediately upserts the club into
    Twenty as a Company AND a Lead, forced to a Hot (100) engagement score, the
    moment the enquiry lands — regardless of whether the club was already
    exported. Best-effort and backgrounded by the caller; never raises."""
    if not client.configured:
        return {"skipped": "not configured"}
    if not (club_name or "").strip():
        return {"skipped": "no club name"}
    try:
        async with async_session_maker() as session:
            club, contact = await _resolve_onboarding_club(
                session, club_name=club_name, contact_name=contact_name,
                email=email, phone=phone)
            if club is None:
                return {"skipped": "no club"}
            await session.commit()
            club_id, contact_id = club.id, contact.id
    except Exception as e:  # noqa: BLE001 — never let a CRM error affect the caller
        logger.exception("twenty push_onboarding_enquiry: club resolve failed for %r", club_name)
        return {"error": str(e)}

    return await push_club_and_contacts(
        club_id, contact_ids=[contact_id],
        engagement_override={"engagementScore": 100, "engagementTier": "HOT", "inSalesCycle": True})


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


async def push_self_serve_registration(*, org_id, org_name: str, contact_name: str = "",
                                       email: str = "", phone: "Optional[str]" = None,
                                       modules: "Optional[list]" = None) -> dict:
    """A self-serve trial registration is a real signal — a real person just
    created real login credentials for a real club — but unlike a direct
    "onboard my club" enquiry it is NOT forced to a flat Hot score any more:
    the club has done nothing yet beyond registering, and per direct
    instruction a registration alone should read as a real-but-modest signal
    (70 for the club's own admin, 55 if a Super Admin performed the
    registration — see services/trial_engagement.py), with the score then
    growing from the club's own subsequent trial-depth (historical import,
    merges, module trial usage) on later refreshes rather than starting
    already maxed out. Find-or-create the linked MarketingClub +
    registering-admin Contact (``_resolve_self_serve_club``), then push
    Company + Lead + Contact using the NORMALLY-COMPUTED engagement rollup
    (``force_lead=True`` so the Lead still lands immediately rather than
    waiting for tomorrow's refresh), scoped to the modules the admin actually
    selected a trial for. An Opportunity is only created here if the
    registration score alone already clears ``OPPORTUNITY_AUTO_THRESHOLD``
    (it won't, at 70/55) — otherwise one is created automatically once a
    later refresh sees the club's trial-depth score cross that line (see
    twenty_leads_tasks._seed_and_refresh_leads), which is the "top performers
    automatically become Opportunities" behaviour this replaces the old
    instant-Opportunity-at-signup with. The Lead opens at ``lifecycleStage``
    "Self-Serve Trial" (until the next daily Lead refresh recomputes it, same
    as any other Lead) and any Opportunity this club goes on to earn opens at
    ``stage`` "Self-Serve Trial" too (permanent — Opportunity stage is never
    recomputed by anything, only a human moving the deal in Twenty changes
    it), so both read distinctly from an enquiry- or outbound-originated deal.
    Best-effort and backgrounded by the caller; never raises."""
    if not client.configured:
        return {"skipped": "not configured"}
    try:
        async with async_session_maker() as session:
            club, contact = await _resolve_self_serve_club(
                session, org_id=org_id, org_name=org_name, contact_name=contact_name,
                email=email, phone=phone)
            await session.commit()
            club_id, contact_id = club.id, contact.id
    except Exception as e:  # noqa: BLE001 — never let a CRM error affect the caller
        logger.exception("twenty push_self_serve_registration: club resolve failed for org %s", org_id)
        return {"error": str(e)}

    return await push_club_and_contacts(
        club_id, contact_ids=[contact_id], force_lead=True,
        create_opportunity=True, opportunity_modules=_twenty_modules(modules or []),
        lead_lifecycle_override="SELF_SERVE_TRIAL", opportunity_stage="SELF_SERVE_TRIAL")


async def push_org_company(org_id, engagement_override: "Optional[dict]" = None) -> dict:
    """Push ONE onboarded club's Company fields (paid/trial modules, ARR, subscription
    status, renewal) to Twenty after a subscription change. Best-effort and
    no-op when Twenty isn't configured or the club has no linked CRM record.

    ``engagement_override`` is used for a trial start/grant — a strong enough
    buying signal that it should read as an immediate Hot (100) score and a
    real Lead, the same treatment ``push_onboarding_enquiry`` gives a direct
    "onboard my club" enquiry, rather than the ordinary billing-fields-only push
    every other subscription change (activate/cancel/renewal-date edit) gets
    here. Only when given does this also compute the engagement rollup and
    create-or-refresh the Lead — an ordinary call is unaffected, both to avoid
    the extra Twenty calls on a routine save and because e.g. a cancel
    shouldn't raise/refresh a Lead."""
    if not client.configured:
        return {"skipped": "twenty not configured"}
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False
            mc = (await session.execute(
                select(MarketingClub).where(MarketingClub.existing_org_id == org_id)
            )).scalar_one_or_none()
            if mc is None:
                return {"skipped": "no linked CRM club"}
            org = await session.get(
                Organisation, org_id,
                options=[selectinload(Organisation.module_subscriptions)],
            )
            company = _company_values(mc, org)
            if engagement_override:
                engagement = {**(await _engagement(session, mc, org)), **engagement_override}
                company = {**company, **engagement}
            async with httpx.AsyncClient() as http:
                ctid, _act = await _upsert(session, http, "club", mc.grassroots_guid,
                                           "companies", "bcClubId", company)
                if engagement_override:
                    from app.services import twenty_leads_tasks
                    await twenty_leads_tasks.upsert_lead_for_club(session, http, mc, org, ctid, engagement)
            await session.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"push_org_company failed for {org_id}: {e}")
        return {"error": str(e)}


async def export_to_twenty(*, filters: Optional[dict] = None,
                           contact_scope: str = "all", selected_only: bool = True,
                           limit: Optional[int] = None) -> dict:
    """Push the filtered directory subset into Twenty. ``contact_scope`` is
    all | named | pst and ``selected_only`` (default) honours the per-officer
    outreach tick the operator set in the directory, so de-selected officers are
    skipped — same control as the BetterComms export. Never raises: a top-level
    failure is logged with a traceback and returned as an ``error`` field so the
    endpoint reports cleanly instead of 500-ing.

    Runs in its own session with ``expire_on_commit=False`` and snapshots all ORM
    data into plain values BEFORE the Twenty IO loop, so the per-club commit /
    rollback can never trigger a lazy reload of an expired ORM object mid-loop
    (the greenlet_spawn async-IO trap)."""
    if not client.configured:
        return {"error": "Twenty is not configured. Set TWENTY_API_URL and "
                          "TWENTY_API_KEY in the server .env."}
    filters = filters or {}
    stats: dict = defaultdict(int)
    errors = 0
    matched = 0
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False

            q = select(MarketingClub).where(
                MarketingClub.detail_fetched_at.isnot(None),
                MarketingClub.excluded.is_(False),
                MarketingClub.kind == "club")  # match the directory list (clubs, not associations)
            for cond in club_filters(**filters):
                q = q.where(cond)
            q = q.order_by(MarketingClub.name)
            if limit:
                q = q.limit(limit)
            clubs = (await session.execute(q)).scalars().all()
            matched = len(clubs)

            # Snapshot everything we need to plain Python — no ORM attribute is
            # touched after this point, so commits/rollbacks below are safe.
            snapshots = []
            for club in clubs:
                org = (await session.get(
                            Organisation, club.existing_org_id,
                            options=[selectinload(Organisation.module_subscriptions)])
                       if club.existing_org_id else None)
                cq = select(MarketingClubContact).where(
                    MarketingClubContact.marketing_club_id == club.id)
                if selected_only:
                    cq = cq.where(MarketingClubContact.outreach_selected.is_(True))
                contacts = (await session.execute(cq)).scalars().all()
                all_unsub = await _all_contacts_unsubscribed(session, club.id)
                company = {**_company_values(club, org, all_unsub=all_unsub),
                           **(await _engagement(session, club, org))}
                club_stage = company["lifecycleStage"]
                people = [{
                    "bc_id": str(ct.id),
                    # clubLifecycleStage denormalises the club's stage onto the Contact
                    # so it's visible/filterable there (always refreshed).
                    "person": {**_person_values(ct, club.country),
                               "clubLifecycleStage": club_stage},
                    "create_extra": _person_create_extra(ct),
                    "role": _officer_role_values(ct, club.name),
                } for ct in _scoped(contacts, contact_scope)]
                snapshots.append({
                    "guid": club.grassroots_guid,
                    "name": club.name,
                    "company": company,
                    "assocs": _club_assocs(club),
                    "people": people,
                    "all_unsub": all_unsub,
                })

            logger.info("twenty export: %d club snapshot(s); officer counts: %s",
                        len(snapshots),
                        {s["name"]: len(s["people"]) for s in snapshots})
            assoc_cache: dict = {}
            async with httpx.AsyncClient() as http:
                # One-time backfill of the email -> existing-Person map (guarded by a
                # marker, so this is a no-op on every export after the first). The map
                # is then maintained incrementally per person upsert, so a shared
                # officer is always adoptable without trusting Twenty's email filter.
                await _prewarm_person_emails(session, http)
                for snap in snapshots:
                    try:
                        ctid, cact = await _upsert(session, http, "club", snap["guid"],
                                                   "companies", "bcClubId", snap["company"])
                        stats["clubs_" + cact] += 1
                        await _sync_lead_from_company(session, http, snap["guid"], snap["company"])
                        logger.info("twenty export: club %r -> company %s id=%s (%d officers)",
                                    snap["name"], cact, ctid, len(snap["people"]))
                        # Association membership is now a read-only array on the Company
                        # (set in _company_values), so there's no clubAssociation junction
                        # to sync here any more.
                        for off in snap["people"]:
                            bc_id = off["bc_id"]
                            try:
                                email = (off["person"].get("emails") or {}).get("primaryEmail")
                                dedup = ("emails.primaryEmail", email) if email else None
                                nm = off["person"].get("name") or {}
                                nkey = _name_key(nm.get("firstName"), nm.get("lastName"))
                                # Resolve a shared officer from OUR link table (Twenty's
                                # filter is unreliable), so the second club adopts the
                                # first club's Contact instead of hitting the duplicate
                                # wall. Match by email first, then by name — Twenty
                                # dedupes a Person on EITHER, and a shared officer's
                                # junior-club record often has a different/blank email.
                                known_id, match_by = None, None
                                if email:
                                    row = await _link_get(session, "person_email", email)
                                    if row:
                                        known_id, match_by = row[0], "email"
                                if not known_id and nkey:
                                    row = await _link_get(session, "person_name", nkey)
                                    if row:
                                        known_id, match_by = row[0], "name"
                                # When adopting by NAME, don't overwrite the existing
                                # Contact's canonical email with this club's (possibly
                                # different/blank) one — drop emails from the patch.
                                person_vals = off["person"]
                                if match_by == "name" and "emails" in person_vals:
                                    person_vals = {k: v for k, v in person_vals.items()
                                                   if k != "emails"}
                                # The Person is identity-only; its native company + first
                                # role are set once via create_extra so a shared officer is
                                # never stolen onto a later club.
                                pid, pact = await _upsert(session, http, "person", bc_id, "people",
                                                          "bcContactId", person_vals, dedup=dedup,
                                                          known_id=known_id,
                                                          create_extra={**off["create_extra"],
                                                                        "companyId": ctid})
                                stats["people_" + pact] += 1
                                # Remember email/name -> Person so later clubs (this run or
                                # a future one) adopt without Twenty's filter.
                                if email:
                                    await _link_put(session, "person_email", email, pid, "")
                                if nkey:
                                    await _link_put(session, "person_name", nkey, pid, "")
                                # Per-club officer detail now lives as read-only arrays on
                                # the Contact (replaces the personClub junction):
                                #   clubRoles = "<role> — <club>" for every club served,
                                #   multiClub / clubCount = a shared-officer flag.
                                # Merged across clubs via our link table (a Twenty ARRAY
                                # write replaces the whole array, so we accumulate locally)
                                # and only PATCHed when the set grows, so steady-state
                                # re-exports cost nothing.
                                role_title = off["role"].get("roleTitle")
                                role_str = (f"{role_title} — {snap['name']}"
                                            if role_title else snap["name"])
                                cl_row = await _link_get(session, "person_clubs", pid)
                                clubs = set(json.loads(cl_row[1]) if cl_row and cl_row[1] else [])
                                pr_row = await _link_get(session, "person_roles", pid)
                                roles = set(json.loads(pr_row[1]) if pr_row and pr_row[1] else [])
                                if ctid not in clubs or role_str not in roles:
                                    clubs.add(ctid)
                                    roles.add(role_str)
                                    await _link_put(session, "person_clubs", pid, pid,
                                                    json.dumps(sorted(clubs)))
                                    await _link_put(session, "person_roles", pid, pid,
                                                    json.dumps(sorted(roles)))
                                    await client.update(http, "people", pid,
                                                        {"multiClub": len(clubs) > 1,
                                                         "clubCount": len(clubs),
                                                         "clubRoles": sorted(roles)})
                                logger.info("twenty export:   officer %s -> %s id=%s (%d club(s))",
                                            bc_id, pact, pid, len(clubs))
                            except Exception:  # noqa: BLE001 - one bad officer must not drop the rest
                                stats["people_errored"] += 1
                                logger.exception(
                                    "twenty export: officer %s failed (email=%r name=%r known_id=%r)",
                                    bc_id, locals().get("email"), locals().get("nkey"),
                                    locals().get("known_id"))
                        if snap["all_unsub"]:
                            await _downgrade_lead_and_opportunities(
                                session, http, snap["guid"], ctid)
                        await session.commit()
                        logger.info("twenty export: committed club %r", snap["name"])
                    except Exception:  # noqa: BLE001 - one bad club must not abort the run
                        errors += 1
                        await session.rollback()
                        logger.exception("twenty export failed for club %s", snap["name"])
                    await asyncio.sleep(0.05)  # stay polite under the 100 req/min cap
    except Exception as e:  # noqa: BLE001 - never bubble a 500 to the UI
        logger.exception("twenty export top-level failure")
        return {"error": f"export failed: {e}", "matched_clubs": matched,
                "errors": errors, **stats}

    return {"matched_clubs": matched, "errors": errors, **stats}


async def refresh_engagement(limit: Optional[int] = None) -> dict:
    """Recompute the engagement rollup (score / tier / 30-day sessions / last seen)
    for every club already in the CRM and PATCH it onto its Company. Cheap, read-
    only on the BetterCricket side bar the usage_events scan, so it's safe to run
    on a schedule — the breadcrumbs move daily, the rest of a Company doesn't.

    Only touches clubs we've already exported (a row in ``twenty_links``); it never
    pulls a new club into the CRM. Never raises: failures are counted and logged."""
    if not client.configured:
        return {"error": "Twenty is not configured."}
    stats: dict = defaultdict(int)
    try:
        async with async_session_maker() as session:
            session.sync_session.expire_on_commit = False
            rows = (await session.execute(text(
                "SELECT bc_id, twenty_id FROM twenty_links WHERE entity_type = 'club' "
                "ORDER BY last_synced_at DESC NULLS LAST"
                + (" LIMIT :lim" if limit else "")),
                {"lim": limit} if limit else {})).all()
            # Map exported club guids back to their MarketingClub rows.
            guids = [r[0] for r in rows]
            tid_by_guid = {r[0]: r[1] for r in rows}
            # Ordered by id so this bulk UPDATE always locks marketing_clubs rows in
            # the same sequence as _seed_and_refresh_leads's equivalent bulk load —
            # two unordered loads over an overlapping row set can lock in opposite
            # order when run concurrently (the two Refresh buttons, or the daily
            # 06:00/07:00 jobs overlapping this), which is a textbook Postgres
            # deadlock. Consistent lock order rules that out.
            clubs = {c.grassroots_guid: c for c in (await session.execute(
                select(MarketingClub).where(
                    MarketingClub.grassroots_guid.in_(guids)
                ).order_by(MarketingClub.id))).scalars().all()
            } if guids else {}
            # Snapshot the engagement fields per company before any IO. Load the
            # linked org (if any) so a customer is scored on health + expansion.
            updates = []
            for guid in guids:
                club = clubs.get(guid)
                if club is None:
                    continue
                org = (await session.get(
                            Organisation, club.existing_org_id,
                            options=[selectinload(Organisation.module_subscriptions)])
                       if club.existing_org_id else None)
                fields = await _engagement(session, club, org)
                # Local BetterCRM equivalent of the OPPORTUNITY_AUTO_THRESHOLD gate
                # below — a club whose score has crossed 70 on this recompute gets
                # its existing platform deal promoted to Engaged. See
                # crm.maybe_promote_by_engagement_score's own docstring.
                from app.services import crm as crm_service
                await crm_service.maybe_promote_by_engagement_score(session, club)
                all_unsub = await _all_contacts_unsubscribed(session, club.id)
                # Recompute the full lifecycle stage every refresh (not just the
                # suppression override) so it — and the Lead mirror below — actually
                # catch any change, not only an all-officers-unsubscribe: a synced
                # club that starts paying, or one that's just been emailed for the
                # first time, moves stage here too.
                paid, _trial, _renewals = _module_split(org) if org is not None else ([], [], [])
                is_paying = bool(paid) or (club.demo_status or "") == "customer"
                fields["lifecycleStage"] = _lifecycle(club, is_paying, all_unsub)
                updates.append((guid, tid_by_guid[guid], fields, all_unsub and not is_paying))

            # This function used to be read/PATCH-only (nothing local to persist), so
            # it never committed. _engagement() above now caches onto each club row —
            # commit here so that cache isn't silently discarded when the session
            # context exits, same as every other _engagement() call site already does.
            await session.commit()

            async with httpx.AsyncClient() as http:
                for guid, tid, fields, suppress in updates:
                    try:
                        await client.update(http, "companies", tid, fields)
                        stats["refreshed"] += 1
                        await _sync_lead_from_company(session, http, guid, fields)
                        if suppress:
                            await _downgrade_lead_and_opportunities(session, http, guid, tid)
                    except Exception:  # noqa: BLE001 - one bad company can't stop the rest
                        stats["errored"] += 1
                        logger.exception("twenty refresh_engagement failed for %s", tid)
                    await asyncio.sleep(0.05)
    except Exception as e:  # noqa: BLE001
        logger.exception("twenty refresh_engagement top-level failure")
        return {"error": f"refresh failed: {e}", **stats}
    return {**stats}
