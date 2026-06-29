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
from app.services.twenty_client import (TwentyApiError, client, currency, emails_value,
                                        full_name, link, phone)

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


async def _engagement(session, club: MarketingClub) -> dict:
    """A small per-club engagement rollup from usage_events (the breadcrumbs),
    pushed onto the Company so the CRM can score/sort without holding raw events.
    A club's activity is matched by its outreach UTM code (prospects) OR its org id
    (customers/trials). Score 0-100 from recency + 30-day session frequency + a
    trial-interest nudge; tier Cold/Warm/Hot."""
    utm = club.utm_code
    org = str(club.existing_org_id) if club.existing_org_id else None
    # Cast the bound params to text explicitly: asyncpg can't infer a type for a
    # bare ":utm IS NOT NULL", so the parameters need a declared type.
    row = (await session.execute(text("""
        SELECT MAX(created_at) AS last_seen,
               COUNT(DISTINCT visitor_id)
                 FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS sessions_30d
        FROM usage_events
        WHERE (CAST(:utm AS text) IS NOT NULL AND utm_id = CAST(:utm AS text))
           OR (CAST(:org AS text) IS NOT NULL AND org_id::text = CAST(:org AS text))
    """), {"utm": utm, "org": org})).first()
    last_seen = row[0] if row else None
    sessions = (row[1] or 0) if row else 0

    score = 0
    if last_seen:
        days = (datetime.datetime.now(datetime.timezone.utc) - last_seen).days
        score += 40 if days <= 7 else 28 if days <= 30 else 14 if days <= 90 else 4
    score += min(sessions * 6, 36)
    if club.requested_trial_modules:
        score += 12
    score = min(score, 100)
    tier = "COLD" if score < 34 else "WARM" if score < 67 else "HOT"

    fields = {"engagementScore": score, "engagementTier": tier, "sessions30d": sessions}
    if last_seen:
        fields["lastSeenAt"] = last_seen.isoformat()
    return fields


