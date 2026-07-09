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

We store the **whole published committee** plus the org-level club mailbox, and a
super admin ticks which contacts (``outreach_selected``) actually receive an
email. Office bearers and the generic club mailbox are pre-ticked.

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

from sqlalchemy import select, func, cast, update, Text, and_, or_, exists, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import (
    MarketingClub, MarketingClubContact, Organisation, CommsContact,
)
from app.services import playhq_directory_client as phq
from app.services.marketing_org import get_outreach_org

logger = logging.getLogger(__name__)

AU_TENANT = "Cricket Australia"


# ── runtime stop/start control ──────────────────────────────────────────────────
# A persisted flag the crawl loops poll, so an operator can stop the background
# crawler (and resume it) without editing env / recreating the container. A Stop
# survives a restart — the continuous runner idles while paused.

async def is_crawl_paused(session: AsyncSession) -> bool:
    val = await session.scalar(text("SELECT paused FROM marketing_crawl_control WHERE id = 1"))
    return bool(val)


async def set_crawl_paused(session: AsyncSession, paused: bool) -> dict:
    await session.execute(text(
        "INSERT INTO marketing_crawl_control (id, paused, updated_at) "
        "VALUES (1, :p, NOW()) ON CONFLICT (id) DO UPDATE SET paused = :p, updated_at = NOW()"),
        {"p": paused})
    await session.commit()
    return {"paused": paused}

# We store the WHOLE committee, with a tidy label + a priority rank so the key
# people sort to the top of each club's contact list. Office bearers rank highest,
# then coordinators, then everyone else. Rank ≤ 4 (office bearers) is also the
# default "email this person" selection (see _DEFAULT_SELECTED_MAX_RANK).
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
_CLUB_CONTACT_RANK = 5    # the org-level generic club mailbox (just below office bearers)
_OTHER_RANK = 50          # any other named committee position
_UNLABELLED_RANK = 60     # a contact with no position at all
# Contacts at or above this rank are pre-selected for outreach by default; the
# rest are stored but unticked, and a super admin chooses per club.
_DEFAULT_SELECTED_MAX_RANK = 4


def _role_for_position(position: Optional[str]) -> tuple[Optional[str], int]:
    """Return (label, rank) for ANY committee position. Office bearers and
    coordinators get a fixed rank; every other role is kept too (rank 50), and a
    contact with no position is kept as 'Committee' (rank 60)."""
    pos = (position or "").strip().upper()
    if not pos:
        return "Committee", _UNLABELLED_RANK
    if pos in _OFFICE_BEARERS:
        return _OFFICE_BEARERS[pos]
    # JUNIOR_CRICKET_COODINATOR → "Junior Cricket Coordinator"; SCORER → "Scorer".
    label = pos.replace("COODINATOR", "COORDINATOR").replace("_", " ").title()
    if _COORDINATOR_RE.search(pos):
        return label, _COORDINATOR_RANK
    return label, _OTHER_RANK


def _default_utm(name: Optional[str]) -> str:
    """The first up-to-THREE words before 'Cricket Club' in the name (split on a
    space OR hyphen), lowercased and hyphen-joined, + '-cricket-club'.
      'Applecross Cricket Club'            → 'applecross-cricket-club'
      'Mount Lawley Cricket Club'          → 'mount-lawley-cricket-club'
      'Bedford-Morley Cricket Club'        → 'bedford-morley-cricket-club'
      'Swan Athletic Caversham CC'         → 'swan-athletic-caversham-cricket-club'
    Empty if there's no usable word."""
    raw = (name or "").strip()
    if not raw:
        return ""
    # Drop a trailing 'cricket club' so we don't repeat it in the slug.
    prefix = re.split(r"(?i)\bcricket[\s-]+club\b", raw, maxsplit=1)[0]
    base = prefix if prefix.strip() else raw
    tokens = []
    for part in re.split(r"[\s-]+", base):           # split on spaces AND hyphens
        tok = re.sub(r"[^a-z0-9]", "", part.lower())
        if tok and tok not in ("cricket", "club"):
            tokens.append(tok)
    if not tokens:
        return ""
    return "-".join(tokens[:3]) + "-cricket-club"     # first one, two or three words


def _full_name(contact: dict) -> Optional[str]:
    name = " ".join(filter(None, [
        (contact.get("firstName") or "").strip(),
        (contact.get("lastName") or "").strip()])).strip()
    return name or None


# ── club upsert (discovery) ─────────────────────────────────────────────────────

