"""Remove the matches a CricketStatz import copied on top of the club's own
synced games.

The importer looked for an existing match by its CricketStatz id and nothing
else, so it had no idea the club already held that fixture from Cricket
Australia. Both then sit in ``v_effective_games``, which unions the synced and
manual tables — and every innings of every overlapping match is counted twice.
A doubling scales runs and dismissals together, so the AVERAGE is unchanged and
only the counts move, which is why it reads as plausible figures rather than
obvious nonsense.

The importer is fixed and a re-import now clears these as it goes, but that is
an hour of Cricket Australia calls a club should not have to spend twice.
Undoing the import is not the answer either — it would take the pre-sync
history with it, which is the half only CricketStatz has.

**A match somebody has edited by hand is never removed**, whatever it
duplicates: correcting a scorecard costs a club hours and there is no upstream
to re-pull it from. Those are reported instead, for a person to decide.

    python -m app.scripts.repair_cricketstatz_duplicates <org-id-or-slug|all>
    python -m app.scripts.repair_cricketstatz_duplicates all --apply

Dry run by default, per the house rule — an imported match that duplicates
nothing looks identical to one that does until this has been read.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services.cricketstatz_import import remove_duplicate_imported_games


async def _orgs(db, target: str) -> list[Organisation]:
    if target == "all":
        return list((await db.execute(
            select(Organisation).where(Organisation.archived_at.is_(None))
            .order_by(Organisation.name)
        )).scalars().all())
    row = (await db.execute(
        select(Organisation).where(Organisation.slug == target)
    )).scalars().first()
    if row is None:
        try:
            row = await db.get(Organisation, target)
        except Exception:
            row = None
    return [row] if row else []


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    target = args[0] if args else "all"

    async with async_session_maker() as db:
        orgs = await _orgs(db, target)
        if not orgs:
            print(f"No club found for {target!r}")
            return 1

        total = removed = held_back = 0
        for org in orgs:
            try:
                result = await remove_duplicate_imported_games(db, org.id, apply=apply)
            except Exception as exc:          # one club is never the whole run
                await db.rollback()
                print(f"{org.name}: skipped — {exc}")
                continue
            if not result["duplicates"] and not result["kept_hand_edited"]:
                await db.rollback()
                continue
            print(f"\n{org.name} — {result['imported_games']} imported match(es), "
                  f"{result['duplicates']} duplicate(s) of games you already have")
            for d in result["sample"]:
                print(f"   {d['played_at']}  v {d['opposition'] or '—'}")
            if result["duplicates"] > len(result["sample"]):
                print(f"   … and {result['duplicates'] - len(result['sample'])} more")
            if result["kept_hand_edited"]:
                print(f"   {result['kept_hand_edited']} left alone — edited by hand, "
                      f"so they are the club's own work, not the import's to remove")
            total += result["duplicates"]
            held_back += result["kept_hand_edited"]
            removed += result["removed"]
            if apply:
                await db.commit()
            else:
                await db.rollback()

        print(f"\n{total} duplicate match(es) {'removed' if apply else 'found'}"
              f"{'' if apply else ' — re-run with --apply to remove them'}.")
        if held_back:
            print(f"{held_back} were left alone because somebody has edited them; "
                  f"open those in Manual Entries if they are genuinely duplicates.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
