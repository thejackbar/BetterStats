"""Results rows carry what Match Cards (RR8) needs to tell a match as it stands.

Asked for (November 2026): a Results post whose cards read right for a game in play
("1ST XI NEED 188 TO WIN") as well as a finished one. To say who is chasing, a card must
know who batted first, and the reference shows each innings's overs and our own team's
name ("1ST XI") beside the grade, and the round per match.

Each results row now carries, when the scorecard can answer it:
  battedFirst  'us' or 'them', from the innings order on the card
  usOvers, themOvers   each side's overs, as cricket notation
  teamLabel    our team's grade part: 'Willetton 1st XI' -> '1ST XI'
  round        the row's own round (a weekend's grades can be on different rounds)
and leaves each key OUT when it cannot, so a layout falls back rather than guessing.
The keys every older layout reads are unchanged (digest printed for the control run).

Pure: the real `_result_row` over synthetic Cricket Australia cards; the grade lookups and
calls are stubbed, no database (as verify_results_two_day_round.py).

Run:  python verification/verify_results_cards_rows.py
Control: the same script against the previous commit fails the new-field checks and
prints the same OLD-KEYS digest.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from app.services import grassroots_scores_client as gr
from app.services import social_rounds as sr

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAIL += 1
        print(f"FAIL {label} {detail}")


ORG_ID = "0e000000-0000-0000-0000-00000000000a"
OTHER = "0e000000-0000-0000-0000-00000000000b"
ORG = SimpleNamespace(id=ORG_ID, name="Willetton Cricket Club", short_name="Willetton", playhq_id=None, logo_url=None, logo_data=None)
US_T, THEM_T = "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


def card(*, innings, us_name="Willetton 1st XI", winner=None, result=None):
    teams = [
        {"id": US_T, "displayName": us_name, "owningOrganisation": {"id": ORG_ID, "name": "Willetton Cricket Club"}},
        {"id": THEM_T, "displayName": "Jandakot Park 1st XI", "owningOrganisation": {"id": OTHER, "name": "Jandakot Park Cricket Club"}},
    ]
    summary = []
    if winner:
        summary = [
            {"id": US_T, "isWinner": winner == "us", "resultType": "WON" if winner == "us" else "LOST"},
            {"id": THEM_T, "isWinner": winner == "them", "resultType": "WON" if winner == "them" else "LOST"},
        ]
    return {"teams": teams, "innings": innings, "matchSummary": {"teams": summary, "result": result}}


def inn(team, order, runs, wkts, overs):
    return {"battingTeamId": team, "inningsOrder": order, "runsScored": runs, "numberOfWicketsFallen": wkts,
            "oversBowled": overs, "batting": [], "bowling": []}


OLD_KEYS = ("grade", "gradeOrder", "opp", "oppClub", "oppMono", "us", "them", "outcome", "margin",
            "topBat", "topBowl", "oppTopBat", "oppTopBowl", "_oppOrgId", "_oppLogoRaw", "live")


def main_rows() -> list[dict]:
    keys = sr.club_match_keys(ORG)
    rows = {}
    # Day one of a two-day game: they batted, all out, we have not batted yet.
    rows["chase_pending"] = sr._result_row(card(innings=[inn(THEM_T, 1, 187, 10, "68.5")]), ORG, keys, "1st Grade", 1, live=True)
    # Listed the other way round on the card, inningsOrder decides: we batted first.
    rows["order_from_field"] = sr._result_row(
        card(innings=[inn(THEM_T, 2, 176, 8, "40"), inn(US_T, 1, 271, 8, 40)], us_name="Willetton 3rd XI", winner="us",
             result="Willetton won by 95 runs"),
        ORG, keys, "One Day C", 7)
    # No inningsOrder at all: the order on the card.
    rows["order_from_list"] = sr._result_row(
        card(innings=[{**inn(US_T, None, 142, 10, "33.4"), "inningsOrder": None},
                      {**inn(THEM_T, None, 143, 3, "28.1"), "inningsOrder": None}], winner="them",
             result="Jandakot Park won by 7 wkts"),
        ORG, keys, "One Day D", 8)
    # A team name with no grade part, an innings with no overs, a first innings naming nobody.
    rows["unknowns"] = sr._result_row(
        card(innings=[{"battingTeamId": "cccccccc-0000-0000-0000-000000000003", "inningsOrder": 1, "runsScored": 5, "numberOfWicketsFallen": 0},
                      {"battingTeamId": US_T, "inningsOrder": 2, "runsScored": 100, "numberOfWicketsFallen": 2},
                      {"battingTeamId": THEM_T, "inningsOrder": 3, "runsScored": 99, "numberOfWicketsFallen": 10}],
             us_name="Willetton", winner="us", result="Willetton won by 8 wickets"),
        ORG, keys, "Twenty20", 9)
    return rows


async def pulls() -> tuple[dict, dict]:
    G1 = str(uuid.uuid4())

    def match(n, rnd):
        return {"id": f"00000000-0000-0000-0000-{n:012d}", "statusId": 3, "round": {"name": rnd}, "grade": {"id": G1},
                "venue": {"name": "Ground"}, "matchType": "One Day",
                "matchSchedule": [{"startDateTime": "2026-11-21T10:00:00"}],
                "teams": [{"isHome": True, "displayName": "Willetton 1st XI", "owningOrganisation": {"id": ORG_ID}},
                          {"isHome": False, "displayName": "Jandakot Park 1st XI", "owningOrganisation": {"id": OTHER}}]}
    m = match(1, "Round 8")
    sc = card(innings=[inn(US_T, 1, 219, 10, "74.5"), inn(THEM_T, 2, 220, 4, "60")], winner="them", result="Jandakot Park won by 6 wkts")

    async def grade_results(guid, since=None, include_live=False):
        return [{"id": m["id"], "grade_id": G1, "played_at": "2026-11-21", "round": "8",
                 "home_team": "Willetton 1st XI", "away_team": "Jandakot Park 1st XI", "home_org_id": ORG_ID, "away_org_id": OTHER}] if guid == G1 else []

    async def none(*a, **k):
        return None
    gr.get_grade_results = grade_results
    gr.get_grade_matches = lambda guid, *a, **k: asyncio.sleep(0, result=[m] if guid == G1 else [])
    gr.get_match_detail = lambda mid: asyncio.sleep(0, result=m if mid == m["id"] else None)
    gr.get_match_scorecard = lambda mid, force=False: asyncio.sleep(0, result=sc)
    sr.current_grade_rows_with_live = lambda db, org_id: asyncio.sleep(0, result=[(G1, uuid.uuid4(), "1st Grade", "2026/27")])
    sr._grade_season = lambda db, org_id, guid: asyncio.sleep(0, result=(uuid.uuid4(), "2026/27") if guid == G1 else None)
    sr._grade_rows_for_season = lambda db, org_id, sid: asyncio.sleep(0, result=[(G1, uuid.uuid4(), "1st Grade", "2026/27")])
    sr._grade_display_orders = lambda db, org_id: asyncio.sleep(0, result={G1: 1})
    sr._category_lookup = lambda db, org_id: asyncio.sleep(0, result=lambda name: ["senior"])
    sr._finalize_opp_logos = none

    class _Date(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 23)
    sr.date = _Date
    latest = await sr.social_results(None, ORG)
    linked = await sr.social_results_for_reference(None, ORG, m["id"])
    return latest, linked


def main() -> None:
    rows = main_rows()
    r = rows["chase_pending"]
    check("chase pending: the row is kept", r is not None)
    r = r or {}
    check("chase pending: they batted first", r.get("battedFirst") == "them", repr(r.get("battedFirst")))
    check("chase pending: their overs", r.get("themOvers") == "68.5", repr(r.get("themOvers")))
    check("chase pending: no overs for a side that has not batted", "usOvers" not in r, repr(r.get("usOvers")))
    check("chase pending: our team label from 'Willetton 1st XI'", r.get("teamLabel") == "1ST XI", repr(r.get("teamLabel")))
    check("chase pending: still LIVE, still '-' for us", r.get("outcome") == "LIVE" and r.get("us") == "-" and r.get("them") == "187", repr((r.get("outcome"), r.get("us"), r.get("them"))))

    r = rows["order_from_field"] or {}
    check("inningsOrder decides, not the order listed: we batted first", r.get("battedFirst") == "us", repr(r.get("battedFirst")))
    check("whole overs print as the card does: 40, not 40.0", r.get("usOvers") == "40" and r.get("themOvers") == "40", repr((r.get("usOvers"), r.get("themOvers"))))
    check("3rd XI label", r.get("teamLabel") == "3RD XI", repr(r.get("teamLabel")))
    check("a win with its margin", r.get("outcome") == "W" and r.get("margin") == "BY 95 RUNS", repr((r.get("outcome"), r.get("margin"))))

    r = rows["order_from_list"] or {}
    check("no inningsOrder: the card's own order (we batted first)", r.get("battedFirst") == "us", repr(r.get("battedFirst")))

    r = rows["unknowns"] or {}
    check("a first innings naming neither side leaves battedFirst out", "battedFirst" not in r, repr(r.get("battedFirst")))
    check("innings with no overs leave both overs out", "usOvers" not in r and "themOvers" not in r, repr((r.get("usOvers"), r.get("themOvers"))))
    check("a team with no grade part leaves teamLabel out", "teamLabel" not in r, repr(r.get("teamLabel")))
    check("...and the row is still built", r.get("us") == "2/100" and r.get("outcome") == "W", repr((r.get("us"), r.get("outcome"))))

    latest, linked = asyncio.run(pulls())
    lrow = ((latest.get("dates") or [{}])[0].get("results") or [{}])[0]
    krow = ((linked.get("dates") or [{}])[0].get("results") or [{}])[0]
    check("latest pull: the row carries its own round", lrow.get("round") == "ROUND 8", repr(lrow.get("round")))
    check("linked pull: the row carries its own round", krow.get("round") == "ROUND 8", repr(krow.get("round")))
    check("latest pull: the new fields reach the route payload", lrow.get("battedFirst") == "us" and lrow.get("usOvers") == "74.5" and lrow.get("teamLabel") == "1ST XI",
          repr({k: lrow.get(k) for k in ("battedFirst", "usOvers", "teamLabel")}))

    # The older layouts' keys, byte for byte: compare this line with the control run.
    old = {name: {k: (row or {}).get(k) for k in OLD_KEYS if k in (row or {})} for name, row in rows.items()}
    old["latest"] = {k: lrow.get(k) for k in OLD_KEYS if k in lrow}
    digest = hashlib.sha256(json.dumps(old, sort_keys=True, default=str).encode()).hexdigest()[:16]
    print(f"OLD-KEYS {digest}")
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


main()