async def _store_contact(session: AsyncSession, club_id, full_name: Optional[str],
                         role: str, role_rank: int, email: Optional[str],
                         phone: Optional[str], selected: Optional[bool] = None) -> None:
    """Upsert one committee contact, deduped on lower(email) per club. A re-crawl
    refreshes name/phone and fills a better role but never overrides the manual
    ``outreach_selected`` choice on an existing row. Contacts with no email are
    kept (phone-only), deduped on (club, full_name) so a re-crawl doesn't pile up.
    New rows are pre-selected for outreach when they're office bearers."""
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
    sel = selected if selected is not None else (role_rank <= _DEFAULT_SELECTED_MAX_RANK)
    session.add(MarketingClubContact(
        marketing_club_id=club_id, full_name=full_name, role=role,
        role_rank=role_rank, email=email, mobile=phone, source="api",
        outreach_selected=sel))


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
    if not club.utm_code:   # default once; never clobber a manual edit on re-crawl
        club.utm_code = _default_utm(club.name)
    club.detail_fetched_at = func.now()   # core data (contacts/address) is present
    club.last_crawled_at = func.now()
    if club.status in (None, "new"):
        club.status = "enriched"
    await session.flush()  # need club.id for contacts + dedupe within the batch

    # Store the whole committee (every contact the club publishes). visible=False
    # contacts are the club's deliberate non-publish, so we still skip those.
    top_email = top_phone = None
    top_rank = 999
    for c in (org.get("contacts") or []):
        if c.get("visible") is False:
            continue
        label, rank = _role_for_position(c.get("position"))
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
    club (with its committee). Idempotent — safe to re-run to pick up new clubs.

    Resilient to transient fetch failures: a failed page is retried (not treated
    as the end of the list, which previously truncated discovery on a single
    network blip), and paging stops only on a genuinely empty page or once the
    reported ``totalRecords`` has been covered."""
    page, seen, new, skipped = 1, 0, 0, 0
    total_reported = None
    while page <= max_pages:
        if await is_crawl_paused(session):
            logger.info("discover_clubs: stopped by operator at %d AU clubs", seen)
            break
        results, tot = None, 0
        for attempt in range(5):
            results, tot = await phq.search_organisations("CLUB", "", page=page, limit=100)
            if results is not None:
                break
            logger.warning("discover_clubs: page %d fetch failed (attempt %d/5), retrying",
                           page, attempt + 1)
        if results is None:
            logger.error("discover_clubs: page %d kept failing — stopping early at %d AU "
                         "clubs (will resume on the next discovery pass)", page, seen)
            break
        if not results:
            break  # confirmed empty page = real end of the list
        if tot:
            total_reported = tot
        for org in results:
            if (org.get("tenant") or {}).get("name") != AU_TENANT:
                skipped += 1
                continue
            if await _upsert_club(session, org):
                new += 1
            seen += 1
        await session.commit()
        page += 1
        if total_reported and (page - 1) * 100 >= total_reported:
            break  # paged through everything the search reports
    stats = {"pages": page - 1, "au_seen": seen, "new": new,
             "non_au_skipped": skipped, "total_reported": total_reported}
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

    stats = {"enriched": 0, "with_association": 0, "with_org_contact": 0,
             "errors": 0, "processed": []}
    for club in frontier:
        if await is_crawl_paused(session):
            logger.info("enrich_associations: stopped by operator")
            break
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
        # Also capture the org-level club mailbox (shown on the PlayHQ org page but
        # absent from the search committee list — common for schools / small clubs
        # that publish one generic address and no named office bearers).
        org_contact = await phq.discover_org_contact(club.playhq_id)
        if org_contact and (org_contact.get("email") or org_contact.get("phone")):
            await _store_contact(
                session, club.id, None, "Club contact", _CLUB_CONTACT_RANK,
                org_contact.get("email"), org_contact.get("phone"), selected=True)
            if org_contact.get("email"):
                stats["with_org_contact"] += 1
                if not club.contact_email:
                    club.contact_email = org_contact["email"].lower()
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
    if await is_crawl_paused(session):
        logger.info("crawl_batch: skipped — crawler is stopped")
        return {"skipped": "stopped"}
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
    """Walk the full directory backfill within the daily active window. Runs a
    (resilient) discovery pass once per day inside the window — so the club list
    is rebuilt completely even if an earlier pass was truncated, and newly
    registered clubs are picked up — then enriches one club per loop (the 15-40s
    gap lives in the client), pausing for a longer break every 30-60 clubs and
    sleeping outside the window."""
    logger.info(
        "marketing crawl (continuous): window %s-%s %s, gap %.0f-%.0fs, break "
        "%.0f-%.0fs every %d-%d clubs",
        settings.marketing_crawl_window_start, settings.marketing_crawl_window_end,
        settings.marketing_crawl_tz, settings.marketing_crawl_min_delay,
        settings.marketing_crawl_max_delay, settings.marketing_crawl_break_min,
        settings.marketing_crawl_break_max, settings.marketing_crawl_break_after_min,
        settings.marketing_crawl_break_after_max)

    last_discover_day = None
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

        # Operator Stop — idle (and keep checking) until they resume.
        async with session_maker() as s:
            if await is_crawl_paused(s):
                await asyncio.sleep(30)
                continue

        # Once per day, inside the window, (re)discover the whole club universe AND
        # the association registry. Both are idempotent + resilient.
        if last_discover_day != now.date():
            async with session_maker() as s:
                await discover_clubs(s)
                await discover_associations_registry(s)
            last_discover_day = now.date()
            continue

        # Association roster sweep takes priority — one resolve links a whole
        # association's clubs at once (far higher leverage than one club at a time),
        # so association filters fill in fast. Falls through to per-club enrichment
        # once every association has been resolved (refreshed weekly).
        async with session_maker() as s:
            swept = await sweep_association_rosters(s, limit=1, delay=_SWEEP_DELAY)
        if swept["resolved"] > 0:
            consecutive_failures = 0
            since_break += 1
            if since_break >= next_break_at:
                brk = random.uniform(settings.marketing_crawl_break_min,
                                     settings.marketing_crawl_break_max)
                logger.info("marketing crawl: break for %.0fs after %d items", brk, since_break)
                await asyncio.sleep(brk)
                since_break = 0
                next_break_at = random.randint(settings.marketing_crawl_break_after_min,
                                               settings.marketing_crawl_break_after_max)
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

        # Frontier empty → backfill complete for now.
        if not settings.marketing_crawl_refresh_daemon:
            logger.info("marketing crawl: backfill complete — runner exiting")
            return
        # Sleep to the next window; the once-a-day discovery at the top of the loop
        # then picks up any newly-registered clubs.
        logger.info("marketing crawl: backfill complete — sleeping until next window")
        await asyncio.sleep(_seconds_until_next_start(_now_tz()))


async def _sleep_until_window() -> None:
    now = _now_tz()
    if not _in_window(now):
        wait = _seconds_until_next_start(now)
        logger.info("marketing crawl: outside window, sleeping %.0fs", wait)
        await asyncio.sleep(wait)


# Treat the crawl as "running" if something was fetched within this many seconds.
# Wide enough to span a single big association resolve (which only commits its
# club timestamps at the end — up to ~10 min) plus the runner's max break, so a
# healthy sweep doesn't flicker to "paused".
_ACTIVE_WITHIN_SECONDS = 900


async def crawl_status(session: AsyncSession) -> dict:
    """Live, stateless crawl status derived from the table + window settings, so
    the page can show running / waiting / idle / complete after any refresh
    (there's no in-memory run state to lose). 'Activity' = the most recent
    ``last_crawled_at`` across all clubs, which both discovery and enrichment bump
    per row."""
    clubs = await session.scalar(select(func.count(MarketingClub.id))) or 0
    pending = await session.scalar(select(func.count(MarketingClub.id)).where(
        MarketingClub.associations.is_(None), MarketingClub.kind == "club")) or 0
    last = await session.scalar(select(func.max(MarketingClub.last_crawled_at)))

    since = None
    if last is not None:
        now = dt.datetime.now(last.tzinfo or dt.timezone.utc)
        since = max(0.0, (now - last).total_seconds())
    recent = since is not None and since < _ACTIVE_WITHIN_SECONDS

    continuous = bool(settings.marketing_crawl_enabled and settings.marketing_crawl_continuous)
    paused = await is_crawl_paused(session)
    in_win = _in_window(_now_tz())
    window = {"start": settings.marketing_crawl_window_start,
              "end": settings.marketing_crawl_window_end,
              "tz": settings.marketing_crawl_tz}

    if paused:
        state = "stopped"
        detail = (f"Stopped by an operator. {pending} clubs still await enrichment. "
                  f"Click Start crawling to resume.")
    elif clubs == 0:
        state, detail = "idle", "No clubs collected yet. Click Run crawl batch to start."
    elif recent:
        state, detail = "running", f"Active — last fetch {int(since)}s ago."
    elif pending == 0:
        state, detail = "complete", f"Backfill complete — {clubs} clubs, all enriched."
    elif continuous and not in_win:
        state = "waiting"
        detail = (f"Outside the active window — resumes at {window['start']} "
                  f"{window['tz']}. {pending} clubs left to enrich.")
    elif continuous and in_win:
        state = "paused"
        detail = (f"In window, no fetch in {int(since)}s — likely on a break, or "
                  f"the runner stalled. {pending} clubs left.")
    else:
        state = "idle"
        detail = (f"Idle — {pending} clubs await association enrichment. Run a batch, "
                  f"or enable the continuous runner.")

    return {
        "state": state, "detail": detail, "paused": paused,
        "clubs": clubs, "associations_pending": pending,
        "last_activity_at": last.isoformat() if last else None,
        "seconds_since_activity": int(since) if since is not None else None,
        "continuous_enabled": continuous,
        "crawl_enabled": bool(settings.marketing_crawl_enabled),
        "in_window": in_win, "window": window,
    }


# ── BetterComms export bridge ──────────────────────────────────────────────────

async def _resolve_outreach_org(session: AsyncSession, organisation_id: Optional[str]) -> Organisation:
    if organisation_id:
        org = await session.get(Organisation, organisation_id)
        if org:
            return org
    org = await get_outreach_org(session)
    if org:
        return org
    raise ValueError(
        "No outreach org. Designate one in BetterComms, pass organisation_id, or "
        "set marketing_outreach_org_slug to a platform org that owns the campaigns.")


def _assoc_names(club: MarketingClub) -> list[str]:
    # Guard non-dict entries (a null / stray string in the associations JSONB would
    # otherwise AttributeError and 500 the whole CSV export) — same guard as
    # twenty_sync._club_assocs.
    return [a["name"] for a in (club.associations or [])
            if isinstance(a, dict) and a.get("name")]


# Contact-presence filters offered on the directory page.
#   any_email   — ≥1 contact with an email (named or not)
#   named_email — ≥1 contact that has BOTH a name and an email
#   pst         — a named+emailed President AND Secretary AND Treasurer
CONTACT_FILTERS = ("any_email", "named_email", "pst")
_PST_ROLES = ("President", "Secretary", "Treasurer")


def _named_email_cond():
    C = MarketingClubContact
    return and_(C.email.isnot(None), C.full_name.isnot(None),
                func.length(func.trim(C.full_name)) > 0)


def _assoc_match(name: str):
    """A club 'belongs to' an association if it's the primary or in the JSONB list."""
    nl = (name or "").lower()
    return or_(func.lower(MarketingClub.association_name) == nl,
               func.lower(cast(MarketingClub.associations, Text)).like(f"%{nl}%"))


def _contact_exists(*conds):
    """A correlated EXISTS over a club's contacts, pinned to correlate ONLY against
    MarketingClub. Without the explicit correlate, an enclosing query that also selects
    MarketingClubContact (the CSV export and the BetterComms export are two-table
    selects) auto-correlates the subquery's own FROM away, and SQLAlchemy raises
    "returned no FROM clauses due to auto-correlation". Correct for the single-table
    list query too (MarketingClub is still the correlated table)."""
    return (exists()
            .where(MarketingClubContact.marketing_club_id == MarketingClub.id, *conds)
            .correlate(MarketingClub))


# ─── Tri-state directory filters (off / include / exclude) ───────────────────
#
# Each of these filters can be OFF, or applied as INCLUDE (keep only matching
# clubs) or EXCLUDE (drop matching clubs). Every filter is defined by an
# (exclude_cond, include_cond) pair — exclude_cond is exactly what the old
# boolean exclude filter applied, so existing behaviour is preserved; the include
# side is its logical counterpart. Applied from the ``modes`` map that the router
# threads through club_filters. See routers/marketing.py + SuperMarketing.jsx.
FILTER_MODE_KEYS = (
    "junior", "carnival", "school", "rep", "cricket_au",
    "emailed", "exported", "suppressed", "excluded",
)
FILTER_MODES = ("off", "include", "exclude")

# Cricket Australia / state-association mailbox domains. A club whose generic
# email (or any officer email) sits on one of these is a governing-body org, not
# a grassroots club we'd cold-email. Matched as the email host (…@domain) or a
# subdomain (…@x.domain), case-insensitively, so "notcricket.com.au" never trips.
CA_EMAIL_DOMAINS = (
    "cricket.com.au", "wacricket.com.au", "saca.com.au", "cricketvictoria.com.au",
    "crickettas.com.au", "cricketnsw.com.au", "ccnsw.com", "cricketact.com.au",
    "qldcricket.com.au", "ntcricket.com.au",
)


def _ca_email_match(col):
    """True if ``col`` is an email on a Cricket Australia / state-body domain."""
    parts = []
    for d in CA_EMAIL_DOMAINS:
        parts.append(func.lower(col).like(f"%@{d}"))
        parts.append(func.lower(col).like(f"%@%.{d}"))
    return or_(*parts)


def _filter_conditions(key: str):
    """(exclude_cond, include_cond) for a tri-state filter, or None for unknown."""
    C = MarketingClubContact
    name = func.lower(MarketingClub.name)
    if key == "junior":
        p = name.like("%junior%"); return (~p, p)
    if key == "carnival":
        p = name.like("%carnival%"); return (~p, p)
    if key == "school":
        p = name.like("%school%"); return (~p, p)
    if key == "rep":
        # Representative teams: a word starting "rep" (Rep / Reps / Representative),
        # so "Prep"/"…prep…" is not caught. Postgres case-insensitive regex.
        p = MarketingClub.name.op("~*")(r"\m(rep|represent)")
        return (~p, p)
    if key == "cricket_au":
        p = or_(_ca_email_match(MarketingClub.contact_email),
                _contact_exists(_ca_email_match(C.email)))
        return (~p, p)
    if key == "emailed":
        return (MarketingClub.emailed_at.is_(None), MarketingClub.emailed_at.isnot(None))
    if key == "exported":
        # exclude = keep clubs that still have an emailable contact not yet in
        # BetterComms (the old behaviour); include = only clubs with nothing left.
        keep = _contact_exists(C.email.isnot(None), C.exported_at.is_(None))
        return (keep, ~keep)
    if key == "suppressed":
        # exclude = keep clubs that still have a subscribed emailable contact;
        # include = only clubs with none left.
        keep = _contact_exists(C.email.isnot(None), C.subscribed.is_(True))
        return (keep, ~keep)
    if key == "excluded":
        # A club a super admin has flagged as excluded from outreach (never
        # exported/sent). exclude = drop excluded clubs; include = only them.
        p = MarketingClub.excluded.is_(True)
        return (~p, p)
    return None


def filter_mode_conditions(modes: Optional[dict]) -> list:
    """Translate a ``{key: 'include'|'exclude'}`` map into WHERE conditions."""
    out = []
    for key in FILTER_MODE_KEYS:
        mode = str((modes or {}).get(key) or "").strip().lower()
        if mode not in ("include", "exclude"):
            continue
        pair = _filter_conditions(key)
        if pair is None:
            continue
        exclude_cond, include_cond = pair
        out.append(include_cond if mode == "include" else exclude_cond)
    return out


def club_filters(q: Optional[str] = None, state: Optional[str] = None,
                 association: Optional[str] = None, status: Optional[str] = None,
                 postcode_from: Optional[str] = None, postcode_to: Optional[str] = None,
                 contact_filter: Optional[str] = None, person: Optional[str] = None,
                 modes: Optional[dict] = None,
                 visited: bool = False,
                 associations: Optional[list] = None,
                 association_extra: Optional[list] = None,
                 countries: Optional[list] = None,
                 engagement_score_gte: Optional[int] = None,
                 engagement_score_lte: Optional[int] = None) -> list:
    """Build the WHERE conditions (on ``MarketingClub``) shared by the list view,
    the CSV export and the BetterComms export, so all three honour the same
    filters. Contact-presence filters use correlated EXISTS over the contacts.

    ``modes`` carries the tri-state directory filters (junior / carnival / school
    / rep / cricket_au / emailed / exported / suppressed), each 'include' or
    'exclude'; see filter_mode_conditions."""
    C = MarketingClubContact
    conds = []
    if state:
        conds.append(MarketingClub.state == state)
    # Tri-state directory filters (off / include / exclude).
    conds.extend(filter_mode_conditions(modes))
    if associations:
        conds.append(or_(*[_assoc_match(n) for n in associations if n]))
    if countries:
        conds.append(MarketingClub.country.in_([c for c in countries if c]))
    if visited:
        # Only clubs where someone has visited the public site from a link tagged
        # with this club's UTM code — resolved through utm_code matches AND manual
        # aliases (see the note above club_visit_stats). One-pass set membership (not
        # a per-club correlated EXISTS). Safe SQL: only fixed table names, never input.
        conds.append(text(_visited_in_sql("marketing_clubs")))
    if person:
        p = f"%{person.lower()}%"
        conds.append(_contact_exists(func.lower(C.full_name).like(p)))
    if status:
        conds.append(MarketingClub.status == status)
    if q:
        like = f"%{q.lower()}%"
        conds.append(or_(func.lower(MarketingClub.name).like(like),
                         func.lower(MarketingClub.association_name).like(like)))
    if association:
        a = f"%{association.lower()}%"
        # primary association OR any in the associations JSONB list OR (when the
        # text matched an association short code, e.g. 'wastca') any club in those
        # association(s).
        name_conds = [func.lower(MarketingClub.association_name).like(a),
                      func.lower(cast(MarketingClub.associations, Text)).like(a)]
        for n in (association_extra or []):
            name_conds.append(_assoc_match(n))
        conds.append(or_(*name_conds))
    # AU postcodes are 4-digit; lexical compare of 4-char numeric strings == numeric,
    # and the regex guard keeps non-4-digit values out (no CAST, so never errors).
    pc_ok = MarketingClub.postcode.op("~")("^[0-9]{4}$")
    if postcode_from:
        conds.append(and_(pc_ok, MarketingClub.postcode >= str(postcode_from).zfill(4)))
    if postcode_to:
        conds.append(and_(pc_ok, MarketingClub.postcode <= str(postcode_to).zfill(4)))
    # Cached score (see MarketingClub.engagement_score) — reuses >=/<= rather than
    # strict >/< (matches the postcode-range precedent above; a club scored exactly
    # on the boundary you typed should show, not be excluded by it).
    if engagement_score_gte is not None:
        conds.append(MarketingClub.engagement_score >= engagement_score_gte)
    if engagement_score_lte is not None:
        conds.append(MarketingClub.engagement_score <= engagement_score_lte)
    if contact_filter == "any_email":
        conds.append(_contact_exists(C.email.isnot(None)))
    elif contact_filter == "named_email":
        conds.append(_contact_exists(_named_email_cond()))
    elif contact_filter == "pst":
        for role in _PST_ROLES:
            conds.append(_contact_exists(_named_email_cond(), C.role == role))
    return conds


async def export_to_comms(session: AsyncSession, organisation_id: Optional[str] = None,
                          only_with_email: bool = True, selected_only: bool = True,
                          filters: Optional[dict] = None) -> dict:
    """Materialise the marketing contacts into ``comms_contacts`` under the
    platform outreach org, so BetterComms does the actual sending (unsubscribe,
    suppression, audit all reused). Honours the same directory ``filters`` the
    page shows (state / association / postcode / contact-presence), and only the
    contacts a super admin ticked (``outreach_selected``) unless ``selected_only``
    is False. The only hard guard is the excluded flag; a suppressed address is
    left untouched. Customers and already-emailed clubs ARE exportable (use the
    directory filters to hold them back when you want to)."""
    org = await _resolve_outreach_org(session, organisation_id)

    q = (
        select(MarketingClubContact, MarketingClub)
        .join(MarketingClub, MarketingClubContact.marketing_club_id == MarketingClub.id)
        .where(MarketingClubContact.subscribed.is_(True))
    )
    for cond in club_filters(**(filters or {})):
        q = q.where(cond)
    # The one hard guard, regardless of the UI filters: never export an excluded
    # club. Customer / already-emailed clubs are eligible (steer them with the
    # tri-state directory filters instead).
    q = q.where(MarketingClub.excluded.is_(False))
    if selected_only:
        q = q.where(MarketingClubContact.outreach_selected.is_(True))
    if only_with_email:
        q = q.where(MarketingClubContact.email.isnot(None))

    rows = (await session.execute(q)).all()
    added = skipped = suppressed = 0
    now = func.now()
    for contact, club in rows:
        if not contact.email:
            continue
        email = contact.email.lower()
        existing = await session.scalar(
            select(CommsContact).where(
                CommsContact.organisation_id == org.id,
                func.lower(CommsContact.email) == email))
        if existing:
            # Already in BetterComms — stamp it exported (idempotent) so the
            # directory shows the badge and won't offer it for re-export.
            contact.exported_at = contact.exported_at or now
            if not existing.subscribed:
                suppressed += 1  # respect an opt-out already on the comms side
            else:
                skipped += 1
            continue
        # {{name}} is the officer's name only. When the crawl found only an email
        # (no officer name), leave it blank rather than falling back to the club
        # name — a blank name is what the "Set First Name" find/replace targets, and
        # a club name in {{name}} would greet a person by their club. The club name
        # still travels on the contact via its linked directory club (the {{club}}
        # variable) and its tags.
        session.add(CommsContact(
            organisation_id=org.id, email=email,
            name=(contact.full_name or "").strip() or None, source="import",
            marketing_club_id=club.id,   # link back so a campaign send flags the club
            tags=[club.name] + _assoc_names(club),
        ))
        contact.exported_at = now
        added += 1
    await session.commit()

    # Diagnostics: how many clubs matched the directory filter, and how many the
    # one hard guard (excluded) held back — so the UI can explain a "0 added"
    # result. Customer / emailed counts are informational only (no longer skipped).
    base = select(MarketingClub.id).where(MarketingClub.detail_fetched_at.isnot(None))
    for cond in club_filters(**(filters or {})):
        base = base.where(cond)

    async def _count(*extra):
        s = base
        for c in extra:
            s = s.where(c)
        return await session.scalar(select(func.count()).select_from(s.subquery())) or 0

    matched = await _count()
    eligible = await _count(MarketingClub.excluded.is_(False))

    result = {"org": org.name, "candidates": len(rows), "added": added,
              "already_present": skipped, "already_suppressed": suppressed,
              "clubs_matched": matched, "clubs_eligible": eligible,
              "customers": await _count(MarketingClub.existing_org_id.isnot(None)),
              "emailed": await _count(MarketingClub.emailed_at.isnot(None)),
              "skipped_excluded": await _count(MarketingClub.excluded.is_(True))}
    logger.info("export_to_comms: %s", result)
    return result


async def sync_suppressions(session: AsyncSession, organisation_id: Optional[str] = None) -> dict:
    """Reconcile the directory with the outreach org's ``comms_contacts``:

    1. Pull unsubscribes/bounces back into ``marketing_club_contacts.subscribed``
       so an opt-out is never re-contacted in a later campaign or CSV export.
    2. Reconcile the per-contact ``exported_at`` flag against the live comms set —
       mark contacts that exist in BetterComms as exported, and clear the flag for
       any contact whose comms record was deleted (so it shows as not-exported and
       can be exported again)."""
    org = await _resolve_outreach_org(session, organisation_id)
    now = func.now()

    # 1. Suppressions (opt-outs / bounces).
    suppressed_emails = (await session.execute(
        select(func.lower(CommsContact.email)).where(
            CommsContact.organisation_id == org.id,
            (CommsContact.subscribed.is_(False)) | (CommsContact.bounced.is_(True)))
    )).scalars().all()
    suppressed_n = 0
    if suppressed_emails:
        res = await session.execute(
            update(MarketingClubContact)
            .where(func.lower(MarketingClubContact.email).in_(list(suppressed_emails)),
                   MarketingClubContact.subscribed.is_(True))
            .values(subscribed=False, unsubscribed_at=now, updated_at=now))
        suppressed_n = res.rowcount or 0

    # 2. Exported reconcile against the full live comms set for this org.
    comms_emails = (await session.execute(
        select(func.lower(CommsContact.email)).where(CommsContact.organisation_id == org.id)
    )).scalars().all()
    comms_set = list({e for e in comms_emails if e})
    marked_n = 0
    if comms_set:
        cleared = await session.execute(
            update(MarketingClubContact)
            .where(MarketingClubContact.exported_at.isnot(None),
                   func.lower(MarketingClubContact.email).notin_(comms_set))
            .values(exported_at=None, updated_at=now))
        marked = await session.execute(
            update(MarketingClubContact)
            .where(MarketingClubContact.exported_at.is_(None),
                   MarketingClubContact.email.isnot(None),
                   func.lower(MarketingClubContact.email).in_(comms_set))
            .values(exported_at=now, updated_at=now))
        marked_n = marked.rowcount or 0
    else:
        # No comms contacts left at all → every exported flag is stale.
        cleared = await session.execute(
            update(MarketingClubContact)
            .where(MarketingClubContact.exported_at.isnot(None))
            .values(exported_at=None, updated_at=now))
    cleared_n = cleared.rowcount or 0
    await session.commit()
    return {"suppressed": suppressed_n, "export_marked": marked_n, "export_cleared": cleared_n}


# ── CSV export ──────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    s = (name or "").strip().lower().replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


async def clubs_to_csv(session: AsyncSession, only_with_email: bool = True,
                       subscribed_only: bool = True,
                       filters: Optional[dict] = None) -> str:
    """Export the directory as CSV — one row per (club, contact), honouring the
    same directory ``filters`` the page shows. Header carries 'Club' + 'UTM' +
    'Name' so it drops straight into the outreach send tooling, plus the
    association(s) and full metadata for filtering elsewhere."""
    join_cond = MarketingClubContact.marketing_club_id == MarketingClub.id
    if subscribed_only:
        join_cond = and_(join_cond, MarketingClubContact.subscribed.is_(True))
    q = (
        select(MarketingClub, MarketingClubContact)
        .outerjoin(MarketingClubContact, join_cond)
        .where(MarketingClub.detail_fetched_at.isnot(None))
        .order_by(MarketingClub.name.asc(), MarketingClubContact.role_rank.asc())
    )
    for cond in club_filters(**(filters or {})):
        q = q.where(cond)

    rows = (await session.execute(q)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Club", "UTM", "Name", "Role", "Email", "Phone", "Email?",
        "Association", "All Associations",
        "Address", "Suburb", "State", "Postcode", "Website",
        "PlayHQ Code", "PlayHQ GUID", "Status", "Emailed",
    ])
    for club, contact in rows:
        if only_with_email and not (contact and contact.email):
            continue
        w.writerow([
            club.name, club.utm_code or _default_utm(club.name),
            (contact.full_name if contact else "") or "",
            (contact.role if contact else "") or "",
            (contact.email if contact else "") or "",
            (contact.mobile if contact else "") or club.contact_phone or "",
            "yes" if (contact and contact.outreach_selected) else "no",
            club.association_name or "", "; ".join(_assoc_names(club)),
            club.address_line1 or "", club.suburb or "", club.state or "",
            club.postcode or "", club.website_url or "", club.playhq_id or "",
            club.grassroots_guid or "", club.status or "",
            club.emailed_via if club.emailed_at else "",
        ])
    return buf.getvalue()


