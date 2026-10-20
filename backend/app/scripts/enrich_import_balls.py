"""Copy balls faced from the synced card onto the import match that replaced it.

An overwrite import keeps only what the club's file carried, and a scorebook has no
balls faced. The synced rows are still there, so this reads them back onto the import's
own batting lines: same player, same runs, same batting position, balls recorded above
zero, exactly one line that fits, and only where the import line has no balls yet. See
services/import_balls_enrich.py.

Dry run by default. Run it after `link_import_players`, `repair_overwrite_pairs` and
`repair_crossed_pairs`, so the players and the pairs are right first.

    python -m app.scripts.enrich_import_balls <org-id-or-slug>             # dry run
    python -m app.scripts.enrich_import_balls <org-id-or-slug> --apply
        [--limit N]          fill at most N lines this run (try 200 first)
    python -m app.scripts.enrich_import_balls <org-id-or-slug> --undo AUDIT_ID

`--apply` prints the audit id. `--undo` puts that run's lines back to NULL, leaving any a
person has corrected since.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import import_balls_enrich


def _opt(name, default=None, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} needs a value")
    return cast(sys.argv[i + 1])


async def run(target, apply, limit, undo) -> int:
    async with async_session_maker() as db:
        club = (await db.execute(text(
            "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": target})).first()
    if not club:
        print(f"No club matching {target!r}.")
        return 1
    async with async_session_maker() as db:
        if undo is not None:
            n = await import_balls_enrich.undo_org(db, club[0], audit_id=undo)
            print(f"{club[1]}: put {n} line(s) back to no balls faced (audit entry {undo}).")
            return 0
        res = await import_balls_enrich.enrich_org(db, club[0], apply=apply, limit=limit)
    print("APPLYING" if apply else "DRY RUN: nothing written (pass --apply to fill)")
    print(f"  {club[1]}: {len(res['lines'])} batting line(s) in {res['games']} match(es) can "
          f"take balls faced; {res['ambiguous']} line(s) have more than one fit and are left")
    for season, v in res["by_season"].items():
        print(f"      {season}: {v['lines']} line(s) in {v['games']} match(es)")
    if apply:
        print(f"\nFilled {res['filled']} line(s). Audit id {res.get('audit_id')} "
              f"(undo with --undo {res.get('audit_id')}).")
    return 0


def main() -> int:
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and not (i > 1 and sys.argv[i - 1] in ("--limit", "--undo"))]
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(args[0], "--apply" in sys.argv, _opt("--limit", None, int),
                           _opt("--undo", None, int)))


if __name__ == "__main__":
    sys.exit(main())
