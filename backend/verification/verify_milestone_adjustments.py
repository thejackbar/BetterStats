"""A club's adjustments, down or up, move a player's milestones.

Raised off Leederville CC (Oct 2026): the club adjusts a player's figures to match PlayCricket, and the
Milestones page has to follow in both directions: a player taken from 100 matches to 98 has not
reached 100, and one taken past a threshold has.

Every adjustment shape goes through the shipped writer (`sync._compute_milestones`, the same call the
manual-entry routes make after a save) and the shipped figures (`milestone_totals.profile_totals`):

- a career adjustment, down and up, over CA's totals and over scorecards;
- a season adjustment with no grade;
- a season adjustment against a grade that holds scorecards;
- runs down across a threshold, wickets up across one;
- a season adjustment against a grade when CA only gives the season as a TOTAL and no scorecard places a
  match in that grade. `_attribute_cells` clamped the cell at zero and the correction vanished, so the
  grid (which the profile header and every milestone are raised to) kept reading 100.

Run on its own database:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@localhost:5432/verify_ms_adj python verification/verify_milestone_adjustments.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import aggregations, milestone_totals
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL
from app.services.sync import _compute_milestones

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


YEAR = date.today().year
ORG, SEASON, GRADE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
NAMES = ("scorecards_minus2", "scorecards_plus3", "ca_minus2", "ca_plus5", "season_null_minus2",
         "season_cell_minus2", "season_grade_total_only_minus2", "runs_minus5", "wickets_plus3", "no_adjustment")
P = {k: uuid.uuid4() for k in NAMES}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID,
                removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Leederville Test', 'lt', true)", i=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer', :y)",
                 i=SEASON, o=ORG, y=YEAR)
        await ex("INSERT INTO grades (id, season_id, name, category, categories) "
                 "VALUES (:i, :s, 'A Grade', 'senior', ARRAY['senior'])", i=GRADE, s=SEASON)
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                     "VALUES (:i, :o, :n, true, 'active')", i=pid, o=ORG, n=k)

        # 100 scorecard games for the two scorecard players and the season-cell player.
        for n in range(100):
            g = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, status) "
                     "VALUES (:i, :g, :d, 'Us', 'Them', 'COMPLETED')", i=g, g=GRADE, d=date.today() - timedelta(days=200 - n))
            for k in ("scorecards_minus2", "scorecards_plus3", "season_cell_minus2"):
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, not_out, did_not_bat) "
                         "VALUES (:g, :p, 1, 10, false, false)", g=g, p=P[k])
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=P[k])

        async def pss(k, matches, runs=0, wickets=0):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, runs, wickets, catches, batting_innings) "
                     "VALUES (:p, :s, :m, :r, :w, 0, 0)", p=P[k], s=SEASON, m=matches, r=runs, w=wickets)

        # CA's season totals: a player with no scorecards held has only these.
        await pss("ca_minus2", 100)
        await pss("ca_plus5", 95)
        await pss("season_null_minus2", 100)
        await pss("season_cell_minus2", 100)
        await pss("season_grade_total_only_minus2", 100)
        await pss("runs_minus5", 30, runs=1002)
        await pss("wickets_plus3", 30, wickets=48)
        await pss("no_adjustment", 100)

        async def career(k, **cols):
            names = ", ".join(cols)
            await ex(f"INSERT INTO manual_career_adjustments (organisation_id, player_id, {names}) "
                     f"VALUES (:o, :p, {', '.join(':' + c for c in cols)})", o=ORG, p=P[k], **cols)

        await career("scorecards_minus2", games_played=-2)
        await career("scorecards_plus3", games_played=3)
        await career("ca_minus2", games_played=-2)
        await career("ca_plus5", games_played=5)
        await career("runs_minus5", batting_runs=-5)
        await career("wickets_plus3", bowling_wickets=3)
        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, grade_id, games_played) "
                 "VALUES (:o, :p, :s, NULL, -2)", o=ORG, p=P["season_null_minus2"], s=SEASON)
        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, grade_id, games_played) "
                 "VALUES (:o, :p, :s, :g, -2)", o=ORG, p=P["season_cell_minus2"], s=SEASON, g=GRADE)
        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, grade_id, games_played) "
                 "VALUES (:o, :p, :s, :g, -2)", o=ORG, p=P["season_grade_total_only_minus2"], s=SEASON, g=GRADE)

        # Every player carries a stored 100 matches milestone from before the adjustment; the runs player a 1,000.
        for k, pid in P.items():
            await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
                     "VALUES (:p, 'matches', 100, '100 career matches', :d)", p=pid, d=date.today() - timedelta(days=2))
        await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
                 "VALUES (:p, 'runs', 1000, '1,000 career runs', :d)", p=P["runs_minus5"], d=date.today() - timedelta(days=2))
        await s.commit()


async def stored(pid) -> set:
    async with Session() as s:
        return {(r[0], r[1]) for r in (await s.execute(text(
            "SELECT milestone_type, milestone_value FROM milestones WHERE player_id = :p"), {"p": pid})).all()}


async def main() -> None:
    await build_schema()
    await seed()
    ids = list(P.values())

    async with Session() as s:
        tot = await milestone_totals.profile_totals(s, ORG, ids, with_split=False)
        grid = await aggregations.grid_matches_for_players(s, str(ORG), [str(i) for i in ids], None, None)
    m = {k: tot[str(pid)]["totals"]["matches"] for k, pid in P.items()}

    print("\n-- THE FIGURES FOLLOW THE ADJUSTMENT --")
    check("career, down, over scorecards: 98", m["scorecards_minus2"] == 98, str(m["scorecards_minus2"]))
    check("career, up, over scorecards: 103", m["scorecards_plus3"] == 103, str(m["scorecards_plus3"]))
    check("career, down, over CA's totals: 98", m["ca_minus2"] == 98, str(m["ca_minus2"]))
    check("career, up, over CA's totals: 100", m["ca_plus5"] == 100, str(m["ca_plus5"]))
    check("season, no grade, down: 98", m["season_null_minus2"] == 98, str(m["season_null_minus2"]))
    check("season, a grade that holds scorecards, down: 98", m["season_cell_minus2"] == 98, str(m["season_cell_minus2"]))
    check("season, a grade CA gives only as a season total, down: 98 (the correction used to vanish)",
          m["season_grade_total_only_minus2"] == 98, f"{m['season_grade_total_only_minus2']} (grid {grid.get(str(P['season_grade_total_only_minus2']))})")
    check("the grid agrees, so the profile header reads the same", grid.get(str(P["season_grade_total_only_minus2"])) == 98,
          str(grid.get(str(P["season_grade_total_only_minus2"]))))
    check("runs down five: 997", tot[str(P["runs_minus5"])]["totals"]["runs"] == 997)
    check("wickets up three: 51", tot[str(P["wickets_plus3"])]["totals"]["wickets"] == 51)
    check("a player nobody adjusted is untouched: 100", m["no_adjustment"] == 100, str(m["no_adjustment"]))

    print("\n-- THE STORED MILESTONES FOLLOW (reconcile, as the manual-entry routes run it) --")
    async with Session() as s:
        report = await _compute_milestones(s, ids, ORG, reconcile=True)
    removed = {(pid, t, v) for pid, t, v in report["removed"]}
    added = {(pid, t, v) for pid, t, v in report["added"]}
    for k in ("scorecards_minus2", "ca_minus2", "season_null_minus2", "season_cell_minus2",
              "season_grade_total_only_minus2"):
        check(f"{k}: the 100 matches milestone is taken back",
              (str(P[k]), "matches", 100) in removed and ("matches", 100) not in await stored(P[k]),
              str(await stored(P[k])))
    check("runs_minus5: the 1,000 runs milestone is taken back", (str(P["runs_minus5"]), "runs", 1000) in removed)
    check("wickets_plus3: the 50 wickets milestone is minted",
          (str(P["wickets_plus3"]), "wickets", 50) in added and ("wickets", 50) in await stored(P["wickets_plus3"]))
    check("scorecards_plus3 and ca_plus5 keep their 100", ("matches", 100) in await stored(P["scorecards_plus3"])
          and ("matches", 100) in await stored(P["ca_plus5"]))
    check("the unadjusted player keeps their 100", ("matches", 100) in await stored(P["no_adjustment"]))

    print("\n-- AN ADJUSTMENT THE OTHER WAY GIVES THE MILESTONE BACK --")
    async with Session() as s:
        await s.execute(text("DELETE FROM manual_career_adjustments WHERE player_id = :p"), {"p": P["ca_minus2"]})
        await s.commit()
    async with Session() as s:
        report = await _compute_milestones(s, [P["ca_minus2"]], ORG, reconcile=True)
    check("take the -2 away and the 100 is back", ("matches", 100) in await stored(P["ca_minus2"]),
          str(await stored(P["ca_minus2"])))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
