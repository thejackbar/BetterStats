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
from collections import defaultdict
from typing import Optional

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import MarketingClub, MarketingClubContact
from app.services.club_directory import club_filters
from app.services.twenty_client import client, currency, full_name, link

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


def _hash(values: dict) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def _clean(d: dict) -> dict:
    """Drop None (so we never clobber a Twenty field we have no value for); keep
    False / 0 / [] which are meaningful."""
    return {k: v for k, v in d.items() if v is not None}


def _modules(keys) -> list:
    return [str(k).upper() for k in (keys or []) if k]


def _club_kind(name: Optional[str]) -> str:
    n = (name or "").lower()
    if "carnival" in n:
        return "CARNIVAL"
    if "school" in n:
        return "SCHOOL"
    if "junior" in n:
        return "JUNIOR"
    return "CLUB"


def _lifecycle(club: MarketingClub) -> str:
    s = (club.status or "").lower()
    if club.existing_org_id or s == "onboarded" or (club.demo_status or "") == "customer":
        return "CUSTOMER"
    if s == "suppressed" or club.excluded:
        return "SUPPRESSED"
    if s == "contacted" or club.emailed_at:
        return "CONTACTED"
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


def _company_values(club: MarketingClub, assoc_twenty_id: Optional[str]) -> dict:
    return _clean({
        "name": club.name,
        "bcClubId": club.grassroots_guid,
        "lifecycleStage": _lifecycle(club),
        "subscriptionStatus": _sub_status(club),
        "trialModules": _modules(club.trial_modules),
        "interestedModules": _modules(club.requested_trial_modules),
        "primaryAssociation": club.association_name,
        "clubKind": _club_kind(club.name),
        "clubState": club.state,
        "country": club.country,
        "postcode": club.postcode,
        "utmCode": club.utm_code,
        "dataSource": "PLAYHQ",
        "publicProfileUrl": link(club.website_url),
        "primaryAssociationLinkId": assoc_twenty_id,
        "lastSyncedAt": _now_iso(),
    })


def _person_values(ct: MarketingClubContact, company_twenty_id: str) -> dict:
    vals = {
        "name": full_name(ct.full_name),
        "bcContactId": str(ct.id),
        "clubRole": _role(ct.role),
        "roleRank": ct.role_rank,
        "subscribed": bool(ct.subscribed),
        "bounced": bool(ct.bounced),
        "outreachSelected": bool(ct.outreach_selected),
        "namedEmail": bool(ct.full_name and ct.email),
        "companyId": company_twenty_id,
    }
    if ct.email:
        vals["emails"] = {"primaryEmail": ct.email}
    src = (ct.source or "").upper()
    if src in ("API", "WEBSITE", "MANUAL"):
        vals["contactSource"] = src
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


async def _upsert(session, http, entity_type, bc_id, plural, ext_field, values):
    """Create-or-update a Twenty record, keyed on the local link table first, then
    the external-key field as a dedupe fallback. Returns (twenty_id, action)."""
    h = _hash(values)
    link_row = await _link_get(session, entity_type, bc_id)
    if link_row:
        tid, old_hash = link_row
        if old_hash == h:
            return tid, "unchanged"
        await client.update(http, plural, tid, values)
        await _link_put(session, entity_type, bc_id, tid, h)
        return tid, "updated"
    existing = await client.find_by(http, plural, ext_field, bc_id) if ext_field else None
    if existing and existing.get("id"):
        tid = existing["id"]
        await client.update(http, plural, tid, values)
        await _link_put(session, entity_type, bc_id, tid, h)
        return tid, "adopted"
    rec = await client.create(http, plural, values)
    tid = rec["id"]
    await _link_put(session, entity_type, bc_id, tid, h)
    return tid, "created"


async def _ensure_assoc(session, http, club, cache, stats) -> Optional[str]:
    bc_id = club.association_guid or ("name:" + club.association_name)
    if bc_id in cache:
        return cache[bc_id]
    values = _clean({"name": club.association_name, "bcAssociationId": bc_id})
    try:
        tid, act = await _upsert(session, http, "association", bc_id,
                                 "associations", "bcAssociationId", values)
        stats["assoc_" + act] += 1
        cache[bc_id] = tid
        return tid
    except Exception as e:  # noqa: BLE001 - association is best-effort
        logger.warning("twenty assoc upsert failed for %s: %s", club.association_name, e)
        return None


async def export_to_twenty(session: AsyncSession, *, filters: Optional[dict] = None,
                           contact_scope: str = "all",
                           limit: Optional[int] = None) -> dict:
    """Push the filtered directory subset into Twenty. ``contact_scope`` is
    all | named | pst (which officers to include for each matched club)."""
    if not client.configured:
        return {"error": "Twenty is not configured. Set TWENTY_API_URL and "
                          "TWENTY_API_KEY in the server .env."}
    filters = filters or {}
    q = select(MarketingClub).where(
        MarketingClub.detail_fetched_at.isnot(None),
        MarketingClub.excluded.is_(False))
    for cond in club_filters(**filters):
        q = q.where(cond)
    q = q.order_by(MarketingClub.name)
    if limit:
        q = q.limit(limit)
    clubs = (await session.execute(q)).scalars().all()

    stats: dict = defaultdict(int)
    assoc_cache: dict = {}
    errors = 0
    async with httpx.AsyncClient() as http:
        for club in clubs:
            try:
                assoc_tid = (await _ensure_assoc(session, http, club, assoc_cache, stats)
                             if club.association_name else None)
                ctid, cact = await _upsert(session, http, "club", club.grassroots_guid,
                                           "companies", "bcClubId",
                                           _company_values(club, assoc_tid))
                stats["clubs_" + cact] += 1
                contacts = (await session.execute(select(MarketingClubContact).where(
                    MarketingClubContact.marketing_club_id == club.id))).scalars().all()
                for ct in _scoped(contacts, contact_scope):
                    _, pact = await _upsert(session, http, "person", str(ct.id),
                                            "people", "bcContactId",
                                            _person_values(ct, ctid))
                    stats["people_" + pact] += 1
                await session.commit()
            except Exception as e:  # noqa: BLE001 - one bad club must not abort the run
                errors += 1
                await session.rollback()
                logger.warning("twenty export failed for club %s: %s", club.name, e)
            await asyncio.sleep(0.05)  # stay polite under the 100 req/min cap

    return {"matched_clubs": len(clubs), "errors": errors, **stats}
