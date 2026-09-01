"""BetterComms dynamic segments — evaluate a saved query into a contact set.

A segment ``definition`` is ``{"match": "all", "rules": [{field, op, value}, ...]}``.
Rules are ANDed (``match: all``). Every rule maps to a safe, whitelisted column —
there is no raw SQL from the client. Fields span three layers:

  * contact   — tag, source (on comms_contacts)
  * player    — role, gender, squad_team (on the linked players row)
  * stat      — matches / runs / wickets / catches THIS SEASON (summed from
                player_season_stats for the club's latest season)

A player/stat rule implies the contact must be a linked player with stats, so it
naturally narrows to the squad. The send gate (sendable_where) is always applied,
so a segment can never reach an unsubscribed / bounced / suppressed address.
See docs/bettercomms-architecture.md.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select, func, exists, and_, or_, text, cast, String, Integer, column, false
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, EmailSuppression, Player, PlayerSeasonStats, PlayerAvailability, Season,
    MarketingClub, Organisation, CommsRecipient, EmailEvent, ClubOnboardingRequest,
    ClubMembership, CrmDeal, CrmPipeline, CrmStage,
)
from app.services.club_directory import _RESOLVED_VISITS
from app.services import club_trial_window
from app.services.marketing_org import org_is_outreach

logger = logging.getLogger(__name__)

# Field groups decide which joins a definition needs.
CONTACT_FIELDS = {"tag", "source"}
PLAYER_FIELDS = {"role", "gender", "squad_team"}
STAT_FIELDS = {
    "matches_this_season", "runs_this_season", "wickets_this_season", "catches_this_season",
    "fifties_this_season", "hundreds_this_season", "five_wickets_this_season",
}
# availability correlates on the contact's player_id, so it needs no join.
# `owes_money` also keys on player_id, but its value can't be expressed in SQL:
# a balance is derived from the rate card, days played and payments, never
# stored. build_query resolves the owing set in Python first (one call to the
# same fees calculation the Accounts screen uses) and the rule becomes a plain
# `player_id IN (...)`, so an audience can never disagree with the balance a
# treasurer is looking at.
SPECIAL_FIELDS = {"availability", "owes_money"}

# ─── Directory (BetterCricket outreach) fields ───────────────────────────────
# These describe a prospect club / its officer rather than a player, so they only
# appear in the BetterCricket Clubs Directory comms context. They let a segment
# track who has DONE something (was emailed, opened, clicked, enquired) or where
# the club sits (its state, association, our outreach pipeline status, and whether
# the club is already a customer). All read data we already hold — no new tracking.
DIR_YESNO_FIELDS = {"exported", "emailed", "opened", "clicked", "enquired"}
# Where the club sits on BetterCricket's OWN sales pipeline. Won / not won is a
# clean partition of every directory club, so one single-select answers both
# directions: pick Won to reach the clubs that bought, pick the other to reach
# everyone else.
DIR_DEAL_FIELDS = {"deal_won"}
# Multi-value (the rule value is a list of keys; match = ANY).
DIR_MULTI_FIELDS = {"is_trialing", "requested_trial", "had_demo", "visited_page",
                    "primary_admin"}
DIR_CLUB_FIELDS = {"club_state", "association", "country", "directory_status", "customer_status",
                   "is_trialing", "requested_trial", "had_demo", "visited_page",
                   "primary_admin"} | DIR_DEAL_FIELDS
# Where the club's own trial actually stands, read off its subscription rows via
# services/club_trial_window.py — the SAME definition the {{trial_days_left}} /
# {{trial_days_since_expiry}} merge variables resolve from, so the number an
# email prints is the number the audience was picked on. `trial_status` answers
# in-a-trial / expired outright; the two numeric fields narrow it ("ends within
# 7 days", "expired in the last month"). A club with no tracked trial has no
# number, so it can never be swept into either by a bound alone.
DIR_TRIAL_FIELDS = {"trial_status", "trial_days_left", "trial_days_since_expiry"}
# Numeric club-level metrics: page views / distinct visitors (from the same
# UTM-resolved usage_events attribution the Club Directory + engagement score
# use) and the cached Twenty engagement score. gte/lte only (no strict < / >
# — mirrors the Club Directory's own engagement-score filter).
DIR_METRIC_FIELDS = {"page_views", "distinct_visitors", "engagement_score"}
DIRECTORY_FIELDS = DIR_YESNO_FIELDS | DIR_CLUB_FIELDS | DIR_METRIC_FIELDS | DIR_TRIAL_FIELDS
# Directory fields that need the linked MarketingClub joined in (visited_page
# correlates a usage_events row on marketing_clubs.utm_code; the trial/demo
# fields read marketing_clubs columns; the metric fields read/join off it too).
_DIR_MC_FIELDS = {"club_state", "association", "country", "directory_status", "customer_status",
                  "is_trialing", "requested_trial", "had_demo", "visited_page",
                  "primary_admin"} | DIR_METRIC_FIELDS | DIR_TRIAL_FIELDS | DIR_DEAL_FIELDS
# The two visit-count fields need the extra usage_events aggregate join;
# engagement_score reads straight off marketing_clubs.engagement_score.
_DIR_VISIT_FIELDS = {"page_views", "distinct_visitors"}

# Tracked public pages a prospect can be matched on (key → path filter). A
# BetterCricket outreach email tags its links with the club's utm_code (as
# ?utm_id=… or ?utm_source=…), captured into usage_events.utm_id / utm_source,
# so a visit maps back to the club.
_VISIT_PATH_SQL = {
    "stats": "split_part(ue.path, '?', 1) ~* '^/modules/betterstats(/|$)'",
    "select": "split_part(ue.path, '?', 1) ~* '^/modules/betterselect(/|$)'",
    "socials": "split_part(ue.path, '?', 1) ~* '^/modules/bettersocials(/|$)'",
    "admin": "split_part(ue.path, '?', 1) ~* '^/modules/betteradmin(/|$)'",
    "betteriq": "split_part(ue.path, '?', 1) ~* '^/modules/betteriq(/|$)'",
    "fantasy": "split_part(ue.path, '?', 1) ~* '^/modules/betterfantasy(/|$)'",
    "pricing": "split_part(ue.path, '?', 1) ~* '^/pricing(/|$)'",
    "compare": "split_part(ue.path, '?', 1) ~* '^/compare(/|$)'",
    "about": "split_part(ue.path, '?', 1) ~* '^/about(/|$)'",
    "faq": "split_part(ue.path, '?', 1) ~* '^/faq(/|$)'",
    "contact": "split_part(ue.path, '?', 1) ~* '^/contact(/|$)'",
}
_DEMO_STATUSES = ("in_trial", "trial_expired", "customer")

# Where a club stands on having somebody at the club actually running it. The
# three states PARTITION every directory row, which is what lets one rule both
# include and exclude: picking `unassigned` targets the test clubs, picking the
# other two leaves them out.
#
#   assigned       — somebody at the club is its Primary Club Admin
#   unassigned     — the club is on the platform, but nobody ever was. A super
#                    admin created or synced it and no real contact took it
#                    over: in practice, a test club.
#   not_onboarded  — there is no club record at all, so there is nobody to be
#                    its admin. An ordinary prospect, NOT a test club — which is
#                    the whole reason this is three states and not a yes/no.
#                    Lumping these in with `unassigned` would make "exclude the
#                    clubs with no primary admin" quietly drop every prospect in
#                    the directory, i.e. almost the entire audience.
_PRIMARY_ADMIN_STATES = ("assigned", "unassigned", "not_onboarded")


def _has_primary_admin_clause():
    """Correlated EXISTS: this directory club's org has a Primary Club Admin.
    The same two conditions ``trial_engagement.org_has_primary_admin`` uses —
    the primary flag is only ever set on a club_admin, and the suite asserts the
    two agree row for row rather than taking that on trust."""
    return exists().where(
        ClubMembership.club_id == MarketingClub.existing_org_id,
        ClubMembership.role == "club_admin",
        ClubMembership.is_primary_admin.is_(True),
    )


def _won_deal_clause():
    """Correlated EXISTS: this directory club has a deal sitting in a WON stage
    on BetterCricket's own sales pipeline.

    WON-NESS COMES FROM THE STAGE, not ``crm_deals.status`` — the same rule
    ``sales_commissions.deal_state`` follows, and for the same reason: the two
    normally agree because every writer derives status from the stage, but the
    live data has rows where they disagree, and the stage is what a reader sees
    on the board.

    Scoped through the STAGE'S OWN PIPELINE rather than ``crm_deals.scope``, so
    a club's own CRM deal (a sponsorship renewal, a grant) can never read as
    BetterCricket having sold them something. Archived deals are excluded, which
    is what every other CRM read does (the commission report included): the
    question is where the club sits on the pipeline, and an archived deal is off
    it.
    """
    return (
        select(CrmDeal.id)
        .join(CrmStage, CrmStage.id == CrmDeal.stage_id)
        .join(CrmPipeline, CrmPipeline.id == CrmStage.pipeline_id)
        .where(
            CrmDeal.marketing_club_id == MarketingClub.id,
            CrmDeal.archived_at.is_(None),
            CrmPipeline.scope == "platform",
            CrmStage.is_won.is_(True),
        )
        .exists()
    )


def _primary_admin_clause(val):
    states = [v for v in _vocab_list(val) if v in _PRIMARY_ADMIN_STATES]
    if not states:
        return None
    onboarded = MarketingClub.existing_org_id.isnot(None)
    has_admin = _has_primary_admin_clause()
    parts = []
    if "assigned" in states:
        parts.append(and_(onboarded, has_admin))
    if "unassigned" in states:
        parts.append(and_(onboarded, ~has_admin))
    if "not_onboarded" in states:
        parts.append(MarketingClub.existing_org_id.is_(None))
    return or_(*parts) if len(parts) > 1 else parts[0]


def _vocab(val) -> str:
    """One value from a fixed vocabulary, matched case-insensitively.

    The picker only ever writes the lowercase key, but a rule can also arrive
    from a saved segment or a hand-made request, and "WON" meaning something
    different from "won" is a trap: an unrecognised value drops the CONDITION,
    which WIDENS the segment to everyone rather than narrowing it. Failing open
    on a typo is the worst direction for an email audience.
    """
    return str(val or "").strip().lower()


def _vocab_list(val) -> list:
    """:func:`_vocab` over a multi-select's list of values."""
    return [v.strip().lower() for v in _as_list(val)]


