"""Clubs that searched for themselves or picked themselves in the registration
wizard, as one outreach list.

The Meta Ads page reports these as two separate tables — "Clubs selected in the
wizard" (they clicked into the wizard) and "Clubs searched in the wizard" (they
typed the name and got a result but never clicked). Both are the same kind of
warm prospect and both want the same follow-up, so this merges them into one
row per club and hangs the outreach machinery off it.

Three things happen here:

  1. **Merge** the two Meta Ads tables on their shared normalised-name key
     (``meta_ads.get_selected_clubs`` / ``get_searched_clubs`` already group on
     exactly that key, and both already drop the clubs a super admin flagged as
     test noise).
  2. **Match** each one to a Club Directory club, so we know who to email. The
     wizard's own beacon captures the club's real CA organisation guid, which is
     the same guid the PlayHQ crawler keys the directory on — so that is the
     first match, with a case-insensitive name match as the fallback for a row
     that predates the guid being captured.
  3. **Report** whether the club has been emailed since. Derived, never stored:
     a campaign carries its audience ``list_id``, a sent ``comms_recipients``
     row carries its contact, and a ``comms_contacts`` row exported from the
     directory carries its ``marketing_club_id``. Join those three and a club's
     whole send history falls out, so it self-corrects and there is no
     send-path hook to keep in step.

Creating a list follows the Club Directory's own export rules
(``club_directory.export_to_comms``) rather than inventing a second set: never
export an excluded club, never export a contact that has opted out, link every
new contact back to its directory club so ``{{club}}`` and the per-recipient
unsubscribe resolve, and stamp ``exported_at`` so the Directory's own badge
stays accurate.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, CommsList, CommsListMember, MarketingClub, MarketingClubContact,
    WizardClubList,
)
from app.services.marketing_org import get_outreach_org

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# What an un-named generic club mailbox (info@, secretary@, the crawler's own
# club-level contact_email) is greeted as. A club address is read by whoever is
# on the committee this year, so the merge variable has to address the group —
# leaving it blank produces "Hi ," and guessing a person's name would be a lie.
GENERIC_FIRST_NAME = "Committee Members"
ORIGIN_LABEL = "Wizard Clubs"


def norm_key(name: Optional[str]) -> str:
    """The wizard tables' own grouping key — see meta_ads.get_selected_clubs,
    which sets ``key`` to the stripped, lowercased club name."""
    return (name or "").strip().lower()


def norm_email(raw: Optional[str]) -> Optional[str]:
    e = (raw or "").strip().lower()
    return e if _EMAIL_RE.match(e) else None


def _first_name(full: Optional[str]) -> str:
    return (full or "").strip().split()[0] if (full or "").strip() else ""


def _iso(v):
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else v


def _later(a, b):
    """Max of two ISO strings, either of which may be None."""
    if a and b:
        return a if a >= b else b
    return a or b


def _earlier(a, b):
    """Min of two ISO strings, either of which may be None."""
    if a and b:
        return a if a <= b else b
    return a or b


# ── merge the two Meta Ads tables ────────────────────────────────────────────

async def merged_wizard_clubs(session: AsyncSession, days: int) -> list[dict]:
    """One row per club across the selected AND searched wizard tables, keyed on
    the normalised name both already group by. A club present in both is one
    row carrying both sets of facts."""
    from app.services import meta_ads

    selected = await meta_ads.get_selected_clubs(session, days)
    searched = await meta_ads.get_searched_clubs(session, days)

    rows: dict[str, dict] = {}

    def _row(key: str, name: str) -> dict:
        return rows.setdefault(key, {
            "key": key, "name": name, "org_id": None,
            "in_selected": False, "in_searched": False,
            "furthest_step": "", "visitors": 0, "searches": 0, "queries": [],
            "via_meta": False, "first_at": None, "last_at": None,
            # Set only by the searched side — a row we could not resolve to a
            # club is the raw query, with the best guess carried alongside.
            "is_query_row": False, "confidence": "", "guess_name": None,
        })

    for c in (selected.get("clubs") or []):
        r = _row(c.get("key") or norm_key(c.get("name")), (c.get("name") or "").strip())
        r["in_selected"] = True
        r["org_id"] = r["org_id"] or c.get("org_id")
        r["furthest_step"] = c.get("furthest_step") or r["furthest_step"]
        r["visitors"] = max(r["visitors"], int(c.get("visitors") or 0))
        r["via_meta"] = r["via_meta"] or bool(c.get("via_meta"))
        r["first_at"] = _earlier(r["first_at"], c.get("first_at"))
        r["last_at"] = _later(r["last_at"], c.get("last_at"))

    for c in (searched.get("clubs") or []):
        r = _row(c.get("key") or norm_key(c.get("name")), (c.get("name") or "").strip())
        r["in_searched"] = True
        r["org_id"] = r["org_id"] or c.get("org_id")
        r["visitors"] = max(r["visitors"], int(c.get("visitors") or 0))
        r["searches"] = max(r["searches"], int(c.get("searches") or 0))
        r["queries"] = r["queries"] or list(c.get("queries") or [])
        r["via_meta"] = r["via_meta"] or bool(c.get("via_meta"))
        # A search we could not pin to a club (see meta_ads._resolve_run) is a
        # QUERY, not a club — it must never be matched against the directory or
        # exported, so the flag travels with it. A club that also appears on the
        # selected side is a real club whatever the search made of it.
        if c.get("is_query_row") and not r["in_selected"]:
            r["is_query_row"] = True
            r["guess_name"] = c.get("guess_name")
        r["confidence"] = c.get("confidence") or r["confidence"]
        r["first_at"] = _earlier(r["first_at"], c.get("first_at"))
        r["last_at"] = _later(r["last_at"], c.get("last_at"))

    for r in rows.values():
        r["source"] = ("both" if r["in_selected"] and r["in_searched"]
                       else "selected" if r["in_selected"] else "searched")
    return list(rows.values())


# ── match a wizard club to its Club Directory row ────────────────────────────

async def _directory_matches(session: AsyncSession, rows: list[dict]) -> dict[str, MarketingClub]:
    """club_key -> the Club Directory club it is, matched on the wizard's own
    captured CA organisation guid first (the strongest signal — it is the same
    guid the PlayHQ crawler keys the directory on, so a club that spells itself
    two ways still lands on one row) and a case-insensitive name second."""
    # A query row is a search term nobody has resolved to a club, so matching
    # it by name would hand back whatever club happens to be spelled like the
    # fragment someone typed. Left unmatched on purpose.
    rows = [r for r in rows if not r.get("is_query_row")]
    guids = {(r.get("org_id") or "").strip() for r in rows if (r.get("org_id") or "").strip()}
    names = {r["key"] for r in rows if r["key"]}

    by_guid: dict[str, MarketingClub] = {}
    by_name: dict[str, MarketingClub] = {}
    if guids:
        for c in (await session.execute(
            select(MarketingClub).where(MarketingClub.grassroots_guid.in_(guids))
        )).scalars().all():
            by_guid[str(c.grassroots_guid)] = c
    if names:
        for c in (await session.execute(
            select(MarketingClub).where(func.lower(MarketingClub.name).in_(names))
        )).scalars().all():
            # First writer wins — two directory rows with the same name is a
            # merge decision for a person, not something to pick between here.
            by_name.setdefault((c.name or "").strip().lower(), c)

    out: dict[str, MarketingClub] = {}
    for r in rows:
        guid = (r.get("org_id") or "").strip()
        club = by_guid.get(guid) if guid else None
        if club is None:
            club = by_name.get(r["key"])
        if club is not None:
            out[r["key"]] = club
    return out


async def _contact_counts(session: AsyncSession, club_ids: list) -> dict:
    """marketing_club_id -> {contacts, emailable} where `emailable` is what a
    list export would actually add: a subscribed contact with a valid email,
    named or not."""
    if not club_ids:
        return {}
    rows = (await session.execute(
        select(MarketingClubContact.marketing_club_id,
               MarketingClubContact.full_name,
               MarketingClubContact.email,
               MarketingClubContact.subscribed)
        .where(MarketingClubContact.marketing_club_id.in_(club_ids))
    )).all()
    out: dict = {}
    seen_emails: dict = {}
    for club_id, full_name, email, subscribed in rows:
        d = out.setdefault(club_id, {"contacts": 0, "emailable": 0, "named": 0, "generic": 0})
        d["contacts"] += 1
        e = norm_email(email)
        if not e or not subscribed:
            continue
        if e in seen_emails.setdefault(club_id, set()):
            continue
        seen_emails[club_id].add(e)
        d["emailable"] += 1
        if (full_name or "").strip():
            d["named"] += 1
        else:
            d["generic"] += 1
    return out


# ── who has been emailed ─────────────────────────────────────────────────────

_EMAIL_HISTORY_SQL = """
    SELECT cc.marketing_club_id                                        AS club_id,
           camp.id::text                                               AS campaign_id,
           COALESCE(NULLIF(TRIM(camp.name), ''), NULLIF(TRIM(camp.subject), ''),
                    'Untitled email')                                  AS campaign_name,
           MAX(r.sent_at)                                              AS sent_at,
           COUNT(*)                                                    AS recipients
    FROM comms_recipients r
    JOIN comms_campaigns camp ON camp.id = r.campaign_id
    JOIN comms_contacts  cc   ON cc.id   = r.contact_id
    WHERE r.status = 'sent'
      AND cc.marketing_club_id IS NOT NULL
      AND camp.audience->>'list_id' IN (SELECT DISTINCT list_id::text FROM wizard_club_lists)
    GROUP BY 1, 2, 3
    ORDER BY MAX(r.sent_at) DESC
