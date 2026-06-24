"""Marketing club directory — enumerate every Australian cricket club from the
PlayHQ public directory for BetterCricket outreach, and bridge the result into
the existing BetterComms send pipeline.

Data source (see ``playhq_directory_client``)
---------------------------------------------
Two unauthenticated PlayHQ GraphQL endpoints, read the same way playhq.com does:

* **Search** enumerates every cricket club in one paged pass (empty query,
  ``sports:[CRICKET]``, ``types:[CLUB]``), filtered to Australia by
  ``tenant.name == "Cricket Australia"``. Each result carries the club's name,
  ``routingCode``, website, address AND its full committee ``contacts[]`` (name +
  position + email + phone) — so contacts come free at discovery, no per-club
  fetch.
* **Main graph** ``discoverCompetitions(routingCode)`` maps a club to the
  association(s) it plays in (a club commonly plays across several). This is the
  one per-club call, run as a separate, slower enrichment pass.

So the crawl is two phases:

1. **Discovery** (``discover_clubs``) — page the search to completion, upsert
   every AU club with its committee + address. Cheap (~70 calls), idempotent.
2. **Association enrichment** (``enrich_associations``) — for each club whose
   ``associations`` is still NULL (the frontier), call ``discoverCompetitions``
   and store the association list. Resumable through the table itself, so a
   restart/deploy never loses progress.

We store **office-bearers + coordinators** (President / Vice-President /
Secretary / Treasurer + junior/female/cricket coordinators), not the whole
committee — the high-signal outreach contacts, with less personal data held.

Politeness is deliberate (``marketing_crawl_*``): one request at a time, a
jittered delay, a nightly cap, run off-peak. We stay a quiet API citizen.
"""
from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import logging
import random
import re
import uuid
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9
    ZoneInfo = None  # type: ignore

from sqlalchemy import select, func, cast, update, Text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import (
    MarketingClub, MarketingClubContact, Organisation, CommsContact,
)
from app.services import playhq_directory_client as phq

logger = logging.getLogger(__name__)

AU_TENANT = "Cricket Australia"

# PlayHQ committee positions we keep, mapped to a tidy label + a priority rank.
# Office bearers rank to the top; coordinators (junior/female/cricket) follow.
# Everything else (general committee, coaches, scorers, …) is skipped — too much
# personal data for too little outreach signal.
_OFFICE_BEARERS = {
    "PRESIDENT": ("President", 1),
    "VICE_PRESIDENT": ("Vice President", 2),
    "SECRETARY": ("Secretary", 3),
    "TREASURER": ("Treasurer", 4),
}
# CA stores some roles with a typo ("COODINATOR" — the R is dropped); match the
# correct spelling and that typo.
_COORDINATOR_RE = re.compile(r"COOR?DINATOR")
_COORDINATOR_RANK = 10


def _role_for_position(position: Optional[str]) -> Optional[tuple[str, int]]:
    """Return (label, rank) for a kept committee position, or None to skip it."""
    pos = (position or "").strip().upper()
    if not pos:
        return None
    if pos in _OFFICE_BEARERS:
        return _OFFICE_BEARERS[pos]
    if _COORDINATOR_RE.search(pos):
        # JUNIOR_CRICKET_COODINATOR → "Junior Cricket Coordinator"
        label = pos.replace("COODINATOR", "COORDINATOR").replace("_", " ").title()
        return label, _COORDINATOR_RANK
    return None


def _full_name(contact: dict) -> Optional[str]:
    name = " ".join(filter(None, [
        (contact.get("firstName") or "").strip(),
        (contact.get("lastName") or "").strip()])).strip()
    return name or None


# ── club upsert (discovery) ─────────────────────────────────────────────────────