def _as_list(val):
    """A rule value that may be a list, a single scalar, or a comma string."""
    if isinstance(val, (list, tuple)):
        return [str(v).strip() for v in val if str(v).strip()]
    s = str(val or "").strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _visited_clause(val):
    """Correlated EXISTS over usage_events for a visit attributable to this
    contact's club, matching ANY of the selected pages. The club's UTM code lands
    in usage_events.utm_id OR usage_events.utm_source depending on how the campaign
    tagged the link (utm_source={{utm_code}} is how outreach is sent in practice),
    so a visit matches on either. Safe SQL: page filters come from a fixed map and
    the club code is a column, never interpolated."""
    pages = _as_list(val)
    extra = ""
    if pages and "any" not in pages:
        frags = [_VISIT_PATH_SQL[p] for p in pages if p in _VISIT_PATH_SQL]
        if not frags:
            return None
        extra = " AND (" + " OR ".join(frags) + ")"
    # A visit resolves to the club via its utm_code (in utm_id or utm_source), a
    # manual alias (marketing_utm_aliases) an operator mapped to the club, OR by
    # landing on the club's own page (first path segment == utm_code).
    path_code = "split_part(split_part(ue.path, '?', 1), '/', 2)"
    return text(
        "EXISTS (SELECT 1 FROM usage_events ue "
        "LEFT JOIN marketing_utm_aliases ua_i ON ua_i.utm_value = ue.utm_id "
        "                                    AND ua_i.marketing_club_id IS NOT NULL "
        "LEFT JOIN marketing_utm_aliases ua_s ON ua_s.utm_value = ue.utm_source "
        "                                    AND ua_s.marketing_club_id IS NOT NULL "
        f"LEFT JOIN marketing_utm_aliases ua_p ON ua_p.utm_value = {path_code} "
        "                                    AND ua_p.marketing_club_id IS NOT NULL "
        "WHERE ue.event_type = 'page_view' "
        # A stale UTM captured once in a browser tab keeps riding along on every
        # later page view from that tab, including a staff member's own
        # authenticated admin browsing — exclude that from "this prospect
        # visited our marketing pages" the same way the Club Directory /
        # engagement score now do.
        "AND ue.user_id IS NULL AND split_part(ue.path, '?', 1) !~* '^/admin' AND ("
        "ue.utm_id = marketing_clubs.utm_code OR ue.utm_source = marketing_clubs.utm_code "
        "OR ua_i.marketing_club_id = marketing_clubs.id "
        "OR ua_s.marketing_club_id = marketing_clubs.id "
        "OR ua_p.marketing_club_id = marketing_clubs.id "
        f"OR ({path_code} <> '' AND {path_code} = marketing_clubs.utm_code) "
        f"OR ({path_code} <> '' AND EXISTS (SELECT 1 FROM organisations o "
        f"     WHERE o.id = marketing_clubs.existing_org_id AND o.slug = {path_code})))"
        + extra + ")")

