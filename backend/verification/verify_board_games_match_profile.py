"""The leaderboards' Games column must agree with the profile's MATCHES, against a real Postgres.

Reported by Shoalwater Bay: David Smith is on 377 games on the leaderboard and 385 on his profile,
and "nearly all the players' games on the leaderboard differ from their profile". Measured on the
live club: 35 of the top 60 batters differed, every one with the profile HIGHER, by the matches
Cricket Australia's per-grade totals claim and the club holds no scorecard for (David Smith:
CA 387, scorecards held 377, the by-grade grid 385).

Two definitions of "games" were in play. The profile header is RAISED to the by-grade grid
(`raise_games_to_grid_total`, per season and grade `max(held, CA claims)`), the boards counted only
the scorecards held (plus imports and seasons held none of). The boards now run the SAME loader and
the SAME attribution (`_grid_inputs`, `_attribute_cells`) for the rows they return and raise to it,
never lower.

Seeds the shapes the grid treats differently and compares all three boards (batting, bowling,
fielding) with the profile header, each through the shipped route body.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_board_games_match_profile.py
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
from app.routers.leaderboard import batting_leaderboard, bowling_leaderboard, fielding_leaderboard
from app.routers.players import get_player_stats
from app.services.aggregations import raise_board_games_to_grid

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

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
S_NEW, S_OLD = uuid.uuid4(), uuid.uuid4()
G_NEW, G_OLD, G_JNR = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

# The reported shape: CA's per-grade total claims 2 more than the cards held in one grade.
SHORT_EXACT = uuid.uuid4()
# No per-grade rows for the season; CA's season total is 1 above the cards, one grade only.
SHORT_SEASON = uuid.uuid4()
# CA and the cards agree.
AGREES = uuid.uuid4()
# CA claims LESS than held: neither side lowers.
HELD_MORE = uuid.uuid4()
# Played senior and junior in one season; CA's season total covers both, so the filter's
# exclusion means the gap is NOT this scope's to place.
MIXED = uuid.uuid4()
PLAYERS = {SHORT_EXACT: "Short, Exact", SHORT_SEASON: "Short, Season", AGREES: "Agrees, Al",
           HELD_MORE: "Held, More", MIXED: "Mixed, Max"}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
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
            CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL, target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)"""))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Board Club", "board"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        for sid, nm, yr in ((S_NEW, "Summer 2025/26", 2025), (S_OLD, "Summer 2024/25", 2024)):
            await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                     i=sid, o=ORG, n=nm, y=yr)
        for gid, sid, nm, cat in ((G_NEW, S_NEW, "A Grade", "senior"), (G_OLD, S_OLD, "A Grade", "senior"),
                                  (G_JNR, S_NEW, "Under 16s", "junior")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, :c, ARRAY[CAST(:c AS TEXT)])", i=gid, s=sid, n=nm, g=str(gid), c=cat)
        for pid, nm in PLAYERS.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

        day = 0

        async def games(player, grade, count):
            nonlocal day
            for _ in range(count):
                day += 1
                gid = uuid.uuid4()
                await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                         " match_format, status) VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                         i=gid, g=grade, d=date(2025, 1, 1) + timedelta(days=day), o=ORG, x=OPP)
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, "
                         " sixes, not_out, dismissal_type, did_not_bat) "
                         "VALUES (:g, :p, 1, 20, 25, 1, 0, false, 'caught', false)", g=gid, p=player)
                await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, "
                         " wickets) VALUES (:g, :p, 1, 4.0, 0, 20, 1)", g=gid, p=player)
                await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                         "VALUES (:g, :p, 1, 0, 0, 0)", g=gid, p=player)
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=player)

        async def season_total(player, season, matches):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
                     " not_outs, wickets, catches, source) VALUES (:p, :s, :m, :m, :r, 0, :m, :m, 'api')",
                     p=player, s=season, m=matches, r=matches * 20)

        async def grade_total(player, season, grade, matches):
            await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) "
                     "VALUES (:p, :s, :g, :m)", p=player, s=season, g=grade, m=matches)

        # SHORT_EXACT: holds 5 in A Grade 25/26, CA's per-grade row says 7.
        await games(SHORT_EXACT, G_NEW, 5)
        await season_total(SHORT_EXACT, S_NEW, 7)
        await grade_total(SHORT_EXACT, S_NEW, G_NEW, 7)
        # SHORT_SEASON: holds 3 in 24/25, no per-grade rows, CA season total 4.
        await games(SHORT_SEASON, G_OLD, 3)
        await season_total(SHORT_SEASON, S_OLD, 4)
        # AGREES: 4 held, CA says 4 both ways.
        await games(AGREES, G_NEW, 4)
        await season_total(AGREES, S_NEW, 4)
        await grade_total(AGREES, S_NEW, G_NEW, 4)
        # HELD_MORE: 6 held, CA claims only 4.
        await games(HELD_MORE, G_NEW, 6)
        await season_total(HELD_MORE, S_NEW, 4)
        await grade_total(HELD_MORE, S_NEW, G_NEW, 4)
        # MIXED: 3 senior + 2 junior held in 25/26; CA's season total (5) covers both, no per-grade rows.
        await games(MIXED, G_NEW, 3)
        await games(MIXED, G_JNR, 2)
        await season_total(MIXED, S_NEW, 6)   # one more than held: a gap the scope cannot place
        await s.commit()


