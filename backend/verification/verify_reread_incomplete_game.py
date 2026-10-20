"""End-to-end check that sync fills in a game stored WITHOUT its player detail, through the real sync.

Reported (Summer Hill, Don Stewart): two matches on one Saturday. His 7th Grade game is stored
(it shows in the club's results with its result, and he has an appearance, so the grade grid
counts 4 seventh-grade games) but holds no batting, bowling, fall of wickets or partnerships, so
his profile lists 3 seventh-grade innings, not 4. The game page still shows his 3 because it is
rebuilt live from Cricket Australia.

Two things kept it that way:
  * once any club player has an appearance on a game, sync called it done and never read its
    batting again (`our_appearances_done`), and
  * an incremental run only reads fixtures newer than the last sync less an overlap, so a game
    stored on Sunday's run was outside every later window.

Drives `sync_grassroots_game_level_data` itself, with the Cricket Australia client stubbed to
return the match list and scorecard, exactly as an incremental run (`since` = yesterday) would.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_reread_incomplete_game.py
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
from app.services import grassroots_scores_client as gr
from app.services.sync import sync_grassroots_game_level_data

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


TODAY = date.today()
ORG, OPP_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE_GUID = uuid.uuid4(), str(uuid.uuid4())
GRADE = uuid.UUID(GRADE_GUID)
DON, MATE = uuid.uuid4(), uuid.uuid4()
MATCH_STORED_EMPTY = uuid.uuid4()   # the reported shape: stored, result set, no detail
MATCH_OLD_EMPTY = uuid.uuid4()      # same shape but 40 days ago: outside the re-read window
MATCH_COMPLETE = uuid.uuid4()       # stored with its batting, fall of wickets and partnerships already
MATCH_NO_FOW = uuid.uuid4()         # batting stored (an earlier re-read), but no fall of wickets or partnerships


def card_for(match_id, days_ago, don_runs, mate_runs):
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    return {
        "id": str(match_id),
        "matchSchedule": [{"startDateTime": iso}],
        "venue": {"name": "Oval"},
        "grade": {"id": GRADE_GUID, "name": "7th Grade"},
        "teams": [
            {"id": ours, "displayName": "SHCC 7th Div", "owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(DON), "roles": []}, {"participantId": str(MATE), "roles": []}]},
            {"id": theirs, "displayName": "Them 7th", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "matchSummary": {
            "resultText": "SHCC lost",
            "teams": [{"id": ours, "displayName": "SHCC 7th Div", "isHome": False},
                      {"id": theirs, "displayName": "Them 7th", "isHome": True}],
        },
        "innings": [{
            "inningsOrder": 2, "fielding": [], "bowling": [],
            # Don out for 3 at 3, his partner out for 11 at 14.
            "fallOfWickets": [
                {"order": 1, "runs": 3, "participantId": str(DON), "playerShortName": "D Stewart"},
                {"order": 2, "runs": 14, "participantId": str(MATE), "playerShortName": "M Mate"},
            ],
            "batting": [
                {"participantId": str(DON), "dismissalTypeId": 2, "dismissalType": "Bowled",
                 "runsScored": don_runs, "ballsFaced": 5, "batOrder": 1},
                {"participantId": str(MATE), "dismissalTypeId": 2, "dismissalType": "Bowled",
                 "runsScored": mate_runs, "ballsFaced": 8, "batOrder": 2},
            ],
        }],
    }


def match_entry(match_id, days_ago):
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    return {
        "id": str(match_id), "matchSchedule": [{"startDateTime": iso}], "status": "COMPLETED",
        "matchType": "One Day", "round": {"name": "Round 3"},
        "teams": [{"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(ORG)}},
                  {"id": str(uuid.uuid4()), "owningOrganisation": {"id": str(OPP_ORG), "name": "Them"}}],
    }


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


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((ORG, "Summer Hill", "sh"), (OPP_ORG, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, :g)", i=SEASON, o=ORG, g=str(SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '7th Grade', :g, 'senior', ARRAY['senior'])", i=GRADE, s=SEASON, g=GRADE_GUID)
        for pid, nm in ((DON, "Stewart, Don"), (MATE, "Mate, Mick")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))
        for mid, days in ((MATCH_STORED_EMPTY, 5), (MATCH_OLD_EMPTY, 40), (MATCH_COMPLETE, 5),
                          (MATCH_NO_FOW, 6)):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, status, "
                     " venue, match_format) VALUES (:i, :g, :d, 'LOSS', NULL, :o, 'COMPLETED', 'Oval', 'One Day')",
                     i=mid, g=GRADE, d=TODAY - timedelta(days=days), o=ORG)
            # An appearance for both players: the club's team sheet WAS stored.
            for p in (DON, MATE):
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=mid, p=p)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                 " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 2, 30, 20, 3, 0, false, 'bowled', false)",
                 g=MATCH_COMPLETE, p=DON)
        await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id, "
                 " batter_name) VALUES (:g, 2, 1, 30, :p, 'D Stewart')", g=MATCH_COMPLETE, p=DON)
        await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, runs, is_club_innings) "
                 "VALUES (:g, 2, 1, :p, 30, true)", g=MATCH_COMPLETE, p=DON)
        for p, runs in ((DON, 3), (MATE, 11)):
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                     " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 2, :r, 5, 0, 0, false, 'bowled', false)",
                     g=MATCH_NO_FOW, p=p, r=runs)
        await s.commit()


async def count(table, game_id):
    async with Session() as s:
        return (await s.execute(text(f"SELECT COUNT(*) FROM {table} WHERE game_id = :g"), {"g": game_id})).scalar()


async def runs_of(game_id, player):
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT runs FROM batting_innings WHERE game_id = :g AND player_id = :p ORDER BY runs"),
            {"g": game_id, "p": player})).all()
    return [r[0] for r in rows]


async def main() -> None:
    await build_schema()
    await seed()

    cards = {
        str(MATCH_STORED_EMPTY): card_for(MATCH_STORED_EMPTY, 5, 3, 11),
        str(MATCH_OLD_EMPTY): card_for(MATCH_OLD_EMPTY, 40, 3, 11),
        str(MATCH_COMPLETE): card_for(MATCH_COMPLETE, 5, 30, 12),
        str(MATCH_NO_FOW): card_for(MATCH_NO_FOW, 6, 3, 11),
    }
    listing = [match_entry(MATCH_STORED_EMPTY, 5), match_entry(MATCH_OLD_EMPTY, 40), match_entry(MATCH_COMPLETE, 5),
               match_entry(MATCH_NO_FOW, 6)]
    fetched: list[str] = []

    async def fake_matches(grade_guid, *a, **k):
        return listing

    async def fake_card(match_id, *a, **k):
        fetched.append(str(match_id))
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    print("\n-- BEFORE: the reported shape --")
    check("the stored game has Don's appearance and no batting", await runs_of(MATCH_STORED_EMPTY, DON) == [])

    print("\n-- AN INCREMENTAL RUN, since = yesterday (the game is 5 days old, outside its window) --")
    stats = await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=1))
    check("the run read the game anyway",
          str(MATCH_STORED_EMPTY) in fetched, f"fetched={fetched}")
    check("Don's 3 is now stored", await runs_of(MATCH_STORED_EMPTY, DON) == [3], str(await runs_of(MATCH_STORED_EMPTY, DON)))
    check("and his teammate's 11", await runs_of(MATCH_STORED_EMPTY, MATE) == [11])
    check("a complete game is not read again (batting, fall of wickets and partnerships are there)",
          str(MATCH_COMPLETE) not in fetched, str(fetched))
    check("its stored figure is untouched", await runs_of(MATCH_COMPLETE, DON) == [30])
    check("and its fall of wickets and partnerships are not doubled",
          await count("fall_of_wickets", MATCH_COMPLETE) == 1 and await count("partnerships", MATCH_COMPLETE) == 1)

    print("\n-- FALL OF WICKETS AND PARTNERSHIPS --")
    check("the stored-empty game gets its 2 wickets", await count("fall_of_wickets", MATCH_STORED_EMPTY) == 2,
          str(await count("fall_of_wickets", MATCH_STORED_EMPTY)))
    check("and its 2 partnerships (3 then 11)", await count("partnerships", MATCH_STORED_EMPTY) == 2,
          str(await count("partnerships", MATCH_STORED_EMPTY)))
    async with Session() as s:
        stands = [r[0] for r in (await s.execute(text(
            "SELECT runs FROM partnerships WHERE game_id = :g ORDER BY wicket_number"), {"g": MATCH_STORED_EMPTY})).all()]
        club = (await s.execute(text(
            "SELECT bool_and(is_club_innings) FROM partnerships WHERE game_id = :g"), {"g": MATCH_STORED_EMPTY})).scalar()
    check("the stands are 3 and 11 and belong to the club's innings", stands == [3, 11] and club is True, f"{stands} {club}")
    check("a game that had its batting but no fall of wickets is read again and gets them",
          str(MATCH_NO_FOW) in fetched and await count("fall_of_wickets", MATCH_NO_FOW) == 2
          and await count("partnerships", MATCH_NO_FOW) == 2, f"fetched={fetched}")
    check("without a second copy of its batting",
          await runs_of(MATCH_NO_FOW, DON) == [3] and await runs_of(MATCH_NO_FOW, MATE) == [11])
    check("a 40 day old empty game stays outside the window", str(MATCH_OLD_EMPTY) not in fetched)
    check("and gets nothing", await runs_of(MATCH_OLD_EMPTY, DON) == [])

    print("\n-- A SECOND RUN CHANGES NOTHING --")
    fetched.clear()
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=1))
    check("Don still has one 3, not two", await runs_of(MATCH_STORED_EMPTY, DON) == [3])
    check("and still 2 wickets and 2 partnerships, not 4",
          await count("fall_of_wickets", MATCH_STORED_EMPTY) == 2 and await count("partnerships", MATCH_STORED_EMPTY) == 2)
    check("the game is no longer re-read once it has detail", str(MATCH_STORED_EMPTY) not in fetched, str(fetched))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