async def _store_contact(session: AsyncSession, club_id, full_name: Optional[str],
                         role: str, role_rank: int, email: Optional[str],
                         phone: Optional[str]) -> None:
    """Upsert one committee contact, deduped on lower(email) per club. A re-crawl
    refreshes name/phone and fills a better role. Contacts with no email are kept
    (phone-only), deduped on (club, full_name) so a re-crawl doesn't pile up."""
    email = (email or "").strip().lower() or None
    phone = (phone or "").strip() or None
    if email:
        existing = await session.scalar(select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id == club_id,
            func.lower(MarketingClubContact.email) == email))
    elif full_name:
        existing = await session.scalar(select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id == club_id,
            MarketingClubContact.email.is_(None),
            func.lower(MarketingClubContact.full_name) == full_name.lower()))
    else:
        return
    if existing:
        existing.mobile = phone or existing.mobile
        existing.full_name = full_name or existing.full_name
        if role_rank < (existing.role_rank or 99):
            existing.role, existing.role_rank = role, role_rank
        existing.updated_at = func.now()
        return
    session.add(MarketingClubContact(
        marketing_club_id=club_id, full_name=full_name, role=role,
        role_rank=role_rank, email=email, mobile=phone, source="api"))


async def _link_existing_org(session: AsyncSession, club: MarketingClub) -> None:
    """Best-effort link to a club we already have as a BetterStats customer so
    outreach can skip it (match on PlayHQ routingCode, then name)."""
    org_id = None
    if club.playhq_id:
        org_id = await session.scalar(
            select(Organisation.id).where(Organisation.playhq_id == club.playhq_id))
    if not org_id and club.grassroots_guid:
        org_id = await session.scalar(select(Organisation.id).where(
            func.lower(cast(Organisation.id, Text)) == club.grassroots_guid.lower()))
    if not org_id and club.name:
        org_id = await session.scalar(select(Organisation.id).where(
            func.lower(Organisation.name) == club.name.lower()))
    club.existing_org_id = org_id


async def _upsert_club(session: AsyncSession, org: dict) -> bool:
    """Insert or refresh one club from a search result. Returns True if newly
    inserted. Leaves ``associations`` untouched (NULL stays the enrichment
    frontier); never clobbers ``status``/``existing_org_id`` on an existing row."""
    guid = org.get("id")
    if not guid:
        return False
    addr = org.get("address") or {}
    club = await session.scalar(
        select(MarketingClub).where(MarketingClub.grassroots_guid == guid))
    is_new = club is None
    if is_new:
        club = MarketingClub(grassroots_guid=guid)
        session.add(club)
    club.playhq_id = org.get("routingCode") or club.playhq_id
    club.name = org.get("name") or club.name or "(unknown)"
    club.kind = "club"
    club.source = "playhq_directory"
    club.website_url = org.get("websiteUrl") or club.website_url
    club.address_line1 = addr.get("line1") or club.address_line1
    club.suburb = addr.get("suburb") or club.suburb
    club.state = addr.get("state") or club.state
    club.postcode = addr.get("postcode") or club.postcode
    club.country = addr.get("country") or club.country
    club.latitude = addr.get("latitude") or club.latitude
    club.longitude = addr.get("longitude") or club.longitude
    club.raw_json = org
    club.detail_fetched_at = func.now()   # core data (contacts/address) is present
    club.last_crawled_at = func.now()
    if club.status in (None, "new"):
        club.status = "enriched"
    await session.flush()  # need club.id for contacts + dedupe within the batch

    # Office-bearers + coordinators only.
    top_email = top_phone = None
    top_rank = 999
    for c in (org.get("contacts") or []):
        if c.get("visible") is False:
            continue
        role = _role_for_position(c.get("position"))
        if not role:
            continue
        label, rank = role
        email = (c.get("email") or "").strip() or None
        phone = (c.get("phone") or "").strip() or None
        await _store_contact(session, club.id, _full_name(c), label, rank, email, phone)
        if rank < top_rank and (email or phone):
            top_rank, top_email, top_phone = rank, email, phone
    # Mirror the top contact onto the club for the list filter + CSV fallback.
    club.contact_email = top_email or club.contact_email
    club.contact_phone = top_phone or club.contact_phone

    await _link_existing_org(session, club)
    return is_new


