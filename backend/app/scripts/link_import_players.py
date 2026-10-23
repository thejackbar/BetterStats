"""Join the initial-only players a spreadsheet import created to the synced player they are.

An import that cannot match "Milne, SA" to the club's "Milne, Solomon" mints a second
player, so the person has two half careers and the scorecard pairing (which compares
player ids) cannot see the same match twice. This joins a pair only on evidence: in
the club's paired matches the import's innings and the synced innings agree on surname,
first initial, runs and batting position, for exactly one synced player, and nobody else
of the club shares the label. See services/import_player_link.py for every rule.

Dry run by default: it lists each pair and each player it would leave, and changes
nothing. A merge moves records and never deletes them, and each one is in the merge
log, where it can be undone.

    python -m app.scripts.link_import_players <org-id-or-slug>                  # dry run
    python -m app.scripts.link_import_players <org-id-or-slug> --apply
        [--min-evidence N]   matches that must agree per player (default 1)
        [--limit N]          merge at most N pairs this run (try 20 first)
        [--report PATH]      also write every pair and every held player as CSV
        [--skip "A, B|C, D"] import player names (as listed) the club says are not the same
                             person; they are left out of the plan and not merged

After it, run app.scripts.repair_overwrite_pairs: with one player id per person the
scorecard pairing can finally see the matches the override missed.
"""
from __future__ import annotations

import asyncio
import csv
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import import_player_link


def _opt(name: str, default=None, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv):
        raise SystemExit(f"{name} needs a value")
    return cast(sys.argv[i + 1])


async def run(target: str, apply: bool, min_evidence: int, limit, report, skip=None) -> int:
    async with async_session_maker() as db:
        club = (await db.execute(text(
            "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"),
            {"o": target})).first()
    if not club:
        print(f"No club matching {target!r}.")
        return 1
    res = await import_player_link.link_players(
        club[0], apply=apply, min_evidence=min_evidence, limit=limit, skip=skip)

    print(f"{club[1]}: {res['initial_only']} initial-only import player(s); "
          f"{res['found']} can be joined to a synced player, {len(res['held'])} left.")
    for p in res["pairs"][:400]:
        state = ("merged" if p.get("merged") else
                 "FAILED: " + p["error"] if p.get("error") else "would merge")
        print(f"  {p['remove_name']!r} -> {p['keep_name']!r}  "
              f"({p['matches']} match(es) agree, {p['games']} game(s) moved)  [{state}]")
    if len(res["pairs"]) > 400:
        print(f"  ... and {len(res['pairs']) - 400} more (see --report)")

    why: dict = {}
    for h in res["held"]:
        why.setdefault(h["why"], []).append(h)
    for reason, rows in why.items():
        print(f"\nLeft for a person ({len(rows)}): {reason}")
        for h in rows[:12]:
            extra = f"  vs {', '.join(h['candidate_names'])}" if h["candidate_names"] else ""
            print(f"  {h['remove_name']!r} ({h['games']} game(s)){extra}")
        if len(rows) > 12:
            print(f"  ... and {len(rows) - 12} more")

    if report:
        with open(report, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["action", "remove", "keep_or_candidates", "matches_agreeing",
                        "games_moved", "reason"])
            for p in res["pairs"]:
                w.writerow(["merge" if p.get("merged") or not apply else "failed",
                            p["remove_name"], p["keep_name"], p["matches"], p["games"], ""])
            for h in res["held"]:
                w.writerow(["held", h["remove_name"], "; ".join(h["candidate_names"]), "",
                            h["games"], h["why"]])
        print(f"\nReport written to {report}")

    if apply:
        print(f"\nMerged {res['merged']} pair(s), {res['failed']} failed.")
    else:
        print("\nDry run: nothing written. Run again with --apply.")
    return 0


def main() -> int:
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(
        args[0], "--apply" in sys.argv, _opt("--min-evidence", 1, int),
        _opt("--limit", None, int), _opt("--report"),
        [n for n in (_opt("--skip", "") or "").split("|") if n.strip()]))


if __name__ == "__main__":
    sys.exit(main())
