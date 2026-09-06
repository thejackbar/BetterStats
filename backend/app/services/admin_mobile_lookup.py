"""Fill in a club admin's missing mobile number from their own club's records.

Neither flow that creates a club admin insists on a mobile. A super admin
creating a club on someone's behalf often doesn't have one yet
(``admin_identity.validate_admin_fields(require_mobile=False)``), and an admin
invited to an existing club is never asked for one at all — so a good number of
platform admins have ``users.mobile_number`` NULL while the SAME person's mobile
is already sitting in their club's own records.

This finds it there. Three places a club holds a phone number for a person, and
all three are read for the admin's OWN club and no other:

  1. ``fee_members.mobile`` — the Clubhouse Directory's person spine, typed in
     by the club.
  2. ``players.phone`` — the linked player's, which the Directory itself falls
     back to (services/directory.py) and which is what a read-through player
     with no member row carries.
  3. ``marketing_club_contacts.mobile`` — the Clubs Directory row for their
     club, reached through ``marketing_clubs.existing_org_id``. This is the
     committee contact list (President / Secretary / Treasurer), which is
     exactly where a brand-new club's first admin tends to appear before
     anybody has built the club's own Directory.

**AN EMAIL MATCH IS AN IDENTITY; A NAME MATCH IS NOT.** So every email match is
preferred over every name match, whichever source it came from — a Clubs
Directory contact carrying the admin's own address is far better evidence than
somebody at their club merely being called the same thing. And where a NAME
match turns up two different numbers, this refuses rather than guessing: a
surname and a first name is the exact shape of a father and son at one club
(the rule ``routers/admin.py``'s duplicate detection already keeps). Two
different numbers under one EMAIL is one person with two recorded numbers, so
there the source order below decides.

**THE NUMBER HAS TO BE A MOBILE.** ``players.phone`` and ``fee_members.mobile``
are free text and routinely hold a landline; ``admin_identity.mobile_valid`` is
the rule ``users.mobile_number`` is written under everywhere else, so a
candidate that fails it is REPORTED rather than stored. Writing a clubroom
landline into a field the platform will one day text is worse than leaving it
blank.

**NOTHING IS EVER OVERWRITTEN.** Only an admin whose ``mobile_number`` is NULL
or blank is considered at all, so a run is idempotent and a second one writes
nothing.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin_contact_list import admin_rows
from app.services.admin_identity import mobile_valid
from app.services.player_aliases import normalise_name_key

logger = logging.getLogger(__name__)

#: Which record wins when the same person carries a number in more than one of
#: them. The club's own Directory first (a club typed it about its own member),
#: then the player record behind it, then the Clubs Directory, which is CA's
#: feed plus whatever outreach enrichment has been done to it.
SOURCE_ORDER = ("member", "player", "directory_contact")
SOURCE_LABELS = {
    "member": "Clubhouse Directory (member record)",
    "player": "Clubhouse Directory (player record)",
    "directory_contact": "Clubs Directory (club contact)",
}

_WS = re.compile(r"\s+")


def _clean(raw) -> str:
    return _WS.sub(" ", str(raw or "").strip())


def _compare_key(mobile: str) -> str:
    """Two spellings of one number — ``0412 345 678`` and ``+61412345678`` —
    must not read as a disagreement, so numbers are compared on their digits
    with an AU country code folded off the front."""
    digits = re.sub(r"\D", "", mobile or "")
    if digits.startswith("61") and len(digits) == 11:
        digits = "0" + digits[2:]
    return digits


def user_name(user) -> str:
    """What the account is called, for name matching. ``display_name`` is what a
    club actually typed; first + last is what the registration form collected.
    The username is deliberately NOT used — it is a login credential, and
    matching a club's member list against "jbarendse" would be a coincidence,
    not evidence."""
    name = _clean(getattr(user, "display_name", ""))
    if name:
        return name
    parts = [_clean(getattr(user, "first_name", "")), _clean(getattr(user, "last_name", ""))]
    return " ".join(p for p in parts if p).strip()


async def club_phone_records(db: AsyncSession, org_id) -> list[dict]:
    """Every person record in one club that carries a phone number.

    The join to ``players`` is org-scoped as well as keyed on the link, per the
    cross-club leak rule this codebase already documents for exactly this join:
    a member row can point at another club's player, and without that condition
    this would serve a stranger's phone number as if it were ours.
    """
    rows: list[dict] = []

    members = (await db.execute(text("""
        SELECT fm.full_name, fm.email, fm.mobile,
               p.email AS player_email, p.phone AS player_phone,
               COALESCE(p.display_name_override, p.name) AS player_name
        FROM fee_members fm
        LEFT JOIN players p
               ON p.id = fm.player_id AND p.organisation_id = fm.organisation_id
        WHERE fm.organisation_id = :org AND fm.archived_at IS NULL
    """), {"org": org_id})).mappings().all()
    for m in members:
        # The member's own number first, then the linked player's — the same
        # precedence the Directory itself displays them in.
        if _clean(m["mobile"]):
            rows.append({"source": "member", "name": _clean(m["full_name"]),
                         "email": _clean(m["email"]) or _clean(m["player_email"]),
                         "mobile": _clean(m["mobile"])})
        if _clean(m["player_phone"]):
            rows.append({"source": "player",
                         "name": _clean(m["player_name"]) or _clean(m["full_name"]),
                         "email": _clean(m["player_email"]) or _clean(m["email"]),
                         "mobile": _clean(m["player_phone"])})

    # Players with no member row appear in the Directory read-through, so they
    # are part of "their club's records" too.
    players = (await db.execute(text("""
        SELECT COALESCE(p.display_name_override, p.name) AS name, p.email, p.phone
        FROM players p
        WHERE p.organisation_id = :org
          AND p.phone IS NOT NULL AND btrim(p.phone) <> ''
          AND NOT EXISTS (SELECT 1 FROM fee_members fm
                           WHERE fm.player_id = p.id AND fm.organisation_id = :org)
    """), {"org": org_id})).mappings().all()
    for p in players:
        rows.append({"source": "player", "name": _clean(p["name"]),
                     "email": _clean(p["email"]), "mobile": _clean(p["phone"])})

    # The Clubs Directory's own contacts for this club. existing_org_id carries
    # no unique constraint, so a club can legitimately have more than one
    # directory row; every one of them is read.
    contacts = (await db.execute(text("""
        SELECT c.full_name, c.email, c.mobile
        FROM marketing_club_contacts c
        JOIN marketing_clubs mc ON mc.id = c.marketing_club_id
        WHERE mc.existing_org_id = :org
          AND c.mobile IS NOT NULL AND btrim(c.mobile) <> ''
    """), {"org": org_id})).mappings().all()
    for c in contacts:
        rows.append({"source": "directory_contact", "name": _clean(c["full_name"]),
                     "email": _clean(c["email"]), "mobile": _clean(c["mobile"])})

    return rows


def match_records(user, records: list[dict], *, allow_name_match: bool = True) -> dict:
    """Pick this admin's mobile out of their club's records.

    Returns ``{"status": ...}`` where status is one of:

      ``found``         — ``mobile``, ``source``, ``matched_on`` and
                          ``matched_name`` say which record it came from and
                          why we believe it.
      ``ambiguous``     — a name match, and the people it matched hold different
                          numbers. Refused rather than guessed.
      ``not_a_mobile``  — the person was found and the number on file is not a
                          mobile (a landline, or something malformed).
      ``no_match``      — nobody at their club looks like them.
    """
    email = _clean(getattr(user, "email", "")).lower()
    name_key = normalise_name_key(user_name(user))

    by_email = [r for r in records if email and r["email"].lower() == email]
    by_name = ([r for r in records if name_key and normalise_name_key(r["name"]) == name_key]
               if allow_name_match else [])

    for tier, hits in (("email", by_email), ("name", by_name)):
        if not hits:
            continue
        valid = [r for r in hits if mobile_valid(r["mobile"])]
        if not valid:
            # Found them, but nothing on file is a mobile. Reported with the
            # number so an operator can see it is a landline rather than
            # wondering why the match "did nothing".
            best = sorted(hits, key=lambda r: SOURCE_ORDER.index(r["source"]))[0]
            return {"status": "not_a_mobile", "mobile": best["mobile"],
                    "source": best["source"], "matched_on": tier,
                    "matched_name": best["name"]}
        distinct = {_compare_key(r["mobile"]) for r in valid}
        if tier == "name" and len(distinct) > 1:
            # A name is not an identity. Two people at one club called the same
            # thing, holding two different numbers, is a father and son — not a
            # number to pick between.
            return {"status": "ambiguous", "matched_on": "name",
                    "candidates": sorted(r["mobile"] for r in valid)}
        best = sorted(valid, key=lambda r: SOURCE_ORDER.index(r["source"]))[0]
        # ``matched_name`` is the record's OWN spelling of the person, kept
        # separate from the account's — they legitimately differ ("Nolan,
        # Sarah" against "Sarah Nolan"), and seeing which record answered is
        # what makes a name match checkable rather than taken on trust.
        return {"status": "found", "mobile": best["mobile"], "source": best["source"],
                "matched_on": tier, "matched_name": best["name"]}

    return {"status": "no_match"}


async def backfill(db: AsyncSession, *, club_id=None, apply: bool = True,
                   allow_name_match: bool = True) -> dict:
    """Fill in every blank ``users.mobile_number`` this can answer.

    ``club_id`` narrows it to one club; omitted, it is every club with a live
    (unarchived) organisation — ``admin_contact_list.admin_rows`` is the one
    definition of "a club admin", so this and the contact-list sync can never
    disagree about who counts as one.

    Does NOT commit — the caller owns the transaction, so ``apply=False`` is a
    genuine dry run once the caller rolls back or simply never commits.
    """
    rows = await admin_rows(db, club_id=club_id)
    blank = [(u, m, o) for u, m, o in rows if not _clean(getattr(u, "mobile_number", ""))]

    records_by_org: dict = {}
    filled: list[dict] = []
    skipped: list[dict] = []

    for user, membership, org in blank:
        if org.id not in records_by_org:
            records_by_org[org.id] = await club_phone_records(db, org.id)
        result = match_records(user, records_by_org[org.id],
                              allow_name_match=allow_name_match)
        entry = {
            "user_id": str(user.id),
            "username": user.username or str(user.id),
            "name": user_name(user) or "",
            "email": _clean(getattr(user, "email", "")),
            "club": org.name,
            "primary": bool(membership.is_primary_admin),
            **result,
        }
        if result["status"] == "found":
            filled.append(entry)
            if apply:
                user.mobile_number = result["mobile"]
        else:
            skipped.append(entry)

    if apply and filled:
        await db.flush()

    return {
        "admins": len(rows),
        "missing": len(blank),
        "filled": filled,
        "skipped": skipped,
        "still_missing": len(blank) - len(filled),
    }
