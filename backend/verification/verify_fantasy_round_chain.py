"""A club whose two day games start on alternate Saturdays must not read as one long round.

Reported (Sunbury CC, Nov 2026): four players on the scorecard of a 7 Nov game scored nothing in
Fantasy and the rounds did not follow the draw. The cause was in how the draw is cut into rounds.
`fantasy_engine._group_rounds` joins every week a two day game touches into one round, and joins
transitively. Sunbury's two day grades start a game on a Saturday every week from 31 Oct, each running
into the next Saturday, so every week was bridged to the next and the whole run from 30 Oct to
20 Dec came out as ONE round (round 4). It locks at its first kick-off, so managers could make no
transfer for seven weeks, and it could not be scored until the 20th of December.

The spans below are the real first and last match day of every Sunbury match in the 2026/27 draw,
read from Cricket Australia (one pair per distinct span, 133 matches). No database: it drives the
shipped `_group_rounds`.

CONTROL: on the commit before this change `_group_rounds` returns one window from 30 Oct to 20 Dec,
so the checks that name a long round fail (reported as failures, not a crash).

Run:  python verification/verify_fantasy_round_chain.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from app.services import fantasy_engine as fe

PASS = FAIL = 0
LIMIT = getattr(fe, "MAX_ROUND_SPAN_DAYS", 14)


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def d(s: str) -> date:
    return date.fromisoformat(s)


# Distinct (first day, last day) of every Sunbury match in the 2026/27 draw.
SUNBURY = [
    ("2026-10-03", "2026-10-03"),
    ("2026-10-04", "2026-10-04"),
    ("2026-10-10", "2026-10-10"),
    ("2026-10-11", "2026-10-11"),
    ("2026-10-17", "2026-10-17"),
    ("2026-10-17", "2026-10-24"),
    ("2026-10-18", "2026-10-18"),
    ("2026-10-23", "2026-10-23"),
    ("2026-10-24", "2026-10-24"),
    ("2026-10-25", "2026-10-25"),
    ("2026-10-30", "2026-10-30"),
    ("2026-10-31", "2026-11-07"),
    ("2026-11-01", "2026-11-01"),
    ("2026-11-01", "2026-11-08"),
    ("2026-11-06", "2026-11-06"),
    ("2026-11-07", "2026-11-07"),
    ("2026-11-07", "2026-11-14"),
    ("2026-11-08", "2026-11-08"),
    ("2026-11-10", "2026-11-10"),
    ("2026-11-13", "2026-11-13"),
    ("2026-11-14", "2026-11-14"),
    ("2026-11-14", "2026-11-21"),
    ("2026-11-15", "2026-11-15"),
    ("2026-11-17", "2026-11-17"),
    ("2026-11-20", "2026-11-20"),
    ("2026-11-21", "2026-11-21"),
    ("2026-11-21", "2026-11-28"),
    ("2026-11-22", "2026-11-22"),
    ("2026-11-24", "2026-11-24"),
    ("2026-11-27", "2026-11-27"),
    ("2026-11-28", "2026-11-28"),
    ("2026-11-28", "2026-12-05"),
    ("2026-11-29", "2026-11-29"),
    ("2026-12-04", "2026-12-04"),
    ("2026-12-05", "2026-12-05"),
    ("2026-12-05", "2026-12-12"),
    ("2026-12-06", "2026-12-06"),
    ("2026-12-08", "2026-12-08"),
    ("2026-12-11", "2026-12-11"),
    ("2026-12-12", "2026-12-12"),
    ("2026-12-12", "2026-12-19"),
    ("2026-12-13", "2026-12-13"),
    ("2026-12-19", "2026-12-19"),
    ("2026-12-20", "2026-12-20"),
    ("2027-01-09", "2027-01-09"),
    ("2027-01-10", "2027-01-10"),
    ("2027-01-12", "2027-01-12"),
    ("2027-01-16", "2027-01-16"),
    ("2027-01-16", "2027-01-23"),
    ("2027-01-17", "2027-01-17"),
    ("2027-01-24", "2027-01-24"),
    ("2027-01-29", "2027-01-29"),
    ("2027-01-30", "2027-01-30"),
    ("2027-01-30", "2027-02-06"),
    ("2027-01-31", "2027-01-31"),
    ("2027-02-05", "2027-02-05"),
    ("2027-02-06", "2027-02-06"),
    ("2027-02-06", "2027-02-13"),
    ("2027-02-07", "2027-02-07"),
    ("2027-02-12", "2027-02-12"),
    ("2027-02-13", "2027-02-13"),
    ("2027-02-13", "2027-02-20"),
    ("2027-02-19", "2027-02-19"),
    ("2027-02-20", "2027-02-20"),
    ("2027-02-20", "2027-02-27"),
    ("2027-02-26", "2027-02-26"),
    ("2027-02-27", "2027-02-27"),
]
SUNBURY = [(d(a), d(b)) for a, b in SUNBURY]


def longest(rounds) -> int:
    return max((b - a).days for a, b in rounds)


print("\n-- 1. The real Sunbury draw --")
rounds = fe._group_rounds(SUNBURY)
check("no round is longer than two weeks (before the change one ran 30 Oct to 20 Dec, 51 days)",
      longest(rounds) <= LIMIT,
      f"longest {longest(rounds)} days: " + ", ".join(f"{a}..{b}" for a, b in rounds if (b - a).days > LIMIT))
check("the first three rounds are untouched (3 is the 17 to 25 Oct pair of weeks a two day game bridges)",
      rounds[:3] == [(d("2026-10-03"), d("2026-10-04")), (d("2026-10-10"), d("2026-10-11")),
                     (d("2026-10-17"), d("2026-10-25"))], str(rounds[:3]))
check("round 4 is 30 Oct to 5 Nov", rounds[3] == (d("2026-10-30"), d("2026-11-05")), str(rounds[3]))
check("round 5 is 6 to 9 Nov, which holds the 7 Nov game", rounds[4] == (d("2026-11-06"), d("2026-11-09")),
      str(rounds[4]))
check("the rounds tile: each starts the day after the one before ends, inside the long run",
      all(b + timedelta(days=1) == nxt[0] for (a, b), nxt in zip(rounds[3:10], rounds[4:11])),
      str(rounds[3:11]))


def round_of(day: date):
    return next((i + 1 for i, (a, b) in enumerate(rounds) if a <= day <= b), None)


gaps = [x for x in (d("2026-10-30") + timedelta(days=n) for n in range(0, 51)) if round_of(x) is None]
check("every date from 30 Oct to 19 Dec falls in a round (none in a gap)", not gaps, str(gaps))
check("both days of a two day game started 31 Oct (31 Oct and 7 Nov) have a round",
      bool(round_of(d("2026-10-31")) and round_of(d("2026-11-07"))))
r7 = round_of(d("2026-11-07"))
check("7 Nov, the game in the report, is in a round no longer than two weeks",
      r7 is not None and (rounds[r7 - 1][1] - rounds[r7 - 1][0]).days <= LIMIT, str(r7))

print("\n-- 2. Windows that were right stay exactly as they were --")
check("a Sat/Sun weekend is one round",
      fe._group_rounds([(d("2026-10-03"), d("2026-10-03")), (d("2026-10-04"), d("2026-10-04"))])
      == [(d("2026-10-03"), d("2026-10-04"))])
check("a two day game a week apart bridges its two weeks into ONE round (the Applecross case)",
      fe._group_rounds([(d("2026-10-17"), d("2026-10-24")), (d("2026-10-18"), d("2026-10-18"))])
      == [(d("2026-10-17"), d("2026-10-24"))])
two_weeks = [(d("2026-10-17"), d("2026-10-24")), (d("2026-10-24"), d("2026-10-24"))]
check("two bridged weeks stay one round (8 days)",
      fe._group_rounds(two_weeks) == [(d("2026-10-17"), d("2026-10-24"))], str(fe._group_rounds(two_weeks)))
three_weeks = [(d("2026-10-17"), d("2026-10-24")), (d("2026-10-24"), d("2026-10-31"))]
check("a chain of three weeks (14 days) is the longest that stays one round",
      fe._group_rounds(three_weeks) == [(d("2026-10-17"), d("2026-10-31"))], str(fe._group_rounds(three_weeks)))
four_weeks = three_weeks + [(d("2026-10-31"), d("2026-11-07"))]
check("a fourth bridged week (21 days) is cut into weekends",
      len(fe._group_rounds(four_weeks)) == 3, str(fe._group_rounds(four_weeks)))
check("a bye week between two rounds still separates them",
      fe._group_rounds([(d("2026-10-03"), d("2026-10-04")), (d("2026-10-17"), d("2026-10-18"))])
      == [(d("2026-10-03"), d("2026-10-04")), (d("2026-10-17"), d("2026-10-18"))])
check("no spans, no rounds", fe._group_rounds([]) == [])

print("\n-- 3. A generated chain, any club --")
chain = [(d("2026-11-07") + timedelta(days=7 * i), d("2026-11-14") + timedelta(days=7 * i)) for i in range(10)]
rs = fe._group_rounds(chain)
check("ten weeks of weekly two day games give ten rounds, not one", len(rs) == 10, f"{len(rs)}: {rs[:3]}")
check("each round is one week long", all((b - a).days <= 7 for a, b in rs[:-1]), str(rs[:3]))
check("the last round reaches the final second day", rs[-1][1] == chain[-1][1], str(rs[-1]))
check("the first round starts on the first match day", rs[0][0] == d("2026-11-07"), str(rs[0]))

print("\n-- 4. A round already scored is never re-cut (Gisborne, Nov 2026) --")
# Gisborne's round 3 was scored as 13 to 31 Oct (18 days, a chain of bridged weeks). Cutting it now would give
# the unscored round after it dates inside the scored one and score those games twice.
gis = [(d("2026-10-13"), d("2026-10-13")), (d("2026-10-17"), d("2026-10-24")), (d("2026-10-24"), d("2026-10-31")),
       (d("2026-10-31"), d("2026-10-31")), (d("2026-11-06"), d("2026-11-14")), (d("2026-11-14"), d("2026-11-21"))]
frozen = [(d("2026-10-13"), d("2026-10-31"))]
got = fe._group_rounds(gis, frozen)
check("a scored 18 day round stays exactly as scored", got[0] == (d("2026-10-13"), d("2026-10-31")), str(got))
check("no round after it starts inside it",
      all(a > d("2026-10-31") for a, _b in got[1:]), str(got))
check("without the frozen window the same draw is cut (so the protection is what holds it)",
      fe._group_rounds(gis)[0] != (d("2026-10-13"), d("2026-10-31")), str(fe._group_rounds(gis)))
chain2 = [(d("2026-11-07") + timedelta(days=7 * i), d("2026-11-14") + timedelta(days=7 * i)) for i in range(6)]
got2 = fe._group_rounds(chain2, [(d("2026-11-07"), d("2026-11-14"))])
check("a short scored round at the head of a long chain keeps its window and the rest is still cut weekly",
      got2[0] == (d("2026-11-07"), d("2026-11-14")) and len(got2) >= 5 and all((b - a).days <= 7 for a, b in got2[1:-1]), str(got2))
check("a scored round elsewhere does not stop a long chain being cut",
      len(fe._group_rounds(chain2, [(d("2026-09-01"), d("2026-09-02"))])) == 6)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