async def profile_games(player) -> int:
    async with Session() as s:
        d = await get_player_stats(
            player_id=str(player), db=s, season_id=None, grade_id=None, last_n_games=None,
            start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


async def board_games(kind: str, player, **kw) -> int | None:
    fn = {"batting": batting_leaderboard, "bowling": bowling_leaderboard, "fielding": fielding_leaderboard}[kind]
    params = dict(org_id=str(ORG), season_id=None, grade_id=None, grade_name=None, limit=50,
                  finals_only=None, captain_only=None, gender=None, overseas=None,
                  categories=None, formats=None, competitions=None)
    if kind == "batting":
        params.update(sort_by="total_runs", min_runs=0, min_rate_innings=0)
    elif kind == "bowling":
        params.update(sort_by="total_wickets", min_overs=0, min_wickets=0, min_rate_spells=0)
    else:
        params.update(sort_by="total_dismissals")
    params.update(kw)
    async with Session() as s:
        rows = await fn(db=s, viewer=None, **params)
    row = next((r for r in rows if str(r["player_id"]) == str(player)), None)
    return None if row is None else row.get("games")


async def main() -> None:
    await build_schema()
    await seed()

    print("\n-- A BOARD'S GAMES READS WHAT THE PLAYER'S OWN PAGE READS --")
    expect = {SHORT_EXACT: 7, SHORT_SEASON: 4, AGREES: 4, HELD_MORE: 6}
    for pid, want in expect.items():
        prof = await profile_games(pid)
        check(f"{PLAYERS[pid]}: the profile reads {want}", prof == want, str(prof))
        for kind in ("batting", "bowling", "fielding"):
            got = await board_games(kind, pid)
            check(f"{PLAYERS[pid]}: the {kind} board reads {want} too (control reads the cards held)",
                  got == want, f"board {got} profile {prof}")

    print("\n-- WHERE THE CA TOTAL COVERS MATCHES THE SCOPE EXCLUDED, THE GAP IS NOT PLACED --")
    prof = await profile_games(MIXED)
    got = await board_games("batting", MIXED)
    check("Mixed: profile and board agree", prof == got, f"board {got} profile {prof}")
    check("and neither invents a match for the senior grade out of the junior games",
          got == 3, str(got))

    print("\n-- A BOARD IS NEVER RAISED WHERE THE FIGURE MEANS SOMETHING ELSE --")
    got_final = await board_games("batting", SHORT_EXACT, finals_only=True)
    check("finals-only is left on its own count (no finals were played: the player is not listed)",
          got_final is None, str(got_final))
    got_grade = await board_games("batting", SHORT_EXACT, grade_name="A Grade")
    check("a picked grade is left on that grade's held matches (5, not the grid's 7)",
          got_grade == 5, str(got_grade))

    print("\n-- A SEASON PICK AGREES TOO --")
    async with Session() as s:
        d = await get_player_stats(
            player_id=str(SHORT_EXACT), db=s, season_id=str(S_NEW), grade_id=None, last_n_games=None,
            start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    prof_season = (d["career_batting"] or {}).get("games")
    board_season = await board_games("batting", SHORT_EXACT, season_id=str(S_NEW))
    check("the season-picked board equals the season-picked profile", prof_season == board_season == 7,
          f"profile {prof_season} board {board_season}")

    print("\n-- A CLUB WITH NO JUNIOR GRADES READS CA'S TOTALS, AND THE BOARD STILL AGREES --")
    async with Session() as s:
        await s.execute(text("UPDATE grades SET category = 'senior', categories = ARRAY['senior'] WHERE id = :g"),
                        {"g": G_JNR})
        await s.commit()
    for pid in (SHORT_EXACT, SHORT_SEASON, AGREES, HELD_MORE, MIXED):
        prof = await profile_games(pid)
        got = await board_games("batting", pid)
        check(f"{PLAYERS[pid]}: board {got} = profile {prof}", prof == got and prof is not None, f"{got} vs {prof}")

    print("\n-- A VERY LARGE BOARD IS LEFT ON ITS OWN COUNT --")
    rows = [{"player_id": str(SHORT_EXACT), "games": 5}, {"player_id": str(SHORT_SEASON), "games": 3}]
    async with Session() as s:
        left = await raise_board_games_to_grid(s, str(ORG), [dict(r) for r in rows], max_rows=1)
        raised = await raise_board_games_to_grid(s, str(ORG), [dict(r) for r in rows])
    check("over the cap nothing changes", [r["games"] for r in left] == [5, 3], str(left))
    check("inside it the same rows are raised", [r["games"] for r in raised] == [7, 4], str(raised))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
