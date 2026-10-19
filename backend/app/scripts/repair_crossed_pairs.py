"""Move the import matches an override paired with the wrong synced game.

A club that plays several grades against one opposition on one day (junior cricket)
got its sheet matches paired crosswise by the import's date-and-opposition rule: the
Under 13 sheet match hides the Under 11 synced match and the other way round. Totals
are right either way, but the wrong card sits behind each match. This uses the
scorecards, which now line up because the club's players are one record each
(`link_import_players`), and moves a pair only where a swap or cycle of pairs gives
every sheet match a synced game it shares MORE scores with. See
services/crossed_pairs.py for every rule.

Dry run by default. Run `link_import_players` and `repair_overwrite_pairs` first.

    python -m app.scripts.repair_crossed_pairs <org-id-or-slug>             # dry run
    python -m app.scripts.repair_crossed_pairs <org-id-or-slug> --apply
        [--skip ID[,ID...]]   leave these sheet matches where they are (the 8 character
                              id the dry run prints); a skipped match also holds back
                              the rest of its swap
        [--report PATH]       write every move and every held pair as CSV

A moved pair is written to the audit log with where it came from. There is no
single-pair undo: put one back by moving it again, or undo the whole import.
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import crossed_pairs


def _opt(name: str, default=None):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} needs a value")
    return sys.argv[i + 1]


def _line(m: dict) -> str:
    return (f"      {m['season']}: import {m['import_date']} v {m['import_opp'] or '?'}  "
            f"[{m['manual_game_id'][:8]}]\n"
            f"          was  synced {m['from_date']} v {m['from_opp'] or '?'}  "
            f"({m['from_shared']} shared scores)\n"
            f"          now  synced {m['to_date']} v {m['to_opp'] or '?'}  "
            f"({m['to_shared']} shared scores)")


async def run(target: str, apply: bool, skip: list[str], report) -> int:
    async with async_session_maker() as db:
        club = (await db.execute(text(
            "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": target})).first()
    if not club:
        print(f"No club matching {target!r}.")
        return 1
    print("APPLYING" if apply else "DRY RUN — nothing written (pass --apply to move)")
    async with async_session_maker() as db:
        res = await crossed_pairs.repair_org(db, club[0], apply=apply, skip=skip)
    print(f"  {club[1]}: {res['paired']} import match(es) paired to a synced game, "
          f"{len(res['moves'])} {'moved' if apply else 'would move'}, "
          f"{len(res['held'])} held back")
    for m in sorted(res["moves"], key=lambda x: (x["season"], str(x["import_date"]))):
        print(_line(m))
    if res.get("skipped"):
        print("    skipped by --skip, left where they are:")
        for m in res["skipped"]:
            print(f"      {m['season']}: import {m['import_date']} v {m['import_opp'] or '?'}  "
                  f"[{m['manual_game_id'][:8]}]")
    if res["held"]:
        print("    held back: a move would not be a closed swap, so a synced game would be "
              "left uncovered or taken twice. Look at these by hand:")
        for m in sorted(res["held"], key=lambda x: (x["season"], str(x["import_date"]))):
            print(_line(m))
    if report:
        with open(report, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["action", "manual_game_id", "season", "import_date", "import_opp",
                        "from_date", "from_opp", "from_shared", "to_date", "to_opp", "to_shared"])
            for tag, rows in (("move", res["moves"]), ("held", res["held"]),
                              ("skipped", res.get("skipped", []))):
                for m in rows:
                    w.writerow([tag, m["manual_game_id"], m["season"], m["import_date"],
                                m["import_opp"], m["from_date"], m["from_opp"], m["from_shared"],
                                m["to_date"], m["to_opp"], m["to_shared"]])
        print(f"\nReport written to {report}")
    return 0


def main() -> int:
    skip_val = _opt("--skip")
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and not (i > 1 and sys.argv[i - 1] in ("--skip", "--report"))]
    if len(args) != 1:
        print(__doc__)
        return 2
    skip = [x.strip() for x in skip_val.split(",") if x.strip()] if skip_val else []
    return asyncio.run(run(args[0], "--apply" in sys.argv, skip, _opt("--report")))


if __name__ == "__main__":
    sys.exit(main())
