"""Debut detection for BetterSocials lineups (services/social_debuts.py).

    DATABASE_URL=postgresql+asyncpg://user:pw@host/db python backend/verification/verify_social_debuts.py

Runs the service's own SQL against a real Postgres. The effective views are
stood in for by plain tables of the same name and the columns the query reads
(the views themselves are owned by services/superseded_ddl.py and are not
re-implemented here), so this proves the debut rules and the query's shape, not
the views. SD_PATH=<a copy without the date, washout or season-year guards> is the control
run and fails the matching checks.
"""
import asyncio
import importlib.util
import os
import sys
import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("social_debuts", os.environ.get("SD_PATH") or os.path.join(HERE, "..", "app", "services", "social_debuts.py"))
sd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sd)

URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1/postgres")
passed = failed = 0


def ck(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name}  {extra}")


STUBS = """
DROP TABLE IF EXISTS game_appearances, v_effective_games, v_effective_batting_innings, v_effective_bowling_spells,
    v_effective_player_season_stats, seasons, players CASCADE;
CREATE TABLE players (id uuid PRIMARY KEY, organisation_id uuid);
CREATE TABLE seasons (id uuid PRIMARY KEY, year int);
CREATE TABLE v_effective_games (id uuid PRIMARY KEY, played_at date, status text);
CREATE TABLE game_appearances (game_id uuid, player_id uuid);
CREATE TABLE v_effective_batting_innings (player_id uuid, game_id uuid);
CREATE TABLE v_effective_bowling_spells (player_id uuid, game_id uuid);
CREATE TABLE v_effective_player_season_stats (player_id uuid, season_id uuid, matches int);
"""


async def main():
    eng = create_async_engine(URL)
    org, other = uuid.uuid4(), uuid.uuid4()
    P = {k: uuid.uuid4() for k in "ABCDEFGHI"}
    G = {k: uuid.uuid4() for k in ("past", "match_day", "washout", "imported")}
    S_old, S_cur = uuid.uuid4(), uuid.uuid4()
    async with eng.begin() as c:
        for stmt in [s for s in STUBS.split(";") if s.strip()]:
            await c.execute(text(stmt))
        for k, v in P.items():
            await c.execute(text("INSERT INTO players VALUES (:i, :o)"), {"i": v, "o": other if k == "H" else org})
        await c.execute(text("INSERT INTO seasons VALUES (:a, 2024), (:b, 2026)"), {"a": S_old, "b": S_cur})
        games = [(G["past"], date(2026, 9, 12), None), (G["match_day"], date(2026, 10, 3), None),
                 (G["washout"], date(2026, 9, 19), "ABANDONED"), (G["imported"], date(2026, 9, 5), None)]
        for gid, d, st in games:
            await c.execute(text("INSERT INTO v_effective_games VALUES (:i, :d, :s)"), {"i": gid, "d": d, "s": st})
        ga = lambda g, p: c.execute(text("INSERT INTO game_appearances VALUES (:g, :p)"), {"g": G[g], "p": P[p]})
        await ga("past", "B")           # B played before the match day
        await ga("match_day", "C")      # C appears only in the match itself (already synced)
        await ga("washout", "D")        # D was only ever named in a washout
        await c.execute(text("INSERT INTO v_effective_batting_innings VALUES (:p, :g)"), {"p": P["E"], "g": G["imported"]})  # E: an imported game
        await c.execute(text("INSERT INTO v_effective_player_season_stats VALUES (:p, :s, 12)"), {"p": P["F"], "s": S_old})  # F: an earlier season
        await c.execute(text("INSERT INTO v_effective_player_season_stats VALUES (:p, :s, 1)"), {"p": P["G"], "s": S_cur})   # G: this season only (includes the match)
        await ga("past", "H")           # H belongs to another club's register

    org_ns = SimpleNamespace(id=org)

    async def run(ids, before):
        async with eng.connect() as c:
            from sqlalchemy.ext.asyncio import AsyncSession
            async with AsyncSession(bind=c) as db:
                return await sd.social_debuts(db, org_ns, [str(P[i]) for i in ids], before)

    r = await run("ABCDEFGHI", date(2026, 10, 3))
    deb = {k for k, v in P.items() if str(v) in r["debuts"]}
    known = {k for k, v in P.items() if str(v) in r["known"]}
    ck("a player with nothing on record is a debut", "A" in deb, str(sorted(deb)))
    ck("an earlier appearance rules a debut out", "B" not in deb and "B" in known)
    ck("an appearance only in the match itself does not", "C" in deb, str(sorted(deb)))
    ck("a washout does not count as a game played", "D" in deb)
    ck("an imported batting line counts as history", "E" not in deb and "E" in known)
    ck("an earlier season's matches count as history", "F" not in deb and "F" in known)
    ck("the current season's own summary does not", "G" in deb)
    ck("another club's player is neither a debut nor known", "H" not in deb and "H" not in known)
    ck("a player id with no row is left out of known", str(uuid.uuid4()) not in r["known"] and len(r["known"]) == 8, str(len(r["known"])))
    ck("the answer names the date it was asked for", r["before"] == "2026-10-03")

    r = await run("B", date(2026, 9, 1))
    ck("asked as at a date before their first game, B is a debut", r["debuts"] == [str(P["B"])], str(r))
    r = await run("F", date(2027, 1, 15))
    ck("January belongs to the season that began the year before", sd.season_start_year(date(2027, 1, 15)) == 2026 and sd.season_start_year(date(2026, 10, 3)) == 2026)
    ck("an empty list answers empty", (await run("", None))["debuts"] == [])
    ids = sd.parse_ids(f"{P['A']}, junk,{P['A']},,{P['B']}")
    ck("parse_ids drops junk and repeats, keeps order", ids == [str(P["A"]), str(P["B"])], str(ids))
    ck("parse_ids caps the list", len(sd.parse_ids(",".join(str(uuid.uuid4()) for _ in range(100)))) == sd.MAX_PLAYERS)

    async with eng.begin() as c:
        await c.execute(text(STUBS.split(";")[0]))
    await eng.dispose()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


asyncio.run(main())
