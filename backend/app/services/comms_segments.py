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

import uuid
from typing import Optional

from sqlalchemy import select, func, exists, or_, text
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, EmailSuppression, Player, PlayerSeasonStats, PlayerAvailability, Season,
    MarketingClub, Organisation, CommsRecipient, EmailEvent, ClubOnboardingRequest,
)

# Field groups decide which joins a definition needs.
CONTACT_FIELDS = {"tag", "source"}
PLAYER_FIELDS = {"role", "gender", "squad_team"}
STAT_FIELDS = {
    "matches_this_season", "runs_this_season", "wickets_this_season", "catches_this_season",
    "fifties_this_season", "hundreds_this_season", "five_wickets_this_season",
}
# availability correlates on the contact's player_id, so it needs no join.
SPECIAL_FIELDS = {"availability"}

# ─── Directory (BetterCricket outreach) fields ───────────────────────────────
# These describe a prospect club / its officer rather than a player, so they only
# appear in the BetterCricket Clubs Directory comms context. They let a segment
# track who has DONE something (was emailed, opened, clicked, enquired) or where
# the club sits (its state, association, our outreach pipeline status, and whether
# the club is already a customer). All read data we already hold — no new tracking.
DIR_YESNO_FIELDS = {"exported", "emailed", "opened", "clicked", "enquired"}
# Multi-value (the rule value is a list of keys; match = ANY).
DIR_MULTI_FIELDS = {"is_trialing", "requested_trial", "had_demo", "visited_page"}
DIR_CLUB_FIELDS = {"club_state", "association", "directory_status", "customer_status",
                   "is_trialing", "requested_trial", "had_demo", "visited_page"}
DIRECTORY_FIELDS = DIR_YESNO_FIELDS | DIR_CLUB_FIELDS
# Directory fields that need the linked MarketingClub joined in (visited_page
# correlates a usage_events row on marketing_clubs.utm_code; the trial/demo
# fields read marketing_clubs columns).
_DIR_MC_FIELDS = {"club_state", "association", "directory_status", "customer_status",
                  "is_trialing", "requested_trial", "had_demo", "visited_page"}

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
    # A visit resolves to the club via its utm_code (in utm_id or utm_source) OR a
    # manual alias (marketing_utm_aliases) an operator mapped to the club.
    return text(
        "EXISTS (SELECT 1 FROM usage_events ue "
        "LEFT JOIN marketing_utm_aliases ua_i ON ua_i.utm_value = ue.utm_id "
        "                                    AND ua_i.marketing_club_id IS NOT NULL "
        "LEFT JOIN marketing_utm_aliases ua_s ON ua_s.utm_value = ue.utm_source "
        "                                    AND ua_s.marketing_club_id IS NOT NULL "
        "WHERE ue.event_type = 'page_view' AND ("
        "ue.utm_id = marketing_clubs.utm_code OR ue.utm_source = marketing_clubs.utm_code "
        "OR ua_i.marketing_club_id = marketing_clubs.id "
        "OR ua_s.marketing_club_id = marketing_clubs.id)" + extra + ")")

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


def _directory_condition(rule: dict, cust):
    """A WHERE clause for one directory (outreach) field. ``cust`` is the aliased
    customer Organisation (joined via the marketing club's existing_org_id), only
    set when a customer_status rule is present."""
    field = (rule or {}).get("field")
    val = (rule or {}).get("value")

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
    return None


def _condition(rule: dict, stats, club_id):
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


async def _current_year(session: AsyncSession, org_id) -> Optional[int]:
    return await session.scalar(
        select(func.max(Season.year)).where(
            Season.organisation_id == org_id, Season.year.isnot(None)))


async def build_query(session: AsyncSession, club, definition: dict):
    """A SELECT of the matching, sendable CommsContact rows for this club."""
    rules = [r for r in ((definition or {}).get("rules") or []) if r and r.get("field") in ALL_FIELDS]
    q = select(CommsContact).where(*sendable_where(club.id))

    if any(r["field"] in (PLAYER_FIELDS | STAT_FIELDS) for r in rules):
        q = q.join(Player, Player.id == CommsContact.player_id)

    # Directory (outreach) joins: the linked prospect club, and — for customer
    # status — the org it converted into.
    cust = None
    if any(r["field"] in _DIR_MC_FIELDS for r in rules):
        q = q.join(MarketingClub, MarketingClub.id == CommsContact.marketing_club_id)
    if any(r["field"] == "customer_status" for r in rules):
        cust = aliased(Organisation)
        q = q.outerjoin(cust, cust.id == MarketingClub.existing_org_id)

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
            cond = _directory_condition(rule, cust)
        else:
            cond = _condition(rule, stats, club.id)
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
