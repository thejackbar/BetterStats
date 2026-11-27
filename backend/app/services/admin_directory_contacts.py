"""Every club admin is a Contact on their club's Clubs Directory row.

The Clubs Directory holds the people BetterCricket knows at a club: the committee
Cricket Australia publishes (President, Secretary, Treasurer) and whoever a rep or
a registration added. A club's admin is the one person we know for certain runs the
club on BetterCricket, yet nothing makes sure they are among those contacts. A club
that was onboarded by a super admin, an admin invited later, and an admin whose club
was crawled before they registered can all be missing, which leaves the Directory
and the Sales Workspace without the person who actually uses the product.

``plan`` reads every club admin and decides, per person, one of:

  * ``have_email``  already a Contact of THEIR club on the same address;
  * ``have_name``   already a Contact of their club under the same full name
                    (the committee member who signed up with a personal address);
  * ``add``         not a Contact, so one is stored;
  * a reason it cannot be: the club has no Directory row, or the person has
    neither an address nor a mobile, or they asked to be removed, or the address is
    on a throwaway-mail domain (a test account, ``TEST_MAIL_DOMAINS``).

``apply`` writes only the ``add`` entries. ``backfill`` is the two together, and with
``apply=False`` writes nothing, so the dry run and the real run read one plan.

**AN EMAIL MATCH IS AN IDENTITY; A NAME MATCH IS NOT.** The same rule
``admin_mobile_lookup`` follows. A name only counts as "this person" when it is a full
name (two words or more, in any order), because the two-field trial sign-up leaves many
admins named by a first name alone and "Sam" is nobody's identity. A name match is
reported separately so a person can see which contacts were treated as the same
human. ``allow_name_match=False`` (the script's ``--email-only``) turns it off.

**ADDITIVE ONLY.** An existing contact is never edited, re-ticked, un-flagged or
given a mobile here, whichever way it matched. Nothing is deleted.

**A ROW THIS WRITES SURVIVES A REDISCOVER.** It is stored with ``source`` other than
``'api'`` (``_prune_committee`` only ever prunes ``'api'`` rows) and a rank a crawl
cannot produce for it, the same protection a rep's typed contact gets. Role and rank
match what a self-serve registration writes (``engagement._resolve_self_serve_club``),
so a club whose admin registered and one backfilled here read the same.

**AN OPT-OUT IS REPRESENTED, NOT HIDDEN.** An address that is globally suppressed or
that BetterCricket's own Comms list holds as unsubscribed, bounced, complained or
excluded gets a contact that says so (``subscribed`` false, not ticked for outreach),
rather than one that reads as reachable. A person who asked to be taken off the
public site is not added at all.

Does NOT commit; the script owns the transaction.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import CommsContact, EmailSuppression, MarketingClubContact
from app.services.admin_contact_list import _marketing_club_by_org, admin_rows
from app.services.marketing_org import get_outreach_org
from app.services.player_aliases import normalise_name_key

logger = logging.getLogger(__name__)

#: What the contact is called in the Directory. The same label a self-serve
#: registration writes, so the two read alike.
ROLE = "Club Admin"
ROLE_RANK = 1
#: ``marketing_club_contacts.source``. Anything but 'api' is spared by a Rediscover.
SOURCE = "club_admin"

#: Throwaway-mail domains: an admin on one of these is a test account, not a person at the club,
#: so the backfill leaves them out (and says so) rather than file a fake "Club Admin" contact that
#: is ticked for outreach. Matched on the address's domain, subdomains included.
TEST_MAIL_DOMAINS = ("yopmail.com", "yopmail.fr", "yopmail.net")

_CHUNK = 500   # keeps every IN list far under the driver's bind-parameter ceiling


def _clean(raw) -> str:
    return " ".join(str(raw or "").split())


def _full_name(user) -> str:
    """The fullest name the account carries. ``display_name`` is what the club typed
    and first + last is what the form collected; a two-field trial sign-up has only a
    first name until the person fills the rest in, so the longer of the two wins."""
    display = _clean(getattr(user, "display_name", ""))
    joined = " ".join(p for p in (_clean(getattr(user, "first_name", "")),
                                  _clean(getattr(user, "last_name", ""))) if p)
    if len(joined.split()) > len(display.split()):
        return joined
    return display or joined


def _keys_for(*names) -> set:
    """Order-independent keys for each full name given. A single word yields none: a first
    name alone is not enough to say two records are one person."""
    out = set()
    for raw in names:
        key = normalise_name_key(raw)
        if len(key.split()) >= 2:
            out.add(key)
    return out


def _name_keys(user) -> set:
    """Every full name the account carries (display name, and first + last)."""
    return _keys_for(getattr(user, "display_name", ""),
                     " ".join(p for p in (_clean(getattr(user, "first_name", "")),
                                          _clean(getattr(user, "last_name", ""))) if p))


class ContactIndex:
    """One club's Directory contacts, indexed the way a person is recognised in them. THE
    definition of "already a Contact", shared by the backfill (``plan``) and a live
    registration (``find_contact``), so the two cannot disagree.

    ``by_email`` an address (an identity); ``by_name`` a full name (two words or more, any
    order; the person may have used another address); ``by_exact`` an address-less contact
    by its exact full name, which is the store's own dedupe key for one."""

    def __init__(self, contacts=()):
        self.by_email: dict = {}
        self.by_name: dict = {}
        self.by_exact: dict = {}
        for c in contacts:
            self.add(c)

    def add(self, c) -> None:
        e = (c.email or "").strip().lower()
        if e:
            self.by_email.setdefault(e, c)
        else:
            self.by_exact.setdefault((c.full_name or "").strip().lower(), c)
        for k in _keys_for(c.full_name):
            self.by_name.setdefault(k, c)

    def find(self, *, email, name, name_keys, allow_name_match=True):
        """``(contact, via)`` with via 'email' | 'name', or ``(None, None)``."""
        hit = self.by_email.get(email) if email else None
        if hit is not None:
            return hit, "email"
        if allow_name_match:
            for key in name_keys:
                if key in self.by_name:
                    return self.by_name[key], "name"
        if not email and name:
            hit = self.by_exact.get(name.strip().lower())
            if hit is not None:
                return hit, "name"
        return None, None