async def mark_emailed(session: AsyncSession, club_id: str, emailed: bool,
                       via: str = "manual", note: Optional[str] = None) -> Optional[dict]:
    """Manually mark / unmark a club as already emailed (so it isn't emailed
    again). Returns the new state, or None if the club isn't found."""
    club = await session.get(MarketingClub, club_id)
    if club is None:
        return None
    if emailed:
        club.emailed_at = func.now()
        club.emailed_via = via if via in ("manual", "campaign") else "manual"
        club.emailed_note = (note or None)
    else:
        club.emailed_at = None
        club.emailed_via = None
        club.emailed_note = None
    club.updated_at = func.now()
    await session.commit()
    await session.refresh(club)
    return {"id": str(club.id), "emailed": club.emailed_at is not None,
            "emailed_via": club.emailed_via, "emailed_note": club.emailed_note,
            "emailed_at": club.emailed_at.isoformat() if club.emailed_at else None}


async def set_excluded(session: AsyncSession, club_id: str, excluded: bool) -> Optional[dict]:
    """Exclude / un-exclude a club from outreach. Sets the hard-guard flag and
    propagates to any comms contacts already exported from this club, so an
    in-flight BetterAdmin Comms list/campaign drops (or restores) them too.
    Reversible. Returns the new state, or None if the club isn't found."""
    club = await session.get(MarketingClub, club_id)
    if club is None:
        return None
    now = func.now()
    club.excluded = excluded
    club.excluded_at = now if excluded else None
    club.updated_at = now
    # Reflect onto the exported comms contacts (only the directory export sets
    # marketing_club_id, so this never touches a club's own member contacts).
    await session.execute(
        update(CommsContact)
        .where(CommsContact.marketing_club_id == club.id)
        .values(excluded=excluded, excluded_at=(now if excluded else None), updated_at=now))
    await session.commit()
    await session.refresh(club)
    return {"id": str(club.id), "excluded": club.excluded,
            "excluded_at": club.excluded_at.isoformat() if club.excluded_at else None}