"""


async def _email_history(session: AsyncSession) -> dict:
    """marketing_club_id -> [{campaign_id, campaign_name, sent_at, recipients}],
    newest first.

    Derived from the send audit rather than stored: only campaigns whose
    audience was one of the lists THIS page created count, so an unrelated
    club-side send can never read as outreach, and correcting a send (or
    re-sending) needs nothing kept in step here. The list_id comparison is
    made as text on purpose — a campaign's audience JSON is free-form and a
    non-uuid value there would abort a ``::uuid`` cast for every row."""
    out: dict = {}
    for row in (await session.execute(text(_EMAIL_HISTORY_SQL))).mappings().all():
        out.setdefault(row["club_id"], []).append({
            "campaign_id": row["campaign_id"],
            "campaign_name": row["campaign_name"],
            "sent_at": _iso(row["sent_at"]),
            "recipients": int(row["recipients"] or 0),
        })
    return out


async def _exports_by_key(session: AsyncSession) -> dict:
    """club_key -> the lists it has been exported into, newest first. A list a
    super admin has since deleted still shows (``deleted: true``) — the export
    happened, and its campaigns still count towards the club's email history."""
    rows = (await session.execute(
        select(WizardClubList, CommsList.id.label("live_id"))
        .outerjoin(CommsList, CommsList.id == WizardClubList.list_id)
        .order_by(WizardClubList.created_at.desc())
    )).all()
    out: dict = {}
    for w, live_id in rows:
        out.setdefault(w.club_key, []).append({
            "list_id": str(w.list_id),
            "list_name": w.list_name or "",
            "contacts_added": int(w.contacts_added or 0),
            "created_at": _iso(w.created_at),
            "deleted": live_id is None,
        })
    return out


