"""StatLab player reports at platform scale: the same rows as before, in a fraction of the time.

A StatLab player report (career, season, grade, any with a filter on) read the
`v_effective_*` views straight against `players`, and the `matches` column behind
career went to the grid loader 300 players at a time, also straight against the
views. On a platform of tens of thousands of games each chunk cost ~10s and one
cold career report ~25s. `services/statlab_rows.py` copies the club's rows out
once per request and the three reports read the copies.

This builds a platform-sized database (36,000 games, 790,000 innings, 480,000
season rows, one club under test among 60 others) and checks, for eleven reports:

  * every report comes back inside the bound below, with the grid cache cleared
    first so each is a COLD load;
  * the rows are exactly what the previous code returned (DUMP=path writes them;
    compare a control dump with `cmp`).

Run (builds in about two minutes; REUSE=1 skips the build):
  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
  DUMP=new.json python verification/verify_statlab_speed.py

Control: `git stash push backend/app/services/statlab.py`, then
  CONTROL=1 REUSE=1 DUMP=old.json python verification/verify_statlab_speed.py
The two dumps must be byte-identical (`cmp old.json new.json`). CONTROL=1 relaxes the
bound so the old code runs to completion (it takes 9 to 11s for the career reports where
the new code takes about 1s); without CONTROL=1 the old code fails the bound.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_records_partnership_grade_names as base
from app.services import aggregations, statlab

check = base.check
ORG, OPP = base.ORG, base.OPP
ORG_SEASONS, GPS = 25, 8
ORG_GAMES, NOISE_CLUBS, NOISE_GAMES = 6000, 60, 500
BOUND_SECONDS = 5.0

# (target, sort_by, filters, context): the reports a person opens first, bare and filtered.
REPORTS = [
    ("player_career", "runs", [], {}),
    ("player_career", "wickets", [], {}),
    ("player_career", "batting_average", ["batting_innings:gte:20"], {}),
    ("player_career", "runs", [], {"min_year": 2010}),
    ("player_career", "runs", [], {"finals_only": True}),
    ("player_career", "runs", [], {"grade_name": "Grade 3"}),
    ("player_career", "runs", [], {"captain_only": True}),
    ("player_season", "runs", [], {}),
    ("player_season", "runs", [], {"min_year": 2015}),
    ("player_grade", "runs", [], {}),
    ("player_grade", "wickets", [], {"result": "won"}),
]


# Filters that read columns of `players` or hang an EXISTS off the player. They match nobody in
# this data, so the check is only that each still RUNS on every player report: a rewrite that
# hid a `players` column from them (the Gender filter once did) turns into a SQL error.
ATTRIBUTE_CONTEXTS = [
    {"gender": "female"}, {"player_role": "Batter"}, {"overseas": "true"},
    {"award_category": "Club Award"}, {"office_bearer": "President"},
    {"first_n_matches": 5}, {"milestone_runs": 1000},
]


async def build_and_seed() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        # Lifespan-created (main.py), so create_all never makes it; two of the filters read it.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_achievements (
                id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL,
                season TEXT, category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL,
                detail TEXT, created_at TIMESTAMPTZ DEFAULT NOW())"""))
    async with base.Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, n, sl in ((ORG,"Long CC","long"),(OPP,"Rivals CC","rivals")):
            await ex("INSERT INTO organisations (id,name,slug,is_active) VALUES (:i,:n,:s,true)", i=oid,n=n,s=sl)
        await ex("INSERT INTO organisations (id,name,slug,is_active) SELECT gen_random_uuid(),'Club '||i,'club-'||i,true FROM generate_series(1,:n) i", n=NOISE_CLUBS)
        # seasons/grades: org + opp + noise clubs
        await ex("INSERT INTO seasons (id,organisation_id,name,year) SELECT gen_random_uuid(),o.id,'Season '||(2000+y),2000+y FROM organisations o, generate_series(0,:n-1) y WHERE o.slug IN ('long','rivals') OR o.slug LIKE 'club-%'", n=ORG_SEASONS)
        await ex("INSERT INTO grades (id,season_id,name,grassroots_id,category,categories) SELECT gen_random_uuid(),s.id,'Grade '||g,gen_random_uuid()::text,'senior',ARRAY['senior'] FROM seasons s, generate_series(1,:g) g", g=GPS)
        # players: org 600, opp 400, noise 300 each
        await ex("INSERT INTO players (id,organisation_id,name,grassroots_id,status) SELECT gen_random_uuid(),o.id,'P'||o.slug||i,gen_random_uuid()::text,'active' FROM organisations o, generate_series(1,CASE WHEN o.slug='long' THEN 600 WHEN o.slug='rivals' THEN 400 ELSE 300 END) i")
        await s.commit()
        # numbered tables for set-based generation
        await ex("""CREATE TEMP TABLE pl AS SELECT p.id, p.organisation_id oid, row_number() OVER (PARTITION BY p.organisation_id ORDER BY p.id) rn, count(*) OVER (PARTITION BY p.organisation_id) cnt FROM players p""")
        await ex("""CREATE TEMP TABLE gr AS SELECT g.id, se.organisation_id oid, row_number() OVER (PARTITION BY se.organisation_id ORDER BY g.id) rn, count(*) OVER (PARTITION BY se.organisation_id) cnt FROM grades g JOIN seasons se ON se.id=g.season_id""")
        # games: org games (home/away alternate, opponent = rivals), noise games (club vs rivals)
        await ex("""
          CREATE TEMP TABLE gm AS
          SELECT gen_random_uuid() id, o.id oid, o.slug, n,
                 (n % 2 = 0) org_home
            FROM organisations o
            CROSS JOIN LATERAL generate_series(1, CASE WHEN o.slug='long' THEN :og WHEN o.slug LIKE 'club-%' THEN :ng ELSE 0 END) n
        """, og=ORG_GAMES, ng=NOISE_GAMES)
        await ex("""
          INSERT INTO games (id,grade_id,played_at,home_team,away_team,home_org_id,away_org_id,result,winning_team,is_final,match_format,status,innings_totals)
          SELECT gm.id, gr.id, DATE '2000-10-01' + (gm.n*3 % 9000),
                 CASE WHEN gm.org_home THEN 'Home '||gm.slug ELSE 'Rivals' END,
                 CASE WHEN gm.org_home THEN 'Rivals' ELSE 'Home '||gm.slug END,
                 CASE WHEN gm.org_home THEN gm.oid ELSE :opp END,
                 CASE WHEN gm.org_home THEN :opp ELSE gm.oid END,
                 'WIN', CASE WHEN gm.n % 3 = 0 THEN 'Rivals' ELSE 'Home '||gm.slug END,
                 (gm.n % 40 = 0), 'One Day', 'COMPLETED',
                 jsonb_build_array(
                   jsonb_build_object('innings_number',1,'runs_scored',120+(gm.n*7%140),'wickets',(gm.n%10)+1,'extras',(gm.n%17)),
                   jsonb_build_object('innings_number',2,'runs_scored',100+(gm.n*11%150),'wickets',((gm.n+3)%10)+1,'extras',(gm.n%13)))
            FROM gm JOIN gr ON gr.oid=gm.oid AND gr.rn = 1 + (gm.n % gr.cnt)
        """, opp=OPP)
        # appearances: our 11 + their 11
        for side, oid_expr, team_expr in (("ours","gm.oid","CASE WHEN gm.org_home THEN 'Home '||gm.slug ELSE 'Rivals' END"),):
            pass
        await ex("""
          INSERT INTO game_appearances (game_id,player_id,team_name,is_captain,is_wicket_keeper,is_reserve,sheet_slot)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 'Home '||gm.slug ELSE 'Rivals' END, k=1, k=2, false, k
            FROM gm CROSS JOIN generate_series(1,11) k
            JOIN pl ON pl.oid=gm.oid AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """)
        await ex("""
          INSERT INTO game_appearances (game_id,player_id,team_name,is_captain,is_wicket_keeper,is_reserve,sheet_slot)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 'Rivals' ELSE 'Home '||gm.slug END, k=1, k=2, false, k
            FROM gm CROSS JOIN generate_series(1,11) k
            JOIN pl ON pl.oid=:opp AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """, opp=OPP)
        await s.commit()
        # batting: org side bats innings 1 if org_home else 2
        await ex("""
          INSERT INTO batting_innings (game_id,player_id,innings_number,runs,balls,fours,sixes,dismissal_type,not_out,batting_position,did_not_bat)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 1 ELSE 2 END,
                 (gm.n*k*7) % 90, 10+((gm.n*k*7) % 90), (gm.n*k)%7, (gm.n*k)%3,
                 CASE WHEN k=11 THEN NULL ELSE 'caught' END, k=11, k, false
            FROM gm CROSS JOIN generate_series(1,11) k
            JOIN pl ON pl.oid=gm.oid AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """)
        await ex("""
          INSERT INTO batting_innings (game_id,player_id,innings_number,runs,balls,fours,sixes,dismissal_type,not_out,batting_position,did_not_bat)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 2 ELSE 1 END,
                 (gm.n*k*5) % 80, 10+((gm.n*k*5) % 80), (gm.n*k)%6, (gm.n*k)%2,
                 CASE WHEN k=11 THEN NULL ELSE 'bowled' END, k=11, k, false
            FROM gm CROSS JOIN generate_series(1,11) k
            JOIN pl ON pl.oid=:opp AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """, opp=OPP)
        # bowling: org bowls the other innings (6 bowlers each side)
        await ex("""
          INSERT INTO bowling_spells (game_id,player_id,innings_number,overs,maidens,runs,wickets,wides,no_balls,economy)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 2 ELSE 1 END, 8, 1, 20+((gm.n*k)%30), (gm.n*k)%4, 1,0, 4.5
            FROM gm CROSS JOIN generate_series(1,6) k
            JOIN pl ON pl.oid=gm.oid AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """)
        await ex("""
          INSERT INTO bowling_spells (game_id,player_id,innings_number,overs,maidens,runs,wickets,wides,no_balls,economy)
          SELECT gm.id, pl.id, CASE WHEN gm.org_home THEN 1 ELSE 2 END, 8, 1, 20+((gm.n*k)%30), (gm.n*k)%4, 1,0, 4.5
            FROM gm CROSS JOIN generate_series(1,6) k
            JOIN pl ON pl.oid=:opp AND pl.rn = 1 + ((gm.n*11+k) % pl.cnt)
        """, opp=OPP)
        await s.commit()
        await s.execute(text("ANALYZE")); await s.commit()
        for t in ("games","batting_innings","bowling_spells","game_appearances","grades","players"):
            print(t,(await s.execute(text(f"select count(*) from {t}"))).scalar())
    async with base.engine.begin() as c:
        # Season totals for every player who batted, from the innings above.
        await c.execute(text("""
          INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, balls_faced, fifties, hundreds, ducks, high_score, fours, sixes,
                                           bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens, five_wicket_innings, wides, no_balls, catches, catches_wk, catches_non_wk, run_outs, stumpings, source)
          SELECT bi.player_id, gr.season_id, count(distinct bi.game_id), count(*), sum(bi.runs), count(*) filter (where bi.not_out), sum(bi.balls),
                 count(*) filter (where bi.runs>=50), 0, count(*) filter (where bi.runs=0), max(bi.runs), sum(bi.fours), sum(bi.sixes),
                 0,0,0,0,0,0,0,0,0,0,0,0,0,0,'api'
            FROM batting_innings bi JOIN games g ON g.id=bi.game_id JOIN grades gr ON gr.id=g.grade_id
           GROUP BY bi.player_id, gr.season_id"""))
        await c.execute(text("ANALYZE player_season_stats"))


