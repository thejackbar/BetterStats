"""A manual game's winner, when its own result line and scores say otherwise.

Reported off Hamilton Veterans' 7 Feb 2012 match (a CSV import): the sheet
named Portland as the winner, its own result line read "Lost by 7 Runs", and
the scores were Portland 159 v Vic Country 166. The WON tag, the Games list
and the club's W/L all read the winner, so the page contradicted itself.
`services/manual_result` settles it at the import and the hand-entry form, and
`scripts/settle_manual_winners` repairs what is already stored.

Drives the SHIPPED route bodies and script against a real Postgres, reusing
the side-names suite's harness.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_side_names \\
  python -m verification.verify_manual_winner

Control run: check out the previous commit and run it again. It REPORTS the
missing parts rather than crashing on the first absent name.
"""
from __future__ import annotations

import asyncio
import importlib
from datetime import date as date_cls
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select, text

import verify_manual_side_names as h
from app.models.db import ManualGame, Organisation, User
from app.routers.manual_entries import ManualGameIn, get_manual_game, update_manual_game

check = h.check
OURS, VIC = h.TEAM, "Vic Country"


def load(name):
    try:
        return importlib.import_module(name)
    except Exception as e:  # noqa: BLE001 - reported, not raised
        print(f"  (absent: {name}: {e})")
        return None


def game_rows(date: str, *, winner: str, result: str, ours: int, theirs: int,
              opp_wkts: int = 10) -> list[dict]:
    """The 7 Feb 2012 shape: Portland batted first."""
    base = {
        "game_key": date, "played_at": date, "opposition": VIC,
        "season_name": "Summer 2010/11", "grade_name": "One Off 40 overs",
        "home_team": OURS, "away_team": VIC, "winning_team": winner, "result": result,
        "innings_number": 1, "opp_innings_number": 2,
    }
    rows = []
    for i, name in enumerate(h.BATTING_ORDER, 1):
        r = {**base, "player_name": name, "batting_position": i, "batting_runs": 20 + i,
             "bowling_overs": 6, "bowling_runs": 20 + i, "bowling_wickets": i % 2}
        if i == 1:
            r.update({"innings_total": ours, "innings_wickets": 5,
                      "opp_total": theirs, "opp_wickets": opp_wkts})
        rows.append(r)
    return rows


async def stored_winner(date: str):
    async with h.Session() as s:
        return (await s.execute(select(ManualGame.winning_team).where(
            ManualGame.organisation_id == h.ORG,
            ManualGame.played_at == date_cls.fromisoformat(date)))).scalar()