# Sales-pipeline module keys a super admin can flag a prospect against.
SALES_MODULE_KEYS = ("core", "select", "socials", "admin", "iq", "fantasy")
DEMO_STATUSES = ("in_trial", "trial_expired", "customer")


def _clean_modules(values) -> list:
    if not isinstance(values, list):
        return []
    seen, out = set(), []
    for v in values:
        k = str(v).strip().lower()
        if k in SALES_MODULE_KEYS and k not in seen:
            seen.add(k)
            out.append(k)
    return out


async def set_sales_state(session: AsyncSession, club_id: str, *,
                          trial_modules=None, requested_trial_modules=None,
                          demo_status=..., not_interested=None) -> Optional[dict]:
    """Set a prospect club's sales-pipeline state (super-admin maintained, no
    automated source). Only the fields passed are changed. Returns the new state,
    or None if the club isn't found.

    Adding a module to Trial Modules OR Requested Trial here queues the same
    super-admin action-queue request the Twenty CRM webhook raises when a
    salesperson does the equivalent edit on the Company (see
    twenty_inbound.request_trial_modules): a real ModuleActionRequest if the club
    is already synced, else a Twenty Task asking for it to be synced first.
    Requested Trial is the "a club asked us for a trial" signal (e.g. by phone/
    email, logged here by a super admin) — it needs the same follow-up action as
    Trial Modules, just earlier in the pipeline, so it raises the identical
    request/Task rather than sitting silently on the club's row. Best-effort —
    never blocks saving the sales state."""
    club = await session.get(MarketingClub, club_id)
    if club is None:
        return None
    old_trial = set(club.trial_modules or [])
    old_requested = set(club.requested_trial_modules or [])
    old_demo_status = club.demo_status
    if trial_modules is not None:
        club.trial_modules = _clean_modules(trial_modules)
    if requested_trial_modules is not None:
        club.requested_trial_modules = _clean_modules(requested_trial_modules)
    if demo_status is not ...:
        ds = (str(demo_status).strip().lower() if demo_status else "") or None
        club.demo_status = ds if ds in DEMO_STATUSES else None
    if not_interested is not None:
        club.not_interested = bool(not_interested)
    club.updated_at = func.now()
    added_trial = set(club.trial_modules or []) - old_trial
    added_requested = set(club.requested_trial_modules or []) - old_requested
    became_in_trial = club.demo_status == "in_trial" and old_demo_status != "in_trial"
    await session.commit()
    await session.refresh(club)
    added_modules = sorted(added_trial | added_requested)
    if added_modules:
        try:
            from app.services.twenty_inbound import request_trial_modules
            org = (await session.get(Organisation, club.existing_org_id)
                   if club.existing_org_id else None)
            await request_trial_modules(session, club, org, added_modules,
                                        source="app", ext_key=f"app:{club.grassroots_guid}")
        except Exception:  # noqa: BLE001 - queueing the follow-up must never block the save
            logger.exception("club_directory: failed to queue trial request for %s", club.id)
    if added_modules or became_in_trial:
        # Requesting or starting a trial here is as strong a buying signal as a
        # direct "onboard my club" enquiry — force the same immediate Hot (100)
        # + Lead treatment rather than letting it filter through as partial
        # credit in the gradual engagement formula (see push_onboarding_enquiry).
        try:
            from app.services.twenty_sync import push_club_and_contacts
            await push_club_and_contacts(
                club.id, engagement_override={
                    "engagementScore": 100, "engagementTier": "HOT", "inSalesCycle": True})
        except Exception:  # noqa: BLE001 - the CRM push must never block the save
            logger.exception("club_directory: failed to push trial engagement for %s", club.id)
    return {
        "id": str(club.id),
        "trial_modules": club.trial_modules or [],
        "requested_trial_modules": club.requested_trial_modules or [],
        "demo_status": club.demo_status,
        "not_interested": bool(club.not_interested),
    }


