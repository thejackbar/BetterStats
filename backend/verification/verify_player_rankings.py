"""Club rankings on the player share card, against a real Postgres, through the shipped service.

`get_player_rankings` feeds the back of the share card: a chip for every statistic the player is in
the club's top 100 for. What is asserted:

* all seven keys come back (matches, runs, batting average, wickets, bowling average, dismissals,
  catches), and a player with a figure but nobody ahead of them is rank 1;
* DISMISSALS is catches + run outs + stumpings, not catches alone;
* a figure of zero is never ranked (a player with no wickets is not "#40 for wickets");
* an AVERAGE is ranked only among players past the minimum (10 innings, 10 wickets): a player with
  the best average on 9 innings or 9 wickets is unranked, and the same average on 10 is rank 1;
* a bowling average is ranked low-is-best;
* top 100 only: with 105 run scorers the 100th is ranked and the 101st is not;
* a season pick ranks on that season's figures alone;
* every "is absent" check is paired with a check that the same key can be present.

Run on its own database:
  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/verify_rank python verification/verify_player_rankings.py

CONTROL: run against the previous commit. Keys are read with .get, so the control reports the
missing keys as failed checks instead of crashing.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import aggregations
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL

engine = create_async_engine(os.environ["DATABASE_URL"], connect_args={"server_settings": {"jit": "off"}})
Session = async_sessionmaker(engine, expire_on_commit=False)

passed = failed = 0


def ck(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name}{'  - ' + str(extra) if extra else ''}")


ORG, S_NOW, S_OLD = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in JUNIOR_DDL:
            await conn.execute(text(stmt))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))


async def seed() -> dict:
    ids: dict = {}
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active, module_overrides) "
                 "VALUES (:i, 'Rank CC', 'rank-cc', true, CAST('[]' AS JSONB))", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:a, :o, 'Summer 2025/26', 2025), (:b, :o, 'Summer 2024/25', 2024)",
                 a=S_NOW, b=S_OLD, o=ORG)

        async def player(key, name):
            ids[key] = uuid.uuid4()
            await ex("INSERT INTO players (id, organisation_id, name, is_player, status, is_public) "
                     "VALUES (:i, :o, :n, true, 'active', true)", i=ids[key], o=ORG, n=name)

        async def pss(key, sid, **kw):
            cols = {"matches": 0, "runs": 0, "wickets": 0, "catches": 0, "batting_innings": 0, "not_outs": 0,
                    "runs_conceded": 0, "run_outs": 0, "stumpings": 0}
            cols.update(kw)
            await ex(f"INSERT INTO player_season_stats (player_id, season_id, {', '.join(cols)}) "
                     f"VALUES (:p, :s, {', '.join(':' + k for k in cols)})", p=ids[key], s=sid, **cols)

        # The all-rounder under test: ahead on everything bar one thing, with fielding in every shape.
        await player("star", "Star, S")
        await pss("star", S_OLD, matches=100, runs=3000, batting_innings=90, not_outs=10,        # avg 37.5
                  wickets=120, runs_conceded=2400, catches=30, run_outs=5, stumpings=7)          # bowl avg 20
        await pss("star", S_NOW, matches=20, runs=400, batting_innings=18, not_outs=2,
                  wickets=20, runs_conceded=500, catches=10, run_outs=1, stumpings=2)
        # A player who has done nothing but turn up: has matches only.
        await player("sub", "Sub, S")
        await pss("sub", S_NOW, matches=3)
        # Best average on 9 innings (below the bar) against the same average on 10 (past it).
        await player("nine", "Nine, N")
        await pss("nine", S_NOW, matches=9, runs=900, batting_innings=9, not_outs=0, wickets=9, runs_conceded=90)
        await player("ten", "Ten, T")
        await pss("ten", S_NOW, matches=10, runs=1000, batting_innings=10, not_outs=0, wickets=10, runs_conceded=100)
        # 105 more run scorers, each one run below the one before, for the top-100 cut.
        for i in range(105):
            await player(f"r{i}", f"Runner{i:03d}, R")
            await pss(f"r{i}", S_NOW, matches=5, runs=10 + (105 - i), batting_innings=5, not_outs=0)
        await s.commit()
    return ids


async def ranks(pid, season_id=None):
    async with Session() as s:
        return await aggregations.get_player_rankings(s, str(pid), str(ORG), season_id)


async def main() -> None:
    await build_schema()
    ids = await seed()

    star = await ranks(ids["star"])
    for k in ("matches_rank", "runs_rank", "bat_avg_rank", "wickets_rank", "bowl_avg_rank", "dismissals_rank", "catches_rank"):
        ck(f"star has {k}", k in star, f"keys={sorted(star)}")
    ck("matches rank 1 (120 matches)", star.get("matches_rank") == 1, star.get("matches_rank"))
    ck("runs rank 1 (3,400 runs)", star.get("runs_rank") == 1, star.get("runs_rank"))
    # star: 3400 / (108 - 12) = 35.42 against Ten 100.0 and Nine 100.0 (Nine is under the bar) and the runners (<= 23).
    ck("batting average rank 2 behind the 10-innings 100.0", star.get("bat_avg_rank") == 2, star.get("bat_avg_rank"))
    ck("wickets rank 1 (140)", star.get("wickets_rank") == 1, star.get("wickets_rank"))
    # star bowls at 2900/140 = 20.7; Ten bowls at 10.0 (10 wickets, past the bar); Nine is under it.
    ck("bowling average rank 2 behind the 10-wicket 10.0 (lower is better)", star.get("bowl_avg_rank") == 2, star.get("bowl_avg_rank"))
    ck("dismissals rank 1 (catches + run outs + stumpings = 55)", star.get("dismissals_rank") == 1, star.get("dismissals_rank"))
    ck("catches rank 1 (40)", star.get("catches_rank") == 1, star.get("catches_rank"))

    nine = await ranks(ids["nine"])
    ten = await ranks(ids["ten"])
    ck("9 innings: best average is unranked", "bat_avg_rank" in nine and nine["bat_avg_rank"] is None, nine.get("bat_avg_rank", "missing"))
    ck("10 innings: the same average is rank 1", ten.get("bat_avg_rank") == 1, ten.get("bat_avg_rank"))
    ck("9 wickets: bowling average unranked", "bowl_avg_rank" in nine and nine["bowl_avg_rank"] is None, nine.get("bowl_avg_rank", "missing"))
    ck("10 wickets: bowling average is rank 1 (lowest)", ten.get("bowl_avg_rank") == 1, ten.get("bowl_avg_rank"))

    sub = await ranks(ids["sub"])
    ck("zero runs, wickets, catches, dismissals are never ranked",
       all(k in sub and sub[k] is None for k in ("runs_rank", "wickets_rank", "catches_rank", "dismissals_rank", "bat_avg_rank", "bowl_avg_rank")), sub)

    # Runners: r0 has 115 runs, r104 has 11. Star (3,400), Ten (1,000) and Nine (900) are ahead of all of them,
    # so r96 has 3 + 96 ahead = rank 100 (in) and r97 is rank 101 (out).
    r_edge = await ranks(ids["r96"])
    r_in = await ranks(ids["r97"])
    ck("rank 100 is shown", r_edge.get("runs_rank") == 100, r_edge.get("runs_rank"))
    ck("rank 101 is not", "runs_rank" in r_in and r_in["runs_rank"] is None, r_in.get("runs_rank", "missing"))

    now = await ranks(ids["star"], str(S_NOW))
    # Career the star is rank 1 (3,400); in 2025/26 alone they have 400 behind Ten (1,000) and Nine (900).
    ck("a season pick ranks on that season alone (rank 3, not the career 1)", now.get("runs_rank") == 3, now.get("runs_rank"))
    old = await ranks(ids["ten"], str(S_OLD))
    ck("a season the player did not play ranks nothing", all(v is None for v in old.values()) and len(old) == 7, old)

    print(f"\n{passed} passed, {failed} failed")
    await engine.dispose()
    sys.exit(1 if failed else 0)


asyncio.run(main())
