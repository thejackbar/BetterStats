"""A club marks a player as named but not playing a synced game; and the season table adds up to the header.

Reported off Piara Waters (Roy Marsh, 297 games on BetterCricket against Play Cricket's 295):

  * The season table summed to 295 while the header read 297. In 2012/13 and 2015/16 CA's per-grade
    rows count a game we hold no scorecard for, and the season view's reserve rule took that game off
    CA's season total as if it were the player's 12th man game (`LEAST(R, CA - N)`). The grid, per
    grade, kept it, and the header is raised to the grid. Section 1: each season row is now raised to
    the grid's row for that season.
  * In 2014/15 and 2017/18 Roy is on a team sheet with nothing recorded (East Fremantle, 5th Grade,
    7 March 2015) and CA's totals leave the game out. The club could only type a -1 season
    adjustment. Sections 2 onward: the club marks the game itself (`services/game_exclusions.py`),
    and every count follows.

Every figure is read through the shipped route bodies and services with the production views, against
a real Postgres. Run this same file against the previous commit as the control: section 1 fails there
(the season table reads 17), and the later sections report the feature as absent rather than crashing.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_game_exclusions.py
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

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from verify_board_games_match_profile import build_schema
from app.models.db import Organisation, User
from app.routers.leaderboard import batting_leaderboard
from app.routers.players import get_player_seasons, get_player_stats
from app.services import superseded_ddl
from app.services.aggregations import get_player_team_breakdown

try:  # absent on the control commit: reported, never crashed on
    from app.routers import game_exclusions as gx_routes
    from app.routers.manual_entries import undo_edit
    from app.services import game_exclusions as gx
    from app.services.game_exclusion_ddl import STATEMENTS as GX_DDL
except ImportError:
    gx_routes = gx = None
    GX_DDL = []

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False, connect_args={"server_settings": {"jit": "off"}})
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + str(detail)) if detail else ''}")


ORG, OPP = uuid.uuid4(), uuid.uuid4()
USER = uuid.uuid4()
S1516, S1415 = uuid.uuid4(), uuid.uuid4()
G = {k: uuid.uuid4() for k in ("F", "E", "C", "C15", "FIFTH")}
P = {k: uuid.uuid4() for k in ("SPLIT", "ROY", "FILLER", "BATTED", "SWAP")}
NAMES = {"SPLIT": "Split, Sam", "ROY": "Marsh, Roy", "FILLER": "Filler, Fred", "BATTED": "Batted, Ben",
         "SWAP": "Swap, Sid"}
GAMES: dict[str, uuid.UUID] = {}
SQUAD: list[uuid.UUID] = []
_day = 0


async def seed() -> None:
    global _day
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Piara Waters", "piara"), (OPP, "East Fremantle", "eastfreo")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO users (id, email, username, password_hash, failed_login_count) VALUES (:i, 'admin@x', 'admin', 'x', 0)", i=USER)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2015/16', 2015)", i=S1516, o=ORG)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2014/15', 2014)", i=S1415, o=ORG)
        for key, season, nm in (("F", S1516, "One Day F"), ("E", S1516, "One Day E"), ("C15", S1516, "One Day C"),
                                ("C", S1415, "One Day C"), ("FIFTH", S1415, "5th Grade")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=G[key], s=season, n=nm, g=str(G[key]))
        for k, pid in P.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=pid, o=ORG, n=NAMES[k], g=str(pid))

        async def game(grade, start) -> uuid.UUID:
            global _day
            _day += 7
            gid = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, "
                     " innings_totals, home_team, away_team) VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED', "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 150, 'wickets', 5)), 'Piara Waters', 'Opposition')",
                     i=gid, g=grade, d=start + timedelta(days=_day), o=ORG, x=OPP)
            # Somebody batted, so the card is not an empty one (`looks_unplayed_sql`).
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P["FILLER"])
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                     " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 30, 40, 2, 0, false, 'caught', false)", g=gid, p=P["FILLER"])
            return gid

        async def played(key, gid):
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=P[key])
            await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, 2, 6, 1, 20, 1)", g=gid, p=P[key])

        async def named(key, gid, reserve=None, slot=None):
            await ex("INSERT INTO game_appearances (game_id, player_id, is_reserve, sheet_slot) VALUES (:g, :p, :r, :sl)",
                     g=gid, p=P[key], r=reserve, sl=slot)

        async def ca(key, season, total, claims):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                     " catches, source) VALUES (:p, :s, :m, 0, 0, 0, 0, 0, 'api')", p=P[key], s=season, m=total)
            for grade, n in claims.items():
                await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, :m)",
                         p=P[key], s=season, g=G[grade], m=n)

        d1516, d1415 = date(2015, 10, 3), date(2014, 10, 4)
        # SPLIT (Roy's 2015/16 shape): 15 One Day F games played, one One Day E, one One Day C, and an
        # extra One Day E appearance the app read as 12th man (slot 12, nothing recorded). CA counts 18:
        # One Day F 16 (one F game we hold no scorecard for), E 1, C 1.
        for _ in range(15):
            await played("SPLIT", await game(G["F"], d1516))
        await played("SPLIT", await game(G["E"], d1516))
        await played("SPLIT", await game(G["C15"], d1516))
        await named("SPLIT", await game(G["E"], d1516), reserve=True, slot=12)
        await ca("SPLIT", S1516, 18, {"F": 16, "E": 1, "C15": 1})

        # ROY (his 2014/15): 18 One Day C games played and East Fremantle, 5th Grade, named with nothing
        # recorded. CA counts 18 (One Day C 18); we count 19 until the club marks the 5th Grade game.
        for _ in range(18):
            gid = await game(G["C"], d1415)
            await played("ROY", gid)
            await played("BATTED", gid) if _ == 0 else None
        GAMES["east_freo"] = await game(G["FIFTH"], d1415 + timedelta(days=200))
        await named("ROY", GAMES["east_freo"])
        await played("BATTED", GAMES["east_freo"])
        await ca("ROY", S1415, 18, {"C": 18})
        await ca("BATTED", S1415, 2, {"C": 1, "FIFTH": 1})

        # SWAP: 3 games played and one named-only; the club already typed a -1 for the season.
        for _ in range(3):
            await played("SWAP", await game(G["C"], d1415))
        GAMES["swap"] = await game(G["C"], d1415 + timedelta(days=210))
        await named("SWAP", GAMES["swap"])
        await ca("SWAP", S1415, 4, {"C": 4})
        # Typed against the grade, as the Adjustments form offers. (A grade-less -1 does not lower the header
        # of a player CA has per-grade rows for: the grid ignores it and the header is raised to the grid.
        # That gap is older than this suite and is reported separately.)
        # Big sheets: eleven squad players who batted, plus EXTRA (named only) on GF, the club's grand final.
        for i in range(11):
            SQUAD.append(uuid.uuid4())
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=SQUAD[-1], o=ORG, n=f"Squad, Player {i + 1:02d}", g=str(SQUAD[-1]))
        for k in ("EXTRA", "EXTRA2"):
            P[k] = uuid.uuid4()
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=P[k], o=ORG, n=f"{k.title()}, Ed", g=str(P[k]))

        async def sheet(extra_reserve=False) -> uuid.UUID:
            gid = await game(G["C"], d1415 + timedelta(days=150))
            await ex("DELETE FROM game_appearances WHERE game_id = :g", g=gid)   # FILLER is not on these sheets
            await ex("DELETE FROM batting_innings WHERE game_id = :g", g=gid)
            for sp in SQUAD:
                await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, 'Piara Waters')", g=gid, p=sp)
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                         " dismissal_type, did_not_bat) VALUES (:g, :p, 1, 10, 12, 1, 0, false, 'caught', false)", g=gid, p=sp)
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name, is_reserve, sheet_slot) "
                     "VALUES (:g, :p, 'Piara Waters', :r, :sl)", g=gid, p=P["EXTRA"],
                     r=True if extra_reserve else None, sl=12 if extra_reserve else None)
            return gid

        GAMES["gf"] = await sheet()
        GAMES["sheet_reserve"] = await sheet(extra_reserve=True)
        GAMES["sheet_checked"] = await sheet()
        await ex("INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory, "
                 " achievement, linked_game_id, auto_created) VALUES (:o, :p, 'Squad, Player 01', '2014/15', 'Premiership', "
                 " 'One Day C', 'Premiership', :g, TRUE)", o=ORG, p=SQUAD[0], g=GAMES["gf"])

        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, grade_id, games_played) "
                 "VALUES (:o, :p, :s, :g, -1)", o=ORG, p=P["SWAP"], s=S1415, g=G["C"])
        await s.commit()


async def header(key) -> int | None:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None, grades=None)
    return (d["career_batting"] or {}).get("games")


async def seasons(key) -> dict:
    async with Session() as s:
        rows = await get_player_seasons(player_id=str(P[key]), categories=None, formats=None, competitions=None,
                                        grades=None, db=s)
    return {r.get("season_name"): r.get("matches") for r in rows}


async def grid(key) -> int:
    async with Session() as s:
        return (await get_player_team_breakdown(s, str(P[key]), str(ORG), None))["grid_matches"]


async def board(key) -> int | None:
    async with Session() as s:
        rows = await batting_leaderboard(db=s, viewer=None, org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
                                         limit=50, finals_only=None, captain_only=None, gender=None, overseas=None,
                                         categories=None, formats=None, competitions=None, sort_by="total_runs",
                                         min_runs=0, min_rate_innings=0)
    row = next((r for r in rows if str(r["player_id"]) == str(P[key])), None)
    return None if row is None else row.get("games")


async def everywhere(key) -> tuple:
    return await header(key), sum(v or 0 for v in (await seasons(key)).values()), await grid(key)


async def as_admin(fn, *args, **kw):
    async with Session() as s:
        user = await s.get(User, USER)
        club = await s.get(Organisation, ORG)
        return await fn(*args, current_user=user, club=club, db=s, **kw)


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS ca_called_off BOOLEAN"))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS round_name TEXT"))
        for stmt in superseded_ddl.STATEMENTS:     # the lifespan re-applies these: production reads THESE views
            await conn.execute(text(stmt))
        for stmt in GX_DDL:
            await conn.execute(text(stmt))
        from app.services.premierships_ddl import STATEMENTS as PREM_DDL
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS player_achievements (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL, season TEXT,
            category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL, detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW())"""))
        await conn.execute(text("ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS season_end TEXT"))
        for stmt in PREM_DDL:
            await conn.execute(text(stmt))
    await seed()

    print("\n-- 1. THE SEASON TABLE ADDS UP TO THE HEADER (Roy's 2012/13 and 2015/16) --")
    rows = await seasons("SPLIT")
    check("the grid holds CA's One Day F claim of 16 beside E and C: 18", await grid("SPLIT") == 18, await grid("SPLIT"))
    check("the header is raised to the grid: 18", await header("SPLIT") == 18, await header("SPLIT"))
    check("the 2015/16 season row reads 18, not the 17 the reserve rule left", rows.get("Summer 2015/16") == 18, rows)
    check("so the season table adds up to the header", sum(v or 0 for v in rows.values()) == await header("SPLIT"))
    clean = await seasons("BATTED")
    check("a season the grid already agrees with is untouched (2 games, 2 in the table)",
          clean.get("Summer 2014/15") == 2, clean)

    if gx is None:
        print("\n-- 2+. MARKING A GAME AS NOT PLAYED --")
        check("the game exclusions feature exists", False, "app.services.game_exclusions is absent on this commit")
        await finish()
        return

    print("\n-- 2. BEFORE: ROY IS COUNTED FOR EAST FREMANTLE, WHERE HE RECORDED NOTHING --")
    h, t, g = await everywhere("ROY")
    check("header, season table and grid all read 19 (Play Cricket counts 18)", (h, t, g) == (19, 19, 19), (h, t, g))
    team = await as_admin(gx_routes.team_list, game_id=str(GAMES["east_freo"]))
    by = {r["player_name"]: r for r in team["players"]}
    check("the team list offers Roy as named with nothing recorded", by.get("Marsh, Roy", {}).get("status") == "named"
          and by["Marsh, Roy"]["can_mark"], by.get("Marsh, Roy"))
    check("and a player who bowled in the game as played, with no option", by.get("Batted, Ben", {}).get("status") == "played"
          and not by["Batted, Ben"]["can_mark"], by.get("Batted, Ben"))
    sug = await as_admin(gx_routes.suggestions)
    keys = {(i["player_id"], i["game_id"]) for i in sug["items"]}
    check("Games to check lists East Fremantle for Roy (19 against CA's 18)",
          (str(P["ROY"]), str(GAMES["east_freo"])) in keys, sug["items"])
    check("and leaves out a player whose season agrees with CA", all(i["player_id"] != str(P["SPLIT"]) for i in sug["items"]))

    print("\n-- 3. A PLAYER WITH A LINE IN THE GAME CANNOT BE MARKED --")
    try:
        await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["east_freo"]),
                       data=gx_routes.NotPlayedIn(player_id=str(P["BATTED"]), reason="twelfth_man"))
        check("refused", False, "accepted")
    except HTTPException as e:
        check("refused with a reason the admin can read", e.status_code == 409 and "counts as played" in e.detail, e.detail)
    try:
        await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["east_freo"]),
                       data=gx_routes.NotPlayedIn(player_id=str(P["ROY"]), reason="nap"))
        check("an unknown reason is refused", False, "accepted")
    except HTTPException as e:
        check("an unknown reason is refused", e.status_code == 422, e.detail)

    print("\n-- 4. THE CLUB MARKS ROY AS 12TH MAN: EVERY COUNT FOLLOWS --")
    out = await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["east_freo"]),
                         data=gx_routes.NotPlayedIn(player_id=str(P["ROY"]), reason="twelfth_man"))
    check("the game now reads as marked 12th man", out["player"]["status"] == "marked"
          and out["player"]["reason_label"] == "12th man", out["player"])
    h, t, g = await everywhere("ROY")
    check("header, season table and grid all read 18, Play Cricket's figure", (h, t, g) == (18, 18, 18), (h, t, g))
    check("the batting board agrees", await board("ROY") == 18, await board("ROY"))
    async with Session() as s:
        pub = await gx_routes.public_not_played(game_id=str(GAMES["east_freo"]), db=s)
    check("the public scorecard can say who was 12th man", pub["players"] == [
        {"player_id": str(P["ROY"]), "player_name": "Marsh, Roy", "reason": "twelfth_man", "reason_label": "12th man"}],
        pub)
    sug = await as_admin(gx_routes.suggestions)
    check("and East Fremantle leaves Games to check", all(i["game_id"] != str(GAMES["east_freo"]) or i["player_id"] != str(P["ROY"])
                                                          for i in sug["items"]))
    async with Session() as s:
        log_id = (await s.execute(text(
            "SELECT id FROM manual_edit_logs WHERE target_table = 'game_exclusions' ORDER BY id DESC LIMIT 1"))).scalar()
    check("the change is on the Manual entries audit trail", log_id is not None)

    print("\n-- 5. A RESYNC OR REBUILD CANNOT UNDO IT --")
    async with Session() as s:
        await s.execute(text("DELETE FROM game_appearances WHERE game_id = :g AND player_id = :p"),
                        {"g": GAMES["east_freo"], "p": P["ROY"]})
        await s.execute(text("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)"),
                        {"g": GAMES["east_freo"], "p": P["ROY"]})
        await s.commit()
    check("control: a re-stored appearance alone puts the game back (19)", await header("ROY") == 19, await header("ROY"))
    async with Session() as s:
        await gx.reapply(s, game_id=GAMES["east_freo"])
        await s.commit()
    check("sync's reapply puts the mark back (18)", await header("ROY") == 18, await header("ROY"))
    async with Session() as s:
        await s.execute(text("UPDATE game_appearances SET is_reserve = NULL WHERE game_id = :g AND player_id = :p"),
                        {"g": GAMES["east_freo"], "p": P["ROY"]})
        await s.commit()
    async with engine.begin() as conn:
        await conn.execute(text(GX_DDL[-1]))
    check("and so does the lifespan statement on boot (18)", await header("ROY") == 18, await header("ROY"))

    print("\n-- 6. UNDO FROM THE AUDIT TRAIL COUNTS IT AGAIN, AND UNDO OF THAT MARKS IT AGAIN --")
    await as_admin(undo_edit, log_id=log_id)
    check("undoing the mark: 19 again", await header("ROY") == 19, await header("ROY"))
    async with Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM game_exclusions"))).scalar()
    check("and the mark is gone", n == 0, n)
    await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["east_freo"]),
                   data=gx_routes.NotPlayedIn(player_id=str(P["ROY"]), reason="late_withdrawal"))
    await as_admin(gx_routes.unmark_not_played, game_id=str(GAMES["east_freo"]), player_id=str(P["ROY"]))
    check("marking then taking the mark off from the match page: 19", await header("ROY") == 19, await header("ROY"))
    async with Session() as s:
        del_log = (await s.execute(text(
            "SELECT id FROM manual_edit_logs WHERE target_table = 'game_exclusions' AND action = 'delete' "
            "ORDER BY id DESC LIMIT 1"))).scalar()
    await as_admin(undo_edit, log_id=del_log)
    t2 = await as_admin(gx_routes.team_list, game_id=str(GAMES["east_freo"]))
    roy = next(r for r in t2["players"] if r["player_name"] == "Marsh, Roy")
    check("undoing the removal marks it again, with its reason", roy["status"] == "marked"
          and roy["reason"] == "late_withdrawal" and await header("ROY") == 18, (roy, await header("ROY")))

    print("\n-- 7. A -1 TYPED BEFORE THIS EXISTED IS MOVED ONTO THE GAME, NOT TAKEN TWICE --")
    check("before: 4 named games and a -1 read 3", await header("SWAP") == 3, await header("SWAP"))
    cand = await as_admin(gx_routes.swap_candidates, game_id=str(GAMES["swap"]), player_id=str(P["SWAP"]))
    check("the -1 is offered for the game's season", len(cand["adjustments"]) == 1
          and cand["adjustments"][0]["matches"] == -1, cand)
    await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["swap"]),
                   data=gx_routes.NotPlayedIn(player_id=str(P["SWAP"]), reason="twelfth_man",
                                              swap_adjustment_id=cand["adjustments"][0]["id"]))
    async with Session() as s:
        m = (await s.execute(text("SELECT games_played FROM manual_season_adjustments WHERE player_id = :p"),
                             {"p": P["SWAP"]})).scalar()
    check("the adjustment goes to 0 and the player reads 3, not 2", m == 0 and await header("SWAP") == 3,
          (m, await header("SWAP")))
    await as_admin(gx_routes.unmark_not_played, game_id=str(GAMES["swap"]), player_id=str(P["SWAP"]))
    async with Session() as s:
        m = (await s.execute(text("SELECT games_played FROM manual_season_adjustments WHERE player_id = :p"),
                             {"p": P["SWAP"]})).scalar()
    check("taking the mark off puts the -1 back: 3 again", m == -1 and await header("SWAP") == 3, (m, await header("SWAP")))

    print("\n-- 8. A DISMISSED SUGGESTION STAYS DISMISSED --")
    sug = await as_admin(gx_routes.suggestions)
    swap_there = any(i["game_id"] == str(GAMES["swap"]) for i in sug["items"])
    check("control: the named-only game is a suggestion (4 held against CA's 4 is not, so seed checks the rule)",
          not swap_there, sug["items"])
    async with Session() as s:
        await s.execute(text("UPDATE player_season_stats SET matches = 3 WHERE player_id = :p"), {"p": P["SWAP"]})
        await s.commit()
    sug = await as_admin(gx_routes.suggestions)
    check("with CA at 3 and ours at 4, the game is listed", any(i["game_id"] == str(GAMES["swap"]) for i in sug["items"]),
          sug["items"])
    await as_admin(gx_routes.dismiss, data=gx_routes.DismissIn(game_id=str(GAMES["swap"]), player_id=str(P["SWAP"])))
    sug = await as_admin(gx_routes.suggestions)
    check("after Keep as played it is not offered again", all(i["game_id"] != str(GAMES["swap"]) for i in sug["items"]))

    big = getattr(gx_routes, "big_sheets", None)
    print("\n-- 9. TEAM SHEETS WITH MORE THAN 11 STILL COUNTED --")
    if big is None:
        check("the team sheet list exists", False, "absent on this commit")
    else:
        items = {i["game_id"]: i for i in (await as_admin(big))["items"]}
        check("a sheet of 11 who batted plus a named extra is listed (12 counted, 1 extra)",
              items.get(str(GAMES["gf"]), {}).get("counted") == 12 and items[str(GAMES["gf"])]["extras"] == 1,
              items.get(str(GAMES["gf"])))
        check("a sheet whose extra the app already read as 12th man is not (11 counted)",
              str(GAMES["sheet_reserve"]) not in items)
        check("a sheet with 11 or fewer named is not listed (Roy's East Fremantle side)",
              str(GAMES["east_freo"]) not in items)
        await as_admin(gx_routes.check_sheet, data=gx_routes.SheetCheckIn(game_id=str(GAMES["sheet_checked"]),
                                                                          team_name="Piara Waters"))
        items = {i["game_id"]: i for i in (await as_admin(big))["items"]}
        check("CHECKED takes a sheet off the list", str(GAMES["sheet_checked"]) not in items
              and str(GAMES["gf"]) in items)
        try:
            await as_admin(gx_routes.check_sheet, data=gx_routes.SheetCheckIn(game_id=str(GAMES["gf"]), team_name="Nobody"))
            check("a side the club does not have in the match is refused", False, "accepted")
        except HTTPException as e:
            check("a side the club does not have in the match is refused", e.status_code == 404, e.detail)

    print("\n-- 10. 12TH MAN IN THE PREMIERS SQUAD TAKES THE MATCH OFF GAMES PLAYED --")
    from app.routers import honours
    if "user_id" not in honours.premierships.edit_squad.__code__.co_varnames:
        check("the Premiers squad is linked to games played", False, "absent on this commit")
    else:
        async def squad(action, pid, role=None, on=True):
            async with Session() as s:
                return await honours.edit_premiership_squad(
                    org_id=ORG, body=honours.SquadEdit(game_id=GAMES["gf"], action=action, player_id=pid, role=role, on=on),
                    db=s, user=await s.get(User, USER), club=await s.get(Organisation, ORG))

        async def gf_status(pid):
            t = await as_admin(gx_routes.team_list, game_id=str(GAMES["gf"]))
            return next((r for r in t["players"] if r["player_id"] == str(pid)), {})

        before = await header("EXTRA")
        out = await squad("add", P["EXTRA"], "12th Man")
        st = await gf_status(P["EXTRA"])
        check("adding the extra as 12th Man marks the match as not played, reason 12th man",
              st.get("status") == "marked" and st.get("reason") == "twelfth_man" and st.get("source") == "premiers", st)
        check("and says so in the reply", (out.get("games_played") or {}).get("changed") is True, out)
        check("their games played drop by one", await header("EXTRA") == before - 1, (before, await header("EXTRA")))
        items = {i["game_id"] for i in (await as_admin(big))["items"]}
        check("so the grand final sheet leaves the big sheets list (11 counted)", str(GAMES["gf"]) not in items)
        await squad("role", P["EXTRA"], "13th Man", True)
        await squad("role", P["EXTRA"], "12th Man", False)
        st = await gf_status(P["EXTRA"])
        check("swapping 12th Man for 13th Man keeps the match off", st.get("status") == "marked", st)
        await squad("remove", P["EXTRA"])
        st = await gf_status(P["EXTRA"])
        check("taking them off the card counts the match again", st.get("status") == "named"
              and await header("EXTRA") == before, (st, await header("EXTRA"), before))
        out = await squad("role", SQUAD[1], "12th Man", True)
        check("12th Man on a player who batted leaves the match counted, and says why",
              (out.get("games_played") or {}).get("changed") is False
              and "still counts" in (out.get("games_played") or {}).get("message", ""), out)
        # A mark the club made by hand is not touched by the Premiers role coming off.
        await as_admin(gx_routes.mark_not_played, game_id=str(GAMES["gf"]),
                       data=gx_routes.NotPlayedIn(player_id=str(P["EXTRA"]), reason="other"))
        await squad("add", P["EXTRA"], "13th Man")
        await squad("remove", P["EXTRA"])
        st = await gf_status(P["EXTRA"])
        check("a mark made on the match page survives the Premiers role coming off",
              st.get("status") == "marked" and st.get("reason") == "other", st)

    await finish()


async def finish() -> None:
    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