async def find_contact(session: AsyncSession, club_id, *, email, name):
    """The existing Directory contact of ``club_id`` that this person already is, or None.
    What a live registration asks before storing one (same rules as the backfill)."""
    email = (email or "").strip().lower() or None
    contacts = (await session.execute(select(MarketingClubContact).where(
        MarketingClubContact.marketing_club_id == club_id))).scalars().all()
    hit, _via = ContactIndex(contacts).find(
        email=email, name=_clean(name), name_keys=_keys_for(name))
    return hit


async def is_opted_out(session: AsyncSession, email) -> bool:
    """Whether this address must not read as reachable (see ``_opted_out_emails``)."""
    e = (email or "").strip().lower()
    return bool(e) and e in await _opted_out_emails(session, [e])


def is_test_address(email) -> bool:
    """Whether the address is on a throwaway-mail domain (``TEST_MAIL_DOMAINS``)."""
    domain = (email or "").strip().lower().rpartition("@")[2]
    return bool(domain) and any(domain == d or domain.endswith("." + d) for d in TEST_MAIL_DOMAINS)


def _chunks(items, n=_CHUNK):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i:i + n]


async def _contacts_by_club(session: AsyncSession, club_ids) -> dict:
    """marketing_club_id -> that club's Directory contacts (every one, including a
    former officer: they are still a Contact on file, and the unique index on
    (club, email) would refuse a second)."""
    out: dict = {cid: [] for cid in club_ids}
    for batch in _chunks(club_ids):
        rows = (await session.execute(select(MarketingClubContact).where(
            MarketingClubContact.marketing_club_id.in_(batch)))).scalars().all()
        for c in rows:
            out.setdefault(c.marketing_club_id, []).append(c)
    return out


async def _opted_out_emails(session: AsyncSession, emails) -> set:
    """Addresses that must not read as reachable: globally suppressed, or held as
    unsubscribed / bounced / complained / excluded on BetterCricket's own Comms list."""
    emails = sorted({e for e in emails if e})
    out: set = set()
    if not emails:
        return out
    outreach = await get_outreach_org(session)
    for batch in _chunks(emails):
        out |= {str(e).lower() for e in (await session.execute(
            select(EmailSuppression.email).where(func.lower(EmailSuppression.email).in_(batch)))).scalars().all()}
        if outreach is not None:
            out |= {str(e).lower() for e in (await session.execute(
                select(CommsContact.email).where(
                    CommsContact.organisation_id == outreach.id,
                    func.lower(CommsContact.email).in_(batch),
                    or_(CommsContact.subscribed.is_(False), CommsContact.bounced.is_(True),
                        CommsContact.complained.is_(True), CommsContact.excluded.is_(True))))).scalars().all()}
    return out


