"""Verification: an admin can switch competitions and grades on and off for a season's
Fantasy scoring. Real Postgres.

Request: choose which competitions/grades are included in the scoring, current season
only, on and off.

Runs the SHIPPED `fantasy_grades.grade_options`, the `routers/fantasy` season_grades and
set_season_grades route bodies, and `fantasy_engine`.

CONTROL (`--control`): the engine before this change (`CONTROL_REV`). It has no way to
leave a grade out, so a grade switched off in the rules still scores.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_grade_scope.py [--control]
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

from fastapi import HTTPException
from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Organisation, Player, Season, Grade, Game, BattingInnings, GameAppearance, FantasySeason, FantasyRound
from app.routers import fantasy as fr
from app.services import fantasy_engine, fantasy_grades
from app.services.club_grades import club_grade_rows

Session, check = base.Session, base.check
ORG, ORG_B, FS_ID, R1, R2, SQ_X, SQ_Y, TODAY = base.ORG, base.ORG_B, base.FS_ID, base.R1, base.R2, base.SQ_X, base.SQ_Y, base.TODAY
P3, P3S, PJ, PF, PFIFTH = (uuid.uuid4() for _ in range(5))      # Thirds (own), Thirds (shared, other club's row), Under 17s, Fourths-to-be
REPO = Path(__file__).resolve().parent.parent.parent
CONTROL_REV = "0a72c85"                                           # the engine before grades could be switched off
G = {}


async def club() -> Organisation:
    async with Session() as s:
        return await s.get(Organisation, ORG)


async def grade_key(name: str) -> str:
    async with Session() as s:
        rows = await club_grade_rows(s, ORG)
        await s.rollback()
    return next(c.key for c in rows if c.name == name)


async def seed() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
            canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    await base.seed()
    async with Session() as s:
        season = (await s.execute(text("SELECT id FROM seasons WHERE organisation_id=:o"), {"o": ORG})).scalar()
        firsts = (await s.execute(text("SELECT id FROM grades WHERE season_id=:s"), {"s": season})).scalar()
        G.update(firsts=firsts, thirds=uuid.uuid4(), u17=uuid.uuid4())
        prem, juniors = uuid.uuid4(), uuid.uuid4()
        await s.execute(text("INSERT INTO club_competitions (id, organisation_id, name, display_order) VALUES (:a,:o,'Premier',1),(:b,:o,'Juniors',2)"),
                        {"a": prem, "b": juniors, "o": ORG})
        s.add_all([Grade(id=G["thirds"], season_id=season, name="Thirds", grassroots_id="g3"),
                   Grade(id=G["u17"], season_id=season, name="Under 17s", grassroots_id="g17")])
        await s.flush()
        await s.execute(text("UPDATE grades SET competition_id=:c WHERE id = ANY(CAST(:ids AS uuid[]))"), {"c": prem, "ids": [str(firsts), str(G["thirds"])]})
        await s.execute(text("UPDATE grades SET competition_id=:c WHERE id=:g"), {"c": juniors, "g": G["u17"]})
        # The opposition owns a same-named Thirds grade and synced the shared fixture first.
        season_b = uuid.uuid4()
        s.add(Season(id=season_b, organisation_id=ORG_B, name="Summer", year=TODAY.year, grassroots_id="sb"))
        await s.flush()
        grade_b = uuid.uuid4()
        s.add(Grade(id=grade_b, season_id=season_b, name="Thirds", grassroots_id="gb3"))
        await s.flush()
        s.add_all([Player(id=P3, name="Third Tom", organisation_id=ORG, grassroots_id="t1"), Player(id=P3S, name="Shared Sid", organisation_id=ORG, grassroots_id="t2"),
                   Player(id=PJ, name="Junior Jo", organisation_id=ORG, grassroots_id="t3"), Player(id=PF, name="Fourth Finn", organisation_id=ORG, grassroots_id="t4")])
        await s.flush()

        async def game(grade, days, pid, home=ORG, away=None):
            gid = uuid.uuid4()
            s.add(Game(id=gid, grade_id=grade, played_at=TODAY - timedelta(days=days), home_team="A", away_team="B", home_org_id=home, away_org_id=away, status="COMPLETED"))
            await s.flush()
            s.add(GameAppearance(game_id=gid, player_id=pid, team_name="A"))
            s.add(BattingInnings(game_id=gid, player_id=pid, innings_number=1, runs=30, balls=30, fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        await game(G["thirds"], 18, P3)                         # round 1 (ended) and round 2 (running), own Thirds
        await game(G["thirds"], 3, P3)
        await game(grade_b, 3, P3S, home=ORG_B, away=ORG)        # the shared Thirds fixture, under the other club's row
        await game(G["u17"], 3, PJ)
        for pid, role in ((P3, "batter"), (P3S, "batter"), (PJ, "batter"), (PF, "batter")):
            s.add(base.FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=pid, role=role, base_price=5, current_price=5))
        # Y holds Third Tom, Shared Sid and Junior Jo; X holds Third Tom.
        for pid in (P3, P3S, PJ):
            s.add(base.FantasySquadPlayer(squad_id=SQ_Y, player_id=pid, role="batter"))
        s.add(base.FantasySquadPlayer(squad_id=SQ_X, player_id=P3, role="batter"))
        await s.commit()
    org = await club()
    async with Session() as s:
        await fr.settle_round(str(R1), club=org, db=s, _=None)
    async with Session() as s:
        await fr.settle_due(str(FS_ID), club=org, _=None, db=s)    # round 2 gets its provisional points


async def stored(pid, rnd) -> float | None:
    async with Session() as s:
        v = (await s.execute(text("SELECT total_points FROM fantasy_player_round_scores WHERE player_id=:p AND round_id=:r"), {"p": pid, "r": rnd})).scalar()
    return None if v is None else float(v)


async def points(squad, rnd) -> float:
    async with Session() as s:
        return float((await s.execute(text("SELECT COALESCE(points,0) FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r"), {"s": squad, "r": rnd})).scalar() or 0)


async def checks() -> None:
    org = await club()
    thirds_key, u17_key = await grade_key("Thirds"), await grade_key("Under 17s")

    print("1. The screen's data: competitions and grades for this season")
    async with Session() as s:
        opts = await fr.season_grades(str(FS_ID), club=org, db=s, _=None)
    comps = {c["name"]: c for c in opts["competitions"]}
    names = {n: [g["name"] for g in c["grades"]] for n, c in comps.items()}
    check("grades are grouped under the club's competitions", names.get("Premier") == ["Firsts", "Thirds"] and names.get("Juniors") == ["Under 17s"], repr(names))
    thirds = next(g for g in comps["Premier"]["grades"] if g["name"] == "Thirds")
    check("a grade's games count includes the shared fixture sitting under the other club's same-named grade", thirds["games"] == 3, repr(thirds))
    check("everything is on to begin with", all(g["on"] for c in opts["competitions"] for g in c["grades"]) and opts["excluded_count"] == 0, repr(opts))

    before_y1, before_y2 = await points(SQ_Y, R1), await points(SQ_Y, R2)
    before_x1 = await points(SQ_X, R1)
    check("(setup) Third Tom scored in the ended round and Shared Sid in the running one", await stored(P3, R1) and await stored(P3S, R2) and before_y1 > 0, repr((await stored(P3, R1), await stored(P3S, R2))))

    print("2. Switch Thirds off")
    async with Session() as s:
        res = await fr.set_season_grades(str(FS_ID), fr.GradeScopeBody(excluded_keys=[thirds_key]), club=org, db=s, _=None)
    check("the choice is saved by name and the rounds were scored again", res["excluded"] == [thirds_key] and res["rescored"]["settled"] == 1, repr(res))
    check("Third Tom's points in the ended round are gone, his stored row too (not left behind)", await stored(P3, R1) is None, repr(await stored(P3, R1)))
    check("and the shared Thirds fixture under the other club's grade row is left out as well", await stored(P3S, R2) is None, repr(await stored(P3S, R2)))
    check("other grades still score (Junior Jo, Firsts' Ann)", (await stored(PJ, R2) or 0) > 0 and (await stored(base.A, R2) or 0) > 0)
    check("teams' round scores fall by exactly what Thirds was worth", await points(SQ_Y, R1) < before_y1 and await points(SQ_X, R1) < before_x1, repr((before_y1, await points(SQ_Y, R1))))
    async with Session() as s:
        tot = (await s.execute(text("SELECT total_points FROM fantasy_pool_players WHERE player_id=:p"), {"p": P3})).scalar()
    check("his season total is back to 0, not left stale", float(tot) == 0.0, repr(tot))
    async with Session() as s:
        lineup = (await s.execute(text("SELECT lineup::text FROM fantasy_squad_round_scores WHERE squad_id=:s AND round_id=:r"), {"s": SQ_Y, "r": R1})).scalar()
    check("the teams keep the players they had that round (Third Tom is still in Y's lineup, on 0)", str(P3) in lineup, lineup[:80])
    async with Session() as s:
        again = await fr.season_grades(str(FS_ID), club=org, db=s, _=None)
    off = [g["name"] for c in again["competitions"] for g in c["grades"] if not g["on"]]
    check("the screen now shows Thirds as off", off == ["Thirds"] and again["excluded_count"] == 1, repr(off))
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R1)
        drift = await fantasy_engine.round_drift(s, fs, rnd)
    check("nothing is out of step with the scorecards afterwards", drift == [], repr(drift))

    print("3. Guard rails")
    for label, keys, code in (("switching every grade off", [g["key"] for c in opts["competitions"] for g in c["grades"]], 400),
                              ("a grade that is not part of this season", ["not-a-grade"], 400)):
        try:
            async with Session() as s:
                await fr.set_season_grades(str(FS_ID), fr.GradeScopeBody(excluded_keys=keys), club=org, db=s, _=None)
            check(f"{label} is refused", False, "no error")
        except HTTPException as e:
            check(f"{label} is refused", e.status_code == code, str(e.status_code))
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        scope = await fantasy_engine._grade_scope(s, fs)
        saved = list((fs.rules or {}).get("excluded_grade_keys", []))
        await s.rollback()
    check("the refused changes left the choice as it was", saved == [thirds_key] and scope is not None and str(G["thirds"]) not in scope, repr(saved))

    print("4. A grade that turns up later counts")
    async with Session() as s:
        season = (await s.execute(text("SELECT id FROM seasons WHERE organisation_id=:o"), {"o": ORG})).scalar()
        fourths = uuid.uuid4()
        s.add(Grade(id=fourths, season_id=season, name="Fourths", grassroots_id="g4"))
        await s.flush()
        gid = uuid.uuid4()
        s.add(Game(id=gid, grade_id=fourths, played_at=TODAY - timedelta(days=2), home_team="A", away_team="B", home_org_id=ORG, status="COMPLETED"))
        await s.flush()
        s.add(GameAppearance(game_id=gid, player_id=PF, team_name="A"))
        s.add(BattingInnings(game_id=gid, player_id=PF, innings_number=1, runs=40, balls=30, fours=0, sixes=0, dismissal_type="bowled", not_out=False))
        await s.commit()
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R2)
        now = await fantasy_engine._round_player_scores(s, fs, rnd)
        await s.rollback()
    check("Fourths was never switched off, so Fourth Finn scores", str(PF) in now and now[str(PF)]["total"] > 0, repr(list(now)))

    print("5. Switch it back on")
    async with Session() as s:
        await fr.set_season_grades(str(FS_ID), fr.GradeScopeBody(excluded_keys=[]), club=org, db=s, _=None)
    check("Third Tom scores again in the ended round, as before", abs((await stored(P3, R1) or 0) - 0) > 0 and abs(await points(SQ_Y, R1) - before_y1) < 1e-6, repr((await stored(P3, R1), await points(SQ_Y, R1), before_y1)))
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        scope = await fantasy_engine._grade_scope(s, fs)
        await s.rollback()
    check("with nothing off the engine reads every grade (no filter at all)", scope is None, repr(scope))

    print("6. The older 'only these grade ids' setting still works, and is replaced by a save")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_seasons SET included_grade_ids = CAST(:g AS jsonb) WHERE id=:f"), {"g": f'["{G["firsts"]}"]', "f": FS_ID})
        await s.commit()
    async with Session() as s:
        o = await fr.season_grades(str(FS_ID), club=org, db=s, _=None)
    check("the screen reads it as everything else being off", o["legacy_inclusion"] and {g["name"] for c in o["competitions"] for g in c["grades"] if g["on"]} == {"Firsts"}, repr(o))
    async with Session() as s:
        await fr.set_season_grades(str(FS_ID), fr.GradeScopeBody(excluded_keys=[u17_key]), club=org, db=s, _=None)
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        inc, ex = fs.included_grade_ids, list(fs.rules.get("excluded_grade_keys", []))
    check("saving replaces it with the name list", inc is None and ex == [u17_key], repr((inc, ex)))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_seasons SET rules = jsonb_set(rules, '{excluded_grade_keys}', '[\"fifths\", \"%s\"]') WHERE id=:f" % u17_key), {"f": FS_ID})
        await s.commit()
    async with Session() as s:
        await fr.set_season_grades(str(FS_ID), fr.GradeScopeBody(excluded_keys=[u17_key]), club=org, db=s, _=None)
    async with Session() as s:
        ex2 = list((await s.get(FantasySeason, FS_ID)).rules["excluded_grade_keys"])
    check("a grade switched off that has no games or row yet stays off for when it appears", "fifths" in ex2, repr(ex2))


async def run_control() -> int:
    await seed()
    thirds_key = await grade_key("Thirds")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_seasons SET rules = jsonb_set(COALESCE(rules,'{}'::jsonb), '{excluded_grade_keys}', CAST(:k AS jsonb)) WHERE id=:f"),
                        {"k": f'["{thirds_key}"]', "f": FS_ID})
        await s.commit()
    src = subprocess.check_output(["git", "show", f"{CONTROL_REV}:backend/app/services/fantasy_engine.py"], cwd=REPO, text=True)
    tmp = Path(__file__).resolve().parent / "_fantasy_engine_control4.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("fantasy_engine_control4", tmp)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        async with Session() as s:
            fs = await s.get(FantasySeason, FS_ID); rnd = await s.get(FantasyRound, R2)
            now = await old._round_player_scores(s, fs, rnd)
            await s.rollback()
        check("(control) a grade switched off in the rules no longer scores", str(P3) not in now, f"Third Tom still scores {now.get(str(P3), {}).get('total')}")
        check("(control) and the grade that is on still does (the check can see scores)", str(PJ) in now, repr(list(now)))
    finally:
        tmp.unlink(missing_ok=True)
    return base.FAIL


async def main() -> int:
    if "--control" in sys.argv:
        return await run_control()
    await seed()
    await checks()
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
