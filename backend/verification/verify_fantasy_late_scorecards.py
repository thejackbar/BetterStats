"""Verification: a scorecard that lands after its Fantasy round was settled is picked up,
without rewriting who was in each team. Real Postgres.

Reported (Scarborough): players who had played in the round were on 0. A round is
settled once its window ends, but scorers finish and correct scorecards afterwards and a
sync can land a game late, and nothing ever looked at a scored round again. Settling a
scored round by hand did look, but scored every team with the picks it holds NOW, so a
transfer made since rewrote the round.

Runs the SHIPPED `fantasy_engine` (settle, round_drift, refresh_recent_rounds) and the
`routers/fantasy` route bodies.

CONTROL (`--control`): the engine before this change (`CONTROL_REV`). Settling a scored
round again must rewrite its lineup to today's picks, and there is no drift check at all.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_late_scorecards.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Player, Organisation, BattingInnings, GameAppearance, FantasySeason, FantasyRound
from app.routers import fantasy as fr
from app.services import fantasy_engine

Session, check = base.Session, base.check
ORG, SQ_X, SQ_Y, R1, FS_ID, TODAY, A, B = base.ORG, base.SQ_X, base.SQ_Y, base.R1, base.FS_ID, base.TODAY, base.A, base.B
L = uuid.uuid4()                       # a Y pick whose scorecard arrives late
REPO = Path(__file__).resolve().parent.parent.parent
CONTROL_REV = "bae2507"
USER = type("U", (), {"id": uuid.uuid4()})()


async def q(sql, **p):
    async with Session() as s:
        return (await s.execute(text(sql), p)).all()


async def lineup_ids(squad) -> set:
    row = await q("SELECT lineup FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=squad, r=R1)
    return {e["player_id"] for e in (row[0][0] if row else [])}


async def r1_points(squad) -> float:
    return float((await q("SELECT points FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r", s=squad, r=R1))[0][0])


async def settle_with(mod):
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, R1)
        await mod.settle_round(s, fs, rnd)
        await s.commit()


async def setup() -> None:
    await base.build_schema()
    await base.seed()
    async with Session() as s:
        s.add(Player(id=L, name="Late Larry", organisation_id=ORG, grassroots_id="larry-ca"))
        await s.flush()
        s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=L, role="batter", base_price=5, current_price=5))
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=L, role="batter"))        # Y picked him
        # Round 1 ended recently (inside the 14 day window the nightly job watches).
        await s.execute(text("UPDATE fantasy_rounds SET start_date=:a, end_date=:b WHERE id=:r"),
                        {"a": TODAY - timedelta(days=20), "b": TODAY - timedelta(days=10), "r": R1})
        await s.commit()
    org = await club()
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)       # Larry's scorecard is not in yet


async def club():
    async with Session() as s:
        return await s.get(Organisation, ORG)


async def late_scorecard(runs: int) -> None:
    """The scorecard for Larry's game arrives (or is corrected) after the settle."""
    async with Session() as s:
        gid = (await s.execute(text("SELECT id FROM games ORDER BY played_at LIMIT 1"))).scalar()      # the round 1 game
        have = (await s.execute(text("SELECT 1 FROM batting_innings WHERE game_id=:g AND player_id=:p"), {"g": gid, "p": L})).scalar()
        if have:
            await s.execute(text("UPDATE batting_innings SET runs=:r WHERE game_id=:g AND player_id=:p"), {"r": runs, "g": gid, "p": L})
        else:
            s.add(GameAppearance(game_id=gid, player_id=L, team_name="Alpha"))
            s.add(BattingInnings(game_id=gid, player_id=L, innings_number=1, runs=runs, balls=runs, fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        await s.commit()


async def checks() -> None:
    org = await club()
    y0 = await r1_points(SQ_Y)
    ft0 = (await q("SELECT free_transfers FROM fantasy_squads WHERE id=:s", s=SQ_Y))[0][0]
    check("Larry (a Y pick) was on 0 when the round settled: no scorecard yet", str(L) not in {r[0] for r in await q("SELECT player_id::text FROM fantasy_player_round_scores WHERE round_id=:r AND total_points > 0", r=R1)})

    print("1. A scorecard lands after the round was settled")
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R1)
        none = await fantasy_engine.round_drift(s, fs, rnd)
    check("before it arrives, nothing has drifted", none == [], repr(none))
    await late_scorecard(50)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R1)
        drift = await fantasy_engine.round_drift(s, fs, rnd)
    check("the round now reports Larry: stored 0, the scorecards give more",
          [(d["name"], d["stored"]) for d in drift if d["name"] == "Late Larry"] == [("Late Larry", 0.0)] and drift[0]["now"] > 0, repr(drift))
    async with Session() as s:
        lst = await fr.list_rounds(str(FS_ID), club=org, db=s, _=None)
    r1 = next(r for r in lst["rounds"] if r["id"] == str(R1))
    check("the admin rounds list shows it, so the club can see why", r1.get("drift") and r1["drift"]["count"] >= 1 and "Late Larry" in r1["drift"]["players"][0], repr(r1.get("drift")))

    print("2. A transfer made since must not rewrite the round")
    async with Session() as s:                       # Y transfers Larry out for Ann (A) after the round settled
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id=:s AND player_id=:p"), {"s": SQ_Y, "p": L})
        s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=A, role="batter"))
        await s.commit()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        n = await fantasy_engine.refresh_recent_rounds(s, fs)
        await s.commit()
    check("the refresh settled the one drifted round", n == 1, str(n))
    y1 = await r1_points(SQ_Y)
    check("Larry's 50 now count for Y, because he was in the team that round", y1 > y0, repr((y0, y1)))
    check("Y's stored lineup is still the one it was settled with: Larry in, the later transfer's Ann out",
          str(L) in await lineup_ids(SQ_Y) and str(A) not in await lineup_ids(SQ_Y), repr(await lineup_ids(SQ_Y)))
    check("no free transfer was banked by settling again", (await q("SELECT free_transfers FROM fantasy_squads WHERE id=:s", s=SQ_Y))[0][0] == ft0)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R1)
        after = await fantasy_engine.round_drift(s, fs, rnd)
    check("and the round is back in step", after == [], repr(after))

    print("3. A correction is picked up the same way")
    await late_scorecard(80)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        n = await fantasy_engine.refresh_recent_rounds(s, fs)
        await s.commit()
    y2 = await r1_points(SQ_Y)
    check("Larry's corrected 80 replaces the 50", n == 1 and abs((y2 - y1) - 30) < 1e-6, repr((y1, y2)))

    print("4. What is left alone")
    async with Session() as s:
        await fr.set_manual_score(str(R1), str(B), fr.ManualScoreBody(points=999), club=org, user=USER, db=s, _=None)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R1)
        dr = await fantasy_engine.round_drift(s, fs, rnd)
    check("a hand-typed score is never reported as drift", all(d["player_id"] != str(B) for d in dr), repr(dr))
    await late_scorecard(10)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        await s.execute(text("UPDATE fantasy_rounds SET end_date=:d WHERE id=:r"), {"d": TODAY - timedelta(days=40), "r": R1})
        n = await fantasy_engine.refresh_recent_rounds(s, fs)
        await s.rollback()
    check("a round that ended more than a fortnight ago is not touched by the nightly refresh", n == 0, str(n))
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)       # the admin's own Settle button still works on any round
    check("(an admin can still settle it by hand, with the same lineup)", str(L) in await lineup_ids(SQ_Y))


