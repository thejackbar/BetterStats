"""Put every club admin on BetterCricket's internal club-admin contact list.

WHAT IT DOES
------------
Finds every user who holds a ``club_admin`` membership — the Primary Club Admin
and any ordinary Club Admin alike, since the primary is that same role carrying
``is_primary_admin`` rather than a role of its own — upserts each one as a
BetterComms contact in the marketing-outreach org, and adds them to the
"Super Admin User Contact List" (created if it isn't there yet).

New admins land on the list on their own from now on: a self-serve
registration, a super admin creating a club, a primary admin being reassigned,
an admin added to an existing club, or a club_member promoted to admin all fire
the same sync (services/admin_contact_list.py). This script is the one-off
backfill for everyone who was already an admin before that existed, and it is
safe to re-run at any time — it is the same code the live hooks run, over the
whole platform instead of one club.

WHAT IT WILL NOT DO
-------------------
It never REMOVES anybody. Losing the club_admin role does not take a person off
the list; that is a decision for a person to make on the Lists screen.

It never overrides an opt-out. Someone who has unsubscribed, hard bounced or
complained keeps their contact row up to date but is NOT put back on the list —
BetterComms drops a suppressed contact from every list, and re-adding them here
would fight it on every run. They are reported as ``suppressed``.

An admin with no email address on file cannot be a contact and is reported by
username, not silently dropped — that count is what says the list is short of
the roster. An ARCHIVED club's admins are left out, the same rule the sync
scheduler and the Twenty pushes already use for a club that is no longer live.

USAGE
-----
    python -m app.scripts.sync_admin_contact_list                  # dry run
    python -m app.scripts.sync_admin_contact_list --apply
    python -m app.scripts.sync_admin_contact_list <org-id-or-slug> # one club
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services import admin_contact_list as acl


async def _resolve_club(session, raw: str):
    """A club by id or slug, so the one-club form can be typed either way."""
    try:
        return await session.get(Organisation, uuid.UUID(raw))
    except (ValueError, AttributeError):
        return (await session.execute(
            select(Organisation).where(Organisation.slug == raw))).scalar_one_or_none()


async def run(target: str | None, apply: bool) -> int:
    async with async_session_maker() as session:
        club_id = None
        if target:
            club = await _resolve_club(session, target)
            if club is None:
                print(f"No club found for {target!r}")
                return 1
            club_id = club.id
            print(f"Club: {club.name} ({club.slug})")

        result = await acl.sync(session, club_id=club_id, apply=apply)
        if result.get("status") == "no_outreach_org":
            print("No marketing-outreach organisation is designated, so there is "
                  "nowhere for the list to live.\nDesignate one from BetterComms "
                  "first, then re-run this.")
            return 1

        if apply:
            await session.commit()

        print(f"\nList: {result['list_name']}")
        print(f"  club admins found          {result['admins']}")
        print(f"  emailable (unique address) {result['emails']}")
        print(f"  contacts created           {result['contacts_added']}")
        print(f"  contacts already on file   {result['contacts_updated']}")
        print(f"  added to the list          {result['list_added']}")
        if result["suppressed"]:
            print(f"  left off (opted out)       {result['suppressed']}")
        if result["no_email"]:
            print(f"\n{len(result['no_email'])} admin(s) have no email address on file "
                  f"and cannot be contacts:")
            for username in sorted(result["no_email"]):
                print(f"  NO EMAIL  {username}")
            print("Add an address on their account if they should be on the list.")

        if not apply:
            print("\nDRY RUN — nothing changed. Re-run with --apply to write it.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    return asyncio.run(run(positional[0] if positional else None, apply))


if __name__ == "__main__":
    raise SystemExit(main())
