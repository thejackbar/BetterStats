"""A results post must list OUR bowlers under our club, not the opposition's.

Reported (North Perth, October 2026): the results posts show "our batters' stats alongside
the opposition's bowlers, instead of our own bowling figures".

An innings' `batting` is the side that batted it and its `bowling` is the side that was
FIELDING. So a side's own bowlers sit in the innings the OTHER side batted. The round results
builder (`social_rounds._result_row`) read its "top wicket takers" out of the innings we
batted, which is the opposition's bowling, and labelled them ours. The player of the match
ranking in the same module already had it right.

Pure: `_result_row` reads a raw Cricket Australia scorecard and a club, no database. Scenarios:

  ours     our top batters are the ones who scored in our innings
  bowlers  our top wicket takers are the ones in the OPPOSITION's innings
  theirs   the opposition's batters and bowlers come back as well, the other way round
  shape    a side with no innings yet still gives empty lists, not a missing key

Run:  python verification/verify_result_performers.py
The control run is the same script against the previous social_rounds.py: `bowlers` fails
(the figures are the opposition's) and `theirs` reports the keys as absent.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from app.services.social_rounds import _result_row

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OPP = str(uuid.uuid4()), str(uuid.uuid4())
OURS_T, THEIRS_T = str(uuid.uuid4()), str(uuid.uuid4())
club = SimpleNamespace(id=uuid.UUID(ORG), name="North Perth Cricket Club", short_name="NPCC", playhq_id=None)


def bat(name, runs, balls, dt_id=2, dt="Bowled"):
    return {"playerShortName": name, "runsScored": runs, "ballsFaced": balls,
            "dismissalTypeId": dt_id, "dismissalType": dt, "participantId": str(uuid.uuid4())}


def bowl(name, w, r, overs):
    return {"playerShortName": name, "wicketsTaken": w, "runsConceded": r, "oversBowled": overs,
            "participantId": str(uuid.uuid4())}


def card(ours_batted=True, theirs_batted=True):
    """We batted first (a 6/188), they chased (all out 184). Each innings' bowling is the OTHER side's."""
    innings = []
    if ours_batted:
        innings.append({
            "inningsOrder": 1, "battingTeamId": OURS_T, "runsScored": 188, "numberOfWicketsFallen": 6,
            "batting": [bat("J Barendse", 64, 71), bat("T Mcnamee", 39, 58), bat("Z Filler", 3, 9)],
            # bowled by THEM
            "bowling": [bowl("M Kelly", 3, 44, 10), bowl("T Hughes", 1, 51, 9)],
        })
    if theirs_batted:
        innings.append({
            "inningsOrder": 2, "battingTeamId": THEIRS_T, "runsScored": 184, "numberOfWicketsFallen": 10,
            "batting": [bat("S Grant", 71, 88), bat("D Price", 34, 49), bat("Q Filler", 2, 7)],
            # bowled by US
            "bowling": [bowl("A Allison", 4, 29, 9.4), bowl("S Roberts", 2, 26, 8)],
        })
    return {
        "matchSummary": {"result": "Won by 4 runs", "teams": [
            {"id": OURS_T, "isWinner": True, "resultType": "WON"}, {"id": THEIRS_T, "resultType": "LOST"}]},
        "teams": [
            {"id": OURS_T, "displayName": "North Perth 1st XI", "owningOrganisation": {"id": ORG}},
            {"id": THEIRS_T, "displayName": "Opponents 1st XI", "owningOrganisation": {"id": OPP, "name": "Opponents"}},
        ],
        "innings": innings,
    }


def names(rows):
    return [r.get("name") for r in (rows or [])]


def main() -> None:
    print("\n-- a finished match --")
    row = _result_row(card(), club, ["north perth"], "1st Grade")
    check("a row comes back", row is not None)
    check("our top scorers are the ones who scored in our innings", names(row["topBat"]) == ["J. BARENDSE", "T. MCNAMEE"], str(row["topBat"]))
    check("our top wicket takers are the ones from the OPPOSITION's innings (we were bowling)",
          names(row["topBowl"]) == ["A. ALLISON", "S. ROBERTS"], str(row["topBowl"]))
    check("and not the opposition's bowlers", not ({"M. KELLY", "T. HUGHES"} & set(names(row["topBowl"]))), str(row["topBowl"]))
    check("the figures are ours too (4/29 off 9.4)", (row["topBowl"] or [{}])[0].get("line") == "4/29 (9.4)", str(row["topBowl"]))

    print("\n-- the opposition's lists --")
    check("their top scorers", names(row.get("oppTopBat")) == ["S. GRANT", "D. PRICE"], str(row.get("oppTopBat")))
    check("their wicket takers are the ones from OUR innings (they were bowling)",
          names(row.get("oppTopBowl")) == ["M. KELLY", "T. HUGHES"], str(row.get("oppTopBowl")))
    check("the scoreline and result are unchanged", row["us"] == "6/188" and row["them"] == "184" and row["outcome"] == "W",
          f"{row['us']} {row['them']} {row['outcome']}")

    print("\n-- a side that has not batted --")
    # `_result_row` gives no row until both innings have a score, so this is the in-between case that does:
    # both innings exist, one side's list is just empty.
    half = card()
    half["innings"][1]["batting"] = []
    half["innings"][1]["bowling"] = []
    row2 = _result_row(half, club, ["north perth"], "1st Grade")
    check("a row still comes back", row2 is not None)
    check("their lists are present and empty rather than missing",
          row2 is not None and row2.get("oppTopBat") == [] and row2.get("topBowl") == [], str(row2 and (row2.get("oppTopBat"), row2.get("topBowl"))))
    check("our batting is unaffected", row2 is not None and names(row2["topBat"]) == ["J. BARENDSE", "T. MCNAMEE"])

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
