"""Copy the match detail an override hid back onto the import that replaced it.

An overwrite import keeps only what the club's file carried. A scorebook names nobody on a
dismissal and has few falls of wickets and no partnerships, while the synced rows PlayHQ
held are still in the database and the manual side has tables that mirror them. This
reads them back: fall of wickets and partnerships (per innings, only where the import has
none) and who took each wicket (per match, only where every bowler's wickets on the card
equal what PlayHQ credits him). See services/import_detail_restore.py for every rule.

Dry run by default. Run it after `link_import_players`, `repair_overwrite_pairs` and
`repair_crossed_pairs`, so the players and the pairs are right first.

    python -m app.scripts.restore_import_detail <org-id-or-slug>             # dry run
    python -m app.scripts.restore_import_detail <org-id-or-slug> --apply
    python -m app.scripts.restore_import_detail <org-id-or-slug> --undo AUDIT_ID

`--apply` prints the audit id. `--undo` removes exactly the rows that run inserted.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import import_detail_restore as idr


def _opt(name, default=None, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} needs a value")
    return cast(sys.argv[i + 1])


async def run(target, apply, undo) -> int:
    async with async_session_maker() as db:
        club = (await db.execute(text(
            "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": target})).first()
    if not club:
        print(f"No club matching {target!r}.")
        return 1
    async with async_session_maker() as db:
        if undo is not None:
            r = await idr.undo_org(db, club[0], audit_id=undo)
            print(f"{club[1]}: removed {r['fow']} fall-of-wicket row(s), {r['part']} "
                  f"partnership row(s), {r['bw']} wicket credit(s) (audit entry {undo}).")
            return 0
        res = await idr.restore_org(db, club[0], apply=apply)
    print("APPLYING" if apply else "DRY RUN: nothing written (pass --apply to write)")
    print(f"  {club[1]}: {res['paired']} import match(es) paired to a synced game; "
          f"{res['matches']} would gain detail")
    print(f"      fall of wickets: {len(res['fow'])} row(s)")
    print(f"      partnerships:    {len(res['part'])} row(s)")
    print(f"      wicket credits (bowler and fielder named): {len(res['bw'])} row(s)")
    for season, n in res["by_season"].items():
        print(f"      {season}: {n} match(es)")
    for why, rows in res["skipped"].items():
        print(f"    skipped, {why}: {len(rows)} match(es)")
    if apply:
        w = res["written"]
        print(f"\nWrote {w['fow']} fall of wickets, {w['part']} partnerships, {w['bw']} credits. "
              f"Audit id {res.get('audit_id')} (undo with --undo {res.get('audit_id')}).")
    return 0


def main() -> int:
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and not (i > 1 and sys.argv[i - 1] == "--undo")]
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(args[0], "--apply" in sys.argv, _opt("--undo", None, int)))


if __name__ == "__main__":
    sys.exit(main())