# ── the page payload ─────────────────────────────────────────────────────────

async def list_wizard_clubs(session: AsyncSession, days: int) -> dict:
    """Every club that searched for or selected itself in the wizard, matched to
    the Club Directory, with its contact count and its send history."""
    rows = await merged_wizard_clubs(session, days)
    matches = await _directory_matches(session, rows)
    counts = await _contact_counts(session, [c.id for c in matches.values()])
    history = await _email_history(session)
    exports = await _exports_by_key(session)

    out: list[dict] = []
    for r in rows:
        club = matches.get(r["key"])
        cnt = counts.get(club.id, {}) if club is not None else {}
        emails = history.get(club.id, []) if club is not None else []
        # A club exported before it could be matched to the directory still has
        # its own export rows, so the list history is keyed on the wizard key.
        lists = exports.get(r["key"], [])
        out.append({
            **r,
            "directory": None if club is None else {
                "id": str(club.id),
                "name": club.name,
                "state": club.state or "",
                "association": club.association_name or "",
                "excluded": bool(club.excluded),
                "is_customer": club.existing_org_id is not None,
            },
            "contact_count": int(cnt.get("contacts") or 0),
            "emailable_count": int(cnt.get("emailable") or 0),
            "named_count": int(cnt.get("named") or 0),
            "generic_count": int(cnt.get("generic") or 0),
            "lists": lists,
            "emails": emails,
            "emailed": bool(emails),
            "last_emailed_at": emails[0]["sent_at"] if emails else None,
            "last_campaign_name": emails[0]["campaign_name"] if emails else None,
        })

    out.sort(key=lambda c: (c["last_at"] or ""), reverse=True)
    return {
        "clubs": out,
        "total_clubs": len(out),
        "total_contacts": sum(c["contact_count"] for c in out),
        "total_emailable": sum(c["emailable_count"] for c in out),
        "matched_clubs": sum(1 for c in out if c["directory"]),
        "emailed_clubs": sum(1 for c in out if c["emailed"]),
    }


