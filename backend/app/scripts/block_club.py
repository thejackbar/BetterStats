"""Block (or unblock) a club, a club name, a Cricket Australia id or an email.

WHY THIS EXISTS
---------------
There was no way to stop a club. Archiving one does not stop its admins signing
in, and a fresh self-serve registration un-archives the row. This writes to the
block list (``registration_blocks``, migration 386), which the registration
steps, the login and every signed-in request read.

WHAT IT DOES
------------
``--org`` names a registered club (slug, id, or exact name). That club gets:
  * an ``org_id`` block: its members (not super admins or sales) cannot sign in
    and an open session stops on its next request (within about 10 seconds);
  * a ``ca_org_id`` block for its Cricket Australia id and a ``club_name`` block
    for its name, so it cannot register again as a "new" club;
  * ``is_active = false``, which takes its public site offline.
Nothing is deleted: no player, game, fee, note or user row is touched, and the
club's own data is exactly as it was. An audit entry is written on the club.

Without ``--org`` it adds only the blocks you name: ``--ca-id``, ``--name``,
``--email``, ``--domain``. Use that for a club that is partway through
registering and has no club row yet.

``--lift`` stamps ``lifted_at`` on the matching live blocks. It does NOT set
``is_active`` back: switch the club on from Super Admin when you mean to.

The reason is stored for staff and is never shown to the people refused.

USAGE (dry run unless --apply)
------------------------------
    python -m app.scripts.block_club --name "Subiaco Marist" --reason "..."
    python -m app.scripts.block_club --org subiaco-marist --apply --reason "..."
    python -m app.scripts.block_club --email someone@example.com --domain example.com --apply
    python -m app.scripts.block_club --org subiaco-marist --lift --apply
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import registration_blocks as rb


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("USAGE")[0], formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--org", help="a registered club: slug, id or exact name")
    p.add_argument("--ca-id", action="append", default=[], help="a Cricket Australia / PlayHQ organisation id")
    p.add_argument("--name", action="append", default=[], help="a club name")
    p.add_argument("--email", action="append", default=[], help="one email address")
    p.add_argument("--domain", action="append", default=[], help="an email domain, e.g. example.com")
    p.add_argument("--reason", default="", help="why (staff only, never shown to the person refused)")
    p.add_argument("--by", default="script:block_club", help="who is doing it, for the record")
    p.add_argument("--lift", action="store_true", help="lift the matching blocks instead of adding them")
    p.add_argument("--apply", action="store_true", help="write it (default is a dry run)")
    return p.parse_args(argv)


async def _find_org(s, ref: str):
    rows = (await s.execute(text(
        "SELECT id, name, slug, playhq_id, is_active FROM organisations "
        "WHERE lower(slug) = lower(:r) OR CAST(id AS text) = lower(:r) OR lower(name) = lower(:r)"
    ), {"r": ref.strip()})).mappings().all()
    return rows


def _wanted(args: argparse.Namespace, org) -> list[tuple[str, str, str]]:
    """(kind, stored value, label) for every block this run is about."""
    out: list[tuple[str, str, str]] = []
    if org is not None:
        out.append(("org_id", rb.normalise_value("org_id", str(org["id"])), f"club {org['name']}"))
        out.append(("ca_org_id", rb.normalise_value("ca_org_id", str(org["id"])), "its Cricket Australia id"))
        if org["playhq_id"]:
            out.append(("ca_org_id", rb.normalise_value("ca_org_id", org["playhq_id"]), "its PlayHQ id"))
        out.append(("club_name", rb.normalise_value("club_name", org["name"]), f"its name ({org['name']})"))
    for v in args.ca_id:
        out.append(("ca_org_id", rb.normalise_value("ca_org_id", v), "CA id"))
    for v in args.name:
        out.append(("club_name", rb.normalise_value("club_name", v), f"name ({v})"))
    for v in args.email:
        out.append(("email", rb.normalise_value("email", v), "email"))
    for v in args.domain:
        out.append(("email_domain", rb.normalise_value("email_domain", v), "email domain"))
    seen, uniq = set(), []
    for k, v, label in out:
        if v and (k, v) not in seen:
            seen.add((k, v))
            uniq.append((k, v, label))
    return uniq


async def main(argv: list[str]) -> int:
    args = _parse(argv)
    mode = "APPLY" if args.apply else "DRY RUN"
    async with async_session_maker() as s:
        org = None
        if args.org:
            found = await _find_org(s, args.org)
            if len(found) != 1:
                print(f"--org {args.org!r} matched {len(found)} clubs; give the slug or id." + (
                    "\n" + "\n".join(f"  {r['id']}  {r['slug']}  {r['name']}" for r in found) if found else ""))
                return 2
            org = found[0]
        wanted = _wanted(args, org)
        if not wanted:
            print("Nothing to do: name a club with --org, or give --ca-id, --name, --email or --domain.")
            return 2
        if not args.lift and not args.reason.strip():
            print("Give a --reason (staff only, never shown to the person refused).")
            return 2

        verb = "LIFT" if args.lift else "BLOCK"
        print(f"[{mode}] {verb}")
        if org is not None:
            print(f"  club: {org['name']} ({org['slug']}), is_active={org['is_active']}")
        for k, v, label in wanted:
            live = (await s.execute(text(
                "SELECT 1 FROM registration_blocks WHERE kind = :k AND value = :v AND lifted_at IS NULL"
            ), {"k": k, "v": v})).first() is not None
            state = "already blocked" if live else "not blocked"
            print(f"  {k:<13} {v}   ({label}; {state})")
        if org is not None and not args.lift:
            print("  would set is_active = false (public site offline); no row is deleted")
        if not args.apply:
            print("Dry run: nothing written. Re-run with --apply.")
            return 0

        for k, v, _ in wanted:
            if args.lift:
                await s.execute(text(
                    "UPDATE registration_blocks SET lifted_at = NOW(), lifted_by = :by "
                    "WHERE kind = :k AND value = :v AND lifted_at IS NULL"
                ), {"k": k, "v": v, "by": args.by})
            else:
                await s.execute(text(
                    "INSERT INTO registration_blocks (kind, value, reason, created_by) "
                    "SELECT :k, :v, :why, :by WHERE NOT EXISTS ("
                    "  SELECT 1 FROM registration_blocks WHERE kind = :k AND value = :v AND lifted_at IS NULL)"
                ), {"k": k, "v": v, "why": args.reason.strip(), "by": args.by})

        audit_ok = True
        if org is not None:
            if not args.lift:
                await s.execute(text("UPDATE organisations SET is_active = FALSE WHERE id = :id"), {"id": org["id"]})
            # The audit entry goes in its own savepoint. A failed INSERT aborts
            # the whole Postgres transaction, and COMMIT on an aborted
            # transaction rolls back WITHOUT an error, so a missing or broken
            # audit table would otherwise undo the block while this script said
            # "Done". (services.audit_log.log_activity swallows its own error,
            # which is exactly what hides it, so it is not used here.)
            try:
                async with s.begin_nested():
                    await s.execute(text(
                        "INSERT INTO audit_logs (org_id, user_id, action, target_type, target_id, details) "
                        "VALUES (:org, NULL, :action, 'organisation', :tid, CAST(:details AS JSONB))"
                    ), {
                        "org": str(org["id"]), "tid": str(org["id"]),
                        "action": "unblock_club" if args.lift else "block_club",
                        "details": json.dumps({
                            "name": org["name"], "was_active": bool(org["is_active"]),
                            "reason": args.reason.strip(), "by": args.by,
                            "blocks": [f"{k}:{v}" for k, v, _ in wanted]}),
                    })
            except Exception as e:  # the block must still stand
                audit_ok = False
                print(f"WARNING: the audit entry could not be written ({type(e).__name__}); the block itself is being saved.")
        await s.commit()
        rb.invalidate_cache()

    # Read it back in a fresh session: say what is true, not what was meant.
    async with async_session_maker() as s:
        problems = []
        for k, v, _ in wanted:
            live = (await s.execute(text(
                "SELECT 1 FROM registration_blocks WHERE kind = :k AND value = :v AND lifted_at IS NULL"
            ), {"k": k, "v": v})).first() is not None
            if live == args.lift:
                problems.append(f"{k}:{v} is {'still blocked' if live else 'not blocked'}")
        if org is not None and not args.lift:
            active = (await s.execute(text("SELECT is_active FROM organisations WHERE id = :id"),
                                      {"id": org["id"]})).scalar()
            if active:
                problems.append("the club is still active")
    if problems:
        print("FAILED, read back from the database:")
        for p_ in problems:
            print("  " + p_)
        return 1
    print(("Lifted" if args.lift else "Blocked") + ", confirmed by reading it back."
          + ("" if args.lift else " Open sessions stop within about 10 seconds."))
    if not audit_ok:
        print("No audit entry was recorded for this change (see the warning above).")
    if args.lift and org is not None:
        print("The club is still inactive: switch it on from Super Admin when you mean to.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
