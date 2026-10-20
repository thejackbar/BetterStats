"""A washed-out game taken off a player's total must not come back through the by-grade grid.

Reported off Leederville CC: after a weekend most players read 101 where PlayCricket reads 100 and the
club expects 99. The season table was right (Wilbur Bissett, 2025/26: CA counts 8, the abandoned round 1
game is taken off, the table reads 7). The profile header read 8, because it is RAISED to the by-grade
grid and the grid takes `max(scorecards held, CA's per-grade claim)`. CA's per-grade claim still counts
the abandoned game (D Grade 1, with no scorecard held for it), so the grid put it straight back.

`v_effective_player_season_stats` already takes an ABANDONED or CANCELLED fixture off CA's total where
the player was named and recorded nothing (migration 266). The grid now takes the same games off CA's
per-grade claim, but only as far as the claim runs past the games we hold: CA counts a washout
`LEAST(W, GREATEST(claim - held, 0))` of the time and a blind subtraction would under-count the players
whose claim never included it.

Reads every figure through the shipped route bodies with the production views, against a real Postgres.
The same file run against the previous commit is the control: the player CA counted the washout for
reads 5 there and 4 here.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_washout_grid.py
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

from verify_board_games_match_profile import build_schema
from app.routers.leaderboard import batting_leaderboard
from app.routers.players import get_player_stats
from app.services import superseded_ddl
from app.services.aggregations import get_player_team_breakdown, get_season_by_season

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


ORG, OPP = uuid.uuid4(), uuid.uuid4()
SEASON = uuid.uuid4()
GRADE_D, GRADE_F = uuid.uuid4(), uuid.uuid4()
P = {k: uuid.uuid4() for k in ("COUNTED", "NOTCOUNTED", "CLEAN", "TWOGRADE", "CANCELLED")}
NAMES = {"COUNTED": "Bissett, Wilbur", "NOTCOUNTED": "Notcounted, Nat", "CLEAN": "Clean, Carl",
         "TWOGRADE": "Twograde, Tom", "CANCELLED": "Cancelled, Cal"}
_day = 0


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Washout Club", "washout"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
        for gid, nm in ((GRADE_D, "D Grade"), (GRADE_F, "F Grade")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=SEASON, n=nm, g=str(gid))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=str(pid))

        async def game(grade, status="COMPLETED") -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            # One scored innings, as the abandoned round 1 game had: play started, then rain.
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, "
                     " innings_totals) VALUES (:i, :g, :d, :r, :o, :x, 'One Day', :st, "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 90, 'wickets', 3)))",
                     i=gid, g=grade, d=date(2025, 10, 4) + timedelta(days=_day), r=None if status != "COMPLETED" else "WIN",
                     o=ORG, x=OPP, st=status)
            return gid

        async def real(key, grade, n):
            for _ in range(n):
                gid = await game(grade)
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                         " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=P[key])

        async def washed(key, grade, status="ABANDONED"):
            gid = await game(grade, status)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])

        async def ca(key, season_total, claims):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=SEASON, m=season_total)
            for grade, n in claims.items():
                await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, :m)",
                         p=P[key], s=SEASON, g=grade, m=n)

        # COUNTED (Bissett's shape): 4 real D Grade games and a washed-out one. CA counted all 5, in total and per grade.
        await real("COUNTED", GRADE_D, 4)
        await washed("COUNTED", GRADE_D)
        await ca("COUNTED", 5, {GRADE_D: 5})
        # NOTCOUNTED: the same games, but CA's own figure never included the washout (4). Nothing to take off the grid.
        await real("NOTCOUNTED", GRADE_D, 4)
        await washed("NOTCOUNTED", GRADE_D)
        await ca("NOTCOUNTED", 4, {GRADE_D: 4})
        # CLEAN: no washout at all.
        await real("CLEAN", GRADE_D, 3)
        await ca("CLEAN", 3, {GRADE_D: 3})
        # TWOGRADE: 3 D Grade and 2 F Grade real games, and a washed-out F Grade game CA counted (per grade: D 3, F 3).
        await real("TWOGRADE", GRADE_D, 3)
        await real("TWOGRADE", GRADE_F, 2)
        await washed("TWOGRADE", GRADE_F)
        await ca("TWOGRADE", 6, {GRADE_D: 3, GRADE_F: 3})
        # CANCELLED: a cancelled fixture is a called-off game the same way.
        await real("CANCELLED", GRADE_D, 2)
        await washed("CANCELLED", GRADE_D, status="CANCELLED")
        await ca("CANCELLED", 3, {GRADE_D: 3})
        await s.commit()


async def header(key) -> int | None:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


async def season_row(key) -> int | None:
    async with Session() as s:
        rows = await get_season_by_season(s, str(P[key]), include_prior=True)
    return next((r["matches"] for r in rows if str(r.get("season_id")) == str(SEASON)), None)


async def grid(key) -> dict:
    async with Session() as s:
        return await get_player_team_breakdown(s, str(P[key]), str(ORG), None)


async def board(key) -> int | None:
    async with Session() as s:
        rows = await batting_leaderboard(db=s, viewer=None, org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
                                         limit=50, finals_only=None, captain_only=None, gender=None, overseas=None,
                                         categories=None, formats=None, competitions=None, sort_by="total_runs",
                                         min_runs=0, min_rate_innings=0)
    row = next((r for r in rows if str(r["player_id"]) == str(P[key])), None)
    return None if row is None else row.get("games")


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:     # the lifespan re-applies these: production reads THESE views
            await conn.execute(text(stmt))
    await seed()

    print("\n-- THE SEASON TABLE ALREADY TAKES THE WASHOUT OFF CA'S TOTAL (migration 266) --")
    check("Bissett's shape: CA counts 5, the season table reads 4", await season_row("COUNTED") == 4, str(await season_row("COUNTED")))

    print("\n-- AND THE GRID AND THE HEADER MUST NOT PUT IT BACK --")
    g = await grid("COUNTED")
    check("the by-grade grid reads 4 (CA's D Grade claim of 5 counted the abandoned game)", g["grid_matches"] == 4, str(g["grid_matches"]))
    check("no D Grade cell is drawn for a game with no scorecard held and no play by the player",
          g["season_rows"][0]["grades"] == {"D Grade": 4}, str(g["season_rows"][0]["grades"]))
    check("the profile header reads 4, the club's figure (CA's own total is 5)", await header("COUNTED") == 4, str(await header("COUNTED")))
    check("the batting board agrees with the profile", await board("COUNTED") == 4, str(await board("COUNTED")))

    print("\n-- WHERE CA NEVER COUNTED IT, NOTHING IS TAKEN OFF THE GRID --")
    check("CA says 4 and the washout is not among them: the header reads 4, not 3", await header("NOTCOUNTED") == 4, str(await header("NOTCOUNTED")))
    check("and its grid cell stays at the games held", (await grid("NOTCOUNTED"))["grid_matches"] == 4)

    print("\n-- A PLAYER WITH NO WASHOUT IS UNTOUCHED --")
    check("3 real games and CA 3 read 3 everywhere", await header("CLEAN") == 3 and await season_row("CLEAN") == 3
          and (await grid("CLEAN"))["grid_matches"] == 3)

    print("\n-- THE CORRECTION LANDS ON THE GRADE THE WASHOUT WAS IN --")
    g2 = await grid("TWOGRADE")
    check("D Grade keeps its 3 and F Grade falls from CA's claim of 3 to the 2 played", g2["season_rows"][0]["grades"] == {"D Grade": 3, "F Grade": 2},
          str(g2["season_rows"][0]["grades"]))
    check("the header reads 5", await header("TWOGRADE") == 5, str(await header("TWOGRADE")))

    print("\n-- A CANCELLED FIXTURE IS CALLED OFF THE SAME WAY --")
    check("CA counts 3, one cancelled: the grid and header read 2",
          (await grid("CANCELLED"))["grid_matches"] == 2 and await header("CANCELLED") == 2,
          f"{(await grid('CANCELLED'))['grid_matches']} / {await header('CANCELLED')}")

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