ALL_FIELDS = CONTACT_FIELDS | PLAYER_FIELDS | STAT_FIELDS | SPECIAL_FIELDS | DIRECTORY_FIELDS

_STAT_COLUMN = {
    "matches_this_season": "matches",
    "runs_this_season": "runs",
    "wickets_this_season": "wickets",
    "catches_this_season": "catches",
    "fifties_this_season": "fifties",
    "hundreds_this_season": "hundreds",
    "five_wickets_this_season": "five_wickets",
}


def sendable_where(club_id):
    """The always-on send gate shared with routers/comms.py: subscribed, not
    bounced / complained / excluded per club, and not on the global suppression
    list."""
    return [
        CommsContact.organisation_id == club_id,
        CommsContact.subscribed.is_(True),
        CommsContact.bounced.is_(False),
        CommsContact.complained.is_(False),
        CommsContact.excluded.is_(False),
        ~exists().where(func.lower(EmailSuppression.email) == func.lower(CommsContact.email)),
    ]


def _num(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avail_exists(club_id, *, available_only: bool):
    """A correlated EXISTS over future availability rows for the contact's player.
    available_only ⇒ status AVAILABLE; otherwise any future response row."""
    conds = [
        PlayerAvailability.player_id == CommsContact.player_id,
        PlayerAvailability.organisation_id == club_id,
        PlayerAvailability.avail_date >= func.current_date(),
    ]
    if available_only:
        conds.append(PlayerAvailability.status == "AVAILABLE")
    return exists().where(*conds)


def _yes(val) -> bool:
    return str(val).strip().lower() in ("yes", "true", "1", "y")


def _event_exists(event_type: str):
    """Correlated EXISTS: this contact has an email event of the given type
    (matched by contact_id or, as a fallback, by address)."""
    return exists().where(or_(
        EmailEvent.contact_id == CommsContact.id,
        func.lower(EmailEvent.email) == func.lower(CommsContact.email),
    )).where(EmailEvent.event_type == event_type)


_LAPSED_STATUSES = ("cancelled", "paused", "past_due")

# Per-club page-view / distinct-visitor counts, aggregated once and joined in —
# the same UTM/alias/path resolution as club_directory.club_visit_stats, just
# expressed as a joinable subquery instead of a standalone query.
_VISIT_STATS_SQL = (
    "SELECT v.cid AS cid, COUNT(*) AS views, COUNT(DISTINCT v.vk) AS visitors "
    f"FROM ({_RESOLVED_VISITS}) v WHERE v.cid IS NOT NULL GROUP BY v.cid"
)


def _visit_stats_subquery():
    return text(_VISIT_STATS_SQL).columns(
        column("cid", String), column("views", Integer), column("visitors", Integer)
    ).subquery()


def _trial_condition(rule: dict, trials):
    """A WHERE clause for one club-trial field, off the joined trial window.

    ``trials`` is the outer-joined per-org window (see
    club_trial_window.trial_window_subquery), so a contact whose club has no
    tracked trial reads NULL in every column here.

    The day count is FLOORed exactly as ``club_trial_window.days_left`` floors
    it in Python, so "at most 7 days left" matches precisely the clubs whose
    email will print ``{{trial_days_left}}`` as 7 or fewer.

    An OPEN-ENDED trial (a trial row with no end date) is excluded from both
    numeric answers and never reads as expired — it has no countdown, and
    telling a club whose trial is still running that it has finished is the one
    thing this must not do.
    """
    field = (rule or {}).get("field")
    val = (rule or {}).get("value")
    if trials is None:
        return None

    ends = trials.c.ends_at
    open_ended = func.coalesce(trials.c.open_ended, false())
    # Non-NULL for every club the subquery emitted. ``ends_at`` cannot stand in
    # for this: it is NULL both for a club with no trial and for one whose only
    # trial has no end date, and those are opposite answers.
    has_trial = trials.c.has_trial.isnot(None)
    days = club_trial_window.days_left_sql(ends)
    # A live, dated trial: an end date that has not passed, with no open-ended
    # row alongside it to muddy the countdown.
    live = and_(has_trial, ends.isnot(None), ~open_ended, days >= 0)
    # Expired: every trial row the club holds has run out.
    gone = and_(has_trial, ends.isnot(None), ~open_ended, days < 0)

    if field == "trial_status":
        v = _vocab(val)
        if v == "in_trial":
            # Open-ended counts as in a trial; it just has no countdown.
            return and_(has_trial, or_(open_ended, days >= 0))
        if v == "expired":
            return gone
        if v == "none":
            # No trial row at all (never onboarded, or converted / removed).
            return ~has_trial
        return None

    n = _num(val)
    if n is None:
        return None
    if field == "trial_days_left":
        # "at most N" is the scenario this exists for: the trial finishes within
        # N days. "at least N" is the mirror, for holding fire on a club that has
        # only just started.
        cmp = days <= n if (rule or {}).get("op") == "lte" else days >= n
        return and_(live, cmp)
    if field == "trial_days_since_expiry":
        # Its own FLOOR, never the negation of days-left — see
        # club_trial_window.days_since for why that is off by one.
        since = club_trial_window.days_since_sql(ends)
        cmp = since <= n if (rule or {}).get("op") == "lte" else since >= n
        return and_(gone, cmp)
    return None


def _directory_condition(rule: dict, cust, visits=None, trials=None):
    """A WHERE clause for one directory (outreach) field. ``cust`` is the aliased
    customer Organisation (joined via the marketing club's existing_org_id), only
    set when a customer_status rule is present. ``visits`` is the joined
    per-club page-view/visitor subquery, only set when a page_views /
    distinct_visitors rule is present. ``trials`` is the joined per-org trial
    window, only set when a trial_* rule is present."""
    field = (rule or {}).get("field")
    val = (rule or {}).get("value")
    if field in DIR_TRIAL_FIELDS:
        return _trial_condition(rule, trials)

    if field == "exported":
        return CommsContact.marketing_club_id.isnot(None) if _yes(val) else CommsContact.marketing_club_id.is_(None)
    if field == "emailed":
        ex = exists().where(or_(
            CommsRecipient.contact_id == CommsContact.id,
            func.lower(CommsRecipient.email) == func.lower(CommsContact.email),
        )).where(CommsRecipient.status == "sent")
        return ex if _yes(val) else ~ex
    if field == "opened":
        ex = _event_exists("open")
        return ex if _yes(val) else ~ex
    if field == "clicked":
        ex = _event_exists("click")
        return ex if _yes(val) else ~ex
    if field == "enquired":
        ex = exists().where(func.lower(ClubOnboardingRequest.email) == func.lower(CommsContact.email))
        return ex if _yes(val) else ~ex

    if field == "club_state":
        return MarketingClub.state == str(val) if val else None
    if field == "association":
        return MarketingClub.association_name == str(val) if val else None
    if field == "country":
        return MarketingClub.country == str(val) if val else None
    if field == "directory_status":
        return MarketingClub.status == str(val) if val else None
    if field == "visited_page":
        return _visited_clause(val)
    if field == "is_trialing":
        keys = _as_list(val)
        return or_(*[MarketingClub.trial_modules.contains([k]) for k in keys]) if keys else None
    if field == "requested_trial":
        keys = _as_list(val)
        return or_(*[MarketingClub.requested_trial_modules.contains([k]) for k in keys]) if keys else None
    if field == "deal_won":
        v = _vocab(val)
        if v == "won":
            return _won_deal_clause()
        if v == "not_won":
            # Everything else: an open deal, a lost one, or no deal at all. The
            # two states partition every directory club, so this one select
            # answers both "who bought" and "who hasn't".
            return ~_won_deal_clause()
        return None
    if field == "primary_admin":
        return _primary_admin_clause(val)
    if field == "had_demo":
        states = [s for s in _as_list(val) if s in _DEMO_STATUSES]
        return MarketingClub.demo_status.in_(states) if states else None
    if field == "customer_status":
        if val == "none":
            return MarketingClub.existing_org_id.is_(None)
        if cust is None:
            return None
        if val == "trial":
            return cust.subscription_status == "trial"
        if val == "active":
            return cust.subscription_status == "active"
        if val == "lapsed":
            return cust.subscription_status.in_(_LAPSED_STATUSES)
        return None

    if field == "engagement_score":
        n = _num(val)
        if n is None:
            return None
        if (rule or {}).get("op") == "lte":
            return MarketingClub.engagement_score <= n
        return MarketingClub.engagement_score >= n  # default / "gte"
    if field in _DIR_VISIT_FIELDS and visits is not None:
        n = _num(val)
        if n is None:
            return None
        col = func.coalesce(visits.c.views if field == "page_views" else visits.c.visitors, 0)
        if (rule or {}).get("op") == "lte":
            return col <= n
        return col >= n  # default / "gte"
    return None


def _condition(rule: dict, stats, club_id, owing_ids=None):
    field = (rule or {}).get("field")
    op = (rule or {}).get("op")
    val = (rule or {}).get("value")
    if field == "tag":
        return CommsContact.tags.contains([str(val)]) if val else None
    if field == "source":
        return CommsContact.source == str(val)
    if field == "role":
        return Player.player_role == str(val)
    if field == "gender":
        return Player.gender == str(val)
    if field == "squad_team":
        try:
            return Player.squad_team_id == uuid.UUID(str(val))
        except (ValueError, TypeError):
            return None
    if field == "owes_money":
        # owing_ids is None when the club has no season to price against, which
        # is not the same as "nobody owes" — drop the rule rather than assert an
        # empty audience.
        if owing_ids is None:
            return None
        wants_owing = _yes(val)
        clause = CommsContact.player_id.in_(owing_ids) if owing_ids else false()
        return clause if wants_owing else ~clause
    if field == "availability":
        if val == "available":
            return _avail_exists(club_id, available_only=True)
        if val == "not_set":
            return ~_avail_exists(club_id, available_only=False)
        return None
    if field in STAT_FIELDS and stats is not None:
        col = stats.c[_STAT_COLUMN[field]]
        n = _num(val)
        if n is None:
            return None
        if op == "lte":
            return col <= n
        if op == "eq":
            return col == n
        return col >= n  # default / "gte"
    return None


async def _owing_player_ids(session: AsyncSession, org_id):
    """Players whose member record still owes money in the club's newest
    season. Returns None when there is no season to price against, so the rule
    can be dropped rather than resolving to nobody."""
    from app.services import fees as fees_svc

    season_id = (await session.execute(
        select(Season.id).where(Season.organisation_id == org_id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc()).limit(1)
    )).scalar_one_or_none()
    if not season_id:
        return None
    return await fees_svc.owing_player_ids(session, org_id, season_id)


async def _current_year(session: AsyncSession, org_id) -> Optional[int]:
    return await session.scalar(
        select(func.max(Season.year)).where(
            Season.organisation_id == org_id, Season.year.isnot(None)))


def directory_rules_allowed(club) -> bool:
    """Only BetterCricket's own outreach org may build on the directory fields.

    They describe a PROSPECT club and its trial / pipeline state — BetterCricket's
    sales data, not a club's own — and in a club's context they answer nothing
    anyway, since every one of its contacts belongs to the single sending club.
    This is the same boundary SegmentsRoute.jsx picks the internal builder on
    (``org_is_outreach``, via /auth/me's ``is_marketing_org``), so the screen and
    the engine cannot disagree about who may ask.
    """
    return org_is_outreach(club)


async def build_query(session: AsyncSession, club, definition: dict):
    """A SELECT of the matching, sendable CommsContact rows for this club."""
    rules = [r for r in ((definition or {}).get("rules") or []) if r and r.get("field") in ALL_FIELDS]
    q = select(CommsContact).where(*sendable_where(club.id))

    # A directory rule reaching a club's own audience can only be a hand-made
    # request — no club-facing screen can build one. FAIL CLOSED rather than
    # dropping the rule: dropping it would WIDEN the audience to everyone, and
    # silently emailing a club's whole list is the worse direction by far. It
    # returns nothing today because the MarketingClub join is empty for a club's
    # own contacts, but that is incidental; this makes it deliberate and
    # independent of how the joins happen to be built.
    foreign = sorted({r["field"] for r in rules if r["field"] in DIRECTORY_FIELDS})
    if foreign and not directory_rules_allowed(club):
        # Logged rather than swallowed: an empty audience nobody can explain is
        # the worst way to find out this fired, and only a hand-made request (or
        # a segment saved before the two field sets were split apart) can reach
        # it at all.
        logger.warning("BetterComms: dropping segment for club %s — directory-only "
                       "rules in a club context: %s", club.id, ", ".join(foreign))
        return q.where(false())

    if any(r["field"] in (PLAYER_FIELDS | STAT_FIELDS) for r in rules):
        q = q.join(Player, Player.id == CommsContact.player_id)

    # Directory (outreach) joins: the linked prospect club, and — for customer
    # status — the org it converted into.
    cust = None
    visits = None
    if any(r["field"] in _DIR_MC_FIELDS for r in rules):
        q = q.join(MarketingClub, MarketingClub.id == CommsContact.marketing_club_id)
    if any(r["field"] == "customer_status" for r in rules):
        cust = aliased(Organisation)
        q = q.outerjoin(cust, cust.id == MarketingClub.existing_org_id)
    if any(r["field"] in _DIR_VISIT_FIELDS for r in rules):
        visits = _visit_stats_subquery()
        q = q.outerjoin(visits, visits.c.cid == cast(MarketingClub.id, String))
    # The club's trial window, keyed on the org the prospect was onboarded into.
    # OUTER joined: a directory club that never became an org still has to reach
    # the WHERE, so "no tracked trial" can be answered rather than silently
    # dropping the contact.
    trials = None
    if any(r["field"] in DIR_TRIAL_FIELDS for r in rules):
        trials = club_trial_window.trial_window_subquery()
        q = q.outerjoin(trials, trials.c.org_id == MarketingClub.existing_org_id)

    # Who owes, resolved once against the club's newest season.
    owing_ids = None
    if any(r["field"] == "owes_money" for r in rules):
        owing_ids = await _owing_player_ids(session, club.id)

    stats = None
    if any(r["field"] in STAT_FIELDS for r in rules):
        year = await _current_year(session, club.id)
        stats = (
            select(
                PlayerSeasonStats.player_id.label("pid"),
                func.coalesce(func.sum(PlayerSeasonStats.matches), 0).label("matches"),
                func.coalesce(func.sum(PlayerSeasonStats.runs), 0).label("runs"),
                func.coalesce(func.sum(PlayerSeasonStats.wickets), 0).label("wickets"),
                func.coalesce(func.sum(PlayerSeasonStats.catches), 0).label("catches"),
                func.coalesce(func.sum(PlayerSeasonStats.fifties), 0).label("fifties"),
                func.coalesce(func.sum(PlayerSeasonStats.hundreds), 0).label("hundreds"),
                func.coalesce(func.sum(PlayerSeasonStats.five_wicket_innings), 0).label("five_wickets"),
            )
            .join(Season, Season.id == PlayerSeasonStats.season_id)
            .where(Season.organisation_id == club.id, Season.year == year)
            .group_by(PlayerSeasonStats.player_id)
            .subquery()
        )
        q = q.join(stats, stats.c.pid == CommsContact.player_id)

    for rule in rules:
        if rule["field"] in DIRECTORY_FIELDS:
            cond = _directory_condition(rule, cust, visits, trials)
        else:
            cond = _condition(rule, stats, club.id, owing_ids)
        if cond is not None:
            q = q.where(cond)
    return q


async def resolve_contacts(session: AsyncSession, club, definition: dict) -> list[CommsContact]:
    q = await build_query(session, club, definition)
    rows = (await session.execute(q.order_by(CommsContact.email))).scalars().all()
    seen, out = set(), []
    for c in rows:
        if c.email in seen:
            continue
        seen.add(c.email)
        out.append(c)
    return out


async def count(session: AsyncSession, club, definition: dict) -> int:
    q = await build_query(session, club, definition)
    # Contacts are unique per (org, email), so a row count is the contact count.
    n = await session.scalar(select(func.count()).select_from(q.subquery()))
    return int(n or 0)
