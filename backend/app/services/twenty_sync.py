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

from app.models.db import (MarketingClub, MarketingClubContact, Organisation,
                           async_session_maker)
from app.services.club_directory import club_filters
from app.services.twenty_client import client, currency, full_name, link, phone

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
    # Must be one of the Company lifecycleStage options (Target / Prospect /
    # Engaged / Trial / Customer / Churned / Suppressed). "Contacted" is an
    # Opportunity pipeline stage, NOT a company lifecycle value, so a contacted
    # club maps to Prospect here.
    s = (club.status or "").lower()
    if club.existing_org_id or s == "onboarded" or (club.demo_status or "") == "customer":
        return "CUSTOMER"
    if (club.demo_status or "") == "in_trial":
        return "TRIAL"
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
# priced-module count. BetterAdmin is the fees+comms+merch umbrella.
def _arr(module_overrides) -> float:
    keys = {str(k).lower() for k in (module_overrides or [])}
    total, priced = 399.0, 0
    if "select" in keys:
        total += 149; priced += 1
    if "socials" in keys:
        total += 149; priced += 1
    if keys & {"fees", "comms", "merch"}:
        total += 149; priced += 1          # BetterAdmin umbrella, charged once
    if "iq" in keys:
        total += 249; priced += 1
    return total - {0: 0, 1: 0, 2: 48, 3: 97, 4: 146}.get(priced, 146)


def _company_values(club: MarketingClub, org: "Optional[Organisation]" = None) -> dict:
    # Association membership is a separate many-to-many via the clubAssociation
    # junction (see _sync_memberships); the company carries only a denormalised
    # primary-association name for quick display. Customer-side fields (paid
    # modules, subscription, renewal, billing, ARR) come from the linked
    # Organisation when the club is already onboarded.
    vals = {
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
        "existingKpCustomer": "YES" if club.existing_org_id else "NO",
        "lastSyncedAt": _now_iso(),
    }
    if org is not None:
        vals["subscriptionStatus"] = (org.subscription_status or "").upper() or None
        vals["paidModules"] = _modules(org.module_overrides)
        vals["arr"] = currency(_arr(org.module_overrides))
        if org.billing_cycle:
            vals["billingCycle"] = org.billing_cycle.upper()
        if org.renewal_date:
            vals["renewalDate"] = org.renewal_date.isoformat() + "T00:00:00Z"
    return _clean(vals)


def _person_values(ct: MarketingClubContact, company_twenty_id: Optional[str],
                   club_country: Optional[str] = None) -> dict:
    vals = {
        "name": full_name(ct.full_name),
        "bcContactId": str(ct.id),
        "clubRole": _role(ct.role),
        "roleRank": ct.role_rank,
        "subscribed": bool(ct.subscribed),
        "bounced": bool(ct.bounced),
        "outreachSelected": bool(ct.outreach_selected),
        "namedEmail": bool(ct.full_name and ct.email),
        "country": club_country,        # an officer inherits their club's country
        "companyId": company_twenty_id,
    }
    if ct.email:
        vals["emails"] = {"primaryEmail": ct.email}
    if ct.mobile:
        vals["phones"] = phone(ct.mobile)
    if ct.role:
        vals["jobTitle"] = ct.role          # the raw role into Twenty's standard Job title
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


async def _upsert(session, http, entity_type, bc_id, plural, ext_field, values,
                  create_extra=None):
    """Create-or-update a Twenty record, keyed on the local link table first, then
    the external-key field as a dedupe fallback. ``create_extra`` is merged only on
    creation (not on update), so fields an operator may edit in Twenty (e.g. a
    membership's isPrimary) are set once and never overwritten. The content hash is
    computed on ``values`` only, so create_extra never forces an update. Returns
    (twenty_id, action)."""
    h = _hash(values)
    link_row = await _link_get(session, entity_type, bc_id)
    if link_row:
        tid, old_hash = link_row
        if old_hash == h:
            return tid, "unchanged"
        updated = await client.update(http, plural, tid, values)
        if updated is not None:
            await _link_put(session, entity_type, bc_id, tid, h)
            return tid, "updated"
        # stale link: the record was deleted in Twenty — fall through to recreate.
    existing = await client.find_by(http, plural, ext_field, bc_id) if ext_field else None
    if existing and existing.get("id"):
        tid = existing["id"]
        if await client.update(http, plural, tid, values) is not None:
            await _link_put(session, entity_type, bc_id, tid, h)
            return tid, "adopted"
    rec = await client.create(http, plural, {**values, **(create_extra or {})})
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
                org = (await session.get(Organisation, club.existing_org_id)
                       if club.existing_org_id else None)
                cq = select(MarketingClubContact).where(
                    MarketingClubContact.marketing_club_id == club.id)
                if selected_only:
                    cq = cq.where(MarketingClubContact.outreach_selected.is_(True))
                contacts = (await session.execute(cq)).scalars().all()
                snapshots.append({
                    "guid": club.grassroots_guid,
                    "name": club.name,
                    "company": _company_values(club, org),
                    "assocs": _club_assocs(club),
                    "people": [(str(ct.id), _person_values(ct, None, club.country))
                               for ct in _scoped(contacts, contact_scope)],
                })

            assoc_cache: dict = {}
            async with httpx.AsyncClient() as http:
                for snap in snapshots:
                    try:
                        ctid, cact = await _upsert(session, http, "club", snap["guid"],
                                                   "companies", "bcClubId", snap["company"])
                        stats["clubs_" + cact] += 1
                        await _sync_memberships(session, http, snap["guid"], snap["name"],
                                                snap["assocs"], ctid, assoc_cache, stats)
                        for bc_id, pvals in snap["people"]:
                            _, pact = await _upsert(session, http, "person", bc_id, "people",
                                                    "bcContactId", {**pvals, "companyId": ctid})
                            stats["people_" + pact] += 1
                        await session.commit()
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
