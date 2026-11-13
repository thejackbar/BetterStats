"""bowler_wickets: name the bowler or fielder CA left out of a dismissal's text, by elimination.

Reported on Ryan Carmody's fielding list: 90 stumpings in the headline, 71 paired to a bowler. The
scorecard text for the rest reads `st:  b: ` (no names) or `st:  b: S Shub` (no keeper), so the
extractor wrote no row (bowler_id is NOT NULL) or a row with no fielder, while the card's own
bowling rows (`wicketsTaken`) and fielding rows (`catches`, `wicketKeeperCatches`, `stumpings`)
still say who did what. The extractor now fills a blank when exactly one answer fits.

Pure: runs the SHIPPED `sync.extract_bowler_wickets` on hand-built cards shaped like the real ones
(the 2008-12-13, 2010-10-09 and 2021-01-24 Applecross games). No database.

Run:  SECRET_KEY=x python verification/verify_bowler_wicket_recovery.py
Control (previous sync.py): the recovery cases fail and the fully-named case still passes.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://root@/none?host=/var/run/postgresql")

from app.services.sync import extract_bowler_wickets

PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


class Cast:
    """Participants by short name, our ids and a gate of the ones that are ours."""
    def __init__(self, ours, theirs=()):
        self.guid = {n: str(uuid.uuid4()) for n in (*ours, *theirs)}
        self.ours = {n: uuid.uuid4() for n in ours}
        self.pid_by_guid = {uuid.UUID(self.guid[n]): self.ours[n] for n in ours}
        self.gate = set(self.ours.values())

    def name_of(self, pid):
        inv = {v: k for k, v in self.ours.items()}
        return inv.get(pid)


def card(cast, dismissals, bowling, fielding):
    """dismissals: [(dismissalType, text)]; bowling: {name: wickets}; fielding: {name: (catches, wk, stumpings)}"""
    return {
        "teams": [{"players": [{"participantId": g, "playerShortName": n} for n, g in cast.guid.items()]}],
        "innings": [{
            "inningsOrder": 1,
            "batting": [{"dismissalType": dt, "dismissalText": tx, "playerShortName": f"Batter{i}",
                         "batOrder": i + 1, "runsScored": 10, "ballsFaced": 12}
                        for i, (dt, tx) in enumerate(dismissals)],
            "bowling": [{"participantId": cast.guid[n], "playerShortName": n, "wicketsTaken": w}
                        for n, w in bowling.items()],
            "fielding": [{"participantId": cast.guid[n], "playerShortName": n, "catches": c,
                          "wicketKeeperCatches": wk, "stumpings": st}
                         for n, (c, wk, st) in fielding.items()],
        }],
    }


def run(cast, c):
    rows = extract_bowler_wickets(c, uuid.uuid4(), cast.gate, cast.pid_by_guid, {})
    return [(cast.name_of(r.bowler_id), cast.name_of(r.fielder_id), r.dismissal_type, r.caught_behind) for r in rows]


def main():
    print("\n-- blank keeper, bowler named (2008-12-13) --")
    c = Cast(["S Shub", "R Carmody", "J Other"])
    got = run(c, card(c, [("Stumped", "st:  b: S Shub")], {"S Shub": 1}, {"R Carmody": (0, 0, 1)}))
    check("the stumping is Shub's, taken by Carmody", got == [("S Shub", "R Carmody", "stumped", False)], str(got))

    print("\n-- both names blank, one bowler with wickets unaccounted for (2021-01-24) --")
    c = Cast(["S Shub", "R Carmody", "J Other"])
    got = run(c, card(c, [("Stumped", "st:  b: "), ("Stumped", "st:  b: ")],
                      {"S Shub": 2, "J Other": 0}, {"R Carmody": (0, 0, 2)}))
    check("both stumpings are Shub's, taken by Carmody",
          got == [("S Shub", "R Carmody", "stumped", False)] * 2, str(got))

    print("\n-- partly named (2010-10-09) --")
    c = Cast(["C Ince", "A Shan", "R Carmody"])
    got = run(c, card(c, [("Stumped", "st:  b: C Ince"), ("Stumped", "st: R Carmody b: C Ince"),
                          ("Stumped", "st: R Carmody b: A Shan")],
                      {"C Ince": 2, "A Shan": 1}, {"R Carmody": (0, 0, 3)}))
    check("the blank keeper is Carmody (3 stumpings, 2 named)",
          sorted(map(str, got)) == sorted(map(str, [("C Ince", "R Carmody", "stumped", False)] * 2
                                              + [("A Shan", "R Carmody", "stumped", False)])), str(got))

    print("\n-- ambiguity is left alone --")
    c = Cast(["S Shub", "J Other", "R Carmody"])
    got = run(c, card(c, [("Stumped", "st:  b: "), ("Stumped", "st:  b: ")],
                      {"S Shub": 1, "J Other": 1}, {"R Carmody": (0, 0, 2)}))
    check("two bowlers each owed a wicket: no bowler is guessed, no row written", got == [], str(got))
    c = Cast(["S Shub", "R Carmody"])
    got = run(c, card(c, [("Stumped", "st:  b: "), ("Stumped", "st:  b: ")], {"S Shub": 1}, {"R Carmody": (0, 0, 2)}))
    check("a shortfall smaller than the blanks (1 owed, 2 blank) is not forced", got == [], str(got))
    c = Cast(["S Shub", "R Carmody", "K Keeper2"])
    got = run(c, card(c, [("Stumped", "st:  b: S Shub")], {"S Shub": 1},
                      {"R Carmody": (0, 0, 1), "K Keeper2": (0, 0, 1)}))
    check("two keepers each owed a stumping: the bowler is kept, the keeper is not guessed",
          got == [("S Shub", None, "stumped", False)], str(got))
    c = Cast(["S Shub", "R Carmody"])
    got = run(c, card(c, [("Stumped", "st: Z Nobody b: S Shub"), ("Stumped", "st:  b: S Shub")],
                      {"S Shub": 2}, {"R Carmody": (0, 0, 2)}))
    check("a NAMED keeper who matched nobody could be the missing one: nothing is filled in",
          got == [("S Shub", None, "stumped", False)] * 2, str(got))

    print("\n-- the club gate still holds --")
    c = Cast(["R Carmody"], theirs=["Their Bowler"])
    got = run(c, card(c, [("Stumped", "st:  b: ")], {"Their Bowler": 1}, {"R Carmody": (0, 0, 1)}))
    check("a wicket recovered to the OTHER side's bowler is not ours: no row", got == [], str(got))

    print("\n-- catches --")
    c = Cast(["S Shub", "R Carmody", "J Other"])
    got = run(c, card(c, [("Caught", "c:  b: S Shub")], {"S Shub": 1}, {"R Carmody": (0, 1, 0)}))
    check("a blank catcher who is the one keeper with a catch: caught behind", got == [("S Shub", "R Carmody", "caught", True)], str(got))
    got = run(c, card(c, [("Caught", "c:  b: S Shub")], {"S Shub": 1}, {"J Other": (1, 0, 0)}))
    check("a blank catcher with an ordinary catch: not behind", got == [("S Shub", "J Other", "caught", False)], str(got))
    got = run(c, card(c, [("Caught", "c:  b: S Shub")], {"S Shub": 1}, {"J Other": (1, 0, 0), "R Carmody": (0, 1, 0)}))
    check("two fielders each owed a catch: the catcher is not guessed", got == [("S Shub", None, "caught", False)], str(got))
    got = run(c, card(c, [("Caught", "c & b: S Shub"), ("Caught", "c:  b: S Shub")], {"S Shub": 2},
                      {"S Shub": (1, 0, 0), "J Other": (1, 0, 0)}))
    check("the bowler's own caught-and-bowled is not taken for the blank catcher",
          got == [("S Shub", None, "caught and bowled", False), ("S Shub", "J Other", "caught", False)], str(got))

    print("\n-- nothing changes where the text already names everyone --")
    c = Cast(["S Shub", "R Carmody", "J Other"])
    got = run(c, card(c, [("Stumped", "st: R Carmody b: S Shub"), ("Caught", "c: J Other b: S Shub"),
                          ("Bowled", "b: S Shub"), ("LBW", "lbw b: S Shub")],
                      {"S Shub": 4}, {"R Carmody": (0, 0, 1), "J Other": (1, 0, 0)}))
    check("named wickets read exactly as before",
          got == [("S Shub", "R Carmody", "stumped", False), ("S Shub", "J Other", "caught", False),
                  ("S Shub", None, "bowled", False), ("S Shub", None, "lbw", False)], str(got))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
