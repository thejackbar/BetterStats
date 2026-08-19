"""Attribute clubs to the sales rep who earned them, from the actions already
on record.

WHY THIS EXISTS
---------------
Commission attribution (migration 264) is stamped at the moment a rep does
the work, so it only knows about calls and emails logged AFTER it shipped.
Migration 264 carries a one-time backfill for everything before that, but it
runs exactly once, on the deploy that applies it — this is the same rule as a
re-runnable command, for when that pass did not happen or did not cover
everything:

  * the migration was applied before the reps' history existed;
  * an activity row arrived from somewhere the live rule does not stamp (a
    row written straight through the CRM's own generic activity endpoint,
    or an import);
  * or you simply want to see who owns what, which the dry run prints.

THE RULE, WHICH IS THE LIVE ONE
-------------------------------
A club is earned by the FIRST qualifying action on it, and only a sales rep
(a User whose membership carries role 'sales') can earn one:

  * a logged call whose outcome is anything other than General Note, or
  * an email sent to one of the club's contacts.

A note, a General Note outcome, and simply being assigned the club all earn
nothing. Earliest action wins, and a club already attributed is left exactly
as it is — including one attributed by hand — so re-running this is a no-op.
Assignment (crm_deals.owner_user_id) is never read and never written: who
holds a club and who earned it are different facts, which is the whole point
of the column.

USAGE
-----
    python -m app.scripts.backfill_commission_attribution            # dry run
    python -m app.scripts.backfill_commission_attribution --apply
    python -m app.scripts.backfill_commission_attribution --rep sam  # one rep

``--rep`` takes a username, a display name or a user id, and narrows the
REPORT to that person; it does not change who else would be attributed by a
full run.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker

# The live rule, in SQL. Mirrors services/sales_workspace.py's GENERAL_OUTCOMES
# and the `type='call' | type='email'` split that attribute_commission is
# called on — keep the three in step.
_QUALIFYING = """
    SELECT DISTINCT ON (a.deal_id)
           a.deal_id,
           a.created_by_user_id AS rep_id,
           a.occurred_at,
           CASE WHEN a.type = 'email' THEN 'email' ELSE 'call' END AS via
      FROM crm_activities a
      JOIN club_memberships cm
        ON cm.user_id = a.created_by_user_id AND cm.role = 'sales'
     WHERE a.deal_id IS NOT NULL
       AND a.created_by_user_id IS NOT NULL
       AND (
             a.type = 'email'
          OR (a.type = 'call' AND (a.outcome IS NULL OR a.outcome <> 'general_note'))
       )
     ORDER BY a.deal_id, a.occurred_at ASC
"""


async def run(apply: bool, rep_ref: str | None) -> int:
    async with async_session_maker() as db:
        reps = (await db.execute(text("""
            SELECT u.id, COALESCE(u.display_name, u.username) AS name, u.username
              FROM users u
              JOIN club_memberships cm ON cm.user_id = u.id
             WHERE cm.role = 'sales'
             ORDER BY name
        """))).mappings().all()
        if not reps:
            print("No sales reps on this platform (nobody holds a 'sales' membership).")
            print("Nothing can be attributed until a rep exists — see Super Admin -> Users.")
            return 0

        wanted = None
        if rep_ref:
            needle = rep_ref.strip().lower()
            match = [r for r in reps
                     if needle in ((r["name"] or "").lower(), (r["username"] or "").lower(), str(r["id"]))]
            if not match:
                print(f"No sales rep matches {rep_ref!r}. Known reps: "
                      + ", ".join(r["name"] for r in reps))
                return 1
            wanted = match[0]["id"]

        # What the rule says, deal by deal, alongside what is stored now.
        rows = (await db.execute(text(f"""
            WITH qualifying AS ({_QUALIFYING})
            SELECT d.id,
                   d.title,
                   d.commission_rep_user_id AS current_rep,
                   q.rep_id                 AS earned_by,
                   q.via,
                   q.occurred_at
              FROM crm_deals d
              JOIN qualifying q ON q.deal_id = d.id
             ORDER BY d.title
        """))).mappings().all()

        name_of = {r["id"]: r["name"] for r in reps}
        to_write = [r for r in rows if r["current_rep"] is None]
        already = [r for r in rows if r["current_rep"] is not None]
        disagree = [r for r in already if r["current_rep"] != r["earned_by"]]

        if wanted:
            to_write = [r for r in to_write if r["earned_by"] == wanted]
            already = [r for r in already if wanted in (r["current_rep"], r["earned_by"])]
            disagree = [r for r in disagree if wanted in (r["current_rep"], r["earned_by"])]
            print(f"Narrowed to {name_of[wanted]}.\n")

        print(f"{len(rows)} club(s) have a qualifying action on record "
              f"(a real call outcome, or an email to a contact).")
        print(f"{len(already)} already attributed, {len(to_write)} not yet.\n")

        by_rep: dict = {}
        for r in to_write:
            by_rep.setdefault(r["earned_by"], []).append(r)
        if by_rep:
            for rep_id, items in sorted(by_rep.items(), key=lambda kv: name_of.get(kv[0], "")):
                print(f"{name_of.get(rep_id, rep_id)} — {len(items)} club(s) "
                      f"{'attributed' if apply else 'to attribute'}:")
                for r in items:
                    when = r["occurred_at"].date().isoformat() if r["occurred_at"] else "?"
                    print(f"  {'SET ' if apply else 'would set'}  {r['title']:<44} "
                          f"earned by {r['via']} on {when}")
                print()
        else:
            print("Nothing to attribute — every club with a qualifying action already has a rep.\n")

        # A stored rep the record disagrees with is NEVER rewritten: it may
        # have been set by hand, and quietly moving commission is the one
        # thing this script must not do on its own.
        if disagree:
            print(f"{len(disagree)} club(s) are attributed to someone OTHER than the "
                  "earliest qualifying action says. Left alone — change these by hand "
                  "if any are wrong:")
            for r in disagree:
                print(f"  KEPT  {r['title']:<44} stored {name_of.get(r['current_rep'], r['current_rep'])}"
                      f", earliest action {name_of.get(r['earned_by'], r['earned_by'])}")
            print()

        if not apply:
            print("DRY RUN — nothing changed. Re-run with --apply to write these.")
            return 0
        if not to_write:
            return 0

        result = await db.execute(text(f"""
            WITH qualifying AS ({_QUALIFYING})
            UPDATE crm_deals d
               SET commission_rep_user_id = q.rep_id,
                   commission_attributed_at = q.occurred_at,
                   commission_attributed_via = q.via
              FROM qualifying q
             WHERE q.deal_id = d.id
               AND d.commission_rep_user_id IS NULL
        """))
        await db.commit()
        print(f"{result.rowcount} club(s) attributed.")
        return 0


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    rep = None
    if "--rep" in args:
        i = args.index("--rep")
        if i + 1 >= len(args):
            print("--rep needs a username, display name or user id after it.")
            return 1
        rep = args[i + 1]
    if any(a.startswith("--") and a not in ("--apply", "--rep") for a in args):
        print(__doc__)
        return 1
    return asyncio.run(run(apply, rep))


if __name__ == "__main__":
    raise SystemExit(main())