async def _filtered_club_ids(session: AsyncSession, filters: Optional[dict],
                             kind: str = "club") -> list:
    """The club ids matching the same filters the list view uses — the target set
    for a bulk action. Materialised (not a correlated subquery) so the contact
    EXISTS conditions in ``club_filters`` bind correctly and can be reused for the
    comms-contact propagation."""
    stmt = select(MarketingClub.id).where(MarketingClub.detail_fetched_at.isnot(None))
    if kind:
        stmt = stmt.where(MarketingClub.kind == kind)
    for cond in club_filters(**(filters or {})):
        stmt = stmt.where(cond)
    return (await session.execute(stmt)).scalars().all()


async def bulk_mark_emailed(session: AsyncSession, emailed: bool, via: str = "manual",
                            note: Optional[str] = None,
                            filters: Optional[dict] = None) -> dict:
    """Mark / unmark every club in the current filtered list as emailed."""
    ids = await _filtered_club_ids(session, filters)
    if not ids:
        return {"updated": 0, "emailed": emailed}
    now = func.now()
    if emailed:
        vals = {"emailed_at": now, "emailed_note": (note or None), "updated_at": now,
                "emailed_via": via if via in ("manual", "campaign") else "manual"}
    else:
        vals = {"emailed_at": None, "emailed_via": None, "emailed_note": None, "updated_at": now}
    await session.execute(update(MarketingClub).where(MarketingClub.id.in_(ids)).values(**vals))
    await session.commit()
    return {"updated": len(ids), "emailed": emailed}


async def bulk_set_excluded(session: AsyncSession, excluded: bool,
                            filters: Optional[dict] = None) -> dict:
    """Exclude / un-exclude every club in the current filtered list, propagating to
    any comms contacts already exported from those clubs (same as the per-club
    toggle)."""
    ids = await _filtered_club_ids(session, filters)
    if not ids:
        return {"updated": 0, "excluded": excluded}
    now = func.now()
    await session.execute(
        update(MarketingClub).where(MarketingClub.id.in_(ids))
        .values(excluded=excluded, excluded_at=(now if excluded else None), updated_at=now))
    await session.execute(
        update(CommsContact).where(CommsContact.marketing_club_id.in_(ids))
        .values(excluded=excluded, excluded_at=(now if excluded else None), updated_at=now))
    await session.commit()
    return {"updated": len(ids), "excluded": excluded}


async def set_utm(session: AsyncSession, club_id: str, utm: str) -> Optional[dict]:
    """Set a club's UTM code (manual edit). Blank resets it to the name-derived
    default. Returns the new value, or None if the club isn't found."""
    club = await session.get(MarketingClub, club_id)
    if club is None:
        return None
    cleaned = (utm or "").strip()
    club.utm_code = cleaned or _default_utm(club.name)
    club.updated_at = func.now()
    await session.commit()
    return {"id": str(club.id), "utm_code": club.utm_code}


async def list_associations(session: AsyncSession) -> list[dict]:
    """All associations for the multi-select filter, from the registry (every
    association we've discovered, ~677) — not just the ones already linked to
    clubs. ``count`` is the linked club count (0 until that association's roster
    has been swept), ``resolved`` says whether its roster has been fetched. The id
    is the PlayHQ routingCode (used to fetch the roster on demand)."""
    known = await session.scalar(text("SELECT COUNT(*) FROM marketing_associations")) or 0
    if known:
        rows = (await session.execute(text("""
            SELECT id, name, club_count, (last_resolved_at IS NOT NULL) AS resolved, short_code
            FROM marketing_associations
            ORDER BY name
        """))).all()
        return [{"name": r[1], "id": r[0], "count": r[2] or 0, "resolved": bool(r[3]),
                 "short": r[4] or ""} for r in rows]
    # Fallback before the registry is populated: derive from linked clubs.
    rows = (await session.execute(text("""
        SELECT elem->>'name' AS name, MIN(elem->>'id') AS id, COUNT(DISTINCT mc.id) AS n
        FROM marketing_clubs mc
        CROSS JOIN LATERAL jsonb_array_elements(mc.associations) elem
        WHERE mc.associations IS NOT NULL
          AND jsonb_typeof(mc.associations) = 'array'
          AND COALESCE(elem->>'name', '') <> ''
        GROUP BY elem->>'name'
        ORDER BY elem->>'name'
    """))).all()
    return [{"name": r[0], "id": r[1], "count": r[2], "resolved": True} for r in rows]


async def list_countries(session: AsyncSession) -> list[dict]:
    """Distinct countries (name + linked-club count) for the multi-select filter.
    Unlike associations there's no registry or short code — a club's country is a
    plain column set from its address at crawl time. AU-only for now."""
    rows = (await session.execute(text("""
        SELECT country, COUNT(*) AS n
        FROM marketing_clubs
        WHERE country IS NOT NULL AND TRIM(country) <> ''
        GROUP BY country
        ORDER BY country
    """))).all()
    return [{"name": r[0], "count": r[1]} for r in rows]


# Bounds for the on-demand association-roster traversal (operator action).
_MAX_RESOLVE_SEASONS = 2
_MAX_RESOLVE_GRADES = 80


def assoc_acronym(name: str) -> str:
    """Derive a searchable short code from the name (PlayHQ has none): the first
    letter of each alphabetic word, uppercased. 'West Australian Suburban Turf
    Cricket Association' → 'WASTCA'."""
    return "".join(w[0] for w in re.findall(r"[A-Za-z]+", name or "")).upper()


async def register_association(session: AsyncSession, assoc_id: str, name: str) -> None:
    """Upsert an association into the registry (for the automatic sweep), with a
    derived short code (e.g. WASTCA) so it's searchable by acronym."""
    if not assoc_id:
        return
    # Set the derived short code on first insert only; never overwrite on the
    # daily re-register, so a hand-edited code persists.
    await session.execute(text(
        "INSERT INTO marketing_associations (id, name, short_code) VALUES (:id, :name, :short) "
        "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
        "short_code = COALESCE(marketing_associations.short_code, EXCLUDED.short_code), "
        "updated_at = NOW()"),
        {"id": assoc_id, "name": name or "", "short": assoc_acronym(name)})


async def set_association_shortcode(session: AsyncSession, assoc_id: str,
                                    short: str) -> Optional[dict]:
    """Manually set an association's short code. Blank resets it to the
    name-derived acronym. Returns the new value, or None if not found."""
    name = await session.scalar(text(
        "SELECT name FROM marketing_associations WHERE id = :id"), {"id": assoc_id})
    if name is None:
        return None
    code = (short or "").strip().upper() or assoc_acronym(name)
    await session.execute(text(
        "UPDATE marketing_associations SET short_code = :c, updated_at = NOW() WHERE id = :id"),
        {"c": code or None, "id": assoc_id})
    await session.commit()
    return {"id": assoc_id, "short": code}