async def discover_clubs(session: AsyncSession, max_pages: int = 200) -> dict:
    """Page the PlayHQ search to completion, upserting every Australian cricket
    club (with its committee). Idempotent — safe to re-run to pick up new clubs."""
    page, seen, new, skipped = 1, 0, 0, 0
    total_au = 0
    while page <= max_pages:
        results, _ = await phq.search_organisations("CLUB", "", page=page, limit=100)
        if not results:
            break
        for org in results:
            if (org.get("tenant") or {}).get("name") != AU_TENANT:
                skipped += 1
                continue
            total_au += 1
            if await _upsert_club(session, org):
                new += 1
            seen += 1
        await session.commit()
        page += 1
    stats = {"pages": page - 1, "au_seen": seen, "new": new, "non_au_skipped": skipped}
    logger.info("discover_clubs: %s", stats)
    return stats


# ── association enrichment ──────────────────────────────────────────────────────

async def enrich_associations(session: AsyncSession, limit: Optional[int] = None) -> dict:
    """For up to ``limit`` clubs whose associations haven't been fetched, call the
    main graph and store the association(s) they play in. Resumable: a fetch
    failure leaves ``associations`` NULL so the club is retried next batch."""
    limit = limit or settings.marketing_crawl_nightly_limit
    frontier = (await session.execute(
        select(MarketingClub)
        .where(MarketingClub.associations.is_(None), MarketingClub.kind == "club")
        # last_crawled_at ASC (nulls first) so a club whose fetch just failed —
        # which bumps last_crawled_at to now — drops to the back of the queue
        # instead of head-of-line blocking the same failing row every iteration.
        .order_by(MarketingClub.last_crawled_at.asc().nullsfirst(),
                  MarketingClub.first_seen_at.asc())
        .limit(limit)
    )).scalars().all()

    stats = {"enriched": 0, "with_association": 0, "errors": 0, "processed": []}
    for club in frontier:
        assocs = await phq.discover_associations(club.playhq_id)
        club.last_crawled_at = func.now()
        if assocs is None:
            stats["errors"] += 1
            stats["processed"].append({"id": str(club.id), "ok": False})
            await session.commit()
            continue
        club.associations = assocs
        if assocs:
            club.association_name = assocs[0]["name"]
            club.association_guid = assocs[0]["id"]
            stats["with_association"] += 1
        stats["enriched"] += 1
        stats["processed"].append({"id": str(club.id), "ok": True})
        await session.commit()

    remaining = await session.scalar(select(func.count(MarketingClub.id)).where(
        MarketingClub.associations.is_(None), MarketingClub.kind == "club"))
    stats["frontier_remaining"] = remaining or 0
    logger.info("enrich_associations: %s", stats)
    return stats


async def crawl_batch(session: AsyncSession, limit: Optional[int] = None,
                      rediscover: bool = False) -> dict:
    """One crawl batch: discover all clubs on first run (or when ``rediscover``),
    then association-enrich the next ``limit`` of the frontier. Safe to call
    repeatedly — it just walks the next slice."""
    total = await session.scalar(select(func.count(MarketingClub.id))) or 0
    discovery = {}
    if total == 0 or rediscover:
        discovery = await discover_clubs(session)
    enrichment = await enrich_associations(session, limit)
    result = {"discovery": discovery, "enrichment": enrichment}
    logger.info("crawl_batch: %s", result)
    return result


# ── continuous background runner ────────────────────────────────────────────────
# A long-lived task that walks the whole backfill inside a daily active window,
# one club at a time, leaning on the client's per-request 15-40s gap and adding
# occasional 2-3min breaks — so the traffic reads as organic, waking-hours
# browsing rather than a scraper. Resumable (it just consults the table), and it
# self-throttles around the window and PlayHQ hiccups.

def _now_tz() -> dt.datetime:
    tz = ZoneInfo(settings.marketing_crawl_tz) if ZoneInfo else None
    return dt.datetime.now(tz)