async def run_reports() -> dict:
    eng = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"jit": "off"}})
    Session = async_sessionmaker(eng, expire_on_commit=False)
    out, secs = {}, {}
    async with Session() as s:
        for i, (target, sort_by, filters, ctx) in enumerate(REPORTS):
            aggregations._GRID_CACHE.clear()   # a COLD load: nothing remembered from the last report
            t0 = time.perf_counter()
            r = await statlab.run_query(s, org_id=str(ORG), target=target, sort_by=sort_by, sort_dir="desc",
                                        limit=500, metric_filters=filters, filter_tree=None, context=dict(ctx))
            dt = time.perf_counter() - t0
            key = f"{i}:{target}:{sort_by}:{ctx}"
            secs[key] = dt
            out[key] = sorted(({k: (str(v) if v is not None else None) for k, v in row.items()} for row in r["rows"]),
                              key=lambda x: json.dumps(x, sort_keys=True))
            print(f"  {dt:6.2f}s  rows={len(out[key]):4d}  {target} {sort_by} {ctx}", flush=True)
    await eng.dispose()
    return {"rows": out, "secs": secs}


async def main() -> None:
    if not os.environ.get("REUSE"):
        await build_and_seed()
    print("\n-- eleven reports, each a cold load --")
    res = await run_reports()
    bound = 10 ** 9 if os.environ.get("CONTROL") else BOUND_SECONDS
    for key, dt in res["secs"].items():
        check(f"inside {BOUND_SECONDS:.0f}s: {key}", dt < bound, f"{dt:.1f}s")
    check("every report returned rows", all(len(v) > 0 for v in res["rows"].values()))
    print("\n-- the player-attribute filters still run on all three reports --")
    eng = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"jit": "off"}})
    SmokeSession = async_sessionmaker(eng, expire_on_commit=False)
    for ctx in ATTRIBUTE_CONTEXTS:
        for target in ("player_career", "player_season", "player_grade"):
            async with SmokeSession() as s:
                try:
                    await statlab.run_query(s, org_id=str(ORG), target=target, sort_by="runs", sort_dir="desc",
                                            limit=50, metric_filters=[], filter_tree=None, context=dict(ctx))
                    ok, why = True, ""
                except Exception as e:  # noqa: BLE001
                    ok, why = False, str(e)[:120]
            check(f"{target} with {ctx}", ok, why)
    await eng.dispose()
    dump = os.environ.get("DUMP")
    if dump:
        Path(dump).write_text(json.dumps(res["rows"], sort_keys=True))
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  FAILED:", f)
    await base.engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