# ── create a list from a filtered set ────────────────────────────────────────

async def _unique_list_name(session: AsyncSession, org_id, base: str) -> str:
    base = (base or "").strip() or "Wizard clubs"
    existing = set((await session.execute(
        select(CommsList.name).where(CommsList.organisation_id == org_id))).scalars().all())
    if base not in existing:
        return base
    for n in range(2, 1000):
        cand = f"{base} ({n})"
        if cand not in existing:
            return cand
    return f"{base} ({uuid.uuid4().hex[:6]})"


def _club_recipients(club: MarketingClub, contacts: list[MarketingClubContact]) -> list[dict]:
    """Every emailable address the directory holds for one club, deduped.

    A contact with a name is greeted by it; an un-named generic mailbox (and
    the club's own crawled ``contact_email``) is greeted as the committee. An
    opted-out or bounced contact is never included — the directory's own
    suppression is the same gate ``club_directory.export_to_comms`` uses."""
    out: list[dict] = []
    seen: set[str] = set()
    for c in sorted(contacts, key=lambda c: (c.role_rank if c.role_rank is not None else 99,
                                             (c.full_name or "").lower())):
        if not c.subscribed:
            continue
        email = norm_email(c.email)
        if not email or email in seen:
            continue
        seen.add(email)
        full = (c.full_name or "").strip()
        out.append({
            "email": email,
            "name": full or None,
            "first_name": _first_name(full) or GENERIC_FIRST_NAME,
            "generic": not full,
            "contact": c,
        })
    # The club's own mailbox, when the crawl found one no officer row carries.
    club_email = norm_email(getattr(club, "contact_email", None))
    if club_email and club_email not in seen:
        seen.add(club_email)
        out.append({"email": club_email, "name": None,
                    "first_name": GENERIC_FIRST_NAME, "generic": True, "contact": None})
    return out


