"""Make sure every club admin is a Contact on their club's Clubs Directory row.

WHAT IT DOES
------------
Reads every ``club_admin`` user (the Primary Club Admin and any ordinary Club Admin
alike, since the primary is that same role carrying ``is_primary_admin``) for every
live club, whatever state its subscription is in: trialling, expired, subscribed or
paying. For each one it looks at the club's Clubs Directory contacts, the committee
already pulled from PlayHQ / Play-Cricket plus anyone added since, and decides:

  * already a Contact on the same email           leave it alone
  * already a Contact under the same full name    leave it alone, and list it so a
    (the committee member who signed up with        person can see the call it made
    a personal address)
  * not a Contact                                 store them as one (role "Club Admin",
                                                  with the name, email and mobile on
                                                  their account)

(services/admin_directory_contacts.py.) It stores them in the Clubs Directory
(``marketing_club_contacts``). To put the same people on BetterCricket's internal Comms
list and its "Super Admin User Contact List" segment, run
``app.scripts.sync_admin_contact_list`` as well; the two are independent and either order
works. If you also run ``app.scripts.backfill_admin_mobiles``, run it FIRST: it fills a
blank mobile on the account from the club's own records, and the new Directory contacts
then carry it.

HOW IT DECIDES
--------------
An EMAIL match is an identity; a NAME match is not. A name only counts as "this person"
when it is a full name (two words or more), because many admins registered through the
two-field trial form and are known by a first name alone. ``--email-only`` turns name
matching off entirely, which is the strictest pass.

WHAT IT WILL NOT DO
-------------------
It never edits, re-ticks or deletes an existing contact, however it matched. It only adds.

A contact it stores is kept by a later Rediscover (a Rediscover prunes only contacts
PlayHQ itself listed), so the next committee refresh does not undo it.

A club with no Clubs Directory row is reported and skipped: there is nothing to attach a
contact to, and creating Directory clubs is not this script's job. An admin with neither an
address nor a mobile is reported. A person who asked to be taken off the public site is
not added. An admin on a throwaway-mail domain (yopmail) is a test account and is
reported and skipped. An address that is suppressed or unsubscribed is stored as a contact that says
so (not subscribed, not ticked), never one that reads as reachable. An ARCHIVED club's
admins are left out, the house rule for "stop treating this club as live".

No network call is made; everything it reads is already in our database.

USAGE
-----
On the box, from /srv/docker with the project pinned (never a bare `docker` command):

    cd /srv/docker
    export COMPOSE_PROJECT_NAME=bltbox_docker_app

    # dry run, every club: read this before writing anything
    docker compose exec -T betterstats-backend \
      python -m app.scripts.ensure_admin_directory_contacts

    # write it
    docker compose exec -T betterstats-backend \
      python -m app.scripts.ensure_admin_directory_contacts --apply

    # one club, by id or public slug
    docker compose exec -T betterstats-backend \
      python -m app.scripts.ensure_admin_directory_contacts applecross --apply

    # exact email matches only
    docker compose exec -T betterstats-backend \
      python -m app.scripts.ensure_admin_directory_contacts --email-only --apply

Dry run by default. UNDOING a run: every row it stores has ``source = 'club_admin'`` and
``role = 'Club Admin'``, and the --apply output lists each one by club and address. To
remove them all:

    DELETE FROM marketing_club_contacts WHERE source = 'club_admin';

(a self-serve registration writes ``source = 'self_serve_trial'`` for the same role, so
that does not touch registrants).
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services import admin_directory_contacts as adc


async def _resolve_club(session, raw: str):
    """A club by id or slug, so the one-club form can be typed either way."""
    try:
        return await session.get(Organisation, uuid.UUID(raw))
    except (ValueError, AttributeError):
        return (await session.execute(
            select(Organisation).where(Organisation.slug == raw))).scalar_one_or_none()


def _who(e: dict) -> str:
    label = e["name"] or e["username"] or "(no name)"
    return f"{label} ({e['club']}){' *primary*' if e.get('primary') else ''}"


def _how(e: dict) -> str:
    bits = [e["email"] or "no email", e["mobile"] or "no mobile"]
    return ", ".join(bits)


async def run(target: str | None, apply: bool, allow_name_match: bool) -> int:
    async with async_session_maker() as session:
        club_id = None
        if target and target.lower() != "all":
            club = await _resolve_club(session, target)
            if club is None:
                print(f"No club found for {target!r}")
                return 1
            club_id = club.id
            print(f"Club: {club.name} ({club.slug})")

        r = await adc.backfill(session, club_id=club_id, apply=apply,
                               allow_name_match=allow_name_match)
        if apply:
            await session.commit()

        print(f"\nClub admins found                    {r['admins']}")
        print(f"  already a Contact (same email)     {len(r['have_email'])}")
        print(f"  already a Contact (same name)      {len(r['have_name'])}")
        print(f"  not a Contact, " + ("stored" if apply else "would store") +
              f"             {len(r['add'])}")
        gaps = (len(r['no_directory_row']) + len(r['nothing_to_store']) + len(r['privacy_removed'])
                + len(r['test_account']))
        if gaps:
            print(f"  could not be added                 {gaps}")

        if r["add"]:
            print("\nSTORED:" if apply else "\nWOULD STORE:")
            for e in sorted(r["add"], key=lambda x: (x["club"], x["name"] or "")):
                note = "  [address is opted out: stored as not subscribed, not ticked]" if e.get("blocked") else ""
                print(f"  {_who(e)}\n      {_how(e)}{note}")

        if r["have_name"]:
            print("\nTREATED AS ALREADY A CONTACT, BY NAME ONLY (check these):")
            for e in sorted(r["have_name"], key=lambda x: (x["club"], x["name"] or "")):
                former = "  (no longer listed on the committee)" if e.get("former") else ""
                print(f"  {_who(e)}  {_how(e)}")
                print(f"      matches contact {e['contact_name']!r}"
                      f"{' (' + e['contact_role'] + ')' if e.get('contact_role') else ''}, "
                      f"filed under {e.get('contact_email') or 'no email'}{former}")
            print("  If any of these is a different person, run again with --email-only.")

        if r["no_directory_row"]:
            clubs = sorted({e["club"] for e in r["no_directory_row"]})
            print(f"\nCLUBS WITH NO CLUBS DIRECTORY ROW, SKIPPED ({len(clubs)}):")
            for c in clubs:
                print(f"  {c}")
        if r["nothing_to_store"]:
            print(f"\nNO EMAIL AND NO MOBILE ON THE ACCOUNT, SKIPPED ({len(r['nothing_to_store'])}):")
            for e in sorted(r["nothing_to_store"], key=lambda x: (x["club"], x["name"] or "")):
                print(f"  {_who(e)}")
        if r["test_account"]:
            print(f"\nTEST ACCOUNTS (THROWAWAY MAIL), SKIPPED ({len(r['test_account'])}):")
            for e in sorted(r["test_account"], key=lambda x: (x["club"], x["name"] or "")):
                print(f"  {_who(e)}  {e['email']}")
        if r["privacy_removed"]:
            print(f"\nASKED TO BE REMOVED, NOT ADDED ({len(r['privacy_removed'])}):")
            for e in r["privacy_removed"]:
                print(f"  {_who(e)}")

        if apply:
            print(f"\nDone. {r['created']} contact(s) created.")
        else:
            print("\nDRY RUN: nothing changed. Re-run with --apply to write it.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    allow_name_match = "--email-only" not in args
    positional = [a for a in args if not a.startswith("-")]
    return asyncio.run(run(positional[0] if positional else None, apply, allow_name_match))


if __name__ == "__main__":
    raise SystemExit(main())
