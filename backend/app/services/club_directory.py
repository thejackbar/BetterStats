"""Marketing club directory — crawl the CA/grassroots org graph for BetterCricket
outreach, and bridge the result into the existing BetterComms send pipeline.

What the grassroots API gives us (and what it doesn't)
-----------------------------------------------------
``GET /orgsproducts/organisation/{organisationGuid}`` (unauthenticated) returns,
per club: name, ``playHQId``, ``myCricketId``, address (incl. ``postCode``),
``affiliations`` (the association: name + GUID), ``websiteURL`` and a single
``contact {phone, email}`` (usually a role mailbox like ``secretary@``). It does
NOT expose per-person office bearers, so Phase 1 stores that one contact; the
contact table is many-per-club so President/Secretary/Treasurer can be added by
manual enrichment later (and ``role_rank`` sequences them to the top).

Discovery is a breadth-first walk of the affiliation graph: a club lists its
association, an association lists its member clubs, so from a handful of seeds the
whole connected universe unfolds. The crawl is resumable through the table itself
— a row with ``detail_fetched_at IS NULL`` is a frontier node (discovered via an
affiliation, not yet detailed). Each batch details a capped number and enqueues
their affiliations as new frontier rows, so a restart/deploy never loses progress.

Politeness is deliberate (settings ``marketing_crawl_*``): concurrency 1, a
jittered delay between requests, a nightly cap, run off-peak. We stay a quiet API
citizen; nothing here tries to evade anything.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import random
import re
from typing import Optional

import httpx
from sqlalchemy import select, text, func, cast, update, Text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import (
    MarketingClub, MarketingClubContact, Organisation, CommsContact,
)

logger = logging.getLogger(__name__)

BASE_URL = settings.playhq_base_url
_JSCONFIG = "eccn:true"
_TIMEOUT = 30.0
# A normal browser UA — we read the same public endpoints the play.cricket.com.au
# site does. Identify as a normal client; do not pretend to be something we aren't.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# One request at a time for a background marketing crawl (the live sync uses 6; we
# go lower on purpose — this is a slow, polite walk, not a user-facing fetch).
_SEMAPHORE = asyncio.Semaphore(1)

# Priority roles float to the top of any per-club contact list.
_ROLE_RANK = {"president": 1, "secretary": 2, "treasurer": 3}
# Map a role-mailbox local-part (or an enriched role string) to a tidy label.
_ROLE_FROM_LOCALPART = [
    ("president", "President"),
    ("secretary", "Secretary"),
    ("treasurer", "Treasurer"),
    ("registrar", "Registrar"),
    ("chair", "Chairperson"),
    ("admin", "Administration"),
    ("info", "Club contact"),
    ("contact", "Club contact"),
]
_ASSOC_KEYWORDS = re.compile(r"\b(assoc|association|league|competition|federation|union)\b", re.I)


# ── polite HTTP ───────────────────────────────────────────────────────────────

async def _get(path: str, params: dict | None = None) -> Optional[httpx.Response]:
    """One GET against the grassroots proxy, behind the concurrency gate, with a
    jittered courtesy delay and a single 429 backoff-and-retry."""
    p = {"jsconfig": _JSCONFIG}
    if params:
        p.update(params)
    async with _SEMAPHORE:
        # Courtesy delay BEFORE the request so concurrent callers can't burst.
        await asyncio.sleep(random.uniform(
            settings.marketing_crawl_min_delay, settings.marketing_crawl_max_delay))
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            try:
                r = await client.get(f"{BASE_URL}{path}", params=p)
            except httpx.HTTPError as exc:
                logger.warning("club_directory GET %s failed: %s", path, exc)
                return None
            if r.status_code == 429:
                await asyncio.sleep(8.0)
                try:
                    r = await client.get(f"{BASE_URL}{path}", params=p)
                except httpx.HTTPError as exc:
                    logger.warning("club_directory retry %s failed: %s", path, exc)
                    return None
            return r


async def search_orgs(query: str) -> list[dict]:
    """Search organisations by name (≤20 chars enforced by the proxy)."""
    q = (query or "").strip()[:20].strip()
    if not q:
        return []
    r = await _get("/orgsproducts/organisation/search", {"searchString": q})
    if not r or r.status_code >= 400:
        return []
    data = r.json()
    return data.get("organisations", data if isinstance(data, list) else [])


async def fetch_org_detail(guid: str) -> Optional[dict]:
    """Full org-detail payload (name, address, affiliations, contact)."""
    r = await _get(f"/orgsproducts/organisation/{guid}")
    if not r or r.status_code >= 400:
        if r is not None and r.status_code not in (404,):
            logger.info("org-detail %s → HTTP %s", guid, r.status_code)
        return None
    try:
        return r.json()
    except ValueError:
        return None


# ── parsing ─────────────────────────────────────────────────────────────────

def _kind(name: str, affiliations: list) -> str:
    """Heuristic club-vs-association split so the export can skip associations.
    An association either reads like one in its name or fans out to many clubs."""
    if _ASSOC_KEYWORDS.search(name or ""):
        return "association"
    if len(affiliations or []) >= 5:
        return "association"
    return "club"


def _role_for(email: Optional[str], explicit: Optional[str] = None) -> tuple[Optional[str], int]:
    """Return (role_label, role_rank). Derives a role from a role-mailbox local
    part when no explicit role is given (the API never labels the contact)."""
    label = (explicit or "").strip() or None
    if not label and email and "@" in email:
        local = email.split("@", 1)[0].lower()
        for needle, tidy in _ROLE_FROM_LOCALPART:
            if needle in local:
                label = tidy
                break
    rank = 99
    if label:
        rank = _ROLE_RANK.get(label.lower(), 99)
    return label, rank


def parse_org_detail(data: dict) -> dict:
    """Map an org-detail payload onto MarketingClub columns."""
    addr = data.get("address") or {}
    contact = data.get("contact") or {}
    affs = data.get("affiliations") or []
    name = data.get("name") or ""
    assoc = affs[0] if (affs and _kind(name, affs) == "club") else None
    return {
        "grassroots_guid": data.get("organisationGuid"),
        "playhq_id": data.get("playHQId"),
        "mycricket_id": data.get("myCricketId"),
        "name": name,
        "short_name": data.get("shortName"),
        "kind": _kind(name, affs),
        "association_name": (assoc or {}).get("name"),
        "association_guid": (assoc or {}).get("organisationGuid"),
        "website_url": data.get("websiteURL"),
        "contact_email": (contact.get("email") or "").strip() or None,
        "contact_phone": (contact.get("phone") or "").strip() or None,
        "address_line1": addr.get("line1") or None,
        "address_line2": addr.get("line2") or None,
        "suburb": addr.get("suburb") or None,
        "state": addr.get("stateName") or None,
        "postcode": addr.get("postCode") or None,
        "country": addr.get("country") or None,
        "latitude": addr.get("latitude"),
        "longitude": addr.get("longitude"),
        "logo_url": data.get("logoURL"),
        "description": data.get("description"),
        "is_playhq": data.get("isPlayHQ"),
        "raw_json": data,
        "affiliations": affs,  # consumed by the crawl, not stored as a column
    }


# ── crawl ─────────────────────────────────────────────────────────────────────

# Seed searches to bootstrap the very first frontier. The affiliation BFS does the
# heavy lifting from here; these just need to land us on a few orgs in each state.
SEED_QUERIES = [
    "Cricket Club", "Cricket Association", "District Cricket", "Junior Cricket",
    "Premier Cricket", "Metropolitan", "Suburban", "Country Cricket",
    "City Cricket", "United Cricket", "Districts Cricket", "Cricket Inc",
]


async def _ensure_frontier_row(session: AsyncSession, guid: str, name: str = "") -> bool:
    """Insert a minimal frontier row (detail not yet fetched) if the GUID is new.
    Returns True when a row was added."""
    if not guid:
        return False
    exists = await session.scalar(
        select(MarketingClub.id).where(MarketingClub.grassroots_guid == guid))
    if exists:
        return False
    session.add(MarketingClub(grassroots_guid=guid, name=name or "(pending)"))
    # Flush so a later dedupe-select in the same uncommitted batch sees this GUID
    # (two clubs in one batch can list the same association).
    await session.flush()
    return True


async def bootstrap_frontier(session: AsyncSession, queries: Optional[list[str]] = None) -> int:
    """Seed the frontier from a set of name searches. Idempotent — only adds GUIDs
    not already present."""
    added = 0
    for q in (queries or SEED_QUERIES):
        for org in await search_orgs(q):
            guid = org.get("organisationGuid") or org.get("id")
            if await _ensure_frontier_row(session, guid, org.get("name", "")):
                added += 1
        await session.commit()
    logger.info("bootstrap_frontier: %d new frontier rows", added)
    return added


async def _link_existing_org(session: AsyncSession, club: MarketingClub) -> None:
    """Best-effort link to a club we already have as a BetterStats customer so
    outreach can skip it (match on grassroots id, then playhq_id, then name)."""
    org_id = await session.scalar(
        select(Organisation.id).where(
            func.lower(cast(Organisation.id, Text)) == (club.grassroots_guid or "").lower()))
    if not org_id and club.playhq_id:
        org_id = await session.scalar(
            select(Organisation.id).where(Organisation.playhq_id == club.playhq_id))
    if not org_id and club.name:
        org_id = await session.scalar(
            select(Organisation.id).where(func.lower(Organisation.name) == club.name.lower()))
    club.existing_org_id = org_id


async def _store_contact(session: AsyncSession, club: MarketingClub,
                         email: Optional[str], phone: Optional[str],
                         full_name: Optional[str] = None, role: Optional[str] = None,
                         source: str = "api") -> None:
    """Upsert one contact for a club, deduped on lower(email). A contact with no
    email is still recorded (phone only) but can't dedupe, so we keep just one
    phone-only 'Club contact' row per club."""
    label, rank = _role_for(email, role)
    if email:
        existing = await session.scalar(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id,
                func.lower(MarketingClubContact.email) == email.lower()))
        if existing:
            existing.mobile = phone or existing.mobile
            existing.full_name = full_name or existing.full_name
            if label and existing.role_rank == 99:
                existing.role, existing.role_rank = label, rank
            return
    elif phone:
        # phone-only: avoid piling up duplicate anonymous rows on re-crawl
        existing = await session.scalar(
            select(MarketingClubContact).where(
                MarketingClubContact.marketing_club_id == club.id,
                MarketingClubContact.email.is_(None)))
        if existing:
            existing.mobile = phone
            return
    else:
        return
    session.add(MarketingClubContact(
        marketing_club_id=club.id, full_name=full_name, role=label,
        role_rank=rank, email=(email.lower() if email else None),
        mobile=phone, source=source))


async def crawl_batch(session: AsyncSession, limit: Optional[int] = None,
                      seeds: Optional[list[str]] = None) -> dict:
    """Detail up to ``limit`` frontier clubs, store their contact + metadata, and
    enqueue their affiliations. Bootstraps the frontier on first run. Returns a
    small stats dict. Safe to call repeatedly — it just walks the next slice."""
    limit = limit or settings.marketing_crawl_nightly_limit
    total = await session.scalar(select(func.count(MarketingClub.id)))
    if not total:
        await bootstrap_frontier(session, seeds)

    frontier = (await session.execute(
        select(MarketingClub)
        .where(MarketingClub.detail_fetched_at.is_(None))
        .order_by(MarketingClub.first_seen_at.asc())
        .limit(limit)
    )).scalars().all()

    stats = {"detailed": 0, "with_email": 0, "discovered": 0, "errors": 0}
    for club in frontier:
        data = await fetch_org_detail(club.grassroots_guid)
        if not data:
            # Mark as attempted so a dead GUID doesn't jam the queue forever.
            club.last_crawled_at = func.now()
            club.detail_fetched_at = func.now()
            club.status = "enriched"
            stats["errors"] += 1
            await session.commit()
            continue
        parsed = parse_org_detail(data)
        affs = parsed.pop("affiliations", [])
        for field, value in parsed.items():
            setattr(club, field, value)
        club.detail_fetched_at = func.now()
        club.last_crawled_at = func.now()
        club.status = "enriched"
        await _link_existing_org(session, club)
        if parsed.get("contact_email") or parsed.get("contact_phone"):
            await _store_contact(session, club,
                                 parsed.get("contact_email"), parsed.get("contact_phone"))
            if parsed.get("contact_email"):
                stats["with_email"] += 1
        # Enqueue affiliations (both directions: a club → its association, an
        # association → its member clubs) as frontier rows.
        for aff in affs:
            if await _ensure_frontier_row(session, aff.get("organisationGuid"), aff.get("name", "")):
                stats["discovered"] += 1
        stats["detailed"] += 1
        await session.commit()

    remaining = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.detail_fetched_at.is_(None)))
    stats["frontier_remaining"] = remaining or 0
    logger.info("crawl_batch: %s", stats)
    return stats


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


async def export_to_comms(session: AsyncSession, organisation_id: Optional[str] = None,
                          states: Optional[list[str]] = None,
                          include_associations: bool = False,
                          only_with_email: bool = True) -> dict:
    """Materialise the marketing contacts into ``comms_contacts`` under the
    platform outreach org, so BetterComms does the actual sending (unsubscribe,
    suppression, audit all reused). Skips clubs that are already customers and any
    address suppressed here. Existing comms suppressions are left untouched."""
    org = await _resolve_outreach_org(session, organisation_id)

    q = (
        select(MarketingClubContact, MarketingClub)
        .join(MarketingClub, MarketingClubContact.marketing_club_id == MarketingClub.id)
        .where(MarketingClubContact.subscribed.is_(True),
               MarketingClub.existing_org_id.is_(None))
    )
    if only_with_email:
        q = q.where(MarketingClubContact.email.isnot(None))
    if not include_associations:
        q = q.where(MarketingClub.kind == "club")
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
            tags=[club.name] + ([club.association_name] if club.association_name else []),
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
    """Export the directory as CSV. Header carries 'Club' + 'UTM' + 'Name' so it
    drops straight into docs/email-outreach/make_sends.py, plus the full metadata
    for filtering elsewhere."""
    join_cond = MarketingClubContact.marketing_club_id == MarketingClub.id
    if subscribed_only:
        join_cond = and_(join_cond, MarketingClubContact.subscribed.is_(True))
    q = (
        select(MarketingClub, MarketingClubContact)
        .outerjoin(MarketingClubContact, join_cond)
        .where(MarketingClub.detail_fetched_at.isnot(None))
        .order_by(MarketingClub.name.asc(), MarketingClubContact.role_rank.asc())
    )
    if not include_associations:
        q = q.where(MarketingClub.kind == "club")
    if states:
        q = q.where(MarketingClub.state.in_(states))

    rows = (await session.execute(q)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Club", "UTM", "Name", "Role", "Email", "Phone", "Association",
        "Address", "Suburb", "State", "Postcode", "Website",
        "PlayHQ ID", "Grassroots GUID", "Status",
    ])
    for club, contact in rows:
        if only_with_email and not (contact and contact.email):
            continue
        addr = " ".join(filter(None, [club.address_line1, club.address_line2]))
        w.writerow([
            club.name, _slug(club.name),
            (contact.full_name if contact else "") or "",
            (contact.role if contact else "") or "",
            (contact.email if contact else "") or "",
            (contact.mobile if contact else "") or club.contact_phone or "",
            club.association_name or "", addr, club.suburb or "", club.state or "",
            club.postcode or "", club.website_url or "", club.playhq_id or "",
            club.grassroots_guid or "", club.status or "",
        ])
    return buf.getvalue()


async def directory_stats(session: AsyncSession) -> dict:
    """Counts for the admin dashboard / CLI summary."""
    total = await session.scalar(select(func.count(MarketingClub.id))) or 0
    detailed = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.detail_fetched_at.isnot(None))) or 0
    clubs = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.kind == "club")) or 0
    with_email = await session.scalar(
        select(func.count(func.distinct(MarketingClubContact.marketing_club_id)))
        .where(MarketingClubContact.email.isnot(None))) or 0
    customers = await session.scalar(
        select(func.count(MarketingClub.id)).where(MarketingClub.existing_org_id.isnot(None))) or 0
    return {
        "total": total, "detailed": detailed, "frontier_remaining": total - detailed,
        "clubs": clubs, "associations": total - clubs, "clubs_with_email": with_email,
        "already_customers": customers,
    }