async def create_list_from_clubs(session: AsyncSession, *, name: str, days: int,
                                 club_keys: list[str], created_by=None) -> dict:
    """Create an auto-generated BetterComms list from the chosen wizard clubs,
    holding every Club Directory contact each one has an email for.

    Idempotent per address: a contact already in BetterComms is reused (and
    linked back to its directory club if it wasn't) rather than colliding on
    the (org, email) unique — so re-exporting a club that overlaps an earlier
    list never mints a duplicate person, and never resurrects an opt-out."""
    outreach = await get_outreach_org(session)
    if outreach is None:
        return {"error": "no_outreach_org",
                "detail": "Designate a BetterCricket marketing org in BetterComms first."}

    wanted = {norm_key(k) for k in (club_keys or []) if norm_key(k)}
    if not wanted:
        return {"error": "no_clubs", "detail": "No clubs were selected."}

    rows = [r for r in await merged_wizard_clubs(session, days) if r["key"] in wanted]
    if not rows:
        return {"error": "no_clubs", "detail": "None of those clubs are in the wizard list."}

    matches = await _directory_matches(session, rows)

    # Every directory contact for the matched clubs, in one query.
    club_ids = [c.id for c in matches.values()]
    contacts_by_club: dict = {}
    if club_ids:
        for c in (await session.execute(
            select(MarketingClubContact)
            .where(MarketingClubContact.marketing_club_id.in_(club_ids))
        )).scalars().all():
            contacts_by_club.setdefault(c.marketing_club_id, []).append(c)

    final_name = await _unique_list_name(session, outreach.id, name)
    lst = CommsList(organisation_id=outreach.id, name=final_name,
                    source="auto", origin=ORIGIN_LABEL)
    session.add(lst)
    await session.flush()  # need lst.id for the membership rows

    existing = {c.email: c for c in (await session.execute(
        select(CommsContact).where(CommsContact.organisation_id == outreach.id))).scalars().all()}

    member_ids: set[uuid.UUID] = set()
    created = 0
    now = func.now()
    per_club: list[dict] = []
    unmatched: list[str] = []
    excluded: list[str] = []

    for r in rows:
        club = matches.get(r["key"])
        if club is None:
            unmatched.append(r["name"])
            continue
        # The one hard guard the Club Directory export also applies: a club a
        # super admin excluded is never contacted, however it was selected.
        if club.excluded:
            excluded.append(r["name"])
            continue

        added_here = 0
        for rec in _club_recipients(club, contacts_by_club.get(club.id, [])):
            c = existing.get(rec["email"])
            if c is None:
                c = CommsContact(
                    organisation_id=outreach.id, email=rec["email"], name=rec["name"],
                    source="import", marketing_club_id=club.id,
                    merge_vars={"first_name": rec["first_name"]},
                    tags=[club.name],
                )
                session.add(c)
                await session.flush()
                existing[rec["email"]] = c
                created += 1
            else:
                # Fill gaps only — never clobber a name someone corrected, and
                # never touch `subscribed` (an opt-out stays an opt-out).
                if rec["name"] and not c.name:
                    c.name = rec["name"]
                if not c.marketing_club_id:
                    c.marketing_club_id = club.id
                mv = dict(c.merge_vars or {})
                if not (mv.get("first_name") or "").strip():
                    mv["first_name"] = rec["first_name"]
                    c.merge_vars = mv
            if rec["contact"] is not None and rec["contact"].exported_at is None:
                rec["contact"].exported_at = now
            if c.id not in member_ids:
                member_ids.add(c.id)
                added_here += 1

        session.add(WizardClubList(
            list_id=lst.id, list_name=final_name, club_key=r["key"], club_name=r["name"],
            marketing_club_id=club.id, contacts_added=added_here, created_by=created_by,
        ))
        per_club.append({"club": r["name"], "contacts": added_here})

    for cid in member_ids:
        session.add(CommsListMember(list_id=lst.id, contact_id=cid))

    await session.commit()
    result = {
        "list_id": str(lst.id),
        "name": final_name,
        "clubs": len(per_club),
        "added": len(member_ids),
        "created_contacts": created,
        "per_club": per_club,
        "unmatched": unmatched,
        "excluded": excluded,
    }
    logger.info("wizard_club_lists.create_list_from_clubs: %s", result)
    return result