def _company_values(club: MarketingClub, org: "Optional[Organisation]" = None) -> dict:
    # Association membership is a separate many-to-many via the clubAssociation
    # junction (see _sync_memberships), each membership carrying an isPrimary flag —
    # so the primary association is recoverable from the relations and the company
    # holds no denormalised association field. Customer-side fields (paid modules,
    # subscription, renewal, billing, ARR) come from the linked Organisation when
    # the club is already onboarded.
    vals = {
        "name": club.name,
        "bcClubId": club.grassroots_guid,
        "lifecycleStage": _lifecycle(club),
        "subscriptionStatus": _sub_status(club),
        "trialModules": _modules(club.trial_modules),
        "interestedModules": _modules(club.requested_trial_modules),
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


async def _prewarm_person_emails(session, http, force: bool = False) -> int:
    """ONE-TIME backfill of the email -> Person id map in twenty_links. The map is the
    permanent index used to adopt a shared officer (Twenty's own email filter doesn't
    reliably match an existing record on this version); it is maintained INCREMENTALLY
    on every person upsert, so the steady state costs nothing extra per export. This
    full scan only exists to seed contacts that already lived in Twenty before the map
    existed — so it runs once (guarded by a marker) and then never again, never on the
    hot path of routine exports. Best-effort. Returns how many entries were indexed.

    Pass ``force=True`` to re-seed (e.g. after bulk manual edits in Twenty)."""
    if not force and await _link_get(session, "_meta", "person_email_backfilled"):
        return 0
    cursor, seen = None, 0
    completed = False
    for _ in range(200):  # cap 200 pages * 60 = 12k people
        try:
            payload = await client.list_page(http, "people", limit=60, starting_after=cursor)
        except Exception:  # noqa: BLE001
            logger.exception("twenty prewarm: listing people failed; will retry next export")
            break
        data = payload.get("data") if isinstance(payload, dict) else None
        people = data.get("people") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not people:
            completed = True
            break
        for p in people:
            pid = p.get("id")
            email = ((p.get("emails") or {}).get("primaryEmail") or "").strip().lower()
            if pid and email:
                await _link_put(session, "person_email", email, pid, "")
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
    # Mark done only on a clean full pass, so a mid-scan failure retries next time
    # instead of leaving the map half-seeded forever.
    if completed:
        await _link_put(session, "_meta", "person_email_backfilled", "1", "")
    await session.commit()
    logger.info("twenty prewarm: indexed %d existing contact email(s)%s",
                seen, "" if completed else " (incomplete, will retry)")
    return seen


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
        updated = await client.update(http, plural, tid, values)
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
        if await client.update(http, plural, adopt_id, values) is not None:
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
                company = {**_company_values(club, org),
                           **(await _engagement(session, club))}
                people = [{
                    "bc_id": str(ct.id),
                    "person": _person_values(ct, club.country),
                    "create_extra": _person_create_extra(ct),
                    "role": _officer_role_values(ct, club.name),
                } for ct in _scoped(contacts, contact_scope)]
                snapshots.append({
                    "guid": club.grassroots_guid,
                    "name": club.name,
                    "company": company,
                    "assocs": _club_assocs(club),
                    "people": people,
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
                        logger.info("twenty export: club %r -> company %s id=%s (%d officers)",
                                    snap["name"], cact, ctid, len(snap["people"]))
                        await _sync_memberships(session, http, snap["guid"], snap["name"],
                                                snap["assocs"], ctid, assoc_cache, stats)
                        for off in snap["people"]:
                            bc_id = off["bc_id"]
                            try:
                                email = (off["person"].get("emails") or {}).get("primaryEmail")
                                dedup = ("emails.primaryEmail", email) if email else None
                                # Resolve a shared officer by email from OUR link table
                                # (Twenty's email filter is unreliable on this version),
                                # so the second club adopts the first club's Person rather
                                # than hitting the duplicate-email wall.
                                known = await _link_get(session, "person_email", email) if email else None
                                known_id = known[0] if known else None
                                # The Person is identity-only; its native company + first
                                # role are set once via create_extra so a shared officer is
                                # never stolen onto a later club.
                                pid, pact = await _upsert(session, http, "person", bc_id, "people",
                                                          "bcContactId", off["person"], dedup=dedup,
                                                          known_id=known_id,
                                                          create_extra={**off["create_extra"],
                                                                        "companyId": ctid})
                                stats["people_" + pact] += 1
                                # Remember email -> Person so later clubs (this run or a
                                # future one) can adopt without Twenty's email filter.
                                if email:
                                    await _link_put(session, "person_email", email, pid, "")
                                # The personClub membership is what makes this officer show
                                # under THIS club (with this club's role), shared or not.
                                _, ract = await _upsert(session, http, "officer_role", bc_id,
                                                        "personClubs", "bcContactId",
                                                        {**off["role"], "personId": pid,
                                                         "companyId": ctid})
                                stats["officer_roles_" + ract] += 1
                                logger.info("twenty export:   officer %s -> %s id=%s (role %s)",
                                            bc_id, pact, pid, ract)
                            except Exception:  # noqa: BLE001 - one bad officer must not drop the rest
                                stats["people_errored"] += 1
                                logger.exception("twenty export: officer %s failed", bc_id)
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
            clubs = {c.grassroots_guid: c for c in (await session.execute(
                select(MarketingClub).where(
                    MarketingClub.grassroots_guid.in_(guids)))).scalars().all()
            } if guids else {}
            # Snapshot the engagement fields per company before any IO.
            updates = []
            for guid in guids:
                club = clubs.get(guid)
                if club is None:
                    continue
                updates.append((tid_by_guid[guid], await _engagement(session, club)))

            async with httpx.AsyncClient() as http:
                for tid, fields in updates:
                    try:
                        await client.update(http, "companies", tid, fields)
                        stats["refreshed"] += 1
                    except Exception:  # noqa: BLE001 - one bad company can't stop the rest
                        stats["errored"] += 1
                        logger.exception("twenty refresh_engagement failed for %s", tid)
                    await asyncio.sleep(0.05)
    except Exception as e:  # noqa: BLE001
        logger.exception("twenty refresh_engagement top-level failure")
        return {"error": f"refresh failed: {e}", **stats}
    return {**stats}
