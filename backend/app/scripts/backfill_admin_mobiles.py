"""Fill in a club admin's missing mobile from their own club's records.

WHAT IT DOES
------------
Finds every ``club_admin`` user — the Primary Club Admin and any ordinary Club
Admin alike, since the primary is that same role carrying ``is_primary_admin``
rather than a role of its own — whose ``users.mobile_number`` is blank, looks
that person up in THEIR OWN club's records, and stores the mobile it finds.

Three places a club holds a phone number, all read for the admin's own club and
no other (services/admin_mobile_lookup.py):

  * the Clubhouse Directory's member record (``fee_members.mobile``);
  * the player record behind it, which the Directory itself falls back to
    (``players.phone``), including a read-through player with no member row;
  * the Clubs Directory contact for their club (``marketing_club_contacts``),
    which is where a brand-new club's first admin usually turns up before
    anybody has built the club's own Directory.

WHY THEY ARE BLANK
------------------
Neither flow that creates a club admin insists on a mobile: a super admin
creating a club on someone's behalf often doesn't have one yet, and an admin
invited to an existing club is never asked for one. The number is frequently
already on file about the same person somewhere else in the club.

HOW IT DECIDES
--------------
An EMAIL match beats a NAME match, whichever record it came from — an address
is an identity and a name is not. Where a NAME match turns up two different
numbers it REFUSES rather than guessing, because a shared name at one club is
the shape of a father and son. A number that is not a mobile (a clubroom
landline, something malformed) is reported and NOT stored: the rule is
``admin_identity.mobile_valid``, the same one every other writer of this field
uses.

WHAT IT WILL NOT DO
-------------------
It never overwrites. Only an admin whose mobile is already blank is considered,
so a run is idempotent and a second one writes nothing.

It never reaches outside the admin's own club, and it makes no network call at
all — everything it reads is already in our database, so it is quick enough to
run platform-wide.

An ARCHIVED club's admins are left out, the house rule for "stop treating this
club as live" that the sync scheduler and the Twenty pushes already follow.

USAGE
-----
On the box, from /srv/docker with the project pinned (never a bare `docker`
command — that is how a second stack ends up on an empty volume):

    cd /srv/docker
    export COMPOSE_PROJECT_NAME=bltbox_docker_app

    # dry run, every club — read this before writing anything
    docker compose exec -T betterstats-backend \
      python -m app.scripts.backfill_admin_mobiles

    # write it
    docker compose exec -T betterstats-backend \
      python -m app.scripts.backfill_admin_mobiles --apply

    # one club, by id or public slug
    docker compose exec -T betterstats-backend \
      python -m app.scripts.backfill_admin_mobiles applecross --apply

    # the strictest pass: exact email matches only, no name matching at all
    docker compose exec -T betterstats-backend \
      python -m app.scripts.backfill_admin_mobiles --email-only --apply

Dry run by default, per the house rule — read what it would change first.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services import admin_mobile_lookup as aml


async def _resolve_club(session, raw: str):
    """A club by id or slug, so the one-club form can be typed either way."""
    try:
        return await session.get(Organisation, uuid.UUID(raw))
    except (ValueError, AttributeError):
        return (await session.execute(
            select(Organisation).where(Organisation.slug == raw))).scalar_one_or_none()


def _row(entry: dict) -> str:
    who = entry["name"] or entry["username"]
    return f"{who} ({entry['club']})"


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

        result = await aml.backfill(session, club_id=club_id, apply=apply,
                                    allow_name_match=allow_name_match)
        if apply:
            await session.commit()

        print(f"\nClub admins found            {result['admins']}")
        print(f"  with no mobile on file     {result['missing']}")
        print(f"  mobile found for           {len(result['filled'])}")
        print(f"  still without one          {result['still_missing']}")

        if result["filled"]:
            print("\nFOUND" + ("" if apply else " (would store)") + ":")
            for e in sorted(result["filled"], key=_row):
                print(f"  {_row(e)}")
                print(f"      {e['mobile']}  — matched on {e['matched_on']}, "
                      f"from {aml.SOURCE_LABELS[e['source']]}")
                if e.get("matched_name") and e["matched_name"] != e["name"]:
                    print(f"      that record is filed as {e['matched_name']!r}")

        unresolved = [e for e in result["skipped"] if e["status"] != "no_match"]
        if unresolved:
            print("\nFOUND SOMEBODY, DID NOT STORE A NUMBER:")
            for e in sorted(unresolved, key=_row):
                if e["status"] == "not_a_mobile":
                    print(f"  {_row(e)}")
                    print(f"      {e['mobile']} is on file but is not a mobile "
                          f"({aml.SOURCE_LABELS[e['source']]}) — check it by hand")
                else:
                    print(f"  {_row(e)}")
                    print(f"      several people at that club share the name and "
                          f"hold different numbers: {', '.join(e['candidates'])}")

        nothing = [e for e in result["skipped"] if e["status"] == "no_match"]
        if nothing:
            print(f"\nNo record at their club matches ({len(nothing)}):")
            for e in sorted(nothing, key=_row):
                print(f"  {_row(e)}  {e['email'] or 'no email on the account'}")

        if not apply:
            print("\nDRY RUN — nothing changed. Re-run with --apply to write it.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    allow_name_match = "--email-only" not in args
    positional = [a for a in args if not a.startswith("-")]
    return asyncio.run(run(positional[0] if positional else None, apply, allow_name_match))


if __name__ == "__main__":
    raise SystemExit(main())
