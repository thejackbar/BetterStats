"""Verification for winter/summer seasons, Recent form and the CA-lag top-up, against a real Postgres.

Reported by a club (three things, one report):

1. "The public season filter shows 2026/27 twice, and my 2026/27 shows 16 innings /
   223 runs including winter games." Winter 2026 and Summer 2026/27 both carry
   year 2026; every season fold, filter expansion and label treated the YEAR as the
   season's identity, so the two collapsed into one.
2. "51 matches (correct); runs 453 (incorrect), it misses the last innings, should be
   456", and the Recent form box had no 3 in it. CA's season totals ran behind a
   scorecard we hold (the profile header and season table read CA's totals only),
   and Recent form read the raw tables and ordered "latest season" by year then NAME,
   which puts "Winter" after "Summer" and so picks the winter season as current.
3. A stored game is never read again once one club player has an appearance on it,
   so an innings missing from the first pull stayed missing.

Runs the SHIPPED services and route bodies over the ``v_effective_*`` views pulled
straight out of the migrations that define them. Read new keys with ``.get`` so a
CONTROL RUN against the previous commit reports the old behaviour as failed checks
instead of crashing.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_season_split_and_topup.py
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
from app.models.db import Base, Player
from app.routers.organisations import get_org_seasons
from app.routers.players import get_player_stats, _snapshot
from app.services.aggregations import get_season_by_season
from app.services.season_aliases import resolve_season_filter

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

try:
    from app.services import participant_relink
except ImportError:  # pragma: no cover
    participant_relink = None

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
ORG, OTHER, OPP = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
S_SUM, S_WIN, S_PRIOR, S_FOREIGN = (uuid.uuid4() for _ in range(4))
G_SUM, G_WIN, G_PRIOR, G_FOREIGN = (uuid.uuid4() for _ in range(4))
# The reported player: 2 winter innings of 50 (CA agrees), 3 summer innings of 10
# held but CA has only counted 2 of them (20 runs): CA's total is one innings behind.
REPORTED = uuid.uuid4()
# A player whose summer game is a shared fixture filed under ANOTHER club's season row.
SHARED = uuid.uuid4()
# A player CA counts MORE for than we hold: nothing may be topped up, or lowered.
HEAVY = uuid.uuid4()
# A player with a held game in a season CA has no row for yet.
FRESH = uuid.uuid4()
S_NEW = uuid.uuid4()
G_NEW = uuid.uuid4()
# Recent form: a DNB row, a not out, bowling, and catches in both seasons.
FORM = uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        # Lifespan DDL: not on `create_all` when the ORM model predates it (the control run).
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
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
                stumpings int)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                undone_at TIMESTAMPTZ)
        """))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm, slug in ((ORG, "Split Club", "split"), (OTHER, "Neighbour CC", "neighbour")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                 i=oid, n=nm, s=slug)
    for sid, org, nm, yr in ((S_SUM, ORG, "Summer 2026/27", 2026), (S_WIN, ORG, "Winter 2026", 2026),
                             (S_PRIOR, ORG, "Summer 2025/26", 2025), (S_NEW, ORG, "Summer 2027/28", 2027),
                             (S_FOREIGN, OTHER, "Summer 2026/27", 2026)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                 i=sid, o=org, n=nm, y=yr)
    for gid, sid, nm in ((G_SUM, S_SUM, "1st Grade"), (G_WIN, S_WIN, "Winter A"),
                         (G_PRIOR, S_PRIOR, "1st Grade"), (G_NEW, S_NEW, "1st Grade"),
                         (G_FOREIGN, S_FOREIGN, "1st Grade")):
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=sid, n=nm, g=str(gid))
    for pid, nm in ((REPORTED, "Reported, Rob"), (SHARED, "Shared, Sam"), (HEAVY, "Heavy, Hal"),
                    (FRESH, "Fresh, Finn"), (FORM, "Form, Fay")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

    async def game(grade, days_ago, home=ORG):
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                 " match_format, status) VALUES (:i, :g, :d, 'WIN', :h, :x, 'One Day', 'COMPLETED')",
                 i=gid, g=grade, d=TODAY - timedelta(days=days_ago), h=home, x=OPP)
        return gid

    async def bat(gid, pid, runs, not_out=False, dnb=False, innings=1):
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, "
                 " sixes, not_out, dismissal_type, did_not_bat) "
                 "VALUES (:g, :p, :n, :r, 20, 0, 0, :no, :dt, :dnb)",
                 g=gid, p=pid, n=innings, r=None if dnb else runs, no=not_out,
                 dt=None if (dnb or not_out) else "caught", dnb=dnb)
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p) "
                 "ON CONFLICT DO NOTHING", g=gid, p=pid)

    # REPORTED: two winter innings of 50, three summer innings of 10 (the newest game last).
    for d in (140, 130):
        await bat(await game(G_WIN, d), REPORTED, 50)
    for d in (20, 13, 6):
        await bat(await game(G_SUM, d), REPORTED, 10)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 2, 2, 100, 0, 0, 'api')", p=REPORTED, s=S_WIN)
    # CA has counted the match (3) but only two innings of the three (the lag in the report).
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 3, 2, 20, 0, 0, 'api')", p=REPORTED, s=S_SUM)

    # SHARED: the summer game is a fixture another club synced first, so it sits under THEIR
    # season row. CA counted it, so nothing is topped up and nothing is counted twice.
    await bat(await game(G_FOREIGN, 9), SHARED, 40)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 1, 1, 40, 0, 0, 'api')", p=SHARED, s=S_SUM)

    # HEAVY: CA counts 5 innings / 200 runs in 2025/26, we hold one innings of 30.
    await bat(await game(G_PRIOR, 300), HEAVY, 30)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, source) VALUES (:p, :s, 5, 5, 200, 0, 0, 'api')", p=HEAVY, s=S_PRIOR)

    # FRESH: a held game in 2027/28, CA has no row for the season at all yet.
    await bat(await game(G_NEW, 60), FRESH, 17)

    # FORM: newest first 7*, 12, DNB, 0, 33, 4, 61 (a DNB row is not an innings). Bowling in
    # winter and summer; catches in both (winter 4, summer 2, CA says summer 3).
    for d, runs, no, dnb in ((3, 7, True, False), (10, 12, False, False), (17, None, False, True),
                             (24, 0, False, False), (31, 33, False, False), (38, 4, False, False),
                             (45, 61, False, False)):
        gid = await game(G_SUM, d)
        await bat(gid, FORM, runs, not_out=no, dnb=dnb)
        if d == 10:
            await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, "
                     " runs, wickets) VALUES (:g, :p, 1, 4.0, 0, 21, 3)", g=gid, p=FORM)
            await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings)"
                     " VALUES (:g, :p, 2, 0, 1, 0)", g=gid, p=FORM)
    wgid = await game(G_WIN, 150)
    await bat(wgid, FORM, 5)
    await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings)"
             " VALUES (:g, :p, 4, 0, 0, 0)", g=wgid, p=FORM)
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, "
             " not_outs, wickets, catches, source) VALUES (:p, :s, 7, 6, 117, 0, 0, 3, 'api')",
             p=FORM, s=S_SUM)


