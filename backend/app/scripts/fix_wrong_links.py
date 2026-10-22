"""Check and fix club scorecards linked to the wrong game, or not linked to the game they match.

The same scan and the same fix as Card review's Possible doubles step, run for a whole club from
the command line. Reported off Shoalwater Bay: a CSV import links a card to the first synced game
that shares a date and an opposition word and ignores grade, so on a day a club plays several
grades against one opposition the B grade card lands on the A grade game, the real B grade game
stays unlinked and counts, and the match is counted twice (once under One Day, once under Two Day).

Dry run by default: prints what the scan found and what the fix would do, and writes nothing.
`--apply` runs the fix as ONE batch, exactly as the "Fix the strong ones" button does:

* every STRONG wrong link is moved to the game that matches the card (most of the smaller card is
  on that game with the same scores), and every strong unlinked pair is linked;
* it repeats (up to --max-rounds, default 3), because a game freed by a moved link may now match
  its own card;
* a link a person confirmed ("Looks right: keep the link") is never touched, and nothing is deleted.

The batch is one audit row (`card_review_bulk`, kind `doubles`) and every card has its own history
line, so it can be undone from the Card review overview or here with `--undo BATCH_ID`.

    python -m app.scripts.fix_wrong_links <org-id-or-slug|all>                   # dry run
    python -m app.scripts.fix_wrong_links <org-id-or-slug|all> --apply
    python -m app.scripts.fix_wrong_links <org-id-or-slug> --undo <batch-id>
    python -m app.scripts.fix_wrong_links <org-id-or-slug> --unlink-wrong-grade [--apply]

`--unlink-wrong-grade` is the step AFTER the fix: a card still linked to a game of another grade (an A
grade card on a B grade game, with no A grade game to move to) is unlinked so it stands alone and the
game counts on its own. Dry run by default; one undoable batch; a link a person confirmed is not touched.

What it does NOT fix, and says so: weaker matches (left for a person in Possible doubles), cards
that already sit on a game that matches them, two cards each on the other's game (a swap with no
free game: `repair_crossed_pairs`), and a Payneham-style history where the club's players are
initials-only records that the scorecards cannot line up (`link_import_players` first).
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from collections import Counter

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import card_review as cr
from app.services import card_review_actions as act
from app.services import card_review_doubles as dbl

KIND_WORDS = {"relink": "wrong link", "ca": "not linked", "club": "two club cards", "swap": "swap"}


def _line(r: dict) -> str:
    a, b = r["a"], r["b"]
    base = f"{r['date'] or '?'}  {a.get('grade') or '?'} v {a.get('opposition') or '?'}"
    if r["kind"] == "swap":
        cur, pt = r.get("current") or {}, (r.get("partner") or {}).get("match") or {}
        return (f"{base}\\n      now on:  {cur.get('grade')} v {cur.get('opposition')} ({cur.get('shared_with_club', 0)} of {a['batters']} batters agree)"
                f"\\n      move to: {b.get('grade')} v {b.get('opposition')} ({r['shared']} of {min(a['batters'], b['batters'])} agree)"
                f"\\n      and the card {pt.get('grade')} v {pt.get('opposition')} ({pt.get('batters', 0)} batters) moves onto {cur.get('grade')} v {cur.get('opposition')}")
    if r["kind"] == "relink":
        cur = r.get("current") or {}
        return (f"{base}\\n      now on:  {cur.get('grade')} v {cur.get('opposition')} "
                f"({cur.get('shared_with_club', 0)} of {a['batters']} batters agree)"
                f"\\n      move to: {b.get('grade')} v {b.get('opposition')} ({r['shared']} of {min(a['batters'], b['batters'])} agree)")
    return f"{base}  ->  {b.get('grade') or '?'} v {b.get('opposition') or '?'}  ({r['shared']} batters agree)"


def tally(found: dict) -> dict:
    c = Counter((r["kind"], r["strength"]) for r in found["rows"])
    return {"strong_relink": c[("relink", "strong")], "strong_link": c[("ca", "strong")], "strong_swap": c[("swap", "strong")],
            "other": sum(n for (k, s), n in c.items() if not (s == "strong" and k in ("relink", "ca", "swap"))),
            "by": {f"{KIND_WORDS[k]} / {s}": n for (k, s), n in sorted(c.items())}}


async def run_org(db, org_id, *, apply: bool, max_rounds: int = 3) -> dict:
    """The report for one club; with `apply`, also runs the fix and the scan again. Pure of printing."""
    found = await dbl.find_doubles(db, org_id)
    before = tally(found)
    review = await cr.review_rows(db, org_id)
    pairing = {r["match_id"] for r in review if r["group"] == "pairing"}
    offered = {r["a"]["id"] for r in found["rows"] if r["kind"] == "relink"}
    left = [r for r in review if r["match_id"] in pairing and r["match_id"] not in offered]
    out = {"before": before, "rows": found["rows"], "pairing_total": len(pairing),
           "pairing_without_a_move": len(pairing - offered), "applied": None, "after": None, "pairing_left": left}
    if apply:
        out["applied"] = await act.bulk_fix_doubles(db, org_id, None, max_rounds=max_rounds)
        out["after"] = tally(await dbl.find_doubles(db, org_id))
    return out


def _print_report(name: str, rep: dict, apply: bool) -> None:
    b = rep["before"]
    print(f"\n=== {name}")
    print("  found: " + (", ".join(f"{n} {k}" for k, n in b["by"].items()) or "nothing"))
    strong = [r for r in rep["rows"] if r["strength"] == "strong" and r["kind"] in ("relink", "ca", "swap")]
    print(f"  the fix would move {b['strong_relink']} wrong link(s), swap {b['strong_swap']} pair(s) of cards and link {b['strong_link']} unlinked pair(s) now"
          f" (a game freed by a move can add more on a later pass)")
    for r in sorted(strong, key=lambda r: ({"relink": 0, "swap": 1}.get(r["kind"], 2), r["date"] or ""))[:12]:
        kind_word = {"relink": "MOVE", "swap": "SWAP"}.get(r["kind"], "LINK")
        print(f"    {kind_word}  " + _line(r).replace("\\n", "\n"))
    if len(strong) > 12:
        print(f"    ... and {len(strong) - 12} more")
    print(f"  left for a person: {b['other']} weaker match(es) in Possible doubles")
    print(f"  'Pairing looks wrong': {rep['pairing_total']}, of which {rep['pairing_without_a_move']} get no move from this scan "
          f"(a swap with no free game, no true twin, or too weak): see repair_crossed_pairs and the Pairing step")
    left = rep.get("pairing_left") or []
    if left:
        print(f"  the cards still 'pairing looks wrong' with no move offered (explain one: python -m app.scripts.explain_card <club> <id>):")
        for r in sorted(left, key=lambda r: str(r["date"]))[:40]:
            print(f"    [{r['match_id'][:8]}] {r['date']}  {r['grade']} v {r['opposition']}  ({r['shared']} of {min(r['club_batters'], r['ca_batters']) or r['club_batters']} batters agree with the game it is on)")
        if len(left) > 40:
            print(f"    ... and {len(left) - 40} more")
    if apply and rep["applied"]:
        a = rep["applied"]
        if not (a["relinked"] or a["linked"] or a["swapped"]):
            print(f"  Nothing to fix: no strong wrong link or strong unlinked pair. No batch was written (skipped {len(a['skipped'])}).")
            return
        print(f"  APPLIED: moved {a['relinked']} link(s), swapped {a['swapped']} pair(s), linked {a['linked']} pair(s), skipped {len(a['skipped'])}.")
        print(f"  BATCH {a['batch_id']}  (undo: --undo {a['batch_id']}, or the Card review overview)")
        for s in a["skipped"][:10]:
            print(f"    skipped {s['match_id'][:8]}: {s['reason']}")
        print(f"  after: {rep['after']['strong_relink']} strong wrong link(s), {rep['after']['strong_swap']} strong swap(s) and {rep['after']['strong_link']} strong unlinked pair(s) remain")


async def _unlink_report(db, name: str, org_id, apply: bool) -> None:
    """Cards on a game of another grade that no move or swap fixes: list them, and with --apply unlink them."""
    rows = await act.wrong_grade_links(db, org_id)
    print(f"\n=== {name}: {len(rows)} card(s) linked to a game of another grade, with no game of their own grade to move to")
    print("    (run the move and swap fix first: a card it can move is not listed here)")
    for r in sorted(rows, key=lambda r: str(r["played_at"])):
        why = "its batters do not appear on that game" if r["verdict"] == "contradicted_grade_differs" else "that game has no batters, or the card has none, to prove it"
        print(f"    [{r['mid'][:8]}] {r['played_at']}  {r['grade']} v {r['opposition']}  is on  {r['g_grade']} v {r['g_opp']}  "
              f"({r['shared']} shared; {r['club_n']} v {r['game_n']} batters): {why}")
    if not rows:
        return
    if not apply:
        print("    DRY RUN: nothing written. With --apply each card is unlinked (one undoable batch) and stands alone; the game counts on its own.")
        return
    res = await act.bulk_unlink_wrong_grade(db, org_id, None)
    print(f"    unlinked {res['unlinked']} card(s), skipped {len(res['skipped'])}.  Undo the whole batch:  --undo {res['batch_id']}")


async def _orgs(db, target: str) -> list:
    if target == "all":
        rows = (await db.execute(text("SELECT o.id::text, o.name FROM organisations o WHERE EXISTS "
                                      "(SELECT 1 FROM manual_games m WHERE m.organisation_id = o.id) ORDER BY o.name"))).all()
    else:
        rows = (await db.execute(text("SELECT id::text, name FROM organisations WHERE id::text = :t OR slug = :t"),
                                 {"t": target})).all()
    return [(r[0], r[1]) for r in rows]


async def main(target: str, apply: bool, undo: str | None, max_rounds: int, unlink_wrong_grade: bool = False) -> int:
    async with async_session_maker() as db:
        orgs = await _orgs(db, target)
        if not orgs:
            print(f"No club '{target}'.")
            return 2
        print("APPLYING" if apply else "UNDOING" if undo else "DRY RUN: nothing is written (pass --apply to fix)")
        for org_id, name in orgs:
            if undo:
                res = await act.bulk_undo(db, org_id, None, uuid.UUID(undo))
                print(f"\n=== {name}: undid {res['undone']} change(s); left alone (changed since): {len(res['left_alone'])}")
                continue
            if unlink_wrong_grade:
                await _unlink_report(db, name, org_id, apply)
                continue
            _print_report(name, await run_org(db, org_id, apply=apply, max_rounds=max_rounds), apply)
    return 0


if __name__ == "__main__":
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--undo", "--max-rounds")]
    if not args:
        print(__doc__)
        sys.exit(2)

    def opt(name, default=None):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    sys.exit(asyncio.run(main(args[0], "--apply" in sys.argv, opt("--undo"), int(opt("--max-rounds", 3)),
                              "--unlink-wrong-grade" in sys.argv)))