def _window_bounds(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    sh, sm = (int(x) for x in settings.marketing_crawl_window_start.split(":"))
    eh, em = (int(x) for x in settings.marketing_crawl_window_end.split(":"))
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start, end


def _in_window(now: dt.datetime) -> bool:
    start, end = _window_bounds(now)
    return start <= now <= end


def _seconds_until_next_start(now: dt.datetime) -> float:
    """Seconds to the next window start strictly in the future (tomorrow's start
    when we're already past today's). Assumes start < end (same-day window)."""
    start, _ = _window_bounds(now)
    nxt = start if now < start else start + dt.timedelta(days=1)
    return max(1.0, (nxt - now).total_seconds())


async def _give_up_club(session: AsyncSession, club_id: str) -> None:
    """Stop retrying a club whose associations can't be fetched (unresolvable
    routingCode, persistent 5xx). Record an empty list so it leaves the frontier
    and the backfill can actually reach 'complete'."""
    try:
        pk = uuid.UUID(club_id)
    except (ValueError, TypeError):
        return
    club = await session.get(MarketingClub, pk)
    if club is not None and club.associations is None:
        club.associations = []
        logger.info("marketing crawl: giving up association fetch for %s (%s)",
                    club.name, club_id)
        await session.commit()


# How many times to retry one club's association fetch before giving up on it.
_MAX_CLUB_RETRIES = 5


async def run_continuous(session_maker, max_consecutive_failures: int = 200) -> None:
    """Walk the full directory backfill within the daily active window. Discovers
    on first run, then enriches one club per loop (the 15-40s gap lives in the
    client), pausing for a longer break every 30-60 clubs and sleeping outside the
    window. When the frontier empties it either exits or, if the refresh daemon is
    on, re-discovers each day to pick up newly-registered clubs."""
    logger.info(
        "marketing crawl (continuous): window %s-%s %s, gap %.0f-%.0fs, break "
        "%.0f-%.0fs every %d-%d clubs",
        settings.marketing_crawl_window_start, settings.marketing_crawl_window_end,
        settings.marketing_crawl_tz, settings.marketing_crawl_min_delay,
        settings.marketing_crawl_max_delay, settings.marketing_crawl_break_min,
        settings.marketing_crawl_break_max, settings.marketing_crawl_break_after_min,
        settings.marketing_crawl_break_after_max)

    # Discover the club universe once (when empty), inside the window.
    async with session_maker() as s:
        total = await s.scalar(select(func.count(MarketingClub.id))) or 0
    if total == 0:
        await _sleep_until_window()
        async with session_maker() as s:
            await discover_clubs(s)

    since_break = 0
    next_break_at = random.randint(settings.marketing_crawl_break_after_min,
                                   settings.marketing_crawl_break_after_max)
    consecutive_failures = 0
    club_fails: dict[str, int] = {}
    while True:
        now = _now_tz()
        if not _in_window(now):
            wait = min(_seconds_until_next_start(now), 1800.0)  # re-check ≥ every 30 min
            await asyncio.sleep(wait)
            continue

        async with session_maker() as s:
            r = await enrich_associations(s, limit=1)
            # Track per-club failures; give up on a club after a few attempts so a
            # permanently-unresolvable routingCode can't stall completion forever.
            for p in r.get("processed", []):
                if p["ok"]:
                    club_fails.pop(p["id"], None)
                else:
                    club_fails[p["id"]] = club_fails.get(p["id"], 0) + 1
                    if club_fails[p["id"]] >= _MAX_CLUB_RETRIES:
                        await _give_up_club(s, p["id"])
                        club_fails.pop(p["id"], None)

        if r["enriched"] > 0:
            consecutive_failures = 0
            since_break += 1
            if since_break >= next_break_at:
                brk = random.uniform(settings.marketing_crawl_break_min,
                                     settings.marketing_crawl_break_max)
                logger.info("marketing crawl: break for %.0fs after %d clubs", brk, since_break)
                await asyncio.sleep(brk)
                since_break = 0
                next_break_at = random.randint(settings.marketing_crawl_break_after_min,
                                               settings.marketing_crawl_break_after_max)
            continue

        if r["frontier_remaining"] > 0:
            # Every remaining club failed to fetch (PlayHQ wobble / unresolved
            # routingCodes). They've dropped to the back of the queue; back off
            # hard after a long streak so we never hot-loop on a bad patch.
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                logger.warning("marketing crawl: %d consecutive fetch failures — "
                               "pausing 1h", consecutive_failures)
                await asyncio.sleep(3600)
                consecutive_failures = 0
            continue

        # Frontier empty → backfill complete.
        if not settings.marketing_crawl_refresh_daemon:
            logger.info("marketing crawl: backfill complete — runner exiting")
            return
        logger.info("marketing crawl: backfill complete — sleeping until next "
                    "window to re-discover new clubs")
        await asyncio.sleep(_seconds_until_next_start(_now_tz()))
        async with session_maker() as s:
            await discover_clubs(s)  # picks up clubs registered since last pass


async def _sleep_until_window() -> None:
    now = _now_tz()
    if not _in_window(now):
        wait = _seconds_until_next_start(now)
        logger.info("marketing crawl: outside window, sleeping %.0fs", wait)
        await asyncio.sleep(wait)


# ── BetterComms export bridge ──────────────────────────────────────────────────

async def _resolve_outreach_org(session: AsyncSession, organisation_id: Optional[str]) -> Organisation:
    if organisation_id:
        org = await session.get(Organisation, organisation_id)
        if org:
            return org
    if settings.marketing_outreach_org_slug:
        org = await session.scalar(
            select(Organisation).where(Organisation.slug == settings.marketing_outreach_org_slug))
        if org:
            return org
    raise ValueError(
        "No outreach org. Pass organisation_id or set marketing_outreach_org_slug "
        "to a platform org that owns the BetterComms campaigns.")


def _assoc_names(club: MarketingClub) -> list[str]:
    return [a.get("name") for a in (club.associations or []) if a.get("name")]


async def export_to_comms(session: AsyncSession, organisation_id: Optional[str] = None,
                          states: Optional[list[str]] = None,
                          include_associations: bool = False,
                          only_with_email: bool = True) -> dict:
    """Materialise the marketing contacts into ``comms_contacts`` under the
    platform outreach org, so BetterComms does the actual sending (unsubscribe,
    suppression, audit all reused). Skips clubs that are already customers and any
    address suppressed here. Existing comms suppressions are left untouched.
    (``include_associations`` is accepted for API compatibility; the directory
    only holds clubs now.)"""
    org = await _resolve_outreach_org(session, organisation_id)

    q = (
        select(MarketingClubContact, MarketingClub)
        .join(MarketingClub, MarketingClubContact.marketing_club_id == MarketingClub.id)
        .where(MarketingClubContact.subscribed.is_(True),
               MarketingClub.existing_org_id.is_(None))
    )
    if only_with_email:
        q = q.where(MarketingClubContact.email.isnot(None))
    if states:
        q = q.where(MarketingClub.state.in_(states))

    rows = (await session.execute(q)).all()
    added = skipped = suppressed = 0
    for contact, club in rows:
        if not contact.email:
            continue
        email = contact.email.lower()
        existing = await session.scalar(
            select(CommsContact).where(
                CommsContact.organisation_id == org.id,
                func.lower(CommsContact.email) == email))
        if existing:
            if not existing.subscribed:
                suppressed += 1  # respect an opt-out already on the comms side
            else:
                skipped += 1
            continue
        session.add(CommsContact(
            organisation_id=org.id, email=email,
            name=contact.full_name or club.name, source="import",
            tags=[club.name] + _assoc_names(club),
        ))
        added += 1
    await session.commit()
    result = {"org": org.name, "candidates": len(rows), "added": added,
              "already_present": skipped, "already_suppressed": suppressed}
    logger.info("export_to_comms: %s", result)
    return result


async def sync_suppressions(session: AsyncSession, organisation_id: Optional[str] = None) -> dict:
    """Pull unsubscribes/bounces from the platform org's comms_contacts back into
    marketing_club_contacts, so an opt-out is never re-contacted in a later
    campaign or CSV export."""
    org = await _resolve_outreach_org(session, organisation_id)
    suppressed_emails = (await session.execute(
        select(func.lower(CommsContact.email)).where(
            CommsContact.organisation_id == org.id,
            (CommsContact.subscribed.is_(False)) | (CommsContact.bounced.is_(True)))
    )).scalars().all()
    if not suppressed_emails:
        return {"suppressed": 0}
    result = await session.execute(
        update(MarketingClubContact)
        .where(func.lower(MarketingClubContact.email).in_(list(suppressed_emails)),
               MarketingClubContact.subscribed.is_(True))
        .values(subscribed=False, unsubscribed_at=func.now(), updated_at=func.now()))
    await session.commit()
    return {"suppressed": result.rowcount or 0}


# ── CSV export ──────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    s = (name or "").strip().lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


async def clubs_to_csv(session: AsyncSession, states: Optional[list[str]] = None,
                       only_with_email: bool = True, include_associations: bool = False,
                       subscribed_only: bool = True) -> str:
    """Export the directory as CSV — one row per (club, contact). Header carries
    'Club' + 'UTM' + 'Name' so it drops straight into the outreach send tooling,
    plus the association(s) and full metadata for filtering elsewhere."""
    join_cond = MarketingClubContact.marketing_club_id == MarketingClub.id
    if subscribed_only:
        join_cond = and_(join_cond, MarketingClubContact.subscribed.is_(True))
    q = (
        select(MarketingClub, MarketingClubContact)
        .outerjoin(MarketingClubContact, join_cond)
        .where(MarketingClub.detail_fetched_at.isnot(None))
        .order_by(MarketingClub.name.asc(), MarketingClubContact.role_rank.asc())
    )
    if states:
        q = q.where(MarketingClub.state.in_(states))

    rows = (await session.execute(q)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Club", "UTM", "Name", "Role", "Email", "Phone",
        "Association", "All Associations",
        "Address", "Suburb", "State", "Postcode", "Website",
        "PlayHQ Code", "PlayHQ GUID", "Status",
    ])
    for club, contact in rows:
        if only_with_email and not (contact and contact.email):
            continue
        w.writerow([
            club.name, _slug(club.name),
            (contact.full_name if contact else "") or "",
            (contact.role if contact else "") or "",
            (contact.email if contact else "") or "",
            (contact.mobile if contact else "") or club.contact_phone or "",
            club.association_name or "", "; ".join(_assoc_names(club)),
            club.address_line1 or "", club.suburb or "", club.state or "",
            club.postcode or "", club.website_url or "", club.playhq_id or "",
            club.grassroots_guid or "", club.status or "",
        ])
    return buf.getvalue()