async def shortcode_association_names(session: AsyncSession, text_q: str) -> list[str]:
    """Association names whose short code matches the text (e.g. 'wastca' → 'West
    Australian Suburban Turf Cricket Association'). Powers shortcode search in the
    'Association contains' filter."""
    q = (text_q or "").strip().lower()
    if not q:
        return []
    rows = (await session.execute(text(
        "SELECT name FROM marketing_associations WHERE short_code IS NOT NULL "
        "AND lower(short_code) LIKE :t"), {"t": f"%{q}%"})).all()
    return [r[0] for r in rows]


async def expand_shortcode(session: AsyncSession, kwargs: dict) -> dict:
    """If the 'Association contains' text matches an association short code, add
    those association names so the filter also matches by shortcode (e.g. wastca)."""
    a = (kwargs or {}).get("association")
    if a:
        kwargs = dict(kwargs)
        kwargs["association_extra"] = await shortcode_association_names(session, a)
    return kwargs


async def resolve_association_clubs(session: AsyncSession, assoc_id: str,
                                    assoc_name: str, delay: tuple | None = None) -> dict:
    """Fetch an association's FULL club roster live (association → seasons → grades
    → ladder → each team's club) and link those clubs to the association in the
    directory, so the association filter shows the complete membership immediately
    instead of waiting for every club to be enriched. Matches clubs by PlayHQ
    routingCode (``playhq_id``). ``delay`` overrides the per-request pace (the
    background sweep passes a politer range than the interactive default)."""
    if not assoc_id:
        return {"error": "This association has no PlayHQ id on record; can't fetch its roster."}
    await register_association(session, assoc_id, assoc_name)
    seasons = await phq.association_seasons(assoc_id, delay=delay)
    # Prefer seasons that have ladders (skip not-yet-started ones), newest-first.
    usable = [s for s in seasons if s.get("status") != "UPCOMING"] or seasons
    usable = usable[:_MAX_RESOLVE_SEASONS]

    grade_ids: list[str] = []
    for s in usable:
        for gid in await phq.season_grade_ids(s["id"], delay=delay):
            grade_ids.append(gid)
    grade_ids = list(dict.fromkeys(grade_ids))[:_MAX_RESOLVE_GRADES]

    club_orgs: dict[str, str] = {}
    for gid in grade_ids:
        for org in await phq.grade_club_orgs(gid, delay=delay):
            club_orgs.setdefault(org["id"], org.get("name") or "")

    matched = linked = 0
    unmatched: list[str] = []
    for rc, cname in club_orgs.items():
        club = await session.scalar(
            select(MarketingClub).where(MarketingClub.playhq_id == rc))
        if club is None:
            unmatched.append(cname or rc)
            continue
        matched += 1
        club.last_crawled_at = func.now()   # so the status pill reflects sweep activity
        assocs = list(club.associations or [])
        already = any(a.get("id") == assoc_id
                      or (a.get("name") or "").lower() == assoc_name.lower() for a in assocs)
        if not already:
            assocs.append({"id": assoc_id, "name": assoc_name, "competition": ""})
            club.associations = assocs
            if not club.association_name:
                club.association_name = assoc_name
                club.association_guid = assoc_id
            club.updated_at = func.now()
            linked += 1
        # Linking via the sweep takes a club off the per-club enrichment queue, so
        # a contactless club (e.g. a school with only a generic mailbox) would
        # otherwise never get its org-level email. Fetch it here for any matched
        # club that still has no contact.
        if not club.contact_email:
            oc = await phq.discover_org_contact(rc, delay=delay)
            if oc and (oc.get("email") or oc.get("phone")):
                await _store_contact(session, club.id, None, "Club contact",
                                     _CLUB_CONTACT_RANK, oc.get("email"), oc.get("phone"),
                                     selected=True)
                if oc.get("email"):
                    club.contact_email = oc["email"].lower()
    # Stamp the registry so the sweep moves on (and refreshes only weekly).
    await session.execute(text(
        "UPDATE marketing_associations SET last_resolved_at = NOW(), club_count = :n, "
        "updated_at = NOW() WHERE id = :id"), {"n": matched, "id": assoc_id})
    await session.commit()
    result = {"association": assoc_name, "seasons_used": len(usable),
              "grades": len(grade_ids), "clubs_found": len(club_orgs),
              "matched": matched, "newly_linked": linked,
              "unmatched_count": len(unmatched), "unmatched": unmatched[:30]}
    logger.info("resolve_association_clubs: %s", result)
    return result


# Background association sweep: discover every association, then resolve each
# roster, refreshing weekly. Politer per-request pace than the interactive button.
_SWEEP_DELAY = (3.0, 8.0)
_SWEEP_STALE_DAYS = 7


async def discover_associations_registry(session: AsyncSession, max_pages: int = 50) -> dict:
    """Enumerate every Australian association via the search ASSOCIATION type and
    upsert them into the registry. Cheap (~8 pages); resilient to a transient page."""
    page, seen = 1, 0
    while page <= max_pages:
        results = None
        for _ in range(4):
            results, _tot = await phq.search_organisations("ASSOCIATION", "", page=page, limit=100)
            if results is not None:
                break
        if results is None:
            break
        if not results:
            break
        for org in results:
            if (org.get("tenant") or {}).get("name") != AU_TENANT:
                continue
            rc = org.get("routingCode")
            if rc:
                await register_association(session, rc, org.get("name") or "")
                seen += 1
        await session.commit()
        page += 1
    logger.info("discover_associations_registry: %d AU associations", seen)
    return {"associations_seen": seen}


async def sweep_association_rosters(session: AsyncSession, limit: int = 1,
                                    delay: tuple | None = None) -> dict:
    """Resolve the roster of up to ``limit`` associations that haven't been
    resolved (or are stale). High leverage — one resolve links a whole roster."""
    rows = (await session.execute(text(
        "SELECT id, name FROM marketing_associations "
        "WHERE last_resolved_at IS NULL "
        "   OR last_resolved_at < NOW() - make_interval(days => :d) "
        "ORDER BY last_resolved_at NULLS FIRST, name LIMIT :lim"),
        {"d": _SWEEP_STALE_DAYS, "lim": limit})).all()
    resolved = linked = 0
    for r in rows:
        res = await resolve_association_clubs(session, r[0], r[1], delay=delay)
        resolved += 1
        linked += res.get("newly_linked", 0)
    pending = await session.scalar(text(
        "SELECT COUNT(*) FROM marketing_associations "
        "WHERE last_resolved_at IS NULL "
        "   OR last_resolved_at < NOW() - make_interval(days => :d)"),
        {"d": _SWEEP_STALE_DAYS})
    return {"resolved": resolved, "newly_linked": linked, "pending": pending or 0}


# ─── Usage breadcrumbs → directory (visits via a club's UTM) ─────────────────
# An outreach email ties a later anonymous site visit back to the recipient club
# through FOUR routes, in priority order:
#   1. a manual alias (marketing_utm_aliases) mapping the raw value an operator
#      saw to a club — needed because a campaign's utm_source isn't always the
#      club's code (utm_source='executive' was Leederville);
#   2. the value equals the club's own utm_code, in utm_id or utm_source;
#   3. the visit LANDED ON the club's own page — its first path segment equals the
#      club's utm_code (e.g. /gosnells-cricket-club?utm_source=camsawatzky, where
#      the UTM is the rep's name, not the club). Works for EVERY club, not just the
#      one in any example: the path segment is matched against all clubs' codes.
#   4. likewise, an already-onboarded club visited at its real public slug
#      (organisations.slug, via marketing_clubs.existing_org_id) — covers clubs
#      whose public URL isn't the utm_code form.
# An exact code match (…-cricket-club) is safe — an organic utm_source like
# "facebook", or a route like /pricing, never equals one. Aliases with a NULL club
# are "ignored" (ad/referrer noise like 'meta') and never attribute. Counting
# distinct visitors falls back to ip_hash when there's no first-party visitor_id.
#
# Every visit-attribution query is built on this single resolution: each
# page_view gets a `cid` (the marketing_clubs.id it resolves to, or NULL). The
# first path segment is split_part(split_part(path,'?',1),'/',2) — the homepage
# yields '' and never matches a (non-empty) utm_code.
_PATH_CODE = "split_part(split_part(ue.path, '?', 1), '/', 2)"
# Resolve each page_view to ONE club id via correlated subqueries (each LIMIT 1),
# not LEFT JOINs — marketing_clubs.utm_code isn't unique (the default formula can
# collide), so a join could multiply the row and over-count visits. Subqueries
# pick a single club per route and COALESCE applies the priority order.
_RESOLVED_VISITS = (
    "SELECT COALESCE("
    "  (SELECT a.marketing_club_id FROM marketing_utm_aliases a "
    "     WHERE a.utm_value = ue.utm_id AND a.marketing_club_id IS NOT NULL LIMIT 1), "
    "  (SELECT a.marketing_club_id FROM marketing_utm_aliases a "
    "     WHERE a.utm_value = ue.utm_source AND a.marketing_club_id IS NOT NULL LIMIT 1), "
    f"  (SELECT a.marketing_club_id FROM marketing_utm_aliases a "
    f"     WHERE a.utm_value = {_PATH_CODE} AND a.marketing_club_id IS NOT NULL LIMIT 1), "
    "  (SELECT mc.id FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_id LIMIT 1), "
    "  (SELECT mc.id FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_source LIMIT 1), "
    f"  (SELECT mc.id FROM marketing_clubs mc WHERE mc.utm_code = {_PATH_CODE} "
    f"     AND {_PATH_CODE} <> '' LIMIT 1), "
    f"  (SELECT mc.id FROM marketing_clubs mc JOIN organisations o ON o.id = mc.existing_org_id "
    f"     WHERE o.slug = {_PATH_CODE} AND {_PATH_CODE} <> '' LIMIT 1)"
    ")::text AS cid, "
    "COALESCE(ue.visitor_id::text, ue.ip_hash) AS vk, "
    "ue.created_at, ue.path, ue.traffic_source, ue.country, ue.city "
    "FROM usage_events ue WHERE ue.event_type = 'page_view' "
    # A stale UTM captured once in a browser tab (see visitor.js getLinkCode())
    # keeps riding along on every later page view from that tab, including a
    # staff member's own authenticated admin browsing — which would otherwise
    # get misattributed to a prospect club as "visits"/"pages viewed" and
    # corrupt the engagement score built on this same CTE (twenty_sync.py
    # _engagement). Same guard usage.py's campaigns()/live() already use to
    # keep staff activity out of visitor numbers.
    "AND ue.user_id IS NULL "
    "AND split_part(ue.path, '?', 1) !~* '^/admin'"
)