def row_for(rows, name_part):
    return next((r for r in rows if name_part in (r.get("season_name") or "")), None)


async def stats(session, player, **kw):
    params = dict(season_id=None, grade_id=None, last_n_games=None, start_date=None,
                  end_date=None, categories=None, formats=None, competitions=None, grades=None)
    params.update(kw)
    return await get_player_stats(player_id=str(player), db=session, **params)


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)
        await s.commit()

    async with Session() as s:
        print("\n-- WINTER AND SUMMER ARE TWO SEASONS --")
        rows = await get_season_by_season(s, str(REPORTED), include_prior=True)
        win, summer = row_for(rows, "Winter"), row_for(rows, "Summer 2026")
        check("the season table draws a Winter 2026 row AND a Summer 2026/27 row",
              win is not None and summer is not None,
              f"rows: {[(r.get('season_name'), r.get('total_runs')) for r in rows]}")
        check("winter is 2 innings / 100 runs, as CA counts it",
              bool(win) and win.get("batting_innings") == 2 and win.get("total_runs") == 100,
              str(win and (win.get('batting_innings'), win.get('total_runs'))))
        check("summer holds no winter runs (control reads one folded row of 120+)",
              bool(summer) and summer.get("total_runs") == 30,
              str(summer and summer.get("total_runs")))

        ws = await resolve_season_filter(s, str(ORG), str(S_WIN), include_shared=True)
        ss = await resolve_season_filter(s, str(ORG), str(S_SUM), include_shared=True)
        check("picking Winter 2026 returns the winter season only",
              set(ws) == {str(S_WIN)}, str(sorted(ws)))
        check("picking Summer 2026/27 returns the summer season and the neighbour's summer, not winter",
              set(ss) == {str(S_SUM), str(S_FOREIGN)}, str(sorted(ss)))

        listed = await get_org_seasons(str(ORG), s)
        names = [x["name"] for x in listed]
        check("the public season list has both, summer ahead of winter in the same year",
              names.index("Summer 2026/27") < names.index("Winter 2026")
              if "Summer 2026/27" in names and "Winter 2026" in names else False, str(names))

        by_summer = await stats(s, REPORTED, season_id=str(S_SUM))
        inn = by_summer.get("batting_innings") or []
        check("the profile's innings list for Summer 2026/27 is its three summer innings",
              len(inn) == 3 and all(i.get("runs") == 10 for i in inn), str([i.get("runs") for i in inn]))

        print("\n-- THE CA LAG IS TOPPED UP FROM THE SCORECARD WE HOLD --")
        career = (await stats(s, REPORTED))["career_batting"]
        check("career runs read 100 + 30 = 130, not CA's 120 (control reads 120)",
              career.get("total_runs") == 130, str(career.get("total_runs")))
        check("career innings read 5, not 4", career.get("innings") == 5, str(career.get("innings")))
        check("and the header says what was added",
              (career.get("topped_up") or {}).get("runs") == 10
              and (career.get("topped_up") or {}).get("innings") == 1, str(career.get("topped_up")))
        check("the season table row agrees with the header (summer 3 innings / 30 runs)",
              bool(summer) and summer.get("batting_innings") == 3, str(summer and summer.get("batting_innings")))
        sum_filter = (await stats(s, REPORTED, season_id=str(S_SUM)))["career_batting"]
        check("a season-picked header agrees too: 30 runs",
              sum_filter.get("total_runs") == 30, str(sum_filter.get("total_runs")))

        shared = (await stats(s, SHARED))["career_batting"]
        check("a shared fixture filed under the neighbour's season row is NOT counted twice",
              shared.get("total_runs") == 40 and not shared.get("topped_up"),
              f"{shared.get('total_runs')} {shared.get('topped_up')}")
        heavy = (await stats(s, HEAVY))["career_batting"]
        check("CA counting MORE than we hold is never lowered or topped up (200, not 30)",
              heavy.get("total_runs") == 200 and not heavy.get("topped_up"),
              f"{heavy.get('total_runs')} {heavy.get('topped_up')}")
        fresh_rows = await get_season_by_season(s, str(FRESH), include_prior=True)
        fresh_row = row_for(fresh_rows, "2027/28")
        check("a held game in a season CA has no row for yet still draws one (17 runs)",
              bool(fresh_row) and fresh_row.get("total_runs") == 17,
              str([(r.get("season_name"), r.get("total_runs")) for r in fresh_rows]))
        fresh = (await stats(s, FRESH))["career_batting"]
        check("and the header matches the table (17)", fresh.get("total_runs") == 17, str(fresh.get("total_runs")))

        print("\n-- RECENT FORM --")
        player = await s.get(Player, FORM)
        snap = await _snapshot(s, player)
        detail = snap.get("recent_batting_detail") or [
            {"runs": r, "not_out": False} for r in snap.get("recent_batting", [])]
        shown = [f"{d['runs']}{'*' if d.get('not_out') else ''}" for d in detail]
        check("last five batting: 7*, 12, 0, 33, 4 (a did-not-bat row is not an innings)",
              shown == ["7*", "12", "0", "33", "4"], str(shown))
        check("bowling shows the spell (3/21)",
              [(b.get("wickets"), b.get("runs")) for b in snap.get("recent_bowling", [])] == [(3, 21)],
              str(snap.get("recent_bowling")))
        check("this season is Summer 2026/27, not Winter 2026",
              snap.get("season_name") == "Summer 2026/27", str(snap.get("season_name")))
        check("season catches are the summer's higher figure, CA's 3 over the card's 2 (control reads winter's 4)",
              snap.get("season_catches") == 3, str(snap.get("season_catches")))
        check("run outs ride along (1)", snap.get("season_run_outs") == 1, str(snap.get("season_run_outs")))
        if os.environ.get("DUMP_FIXTURES"):
            # The browser twin drives the real screens with THESE payloads, not hand-typed ones.
            import json
            rep = await stats(s, REPORTED)
            Path(os.environ["DUMP_FIXTURES"]).write_text(json.dumps({
                "snapshot": snap,
                "stats": rep,
                "seasons": await get_org_seasons(str(ORG), s),
                "season_stats": await get_season_by_season(s, str(REPORTED), include_prior=True),
                "ids": {"reported": str(REPORTED), "form": str(FORM), "org": str(ORG),
                        "summer": str(S_SUM), "winter": str(S_WIN)},
            }, default=str))

        print("\n-- A STORED GAME IS RE-READ FOR MISSING ROWS --")
        if participant_relink is None or not hasattr(participant_relink, "reread_stored_game"):
            check("participant_relink.reread_stored_game exists", False, "missing (control run)")
        else:
            gid = uuid.uuid4()
            await s.execute(text(
                "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, status) "
                "VALUES (:i, :g, :d, 'WIN', :o, :x, 'COMPLETED')"),
                {"i": gid, "g": G_SUM, "d": TODAY - timedelta(days=3), "o": ORG, "x": OPP})
            # One of the club's two players already has an appearance and a batting row; the other
            # has an appearance and NOTHING else (the shape of the report: partly stored).
            for p in (HEAVY, FRESH):
                await s.execute(text("INSERT INTO game_appearances (game_id, player_id) VALUES (:g,:p)"),
                                {"g": gid, "p": p})
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 1, 8, 10, 1, 0, false, 'caught', false)"),
                {"g": gid, "p": HEAVY})
            await s.commit()
            guid_of = {"h": str(uuid.uuid4()), "f": str(uuid.uuid4())}
            card = {
                "matchSchedule": [{"startDateTime": (TODAY - timedelta(days=3)).isoformat() + "T10:00:00Z"}],
                "teams": [{"owningOrganisation": {"id": str(ORG)}, "displayName": "Split Club 1sts",
                           "players": [{"participantId": guid_of["h"], "roles": []},
                                       {"participantId": guid_of["f"], "roles": []}]}],
                "innings": [{"inningsOrder": 1, "fielding": [], "bowling": [], "batting": [
                    {"participantId": guid_of["h"], "dismissalTypeId": 2, "dismissalType": "Caught",
                     "runsScored": 8, "ballsFaced": 10, "batOrder": 1},
                    {"participantId": guid_of["f"], "dismissalTypeId": 2, "dismissalType": "Caught",
                     "runsScored": 3, "ballsFaced": 7, "batOrder": 2}]}],
            }
            resolve = {guid_of["h"]: HEAVY, guid_of["f"]: FRESH}.get
            check("a game from three days ago is inside the re-read window",
                  participant_relink.played_within(card))
            old_card = {**card, "matchSchedule": [
                {"startDateTime": (TODAY - timedelta(days=40)).isoformat() + "T10:00:00Z"}]}
            check("a game from forty days ago is not", not participant_relink.played_within(old_card))
            added = await participant_relink.reread_stored_game(s, ORG, gid, card, resolve)
            check("the missing innings (a 3) is added", bool(added) and added.get("batting") == 1, str(added))
            runs = (await s.execute(text(
                "SELECT player_id::text, runs FROM batting_innings WHERE game_id = :g ORDER BY runs"),
                {"g": gid})).all()
            check("the stored 8 is untouched and the 3 is there",
                  [(r[1]) for r in runs] == [3, 8], str(runs))
            again = await participant_relink.reread_stored_game(s, ORG, gid, card, resolve)
            check("reading it a second time changes nothing", again is None, str(again))

            print("\n-- A RECENT GAME STORED WITH NO DETAIL IS FOUND, EVEN OUTSIDE THE RUN'S WINDOW --")
            # The reported game: a `games` row with its result and no batting, bowling, fall of
            # wickets or partnerships (the page still draws a card, rebuilt live from CA).
            async def mk(days_ago, grade=G_SUM, home=ORG):
                g = uuid.uuid4()
                await s.execute(text(
                    "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, status) "
                    "VALUES (:i, :g, :d, 'LOSS', :o, :x, 'COMPLETED')"),
                    {"i": g, "g": grade, "d": TODAY - timedelta(days=days_ago), "o": home, "x": OPP})
                return g
            empty_recent = await mk(5)
            empty_old = await mk(40)
            complete = await mk(5)
            theirs_only = await mk(5)
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 1, 9, 12, 1, 0, false, 'caught', false)"),
                {"g": complete, "p": HEAVY})
            await s.execute(text(
                "INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id, "
                " batter_name) VALUES (:g, 1, 1, 9, :p, 'H Heavy')"), {"g": complete, "p": HEAVY})
            no_fow = await mk(5)
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 1, 9, 12, 1, 0, false, 'caught', false)"),
                {"g": no_fow, "p": HEAVY})
            stranger = uuid.uuid4()
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                                 "VALUES (:i, :o, 'Other, Olly', :g, 'active')"),
                            {"i": stranger, "o": OTHER, "g": str(stranger)})
            await s.execute(text(
                "INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                " not_out, dismissal_type, did_not_bat) VALUES (:g, :p, 1, 14, 20, 2, 0, false, 'bowled', false)"),
                {"g": theirs_only, "p": stranger})
            await s.commit()
            if not hasattr(participant_relink, "recent_games_without_detail"):
                check("participant_relink.recent_games_without_detail exists", False, "missing (control run)")
            else:
                found = await participant_relink.recent_games_without_detail(s, ORG)
                check("the recent game with no player detail is picked up", str(empty_recent) in found, str(found))
                check("a recent game with batting, fall of wickets and partnerships data is left alone",
                      str(complete) not in found)
                check("a recent game with batting but no fall of wickets or partnerships is picked up",
                      str(no_fow) in found)
                check("a game older than the 14 day window is not", str(empty_old) not in found)
                check("a shared fixture where only the OTHER club's players have rows still counts as empty for us",
                      str(theirs_only) in found)

    print("\n-- THE CLUB'S 'AMALGAMATE' SWITCH RESTORES ONE SEASON PER YEAR --")
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET amalgamate_seasons = true WHERE id = :o"), {"o": ORG})
        await s.commit()
    async with Session() as s:
        rows = await get_season_by_season(s, str(REPORTED), include_prior=True)
        y2026 = [r for r in rows if r.get("year") == 2026]
        check("one 2026 row in the season table", len(y2026) == 1,
              str([(r.get("season_name"), r.get("total_runs")) for r in rows]))
        check("it holds winter and summer together: 100 + 30 = 130",
              bool(y2026) and y2026[0].get("total_runs") == 130, str(y2026 and y2026[0].get("total_runs")))
        check("the summer row stands for the year (name Summer 2026/27)",
              bool(y2026) and y2026[0].get("season_name") == "Summer 2026/27",
              str(y2026 and y2026[0].get("season_name")))
        ids = await resolve_season_filter(s, str(ORG), str(S_SUM), include_shared=True)
        check("picking the summer season returns the winter season too",
              str(S_WIN) in ids, str(sorted(ids)))
        listed = await get_org_seasons(str(ORG), s)
        check("the public season list shows one 2026 entry",
              len([x for x in listed if x.get("year") == 2026]) == 1,
              str([(x["name"], x.get("year")) for x in listed]))
        snap = await _snapshot(s, await s.get(Player, FORM))
        check("Recent form's season covers the whole year: catches 4 + 3 = at least 4",
              (snap.get("season_catches") or 0) >= 4, str(snap.get("season_catches")))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