async def run_control() -> int:
    await setup()
    await late_scorecard(50)
    src = subprocess.check_output(["git", "show", f"{CONTROL_REV}:backend/app/services/fantasy_engine.py"], cwd=REPO, text=True)
    tmp = Path(__file__).resolve().parent / "_fantasy_engine_control3.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("fantasy_engine_control3", tmp)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        check("(control) the engine checks scored rounds against the scorecards", hasattr(old, "round_drift") and hasattr(old, "refresh_recent_rounds"),
              "no round_drift or refresh_recent_rounds: a scored round is never looked at again")
        async with Session() as s:                   # a manager transfers Larry out, then the club presses Settle again
            await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id=:s AND player_id=:p"), {"s": SQ_Y, "p": L})
            s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=A, role="batter"))
            await s.commit()
        await settle_with(old)
        check("(control) settling a scored round again keeps the lineup it was settled with", str(L) in await lineup_ids(SQ_Y),
              f"lineup now: Larry in={str(L) in await lineup_ids(SQ_Y)}, Ann in={str(A) in await lineup_ids(SQ_Y)}")
    finally:
        tmp.unlink(missing_ok=True)
    return base.FAIL


async def main() -> int:
    if "--control" in sys.argv:
        return await run_control()
    await setup()
    await checks()
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