async def directory_stats(session: AsyncSession) -> dict:
    """Counts for the admin dashboard / CLI summary."""
    clubs = await session.scalar(select(func.count(MarketingClub.id))) or 0
    assoc_fetched = await session.scalar(select(func.count(MarketingClub.id)).where(
        MarketingClub.associations.isnot(None))) or 0
    assoc_pending = await session.scalar(select(func.count(MarketingClub.id)).where(
        MarketingClub.associations.is_(None))) or 0
    with_email = await session.scalar(
        select(func.count(func.distinct(MarketingClubContact.marketing_club_id)))
        .where(MarketingClubContact.email.isnot(None))) or 0
    contacts = await session.scalar(select(func.count(MarketingClubContact.id))) or 0
    customers = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.existing_org_id.isnot(None))) or 0
    distinct_assoc = await session.scalar(
        select(func.count(func.distinct(MarketingClub.association_guid)))
        .where(MarketingClub.association_guid.isnot(None))) or 0
    return {
        "clubs": clubs,
        "contacts": contacts,
        "clubs_with_email": with_email,
        "associations_fetched": assoc_fetched,
        "associations_pending": assoc_pending,
        "distinct_associations": distinct_assoc,
        "already_customers": customers,
        # Back-compat keys the dashboard/CLI may still read.
        "total": clubs,
        "frontier_remaining": assoc_pending,
    }
