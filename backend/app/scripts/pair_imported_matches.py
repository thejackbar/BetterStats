"""Work out again which imported match the Cricket Australia sync also holds.

A club that syncs from CA and has also imported its CricketStatz history holds
many of the same matches twice, and `services/match_pairing.py` is what counts
each one once. That pass runs as an import goes, after a full sync, once at
boot and nightly — but a club stuck counting both sources needs a way to fix it
now and to see what happened, without waiting for any of those.

Reports what it found per club and never guesses: a match it cannot pair is
left counted on its own, which is visible, rather than paired to the wrong
fixture, which is not.

    python -m app.scripts.pair_imported_matches                 # every club, dry run
    python -m app.scripts.pair_imported_matches <org|all> --apply
"""
from __future__ import annotations

import asyncio
import sys
import time

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import match_pairing


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    which = args[0] if args else "all"

    async with async_session_maker() as db:
        if which == "all":
            orgs = (await db.execute(text("""
                SELECT DISTINCT mg.organisation_id, o.name
                  FROM manual_games mg
                  JOIN organisations o ON o.id = mg.organisation_id
                 WHERE mg.cricketstatz_import_id IS NOT NULL
                 ORDER BY o.name
            """))).all()
        else:
            orgs = (await db.execute(text("""
                SELECT id, name FROM organisations
                 WHERE id::text = :o OR slug = :o
            """), {"o": which})).all()
            if not orgs:
                raise SystemExit(f"no club matches {which!r}")

    if not orgs:
        print("No club holds a CricketStatz import.")
        return

    for org_id, name in orgs:
        started = time.perf_counter()
        try:
            async with async_session_maker() as db:
                res = await match_pairing.reconcile_org(db, org_id, commit=apply)
        except Exception as exc:  # one club is never the whole run
            print(f"  {name}: FAILED — {type(exc).__name__}: {exc}")
            continue
        took = time.perf_counter() - started
        print(f"  {name}: {res['imported']} imported, {res['synced']} synced -> "
              f"{res['paired']} paired "
              f"({res['only_cricketstatz']} only CricketStatz, "
              f"{res['only_synced']} only Cricket Australia), "
              f"{res['changed']} row(s) {'written' if apply else 'would change'} "
              f"[{took:.1f}s]")
    if not apply:
        print("\nDry run — nothing written. Re-run with --apply.")


if __name__ == "__main__":
    asyncio.run(main())
