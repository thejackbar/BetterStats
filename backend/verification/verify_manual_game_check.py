"""A hand-entered game that does not add up is warned about, never refused.

Reported off Hamilton Veterans' 23 Oct 2011 game (Mt Gambier batted first):
both sides read 142/7 in 40 overs. The form draws the opposition-total boxes
only for an opposition innings, so a total typed while an innings was set to
"Opposition" stayed on the row after the innings was flipped to "Our innings",
hidden, and replaced our batters' 125/8.

Covers, against a real Postgres through the SHIPPED write path, scorecard and
route bodies:
  * a total on OUR innings is not stored, so the card totals from its batters;
  * the opposition's total is stored and shown;
  * `services/manual_game_check` says what does not add up, for the reported
    game and for each shape on its own, and says nothing about a game that does;
  * a game missing every figure still SAVES (the check never refuses one);
  * `scripts/fix_stray_innings_totals` finds the stored copy, changes nothing on
    a dry run, clears only that row on apply, writes an audit entry, leaves a
    legitimate total and a tie alone, and finds nothing the second time.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_game_check \\
  python -m verification.verify_manual_game_check

Control run: check out the previous commit and run it again. It REPORTS the
missing parts rather than crashing on the first absent name.
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select, text

import verify_manual_side_names as h
from app.models.db import ManualEditLog, ManualGame, Organisation, Player, User
from app.routers.manual_entries import (
    ManualBattingIn, ManualBowlingIn, ManualGameIn, ManualInningsIn,
    _replace_game_children,
)
from app.routers.games import get_scorecard

check = h.check


def load(name):
    try:
        return importlib.import_module(name)
    except Exception as e:  # noqa: BLE001 - reported, not raised
        print(f"  (absent: {name}: {e})")
        return None


NOT_OUT = {5, 6, 10}  # Hollis, Petch, Vaughan
BATS = [19, 14, 3, 17, 11, 23, 22, 0, 5, 3, 1]
SPELLS = [(5, 16, 0), (5, 25, 0), (3, 14, 1), (5, 4, 0), (5, 19, 1), (5, 11, 2),
          (3, 14, 0), (3, 14, 0), (1, 1, 1)]


async def seed_players() -> tuple[list[str], list[str]]:
    async with h.Session() as s:
        bat = [Player(id=uuid.uuid4(), organisation_id=h.ORG, name=f"Bat {i}") for i in range(len(BATS))]
        bowl = [Player(id=uuid.uuid4(), organisation_id=h.ORG, name=f"Bowl {i}") for i in range(len(SPELLS))]
        s.add_all(bat + bowl)
        await s.commit()
        return [str(p.id) for p in bat], [str(p.id) for p in bowl]


def reported_game(bat_ids, bowl_ids, *, us_total=None, opp_total=142, result="Lost By 16 Runs"):
    """The 23 Oct 2011 shape: Mt Gambier batted first, so innings 1 is theirs."""
    return ManualGameIn(
        season_id=str(h.S_ID), grade_id=str(h.G_ID), played_at="2011-10-23",
        home_team=h.TEAM, away_team=h.OPP, opposition=h.OPP,
        winning_team=h.OPP, result=result,
        batting_innings=[ManualBattingIn(player_id=pid, innings_number=2, batting_position=i + 1,
                                         runs=r, dismissal_type=None if i in NOT_OUT else "b X",
                                         not_out=i in NOT_OUT)
                         for i, (pid, r) in enumerate(zip(bat_ids, BATS))],
        bowling_spells=[ManualBowlingIn(player_id=pid, innings_number=1, overs=o, runs=r, wickets=w)
                        for pid, (o, r, w) in zip(bowl_ids, SPELLS)],
        innings=[
            ManualInningsIn(innings_number=1, batting_side="opposition", byes=7, leg_byes=6,
                            wides=1, no_balls=1, penalty=0,
                            total_runs=opp_total, total_wickets=7, overs=40),
            ManualInningsIn(innings_number=2, batting_side="us", byes=4, leg_byes=3, penalty=0,
                            total_runs=us_total, total_wickets=7 if us_total else None,
                            overs=40 if us_total else None),
        ],
    )


async def new_game(data: ManualGameIn) -> str:
    async with h.Session() as s:
        g = ManualGame(id=uuid.uuid4(), organisation_id=h.ORG, season_id=h.S_ID, grade_id=h.G_ID,
                       played_at=date_cls(2011, 10, 23), home_team=h.TEAM, away_team=h.OPP,
                       opposition=h.OPP, winning_team=h.OPP, result=data.result)
        s.add(g)
        await s.flush()
        await _replace_game_children(s, g.id, data, h.ORG)
        await s.commit()
        return str(g.id)


def kinds(ws):
    return sorted(w["kind"] for w in ws)


async def main() -> None:
    await h.setup()
    gc = load("app.services.manual_game_check")
    if gc is None:
        check("the game check service exists", False)
        print(f"\n{h.PASS} passed, {h.FAIL} failed")
        sys.exit(1)
    bat_ids, bowl_ids = await seed_players()

    print("\n-- THE FORM'S LEFTOVER TOTAL IS NOT STORED --")
    # Exactly what the form sent: the opposition total ALSO sitting on our innings.
    gid = await new_game(reported_game(bat_ids, bowl_ids, us_total=142))
    async with h.Session() as s:
        rows = {r[0]: r[1:] for r in (await s.execute(text(
            "SELECT innings_number, batting_side, total_runs, total_wickets, overs "
            "FROM manual_innings WHERE manual_game_id = :g"), {"g": gid})).all()}
        card = await get_scorecard(gid, s)
    check("our innings stores no total, wickets or overs", rows.get(2) == ("us", None, None, None), str(rows.get(2)))
    check("the opposition's total is stored as entered", rows.get(1) == ("opposition", 142, 7, 40), str(rows.get(1)))
    t = card["innings_totals"]
    ours = (t[2]["runs"] + t[2]["extras"], t[2]["wickets"])
    theirs = (t[1]["runs"] + t[1]["extras"], t[1]["wickets"])
    check("Portland's card totals from its batters: 125/8", ours == (125, 8), str(ours))
    check("Mt Gambier keeps 142/7", theirs == (142, 7), str(theirs))
    check("the two sides no longer share a score", ours != theirs)

    print("\n-- WHAT THE CHECK SAYS ABOUT THE REPORTED GAME --")
    payload = reported_game(bat_ids, bowl_ids).model_dump()
    ws = gc.check_game(payload)
    check("it says the bowling does not reach the opposition total",
          "bowling_runs" in kinds(ws), str(ws))
    bw = next((w for w in ws if w["kind"] == "bowling_runs"), {"text": ""})
    check("and names both figures and the overs",
          "118" in bw["text"] and "142" in bw["text"] and "35 overs against 40" in bw["text"], bw["text"])
    check("it says the result line is one run off the totals", "result_margin" in kinds(ws), str(ws))
    check("and says the totals are 125 to 142, a difference of 17",
          any("125 to 142" in w["text"] and "17" in w["text"] for w in ws), str(ws))
    check("nothing else is said", kinds(ws) == ["bowling_runs", "result_margin"], str(kinds(ws)))

    print("\n-- EACH SHAPE ON ITS OWN --")
    def with_(**changes):
        p = reported_game(bat_ids, bowl_ids).model_dump()
        for k, v in changes.items():
            p[k] = v
        return p

    no_total = reported_game(bat_ids, bowl_ids, opp_total=None).model_dump()
    check("no opposition total is named, with the way out",
          kinds(gc.check_game(no_total)) == ["opp_total_missing"]
          and "can save" in gc.check_game(no_total)[0]["text"], str(gc.check_game(no_total)))
    check("a photo upload, which carries the opposition's card, needs no typed total",
          "opp_total_missing" not in kinds(gc.check_game({**no_total, "extracted_payload": {"innings": [1]}})))
    flipped = with_(innings=[
        {"innings_number": 1, "batting_side": "us"}, {"innings_number": 2, "batting_side": "opposition"}])
    fk = kinds(gc.check_game(flipped))
    check("innings set the wrong way round against their rows is named for both innings",
          fk.count("side_mismatch") == 2, str(fk))
    check("a missing side is inferred from its rows, not warned about",
          "side_mismatch" not in kinds(gc.check_game(with_(innings=[]))),
          str(gc.check_game(with_(innings=[]))))
    contradicting = reported_game(bat_ids, bowl_ids, result="Won By 17 Runs").model_dump()
    check("a result that has us winning when the totals have us losing is named",
          "result_outcome" in kinds(gc.check_game(contradicting)), str(gc.check_game(contradicting)))
    exact = reported_game(bat_ids, bowl_ids, result="Lost By 17 Runs").model_dump()
    check("a result that matches the totals is not questioned",
          "result_margin" not in kinds(gc.check_game(exact)) and "result_outcome" not in kinds(gc.check_game(exact)))
    over = with_(bowling_spells=[{**b, "runs": 200} for b in with_()["bowling_spells"][:1]])
    check("bowlers conceding more than the opposition scored is named even with no itemised extras",
          "bowling_runs" in kinds(gc.check_game({**over, "innings": [
              {"innings_number": 1, "batting_side": "opposition", "total_runs": 142},
              {"innings_number": 2, "batting_side": "us"}]})))
    check("a game with nothing entered says nothing",
          gc.check_game({"batting_innings": [], "bowling_spells": [], "innings": []}) == [])
    check("six-ball overs read as cricket notation: 10.2 is 62 balls", gc.overs_to_balls(10.2) == 62)

    # A game whose every figure agrees is not questioned.
    agree = reported_game(bat_ids, bowl_ids, result="Lost By 17 Runs").model_dump()
    agree["bowling_spells"] = [{**b, "runs": (b["runs"] or 0) + (11 if i == 0 else 0),
                                "overs": {0: 10}.get(i, b["overs"])}
                               for i, b in enumerate(agree["bowling_spells"])]
    agree["bowling_spells"][0]["overs"] = 10
    check("a game that adds up gives no warning",
          gc.check_game(agree) == [], str(gc.check_game(agree)))

    print("\n-- SAVING IS NEVER REFUSED --")
    bare = ManualGameIn(
        season_id=str(h.S_ID), grade_id=str(h.G_ID), played_at="2011-11-01", opposition=h.OPP,
        result="Lost By 16 Runs",
        batting_innings=[ManualBattingIn(player_id=bat_ids[0], innings_number=2, runs=10, dismissal_type="b X")],
        innings=[ManualInningsIn(innings_number=1, batting_side="us"),
                 ManualInningsIn(innings_number=2, batting_side="opposition")],
    )
    check("the check has things to say about it",
          len(gc.check_game(bare.model_dump())) >= 2, str(gc.check_game(bare.model_dump())))
    try:
        bid = await new_game(bare)
        saved = True
    except Exception as e:  # noqa: BLE001
        bid, saved = None, False
        print("   ", type(e).__name__, e)
    check("and the game saves anyway", saved)
    if bid:
        async with h.Session() as s:
            card = await get_scorecard(bid, s)
        check("its scorecard still opens", "innings_totals" in card)

    print("\n-- THE ROUTE --")
    from app.routers import manual_entries as me
    route = getattr(me, "check_manual_game", None)
    check("the check is routed", route is not None)
    if route:
        got = await route(data=reported_game(bat_ids, bowl_ids), current_user=None)
        check("the route returns the same warnings as the service",
              got == {"warnings": gc.check_game(reported_game(bat_ids, bowl_ids).model_dump())}, str(got))
        async with h.Session() as s:
            n = (await s.execute(text("SELECT COUNT(*) FROM manual_games"))).scalar()
        check("and writes nothing", n == 2, str(n))

    print("\n-- THE REPAIR SCRIPT, OVER A GAME ALREADY STORED WRONG --")
    script = load("app.scripts.fix_stray_innings_totals")
    if script is None:
        check("the repair script exists", False)
        print(f"\n{h.PASS} passed, {h.FAIL} failed")
        sys.exit(1)
    await h.wipe()
    stray_id = await new_game(reported_game(bat_ids, bowl_ids))
    # Store it the way the old form did: our innings carrying a copy of theirs.
    async def our_row(gid_):
        async with h.Session() as s:
            return (await s.execute(text(
                "SELECT total_runs, total_wickets, overs FROM manual_innings "
                "WHERE manual_game_id = :g AND batting_side = 'us'"), {"g": gid_})).first()
    async def stray(gid_):
        async with h.Session() as s:
            await s.execute(text(
                "UPDATE manual_innings SET total_runs = 142, total_wickets = 7, overs = 40 "
                "WHERE manual_game_id = :g AND batting_side = 'us'"), {"g": gid_})
            await s.commit()
    await stray(stray_id)
    # A legitimate total on our innings (a scorebook import's), differing from theirs.
    legit_id = await new_game(reported_game(bat_ids, bowl_ids))
    async with h.Session() as s:
        await s.execute(text(
            "UPDATE manual_innings SET total_runs = 131, total_wickets = 8, overs = 38 "
            "WHERE manual_game_id = :g AND batting_side = 'us'"), {"g": legit_id})
        await s.commit()
    # A tie whose batters add up to the recorded total: nothing is wrong with it.
    tie_id = await new_game(reported_game(bat_ids, bowl_ids, opp_total=125))
    async with h.Session() as s:
        await s.execute(text(
            "UPDATE manual_innings SET total_runs = 125, total_wickets = 7, overs = 40 "
            "WHERE manual_game_id = :g AND batting_side IN ('us', 'opposition')"), {"g": tie_id})
        await s.commit()

    dry = await script.repair("hamilton-vets", apply=False)
    check("a dry run finds exactly the one game", len(dry) == 1 and dry[0]["game_id"] == stray_id, str(dry))
    check("and writes nothing", await our_row(stray_id) == (142, 7, 40), str(await our_row(stray_id)))
    applied = await script.repair("hamilton-vets", apply=True)
    check("applying clears the leftover total on our innings",
          len(applied) == 1 and await our_row(stray_id) == (None, None, None), str(await our_row(stray_id)))
    async with h.Session() as s:
        opp = (await s.execute(text(
            "SELECT total_runs FROM manual_innings WHERE manual_game_id = :g AND batting_side = 'opposition'"),
            {"g": stray_id})).scalar()
        card = await get_scorecard(stray_id, s)
    check("the opposition's total is untouched", opp == 142, str(opp))
    check("Portland now reads 125/8", (card["innings_totals"][2]["runs"] + card["innings_totals"][2]["extras"],
                                       card["innings_totals"][2]["wickets"]) == (125, 8), str(card["innings_totals"][2]))
    check("a legitimate total on our innings is left alone", await our_row(legit_id) == (131, 8, 38))
    check("a tie whose batters match the total is left alone", await our_row(tie_id) == (125, 7, 40))
    async with h.Session() as s:
        logs = (await s.execute(select(ManualEditLog).where(
            ManualEditLog.target_id == stray_id, ManualEditLog.action == "update"))).scalars().all()
    check("one audit entry holds the before and the after", len(logs) == 1
          and logs[0].before_json and logs[0].after_json, str(len(logs)))
    if logs:
        b_in = (logs[0].before_json.get("children") or {}).get("innings") or []
        check("the audit entry's before still carries the total, so it can be undone",
              any(r.get("total_runs") == 142 and r.get("batting_side") == "us" for r in b_in), str(b_in))
    again = await script.repair("all", apply=True)
    check("a second run finds nothing", again == [], str(again))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
