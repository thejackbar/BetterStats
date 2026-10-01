"""Verification: a game that looks never played is not a match, whatever CA's status says.

Reported off Jonathon Seen (ACC): 202 matches here against 197 on Cricket
Australia's own profile, innings and runs identical. All five extra games were
completed fixtures with a result and NO PLAY recorded: four with no innings at
all, one with 4.4 overs bowled by the opposition and a "DRAW". Cricket
Australia's status for every one of them reads COMPLETED, so the existing
called-off rule (`ABANDONED` / `CANCELLED`) never saw them, and the club's
named side counted them as matches played.

The rule under test (`services/game_status.looks_unplayed_sql`): a synced game
CA calls COMPLETED (or has no status for) is treated as called off when its
scorecard is EMPTY: no innings scored a run or lost a wicket, nobody has a real
batting line and nobody has a bowling spell. A game that started and was then
stopped has play behind it and still counts (the 4.4-over draw below), as does
any game with a real line for the player. Hand-typed games are never touched.

Runs the SHIPPED service and route bodies over the `v_effective_*` views
pulled straight out of the migrations.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_inferred_unplayed.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.routers.players import (get_player_stats, get_player_formats,
                                 get_player_competitions,
                                 get_player_team_breakdown_endpoint)
from app.routers.records import get_records
from app.services import match_coverage
from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS

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


ORG = uuid.uuid4()
OPPONENT = uuid.uuid4()
S_NEW = uuid.uuid4()
G_1ST = uuid.uuid4()
G_JNR = uuid.uuid4()   # a junior grade, so a Men's/senior scope is ACTIVE

PLAYER = uuid.uuid4()      # the player whose count is read: named in every game
BOWLER = uuid.uuid4()      # bowled in the "4.4 overs" game
BATTER = uuid.uuid4()      # a real batting line in the one-innings game
JUNIOR = uuid.uuid4()      # makes the club have a junior grade


def _scoring(runs: int, wickets: int = 0) -> dict:
    return {"innings_number": 1, "runs_scored": runs, "wickets": wickets, "extras": 1}


TWO_INNINGS = [dict(_scoring(180, 6), innings_number=1), dict(_scoring(150, 10), innings_number=2)]
ONE_INNINGS = [_scoring(13, 0)]
# Innings placeholders CA sends for a game that never started.
EMPTY_INNINGS = [dict(innings_number=1, runs_scored=0, wickets=0, extras=0)]

# name -> (status, result, innings_totals, rows, expected_counts_for_PLAYER)
#   rows: which rows exist in the game, by player
GAMES = {
    # The player was named in a side that played a full match: counts, however
    # little they did. This is the false positive the rule must not make.
    "played_full":        ("COMPLETED", "WIN", TWO_INNINGS, {"bat": [BATTER], "bowl": [BOWLER]}, True),
    # The reported games: completed, a result, no innings and nobody recorded
    # anything. Four of the five were exactly this.
    "no_play_win":        ("COMPLETED", "WIN", None, {}, False),
    "no_play_no_result":  ("COMPLETED", None, None, {}, False),
    "no_play_zero_innings": ("COMPLETED", "WIN", EMPTY_INNINGS, {}, False),
    # Older games synced before CA's status was stored: NULL status, no play.
    "no_play_null_status": (None, "WIN", None, {}, False),
    # Play STARTED: 4.4 overs bowled by the opposition, a DRAW recorded, our
    # side bowled. A game begun and then stopped is a game (and CA counts it);
    # an earlier draft of the rule wrongly dropped it.
    "drawn_after_4_overs": ("COMPLETED", "DRAW", ONE_INNINGS, {"bowl": [BOWLER]}, True),
    # One innings of totals and real rows on both sides: counts.
    "one_innings_recorded":      ("COMPLETED", "WIN", ONE_INNINGS, {"bat": [BATTER], "bowl": [BOWLER]}, True),
    # In progress, nothing yet: not our call to make.
    "live_no_innings":    ("LIVE", None, None, {}, True),
    # An older scorecard with real rows but no stored totals: counts.
    "old_scorecard":      (None, "WIN", None, {"bat": [BATTER]}, True),
    # Called off outright: the existing rule, unchanged.
    "abandoned":          ("ABANDONED", None, None, {}, False),
    # The player recorded a real line in an otherwise empty game: keeps it.
    "no_play_but_player_bowled": ("COMPLETED", "WIN", None, {"bowl": [PLAYER]}, True),
}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        # Lifespan DDL (main.py): not on the ORM model.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in (
            "CREATE TABLE IF NOT EXISTS grade_merge_logs (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)",
            "CREATE TABLE IF NOT EXISTS season_aliases (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, undone_at TIMESTAMPTZ)",
            "CREATE TABLE IF NOT EXISTS org_merge_logs (id UUID PRIMARY KEY DEFAULT gen_random_uuid(), source_org_id UUID, source_org_name TEXT NOT NULL, target_org_id UUID NOT NULL, performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)",
        ):
            await conn.execute(text(stmt))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


GAME_ID: dict[str, uuid.UUID] = {}
MANUAL_ID = uuid.uuid4()


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Test CC', 'test', true)", i=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2025/26', 2025)",
             i=S_NEW, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])", i=G_1ST, s=S_NEW, g=str(G_1ST))
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'Under 16s', :g, 'junior', ARRAY['junior'])", i=G_JNR, s=S_NEW, g=str(G_JNR))
    for pid, nm in ((PLAYER, "Seen, Jonathon"), (BOWLER, "Bowler, Ben"),
                    (BATTER, "Batter, Bob"), (JUNIOR, "Junior, Jim")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

    day = 1
    for name, (status, result, totals, rows, _expected) in GAMES.items():
        gid = uuid.uuid4()
        GAME_ID[name] = gid
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                 " match_format, status, innings_totals) "
                 "VALUES (:i, :g, :d, :r, :o, :x, 'One Day', :s, CAST(:t AS JSONB))",
                 i=gid, g=G_1ST, d=date(2025, 1, day), r=result, o=ORG, x=OPPONENT,
                 s=status, t=json.dumps(totals) if totals is not None else None)
        day += 1
        # The club's side is named in every game.
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=PLAYER)
        for p in rows.get("bat", []):
            await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, "
                     " not_out, dismissal_type, did_not_bat) "
                     "VALUES (:g, :p, 20, 30, 1, 0, false, 'caught', false)", g=gid, p=p)
        for p in rows.get("bowl", []):
            await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, 4.0, 0, 20, 1)", g=gid, p=p)

    # A junior game, so the club has a junior grade and the career scope below
    # is genuinely ACTIVE (the filtered path, which is what reads held games).
    jg = uuid.uuid4()
    await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
             " match_format, status, innings_totals) "
             "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED', CAST(:t AS JSONB))",
             i=jg, g=G_JNR, d=date(2025, 2, 1), o=ORG, x=OPPONENT, t=json.dumps(TWO_INNINGS))
    await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, dismissal_type, "
             " did_not_bat) VALUES (:g, :p, 4, 9, false, 'caught', false)", g=jg, p=JUNIOR)

    # A hand-typed game for PLAYER with nothing but a team sheet line: a manual
    # game has no upstream to re-pull from and is NEVER inferred away.
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, played_at, result, "
             " home_team, away_team) VALUES (:i, :o, :s, :d, 'WIN', 'Us', 'Them')",
             i=MANUAL_ID, o=ORG, s=S_NEW, d=date(2025, 3, 1))
    await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, runs, not_out, "
             " did_not_bat) VALUES (:g, :p, 0, false, true)", g=MANUAL_ID, p=PLAYER)


EXPECTED = {n for n, v in GAMES.items() if v[4]}
EXPECTED_N = len(EXPECTED) + 1   # + the hand-typed game


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()

    async with Session() as session:
        # A scope that is ACTIVE (senior only), so the header counts games we hold.
        header = await get_player_stats(
            player_id=str(PLAYER), db=session, season_id=None, grade_id=None,
            last_n_games=None, start_date=None, end_date=None,
            categories="senior", formats=None, competitions=None)
        games = header["career_batting"]["games"]
        print("\n-- the header's Matches, counted from games we hold --")
        check(f"counts exactly the {EXPECTED_N} games that were played "
              f"({', '.join(sorted(EXPECTED))} + the hand-typed one)",
              games == EXPECTED_N, f"got {games}")

        held = await match_coverage.scorecard_matches(session, str(PLAYER), ORG)
        print("\n-- the coverage note counts the same games --")
        check("scorecard_matches agrees with the header", held == EXPECTED_N, f"got {held}")

        # Every other reader of "matches played" goes through the same shared
        # predicate; if one of them quietly kept its own copy it would read 11.
        print("\n-- every other reader agrees --")
        fm = await get_player_formats(player_id=str(PLAYER), season_id=None, db=session)
        fmt_total = sum(int(r.get("matches") or 0) for r in fm["formats"]) \
            + int((fm.get("not_recorded") or {}).get("matches") or 0)
        check("Formats splits the same games", fmt_total == EXPECTED_N,
              f"got {fmt_total}; keys {list(fm.keys())}")
        comp = await get_player_competitions(player_id=str(PLAYER), season_id=None, db=session)
        comp_total = sum(int(r.get("matches") or 0) for r in (comp.get("rows") or comp.get("competitions") or []))
        comp_total += int(comp.get("unattributed") or 0)
        check("Competitions counts the same games", comp_total == EXPECTED_N,
              f"got {comp_total}; keys {list(comp.keys())}")
        grid = await get_player_team_breakdown_endpoint(
            player_id=str(PLAYER), season_id=None, categories=None, formats=None,
            competitions=None, db=session)
        grid_total = sum(int(r.get("scorecard_matches") or 0) for r in grid["rows"]) \
            + int(grid.get("unattributed") or 0)
        check("the by-grade grid counts the same games (held, before CA's own figure)",
              grid_total >= EXPECTED_N - 1 and grid_total <= EXPECTED_N,
              f"got {grid_total}")
        from app.services import milestone_totals
        mt = await milestone_totals.profile_totals(session, ORG, [PLAYER], with_split=False)
        check("Milestones' matches figure counts the same games",
              int(mt[str(PLAYER)]["totals"]["matches"]) == EXPECTED_N,
              f"got {mt.get(str(PLAYER))}")
        rec = await get_records(org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
                                finals_only=False, captain_only=False, gender=None,
                                categories="senior", formats=None, competitions=None,
                                debug_timing=False, db=session, viewer=None)
        mm = {r["player_id"]: r for r in (rec.get("team") or {}).get("most_matches", [])}
        row = mm.get(str(PLAYER))
        # The board is built from graded games, so the grade-less hand-typed game
        # is not on it either way (true before this change too): 5, not 6.
        check("Records' Most Matches counts the same played games",
              row is not None and int(row.get("matches") or 0) == EXPECTED_N - 1,
              f"got {row}")

        # Per game, so a failure names the scenario rather than a bare number.
        print("\n-- each scenario on its own --")
        for name, (_s, _r, _t, _rows, expected) in GAMES.items():
            only = await session.execute(text("""
                SELECT COUNT(*) FROM (
                    SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = :p
                    UNION SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = :p
                    UNION SELECT ga.game_id FROM game_appearances ga
                           WHERE ga.player_id = :p AND {pred}
                ) u WHERE u.game_id = :g
            """.replace("{pred}", __import__("app.services.game_status", fromlist=["x"])
                        .appearance_counts_as_match("ga"))), {"p": PLAYER, "g": GAME_ID[name]})
            counted = only.scalar() == 1
            check(f"{name}: {'counted' if expected else 'not counted'}", counted == expected,
                  f"counted={counted}")

        print("\n-- the hand-typed game is never inferred away --")
        manual_counted = await session.execute(text(
            "SELECT 1 FROM v_effective_batting_innings WHERE game_id = :g AND player_id = :p"),
            {"g": MANUAL_ID, "p": PLAYER})
        check("the manual game still has its row", manual_counted.first() is not None)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