async def main() -> None:
    await h.setup()
    mr = load("app.services.manual_result")

    print("\n-- THE RULE --")
    if mr is None:
        check("services/manual_result exists", False)
    else:
        check("a result line opening 'Lost' reads as lost", mr.text_outcome("Lost By 16 Runs") == "lost")
        check("one opening 'Won' reads as won", mr.text_outcome("Won by 72 runs") == "won")
        check("a line naming a team is not read as ours",
              mr.text_outcome("Rockingham won by 5 wickets") is None)
        check("a tie says nothing", mr.text_outcome("Tied") is None)
        sw = mr.settled_winner
        check("the reported case: winner, result and scores two against one",
              sw(OURS, "Lost by 7 Runs", OURS, VIC, 159, 166) == VIC)
        check("the other way round",
              sw(VIC, "Won by 53 runs", OURS, VIC, 189, 136) == OURS)
        check("a consistent game is left alone", sw(OURS, "Won by 72 runs", OURS, VIC, 184, 112) is None)
        check("scores that side with the recorded winner leave it (a rain rule, say)",
              sw(OURS, "Lost by 3 runs", OURS, VIC, 150, 140) is None)
        check("level scores decide nothing", sw(OURS, "Lost by 7 runs", OURS, VIC, 150, 150) is None)
        check("a missing total decides nothing", sw(OURS, "Lost by 7 runs", OURS, VIC, None, 150) is None)
        check("a winner naming neither side is left alone",
              sw("Somebody Else", "Lost by 7 runs", OURS, VIC, 159, 166) is None)
        check("punctuation does not make a contradiction",
              sw("Portland Over 60's", "Won by 7 runs", OURS, VIC, 166, 159) is None)

    print("\n-- THE REPORTED MATCH, IMPORTED --")
    out, err = await h.run_import(game_rows("2012-02-07", winner=OURS, result="Lost by 7 Runs",
                                            ours=159, theirs=166))
    check("it imports", err is None and (out or {}).get("games_created") == 1, str(err or out))
    check("the winner is stored as Vic Country", await stored_winner("2012-02-07") == VIC,
          str(await stored_winner("2012-02-07")))
    warns = " ".join((out or {}).get("warnings") or [])
    check("the import says it corrected it, and why",
          "Vic Country" in warns and "Lost by 7 Runs" in warns, warns)
    gid = (await h.game_ids() or [None])[0]
    card = None
    if gid:
        async with h.Session() as s:
            card = await h.get_scorecard(gid, s)
    check("the scorecard's winner agrees with its result line",
          (card or {}).get("winning_team") == VIC, str((card or {}).get("winning_team")))

    print("\n-- A GAME THAT ALREADY AGREES --")
    await h.wipe()
    out, err = await h.run_import(game_rows("2012-02-05", winner=OURS, result="Won by 72 runs",
                                            ours=184, theirs=112, opp_wkts=9))
    check("it keeps its winner", await stored_winner("2012-02-05") == OURS)
    check("and the import says nothing about it",
          not any("winner" in w for w in (out or {}).get("warnings") or []),
          str((out or {}).get("warnings")))

    print("\n-- SCORES THAT SIDE WITH THE RECORDED WINNER --")
    await h.wipe()
    out, err = await h.run_import(game_rows("2012-02-06", winner=OURS, result="Lost by 3 runs",
                                            ours=150, theirs=140))
    check("the club's winner stands when only one of the other two disagrees",
          await stored_winner("2012-02-06") == OURS)

    print("\n-- THE HAND-ENTRY FORM --")
    await h.wipe()
    await h.run_import(game_rows("2012-02-07", winner=VIC, result="Lost by 7 Runs",
                                 ours=159, theirs=166))
    gid = (await h.game_ids() or [None])[0]
    res = {}
    if gid:
        async with h.Session() as s:
            c, u = await s.get(Organisation, h.ORG), await s.get(User, h.USER)
            full = await get_manual_game(game_id=gid, current_user=u, club=c, db=s)
            payload = {k: v for k, v in full.items() if k in ManualGameIn.model_fields}
            payload["winning_team"] = OURS
            res = await update_manual_game(game_id=gid, data=ManualGameIn(**payload),
                                           current_user=u, club=c, db=s)
    check("saving a contradicting winner stores the one the result and scores agree on",
          await stored_winner("2012-02-07") == VIC, str(await stored_winner("2012-02-07")))
    check("and the save says so", "Vic Country" in str(res.get("winner_corrected")),
          str(res.get("winner_corrected")))

    print("\n-- THE REPAIR SCRIPT, OVER A GAME ALREADY STORED WRONG --")
    script = load("app.scripts.settle_manual_winners")
    async with h.Session() as s:
        await s.execute(text("UPDATE manual_games SET winning_team = :w WHERE organisation_id = :o"),
                        {"w": OURS, "o": str(h.ORG)})
        await s.commit()
    if script is None:
        check("the repair script exists", False)
    else:
        dry = await script.settle("hamilton-vets", apply=False)
        check("a dry run finds the one game", len(dry) == 1, str(dry))
        check("and writes nothing", await stored_winner("2012-02-07") == OURS)
        applied = await script.settle("hamilton-vets", apply=True)
        check("applying corrects it", len(applied) == 1 and await stored_winner("2012-02-07") == VIC)
        again = await script.settle("all", apply=True)
        check("a second run finds nothing", again == [], str(again))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