# Single-pass form for the directory "visited" filter + the dashboard count.
# Resolve every page_view to ONE club (the same single-attribution priority the
# visit stats use), then keep clubs that are some visit's resolved club. This is a
# set membership test evaluated ONCE for the whole query, replacing a correlated
# EXISTS that re-scanned usage_events for every candidate club (and that used the
# broader any-overlap attribution, so a single visit could mark several colliding
# clubs visited — out of step with the per-club stats). ``{mc}`` is the outer
# table/alias. The resolution probes are all indexed: marketing_clubs(utm_code),
# marketing_utm_aliases(utm_value) UNIQUE, organisations(slug).
def _visited_in_sql(mc: str = "marketing_clubs") -> str:
    return f"{mc}.id::text IN (SELECT v.cid FROM ({_RESOLVED_VISITS}) v WHERE v.cid IS NOT NULL)"


# ─── Login-intent (visited a club's pages, then went to /login) ─────────────
# /login itself never resolves to a club through _RESOLVED_VISITS — it's a
# single global route, not a club slug or UTM code — so a visitor hitting it
# is otherwise invisible to the directory. But the SAME visitor's OTHER
# page-views in the same browsing session usually do resolve (they landed on
# or browsed the club's public page first). Chaining the two is the strongest
# "wants an account" signal we hold, especially for a club with no
# existing_org_id: there's nothing of theirs to log into yet, so repeat
# /login visits from that visitor read as onboarding interest, not a member
# who forgot their password.
_LOGIN_HITS_CTE = (
    f"WITH resolved AS ({_RESOLVED_VISITS}), "
    "logins AS ("
    "  SELECT vk, created_at, country, city FROM resolved "
    "  WHERE split_part(path, '?', 1) = '/login'"
    "), "
    "visitor_club AS ("
    "  SELECT DISTINCT ON (vk) vk, cid FROM resolved "
    "  WHERE cid IS NOT NULL AND split_part(path, '?', 1) <> '/login' "
    "  ORDER BY vk, created_at DESC"
    "), "
    "login_hits AS ("
    "  SELECT l.created_at, l.country, l.city, l.vk, vc.cid "
    "  FROM logins l JOIN visitor_club vc ON vc.vk = l.vk"
    ") "
)


async def club_login_intent_stats(session: AsyncSession, club_ids: list) -> dict:
    """Visitors who hit /login after browsing a club's own pages, keyed by club
    id — same ``{club_id: {visitors, last_seen}}`` shape as club_visit_stats,
    so the directory can merge it in alongside the 'visited' badge."""
    ids = sorted({str(c) for c in (club_ids or []) if c})
    if not ids:
        return {}
    rows = (await session.execute(text(
        _LOGIN_HITS_CTE
        + "SELECT cid, COUNT(DISTINCT vk) AS visitors, MAX(created_at) AS last_seen "
          "FROM login_hits WHERE cid = ANY(:ids) GROUP BY cid"
    ), {"ids": ids})).all()
    return {
        r.cid: {
            "visitors": int(r.visitors or 0),
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        }
        for r in rows
    }


async def club_login_intent_detail(session: AsyncSession, club_id, limit: int = 50) -> dict:
    """Trail of /login hits attributed to one club's visitors. Powers the
    directory's expanded-row panel, mirroring club_visit_detail."""
    cid = str(club_id or "").strip()
    empty = {"club_id": cid, "hits": 0, "visitors": 0,
              "first_seen": None, "last_seen": None, "recent": []}
    if not cid:
        return empty
    summary = (await session.execute(text(
        _LOGIN_HITS_CTE
        + "SELECT COUNT(*) AS hits, COUNT(DISTINCT vk) AS visitors, "
          "MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
          "FROM login_hits WHERE cid = :cid"
    ), {"cid": cid})).one()
    if not summary.hits:
        return empty
    recent = (await session.execute(text(
        _LOGIN_HITS_CTE
        + "SELECT created_at, country, city FROM login_hits "
          "WHERE cid = :cid ORDER BY created_at DESC LIMIT :lim"
    ), {"cid": cid, "lim": max(1, min(int(limit or 50), 200))})).all()
    return {
        "club_id": cid,
        "hits": int(summary.hits or 0),
        "visitors": int(summary.visitors or 0),
        "first_seen": summary.first_seen.isoformat() if summary.first_seen else None,
        "last_seen": summary.last_seen.isoformat() if summary.last_seen else None,
        "recent": [
            {"at": r.created_at.isoformat() if r.created_at else None,
             "country": r.country, "city": r.city}
            for r in recent
        ],
    }


async def club_visit_stats(session: AsyncSession, club_ids: list) -> dict:
    """Summarise site visits for a page of clubs in ONE query, keyed by club id.
    Returns ``{club_id: {views, visitors, last_seen}}`` for clubs with any visit,
    so the directory list can show a 'visited' badge without an N+1."""
    ids = sorted({str(c) for c in (club_ids or []) if c})
    if not ids:
        return {}
    rows = (await session.execute(text(
        "SELECT v.cid AS cid, COUNT(*) AS views, COUNT(DISTINCT v.vk) AS visitors, "
        "       MAX(v.created_at) AS last_seen "
        f"FROM ({_RESOLVED_VISITS}) v "
        "WHERE v.cid = ANY(:ids) GROUP BY v.cid"), {"ids": ids})).all()
    return {
        r.cid: {
            "views": int(r.views or 0),
            "visitors": int(r.visitors or 0),
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        }
        for r in rows
    }


async def top_clubs_by_visits(session: AsyncSession, metric: str, n: int,
                              candidate_ids: Optional[list] = None) -> list:
    """Rank clubs by page views or distinct visitors (the same _RESOLVED_VISITS
    site-visit resolution club_visit_stats uses), returning the top ``n`` as
    ``[{"id", "views", "visitors"}, ...]`` in rank order — one GROUP BY pass,
    not a per-club query. ``candidate_ids`` restricts ranking to that set (e.g.
    "top N of what's currently filtered" — pass the id list the other active
    filters already produced); pass None (not ``[]``) to rank the whole
    directory. An empty ``candidate_ids`` list correctly ranks nothing."""
    metric_col = "COUNT(DISTINCT v.vk)" if metric == "visitors" else "COUNT(*)"
    if candidate_ids is not None:
        ids = sorted({str(c) for c in candidate_ids if c})
        if not ids:
            return []
        where, params = "WHERE v.cid = ANY(:ids) ", {"n": n, "ids": ids}
    else:
        where, params = "", {"n": n}
    rows = (await session.execute(text(
        "SELECT v.cid AS cid, COUNT(*) AS views, COUNT(DISTINCT v.vk) AS visitors "
        f"FROM ({_RESOLVED_VISITS}) v {where}"
        f"GROUP BY v.cid ORDER BY {metric_col} DESC LIMIT :n"), params)).all()
    return [{"id": r.cid, "views": int(r.views or 0), "visitors": int(r.visitors or 0)}
            for r in rows]