async def plan(session: AsyncSession, *, club_id=None, allow_name_match: bool = True) -> dict:
    """What each club admin needs. Reads only; ``club_id`` narrows to one club.

    A person planned as an ``add`` is counted as a Contact for the next admin of the
    same club (two admins sharing a mailbox are one contact, and the dry run must say
    so as the real run would), which is what keeps the dry run equal to the apply."""
    from app.services import privacy_email

    rows = await admin_rows(session, club_id=club_id)
    mc_by_org = await _marketing_club_by_org(session, [org.id for _, _, org in rows])
    contacts = await _contacts_by_club(session, [mc.id for mc in mc_by_org.values()])
    opted_out = await _opted_out_emails(
        session, [(u.email or "").strip().lower() for u, _, _ in rows])

    # Per club, grown as additions are planned.
    index = {mc.id: ContactIndex(contacts.get(mc.id, [])) for mc in mc_by_org.values()}

    entries: list[dict] = []
    for user, membership, org in rows:
        mc = mc_by_org.get(org.id)
        email = (user.email or "").strip().lower()
        mobile = _clean(getattr(user, "mobile_number", "")) or None
        name = _full_name(user)
        base = {
            "user_id": user.id, "username": user.username, "name": name, "email": email or None,
            "mobile": mobile, "club": org.name, "club_id": org.id,
            "primary": bool(getattr(membership, "is_primary_admin", False)),
            "marketing_club_id": mc.id if mc else None,
        }
        if mc is None:
            entries.append({**base, "status": "no_directory_row"})
            continue
        if is_test_address(email):
            entries.append({**base, "status": "test_account"})
            continue
        if not email and not mobile:
            entries.append({**base, "status": "nothing_to_store"})
            continue
        if email and await privacy_email.is_removed_address(email, session):
            entries.append({**base, "status": "privacy_removed"})
            continue

        hit, via = index[mc.id].find(email=email, name=name, name_keys=_name_keys(user),
                                     allow_name_match=allow_name_match)
        if hit is not None and via == "email":
            entries.append({**base, "status": "have_email", "contact_id": hit.id,
                            "contact_name": hit.full_name, "contact_role": hit.role,
                            "former": hit.former_at is not None,
                            "planned": getattr(hit, "_planned", False)})
            continue
        if hit is not None:
            entries.append({**base, "status": "have_name", "contact_id": hit.id,
                            "contact_name": hit.full_name, "contact_email": hit.email,
                            "contact_role": hit.role, "former": hit.former_at is not None})
            continue

        blocked = bool(email) and email in opted_out
        entries.append({**base, "status": "add", "blocked": blocked})
        # Count the planned row as a Contact for whoever comes next at this club.
        index[mc.id].add(type("Planned", (), {"email": email or None, "full_name": name, "role": ROLE,
                                              "former_at": None, "id": None, "_planned": True})())
    return {"entries": entries}


async def apply_plan(session: AsyncSession, entries) -> int:
    """Store the ``add`` entries. Returns how many contacts it created. Flushes, does
    not commit."""
    from app.services.club_directory import _store_contact

    created = 0
    for e in entries:
        if e["status"] != "add":
            continue
        blocked = bool(e.get("blocked"))
        cid = await _store_contact(
            session, e["marketing_club_id"], full_name=e["name"] or None, role=ROLE,
            role_rank=ROLE_RANK, email=e["email"], phone=e["mobile"],
            selected=not blocked, source=SOURCE)
        if cid is None:
            continue
        row = await session.get(MarketingClubContact, cid)
        if row is not None and row.source == SOURCE:
            created += 1
            if blocked:
                # Say so, rather than leave a contact that reads as reachable.
                row.subscribed = False
                row.outreach_selected = False
    await session.flush()
    return created


def summarise(entries) -> dict:
    by: dict = {}
    for e in entries:
        by.setdefault(e["status"], []).append(e)
    return {
        "admins": len(entries),
        "add": by.get("add", []),
        "have_email": by.get("have_email", []),
        "have_name": by.get("have_name", []),
        "no_directory_row": by.get("no_directory_row", []),
        "nothing_to_store": by.get("nothing_to_store", []),
        "test_account": by.get("test_account", []),
        "privacy_removed": by.get("privacy_removed", []),
    }


async def backfill(session: AsyncSession, *, club_id=None, apply: bool = False,
                   allow_name_match: bool = True) -> dict:
    """:func:`plan`, and with ``apply`` :func:`apply_plan`. Does not commit."""
    entries = (await plan(session, club_id=club_id, allow_name_match=allow_name_match))["entries"]
    result = summarise(entries)
    result["created"] = await apply_plan(session, entries) if apply else 0
    return result