async def club_visit_detail(session: AsyncSession, club_id, limit: int = 50) -> dict:
    """Full breadcrumb trail for one club: overall totals, the pages they viewed
    (top first) and the most-recent visits. Resolves visits through the alias map
    the same way the list does. Powers the expanded-row 'visited the site' panel."""
    cid = str(club_id or "").strip()
    empty = {"club_id": cid, "views": 0, "visitors": 0,
             "first_seen": None, "last_seen": None, "pages": [], "recent": []}
    if not cid:
        return empty
    base = f"FROM ({_RESOLVED_VISITS}) v WHERE v.cid = :cid"
    summary = (await session.execute(text(
        "SELECT COUNT(*) AS views, COUNT(DISTINCT v.vk) AS visitors, "
        f"MIN(v.created_at) AS first_seen, MAX(v.created_at) AS last_seen {base}"),
        {"cid": cid})).one()
    if not summary.views:
        return empty
    pages = (await session.execute(text(
        "SELECT split_part(v.path, '?', 1) AS page, COUNT(*) AS views, "
        f"MAX(v.created_at) AS last_seen {base} "
        "GROUP BY 1 ORDER BY views DESC, last_seen DESC LIMIT 30"),
        {"cid": cid})).all()
    recent = (await session.execute(text(
        f"SELECT v.path, v.created_at, v.traffic_source, v.country, v.city {base} "
        "ORDER BY v.created_at DESC LIMIT :lim"),
        {"cid": cid, "lim": max(1, min(int(limit or 50), 200))})).all()
    return {
        "club_id": cid,
        "views": int(summary.views or 0),
        "visitors": int(summary.visitors or 0),
        "first_seen": summary.first_seen.isoformat() if summary.first_seen else None,
        "last_seen": summary.last_seen.isoformat() if summary.last_seen else None,
        "pages": [{"page": p.page, "views": int(p.views or 0),
                   "last_seen": p.last_seen.isoformat() if p.last_seen else None}
                  for p in pages],
        "recent": [{"path": r.path,
                    "at": r.created_at.isoformat() if r.created_at else None,
                    "source": r.traffic_source,
                    "country": r.country, "city": r.city}
                   for r in recent],
    }


async def list_utm_values(session: AsyncSession) -> list:
    """Every value a visit can be attributed by — utm_source, utm_id, or a
    club-looking page slug it landed on — with its view count, where it appeared
    (``sources``) and how it currently resolves: 'auto' (equals a club's utm_code
    or an onboarded club's public slug), 'mapped' (a manual alias → club),
    'ignored' (alias marked not-a-club) or 'unmatched'. Drives the manual
    UTM-matching panel, so a slug like 'willetton-cricket-club' that matches no
    club can be mapped to the right one by hand."""
    seg = "split_part(split_part(ue.path, '?', 1), '/', 2)"
    # Staff-noise guard (see _RESOLVED_VISITS above) so a UTM's view count here
    # reflects genuine visitor traffic, not a staff member's own admin browsing
    # in a tab that once carried this value.
    staff_guard = "AND ue.user_id IS NULL AND split_part(ue.path, '?', 1) !~* '^/admin' "
    rows = (await session.execute(text(
        "SELECT val, source, SUM(n) AS views FROM ("
        "  SELECT ue.utm_source AS val, 'utm' AS source, COUNT(*) n FROM usage_events ue "
        "  WHERE ue.event_type='page_view' AND ue.utm_source IS NOT NULL "
        f"  AND ue.utm_source <> '' {staff_guard}GROUP BY 1 "
        "  UNION ALL "
        "  SELECT ue.utm_id AS val, 'utm' AS source, COUNT(*) n FROM usage_events ue "
        "  WHERE ue.event_type='page_view' AND ue.utm_id IS NOT NULL "
        f"  AND ue.utm_id <> '' {staff_guard}GROUP BY 1 "
        "  UNION ALL "
        f"  SELECT {seg} AS val, 'path' AS source, COUNT(*) n FROM usage_events ue "
        f"  WHERE ue.event_type='page_view' AND {seg} ~* 'cricket|club' {staff_guard}GROUP BY 1 "
        ") t GROUP BY val, source"))).all()
    # Collapse to one row per value, summing views and collecting the sources.
    by_val: dict = {}
    for r in rows:
        e = by_val.setdefault(r.val, {"views": 0, "sources": set()})
        e["views"] += int(r.views or 0)
        e["sources"].add(r.source)
    values = list(by_val.keys())
    if not values:
        return []
    aliases = {a.utm_value: a for a in (await session.execute(text(
        "SELECT a.utm_value, a.marketing_club_id::text AS club_id, mc.name AS club_name "
        "FROM marketing_utm_aliases a "
        "LEFT JOIN marketing_clubs mc ON mc.id = a.marketing_club_id "
        "WHERE a.utm_value = ANY(:vals)"), {"vals": values})).all()}
    # Auto matches: a value equals a club's utm_code OR an onboarded club's slug.
    direct = {d.utm_code: d for d in (await session.execute(
        select(MarketingClub.utm_code, MarketingClub.id, MarketingClub.name)
        .where(MarketingClub.utm_code.in_(values)))).all()}
    slugs = {s.slug: s for s in (await session.execute(text(
        "SELECT o.slug, mc.id, mc.name FROM marketing_clubs mc "
        "JOIN organisations o ON o.id = mc.existing_org_id "
        "WHERE o.slug = ANY(:vals)"), {"vals": values})).all()}
    out = []
    for val, e in by_val.items():
        a = aliases.get(val)
        auto = direct.get(val) or slugs.get(val)
        if a is not None and a.club_id:
            status, club = "mapped", {"id": a.club_id, "name": a.club_name}
        elif a is not None:
            status, club = "ignored", None
        elif auto is not None:
            status, club = "auto", {"id": str(auto.id), "name": auto.name}
        else:
            status, club = "unmatched", None
        out.append({"utm_value": val, "views": e["views"],
                    "sources": sorted(e["sources"]), "status": status, "club": club})
    out.sort(key=lambda x: x["views"], reverse=True)
    return out[:500]


async def set_utm_alias(session: AsyncSession, utm_value: str,
                        marketing_club_id: Optional[str], ignore: bool = False) -> Optional[dict]:
    """Map a raw UTM value to a club, mark it ignored (NULL club), or clear it.
    ``ignore`` wins; then a club id maps; with neither the alias is removed (the
    value falls back to its auto/unmatched state)."""
    val = (utm_value or "").strip()
    if not val:
        return None
    if not ignore and not marketing_club_id:
        await session.execute(text("DELETE FROM marketing_utm_aliases WHERE utm_value = :v"),
                              {"v": val})
        await session.commit()
        return {"utm_value": val, "status": "unmatched", "club": None}
    club_id = None
    club_name = None
    if not ignore and marketing_club_id:
        try:
            club = await session.get(MarketingClub, uuid.UUID(str(marketing_club_id)))
        except (ValueError, AttributeError):
            club = None
        if club is None:
            return None
        club_id, club_name = str(club.id), club.name
    await session.execute(text(
        "INSERT INTO marketing_utm_aliases (utm_value, marketing_club_id) "
        "VALUES (:v, CAST(:c AS uuid)) "
        "ON CONFLICT (utm_value) DO UPDATE SET marketing_club_id = CAST(:c AS uuid), "
        "updated_at = NOW()"), {"v": val, "c": club_id})
    await session.commit()
    return {"utm_value": val, "status": "ignored" if ignore else "mapped",
            "club": ({"id": club_id, "name": club_name} if club_id else None)}


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
    selected = await session.scalar(select(func.count(MarketingClubContact.id))
        .where(MarketingClubContact.outreach_selected.is_(True),
               MarketingClubContact.email.isnot(None))) or 0
    customers = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.existing_org_id.isnot(None))) or 0
    emailed = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.emailed_at.isnot(None))) or 0
    visited = await session.scalar(text(
        f"SELECT COUNT(DISTINCT v.cid) FROM ({_RESOLVED_VISITS}) v WHERE v.cid IS NOT NULL")) or 0
    login_intent = await session.scalar(text(
        _LOGIN_HITS_CTE + "SELECT COUNT(DISTINCT cid) FROM login_hits")) or 0
    login_intent_not_customer = await session.scalar(text(
        _LOGIN_HITS_CTE
        + "SELECT COUNT(DISTINCT lh.cid) FROM login_hits lh "
          "JOIN marketing_clubs mc ON mc.id::text = lh.cid "
          "WHERE mc.existing_org_id IS NULL"
    )) or 0
    distinct_assoc = await session.scalar(
        select(func.count(func.distinct(MarketingClub.association_guid)))
        .where(MarketingClub.association_guid.isnot(None))) or 0
    assoc_known = await session.scalar(text("SELECT COUNT(*) FROM marketing_associations")) or 0
    assoc_resolved = await session.scalar(text(
        "SELECT COUNT(*) FROM marketing_associations WHERE last_resolved_at IS NOT NULL")) or 0
    return {
        "clubs": clubs,
        "contacts": contacts,
        "selected_contacts": selected,
        "clubs_with_email": with_email,
        "associations_fetched": assoc_fetched,
        "associations_pending": assoc_pending,
        "distinct_associations": distinct_assoc,
        "associations_registry": assoc_known,
        "associations_resolved": assoc_resolved,
        "already_customers": customers,
        "emailed": emailed,
        "visited": visited,
        "login_intent": login_intent,
        "login_intent_not_customer": login_intent_not_customer,
        # Back-compat keys the dashboard/CLI may still read.
        "total": clubs,
        "frontier_remaining": assoc_pending,
    }
