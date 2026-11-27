"""A club leaves a whole match out of its players' stats, and counts it again.

Reported by Kalamunda: the Tuesday T20 against Hills (Mountford Tillemans Shield 2026,
play.cricket.com.au/match/97e4fbfe-6bf7-4571-ba86-b2f8c20e6012) is a social fixture Cricket Australia
lists like any other, and the club wants it on Results and off every player's career.

The fixture here is filed under HILLS' season (Hills synced it first), the harder of the two cases:
Kalamunda's figures must lose it, Hills' must keep it, and the scorecard must still show it whole.

Every figure is read through the shipped route bodies and services with the production views, against a
real Postgres. Run this same file against the previous commit as the control: section 1 passes there,
and the later sections report the feature as absent rather than crashing.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \\
  python verification/verify_stat_exclusions.py
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
from app.routers.records import get_records
from app.services import grade_scope, milestone_totals, statlab, superseded_ddl
from app.services.aggregations import (
    get_game_fall_of_wickets, get_game_partnerships, get_player_by_opposition, get_player_team_breakdown,
)
from app.services.game_status import appearance_counts_as_match

try:  # absent on the control commit: reported, never crashed on
    from app.routers import stat_exclusions as sx_routes
    from app.routers.manual_entries import undo_edit
    from app.services import stat_exclusions as sx
except ImportError:
    sx_routes = sx = None

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


KCC, HWCC, OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
USER = uuid.uuid4()
S_KCC, S_HWCC, S_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_SAT, G_T20_HWCC, G_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
P = {k: uuid.uuid4() for k in ("ALEX", "BEN", "HANK")}
T20 = uuid.UUID("97e4fbfe-6bf7-4571-ba86-b2f8c20e6012")
STRANGERS = uuid.uuid4()
SAT_GAMES: list[uuid.UUID] = []
PC_LINK = ("https://play.cricket.com.au/match/97e4fbfe-6bf7-4571-ba86-b2f8c20e6012/"
           "hwcc-tuesday-t20-kcc-tuesday-t20-mountford-tillemans-shield-2026?tab=scorecard")
BC_LINK = "https://betterat.cricket/games/97e4fbfe-6bf7-4571-ba86-b2f8c20e6012"


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((KCC, "Kalamunda CC", "kalamunda"), (HWCC, "Hills CC", "hills"), (OTHER, "Other CC", "other")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO users (id, email, username, password_hash, failed_login_count) "
                 "VALUES (:i, 'admin@x', 'kcc-admin', 'x', 0)", i=USER)
        # The same real season for both clubs: one CA season guid.
        for sid, oid in ((S_KCC, KCC), (S_HWCC, HWCC), (S_OTHER, OTHER)):
            await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                     "VALUES (:i, :o, 'Summer 2026/27', 2026, 'ca-season-2026')", i=sid, o=oid)
        for gid, sid, nm in ((G_SAT, S_KCC, "A Grade"), (G_T20_HWCC, S_HWCC, "Tuesday T20"),
                             (G_OTHER, S_OTHER, "B Grade")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=sid, n=nm, g=str(gid))
        for k, oid, nm in (("ALEX", KCC, "Able, Alex"), ("BEN", KCC, "Bench, Ben"), ("HANK", HWCC, "Hills, Hank")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')",
                     i=P[k], o=oid, n=nm, g=str(P[k]))

        async def game(gid, grade, day, home, away, home_org, away_org):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status, "
                     " innings_totals, home_team, away_team) VALUES (:i, :g, :d, 'WIN', :h, :a, 'T20', 'COMPLETED', "
                     " jsonb_build_array(jsonb_build_object('runs_scored', 150, 'wickets', 5)), :ht, :at)",
                     i=gid, g=grade, d=day, h=home_org, a=away_org, ht=home, at=away)

        async def bat(gid, pid, runs, inn=1):
            await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                     " dismissal_type, did_not_bat) VALUES (:g, :p, :i, :r, :b, 2, 1, false, 'caught', false)",
                     g=gid, p=pid, i=inn, r=runs, b=runs + 5)

        async def bowl(gid, pid, wkts, inn=2):
            await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                     "VALUES (:g, :p, :i, 4, 0, 25, :w)", g=gid, p=pid, i=inn, w=wkts)

        async def appear(gid, pid, team):
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name) VALUES (:g, :p, :t)", g=gid, p=pid, t=team)

        # Three Saturday games for Alex: 20 runs and a wicket each.
        for i in range(3):
            gid = uuid.uuid4()
            SAT_GAMES.append(gid)
            await game(gid, G_SAT, date(2026, 10, 3) + timedelta(days=7 * i), "Kalamunda", "Opposition", KCC, None)
            await appear(gid, P["ALEX"], "Kalamunda")
            await bat(gid, P["ALEX"], 20)
            await bowl(gid, P["ALEX"], 1)

        # THE TUESDAY T20, filed under Hills' season. Alex 55 and 3 wickets and a catch; Ben named and nothing
        # else; Hank (Hills) 40 and 2 wickets.
        await game(T20, G_T20_HWCC, date(2026, 11, 24), "HWCC Tuesday T20", "KCC Tuesday T20", HWCC, KCC)
        for pid, team in ((P["ALEX"], "KCC Tuesday T20"), (P["BEN"], "KCC Tuesday T20"), (P["HANK"], "HWCC Tuesday T20")):
            await appear(T20, pid, team)
        await bat(T20, P["HANK"], 40, inn=1)
        await bat(T20, P["ALEX"], 55, inn=2)
        await bowl(T20, P["ALEX"], 3, inn=1)
        await bowl(T20, P["HANK"], 2, inn=2)
        await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, run_outs, stumpings) "
                 "VALUES (:g, :p, 1, 0, 0, 0)", g=T20, p=P["ALEX"])
        await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, overs_at_fall, "
                 " player_id, batter_name) VALUES (:g, 2, 1, 80, 9.2, :p, 'Able, Alex')", g=T20, p=P["ALEX"])
        await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, balls, "
                 " batter1_runs, batter2_runs, is_club_innings, batter1_name, batter2_name) "
                 "VALUES (:g, 2, 1, :p, NULL, 80, 56, 55, 25, true, 'Able, Alex', 'Somebody')", g=T20, p=P["ALEX"])

        # A match neither of these clubs played, for the refusal.
        await game(STRANGERS, G_OTHER, date(2026, 11, 1), "Other CC", "Elsewhere", OTHER, None)

        # Cricket Australia's season totals, which count the T20.
        # Alex's CA total also counts a fourth Saturday game we hold NO scorecard for: 30 runs, 1 for 25 off 4.
        # So CA reads 5 games, 145 runs, 7 wickets, best 3-25 and a high score of 55 (both in the T20).
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, fifties, "
                 " high_score, is_hs_not_out, balls_faced, wickets, overs, bowling_balls, runs_conceded, maidens, "
                 " best_bowling_wickets, best_bowling_figures, bowling_innings, catches, source) "
                 "VALUES (:p, :s, 5, 5, 145, 0, 1, 55, false, 180, 7, 20, 120, 125, 0, 3, '3-25', 5, 1, 'api')",
                 p=P["ALEX"], s=S_KCC)
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                 " catches, source) VALUES (:p, :s, 1, 0, 0, 0, 0, 0, 'api')", p=P["BEN"], s=S_KCC)
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, runs, not_outs, wickets, "
                 " catches, source) VALUES (:p, :s, 1, 1, 40, 0, 2, 0, 'api')", p=P["HANK"], s=S_HWCC)
        for pid, sid, gid, m in ((P["ALEX"], S_KCC, G_SAT, 4), (P["ALEX"], S_KCC, G_T20_HWCC, 1),
                                 (P["BEN"], S_KCC, G_T20_HWCC, 1), (P["HANK"], S_HWCC, G_T20_HWCC, 1)):
            await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, matches) VALUES (:p, :s, :g, :m)",
                     p=pid, s=sid, g=gid, m=m)
        await s.commit()


async def career(key) -> dict:
    async with Session() as s:
        d = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                   start_date=None, end_date=None, categories=None, formats=None, competitions=None,
                                   grades=None)
    b, w, f = d.get("career_batting") or {}, d.get("career_bowling") or {}, d.get("career_fielding") or {}
    return {"games": b.get("games"), "runs": b.get("total_runs"), "fifties": b.get("fifties"),
            "wickets": w.get("total_wickets"), "catches": f.get("total_catches"), "hs": b.get("high_score"),
            "best": w.get("best_bowling_figures")}


async def filtered(key) -> dict:
    """The paths a filter takes: the last 10 games, a category, the season table under it, by opposition."""
    async with Session() as s:
        last = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=10,
                                      start_date=None, end_date=None, categories=None, formats=None, competitions=None,
                                      grades=None)
        cat = await get_player_stats(player_id=str(P[key]), db=s, season_id=None, grade_id=None, last_n_games=None,
                                     start_date=None, end_date=None, categories=["senior"], formats=None,
                                     competitions=None, grades=None)
        seas = await get_player_seasons(player_id=str(P[key]), categories=["senior"], formats=None, competitions=None,
                                        grades=None, db=s)
        opp = await get_player_by_opposition(s, str(P[key]))
    return {
        "last10": ((last.get("career_batting") or {}).get("games"), (last.get("career_batting") or {}).get("total_runs")),
        "senior": ((cat.get("career_batting") or {}).get("games"), (cat.get("career_batting") or {}).get("total_runs")),
        "senior_seasons": sorted((r.get("matches"), r.get("total_runs")) for r in seas),
        "opposition_games": sum(int(r.get("matches") or r.get("games") or 0) for r in opp),
    }


async def season_rows(key) -> dict:
    async with Session() as s:
        rows = await get_player_seasons(player_id=str(P[key]), categories=None, formats=None, competitions=None,
                                        grades=None, db=s)
    return {r.get("season_name"): (r.get("matches"), r.get("total_runs"), r.get("total_wickets")) for r in rows}


async def grid(key, org) -> int:
    async with Session() as s:
        return (await get_player_team_breakdown(s, str(P[key]), str(org), None))["grid_matches"]


async def board(key, org) -> tuple | None:
    async with Session() as s:
        rows = await batting_leaderboard(db=s, viewer=None, org_id=str(org), season_id=None, grade_id=None, grade_name=None,
                                         limit=50, finals_only=None, captain_only=None, gender=None, overseas=None,
                                         categories=None, formats=None, competitions=None, sort_by="total_runs",
                                         min_runs=0, min_rate_innings=0)
    row = next((r for r in rows if str(r["player_id"]) == str(P[key])), None)
    return None if row is None else (row.get("games"), row.get("total_runs"))


async def appearances_counted(pid, gid, for_stats=True) -> bool:
    async with Session() as s:
        return bool((await s.execute(text(
            f"SELECT 1 FROM game_appearances ga WHERE ga.game_id = :g AND ga.player_id = :p "
            f"AND {appearance_counts_as_match('ga', for_stats=for_stats)}"), {"g": gid, "p": pid})).first())


async def card(org) -> tuple[int, int]:
    async with Session() as s:
        return (len(await get_game_fall_of_wickets(s, T20, str(org))),
                len(await get_game_partnerships(s, T20, str(org))))


async def as_admin(fn, **kw):
    async with Session() as s:
        user = await s.get(User, USER)
        club = await s.get(Organisation, KCC)
        return await fn(current_user=user, club=club, db=s, **kw)


async def records(org=KCC) -> dict:
    async with Session() as s:
        rec = await get_records(str(org), db=s, season_id=None, grade_id=None, grade_name=None, finals_only=False,
                                captain_only=False, gender=None, categories=None, formats=None, competitions=None,
                                debug_timing=False, viewer=None)
    def on(rows):
        r = next((r for r in rows if str(r.get("player_id")) == str(P["ALEX"])), None)
        return None if r is None else {k: r.get(k) for k in ("matches", "runs", "wickets", "total_runs", "total_wickets")
                                       if r.get(k) is not None}
    top_scores = [r.get("runs") for r in rec["batting"]["top_high_scores"]
                  if str(r.get("player_id")) == str(P["ALEX"])]
    figures = [r.get("wickets") for r in rec["bowling"]["best_innings_figures"]
               if str(r.get("player_id")) == str(P["ALEX"])]
    return {"career_runs": on(rec["batting"]["top_career_runs"]), "career_wkts": on(rec["bowling"]["top_career_wickets"]),
            "most_matches": on(rec["team"]["most_matches"]), "top_scores": sorted(top_scores, reverse=True),
            "figures": sorted(figures, reverse=True)}


async def statlab_alex() -> dict:
    async with Session() as s:
        scope = await grade_scope.resolve_scope(s, str(KCC), None)
        out = await statlab.run_query(s, org_id=str(KCC), target="player_career", sort_by="matches", sort_dir="desc",
                                      limit=100, page=1, metric_filters=[], filter_tree=None,
                                      context={statlab._SCOPE_KEY: scope})
    r = next((r for r in out["rows"] if r["player_id"] == str(P["ALEX"])), {})
    return {k: r.get(k) for k in ("matches", "runs", "wickets")}


async def milestones_alex() -> dict:
    async with Session() as s:
        t = await milestone_totals.totals_under(s, str(KCC), [P["ALEX"]], None)
    r = t.get(str(P["ALEX"])) or {}
    return {k: r.get(k) for k in ("matches", "runs", "wickets", "catches")}


async def snapshot() -> dict:
    return {"alex": await career("ALEX"), "ben": await career("BEN"), "hank": await career("HANK"),
            "alex_seasons": await season_rows("ALEX"), "alex_grid": await grid("ALEX", KCC),
            "alex_board": await board("ALEX", KCC), "hank_board": await board("HANK", HWCC),
            "records": await records(), "statlab": await statlab_alex(), "milestones": await milestones_alex(),
            "filtered": await filtered("ALEX")}


async def main() -> None:
    await build_schema()
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS ca_called_off BOOLEAN"))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS round_name TEXT"))
        for stmt in superseded_ddl.STATEMENTS:     # the lifespan re-applies these: production reads THESE views
            await conn.execute(text(stmt))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS player_achievements (
            id SERIAL PRIMARY KEY, org_id UUID NOT NULL, player_id UUID, player_name TEXT NOT NULL, season TEXT,
            category TEXT NOT NULL, subcategory TEXT, achievement TEXT NOT NULL, detail TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW())"""))
    await seed()

    print("\n-- 1. BEFORE: THE T20 COUNTS FOR BOTH CLUBS --")
    before = await snapshot()
    check("Alex: CA's 5 games, 145 runs, a fifty, 7 wickets, 1 catch, HS 55, best 3-25",
          before["alex"] == {"games": 5, "runs": 145, "fifties": 1, "wickets": 7, "catches": 1, "hs": 55, "best": "3-25"},
          before["alex"])
    check("Ben: 1 game (named in the T20)", before["ben"]["games"] == 1, before["ben"])
    check("Hank (Hills): 1 game, 40 runs, 2 wickets", (before["hank"]["games"], before["hank"]["runs"],
                                                       before["hank"]["wickets"]) == (1, 40, 2), before["hank"])
    check("Alex's batting board reads 5 games, 145 runs", before["alex_board"] == (5, 145), before["alex_board"])
    check("the scorecard holds a fall of wicket and a stand", await card(KCC) == (1, 1), await card(KCC))
    check("control: Records lists the 55 among Alex's top scores, and the 3-wicket haul",
          55 in before["records"]["top_scores"] and 3 in before["records"]["figures"], before["records"])
    print("     records:", before["records"], "\n     statlab:", before["statlab"], "\n     milestones:", before["milestones"])

    if sx is None:
        print("\n-- 2+. LEAVING A MATCH OUT --")
        check("the stat exclusion feature exists", False, "app.services.stat_exclusions is absent on this commit")
        return await finish()

    print("\n-- 2. THE LINK --")
    check("a play.cricket.com.au link reads as the match", sx.parse_link(PC_LINK) == T20)
    check("a BetterCricket link reads as the same match", sx.parse_link(BC_LINK) == T20)
    for bad, word in (("https://www.playhq.com/cricket-australia/org/x/y/game-centre/abecedd5", "PlayHQ"),
                      ("hello", "match link")):
        try:
            await as_admin(sx_routes.lookup, link=bad)
            check(f"refused: {bad[:30]}", False, "accepted")
        except HTTPException as e:
            check(f"refused with a reason the admin can read ({word})", e.status_code == 422 and word in e.detail, e.detail)
    try:
        await as_admin(sx_routes.lookup, link=f"https://betterat.cricket/games/{STRANGERS}")
        check("a match the club did not play is refused", False, "accepted")
    except HTTPException as e:
        check("a match the club did not play is refused", e.status_code == 404 and "isn't one of your club's" in e.detail,
              e.detail)
    try:
        await as_admin(sx_routes.lookup, link=f"https://betterat.cricket/games/{uuid.uuid4()}")
        check("a match we do not hold is refused", False, "accepted")
    except HTTPException as e:
        check("a match we do not hold is refused, and says why", e.status_code == 404 and "synced" in e.detail, e.detail)

    info = await as_admin(sx_routes.lookup, link=PC_LINK)
    check("the lookup names the match", (info["home_team"], info["away_team"]) == ("HWCC Tuesday T20", "KCC Tuesday T20"),
          info)
    names = {p["name"]: (p["runs"], p["wickets"]) for p in info["players"]}
    check("and lists only Kalamunda's players, with what comes off", names == {"Able, Alex": (55, 3), "Bench, Ben": (0, 0)},
          names)
    check("with totals for the confirm step", info["totals"] == {"players": 2, "runs": 55, "wickets": 3, "dismissals": 1},
          info["totals"])
    check("and no exclusion in force yet", info["exclusion"] is None)
    check("and names the side that keeps it, from the team sheet",
          (info["club_team"], info["other_team"]) == ("KCC Tuesday T20", "HWCC Tuesday T20"), info)

    print("\n-- 3. KALAMUNDA EXCLUDES THE T20 --")
    out = await as_admin(sx_routes.exclude, data=sx_routes.ExcludeIn(link=PC_LINK, note="Social T20"))
    check("the reply carries the exclusion", out["match"]["exclusion"] and out["match"]["exclusion"]["note"] == "Social T20",
          out["match"]["exclusion"])
    after = await snapshot()
    check("Alex: 4 games, 90 runs, no fifty, 4 wickets, no catch: the T20 comes off CA's total",
          {k: after["alex"][k] for k in ("games", "runs", "fifties", "wickets", "catches")}
          == {"games": 4, "runs": 90, "fifties": 0, "wickets": 4, "catches": 0}, after["alex"])
    check("THE GAME WE HOLD NO SCORECARD FOR STILL COUNTS (90 runs, not the 60 on our cards)",
          after["alex"]["runs"] == 90, after["alex"])
    check("the high score set in the T20 falls to the best of his other cards (20)", after["alex"]["hs"] == 20,
          after["alex"])
    check("and best bowling to 1-25", after["alex"]["best"] == "1-25", after["alex"])
    check("his season row agrees (4 games, 90 runs, 4 wickets)",
          after["alex_seasons"].get("Summer 2026/27") == (4, 90, 4), after["alex_seasons"])
    check("the by-grade grid reads 4", after["alex_grid"] == 4, after["alex_grid"])
    check("the batting board reads 4 games, 90 runs", after["alex_board"] == (4, 90), after["alex_board"])
    check("Ben's only game is gone", not after["ben"]["games"], after["ben"])
    check("the team sheet no longer counts as a match played for Alex", not await appearances_counted(P["ALEX"], T20))
    check("but fees still count it as a match day", await appearances_counted(P["ALEX"], T20, for_stats=False))
    check("HILLS KEEP IT: Hank still reads 1 game, 40 runs, 2 wickets",
          after["hank"] == before["hank"], (before["hank"], after["hank"]))
    check("and Hills' board is unchanged", after["hank_board"] == before["hank_board"],
          (before["hank_board"], after["hank_board"]))
    check("the scorecard still holds its fall of wicket and its stand", await card(KCC) == (1, 1), await card(KCC))
    print("     alex before:", before["alex"], "after:", after["alex"], "\n     seasons after:", after["alex_seasons"],
          "grid", after["alex_grid"], "board", after["alex_board"])
    print("     filtered before:", before["filtered"], "after:", after["filtered"])
    check("control: every filtered path counts the T20 before (last 10 cards 4 / 115, category 5 / 145, 1 v Hills)",
          before["filtered"]["last10"] == (4, 115) and before["filtered"]["senior"] == (5, 145)
          and before["filtered"]["opposition_games"] == 1, before["filtered"])
    check("filtered: the last 10 games read 3 games, 60 runs", after["filtered"]["last10"] == (3, 60), after["filtered"])
    check("filtered: a category filter reads 4 games, 90 runs", after["filtered"]["senior"] == (4, 90), after["filtered"])
    check("filtered: the season table under it reads 4 games, 90 runs",
          after["filtered"]["senior_seasons"] == [(4, 90)], after["filtered"])
    check("filtered: by opposition, the Hills row is gone", after["filtered"]["opposition_games"] == 0, after["filtered"])
    print("     records:", after["records"], "\n     statlab:", after["statlab"], "\n     milestones:", after["milestones"])
    check("Records: career runs 90 over 4 matches, and the 55 is off the top scores",
          (after["records"]["career_runs"] or {}).get("matches") == 4
          and 90 in (after["records"]["career_runs"] or {}).values() and 55 not in after["records"]["top_scores"],
          after["records"])
    check("Records: the 3-wicket haul is off best figures", 3 not in after["records"]["figures"]
          and 1 in after["records"]["figures"], after["records"])
    check("Records: career wickets 4", 4 in (after["records"]["career_wkts"] or {}).values(), after["records"])
    check("Records: most matches 4", (after["records"]["most_matches"] or {}).get("matches") == 4, after["records"])
    check("StatLab: 4 matches, 90 runs, 4 wickets", after["statlab"] == {"matches": 4, "runs": 90, "wickets": 4},
          after["statlab"])
    check("Milestones: 4 matches, 90 runs, 4 wickets, no catch",
          after["milestones"] == {"matches": 4, "runs": 90, "wickets": 4, "catches": 0}, after["milestones"])
    async with Session() as s:
        pub_k = await sx.is_excluded(s, KCC, T20)
        pub_h = await sx.is_excluded(s, HWCC, T20)
    check("the scorecard badge reads excluded for Kalamunda and not for Hills",
          pub_k is True and pub_h is False, (pub_k, pub_h))
    listed = await as_admin(sx_routes.list_exclusions)
    check("the admin list holds the match with its grade and note",
          [(e["game_id"], e["grade_name"], e["note"]) for e in listed["exclusions"]] == [(str(T20), "Tuesday T20", "Social T20")],
          listed)
    try:
        await as_admin(sx_routes.exclude, data=sx_routes.ExcludeIn(link=BC_LINK))
        check("excluding it twice is refused", False, "accepted")
    except HTTPException as e:
        check("excluding it twice is refused", e.status_code == 409, e.detail)

    print("\n-- 4. COUNT IT AGAIN (THE LIST'S UNDO) --")
    ex_id = listed["exclusions"][0]["id"]
    await as_admin(sx_routes.restore, exclusion_id=ex_id)
    back = await snapshot()
    check("every figure is back where it started", back == before, {k: (before[k], back[k]) for k in back if back[k] != before[k]})
    async with Session() as s:
        kept = (await s.execute(text("SELECT restored_at IS NOT NULL, restored_by FROM game_stat_exclusions WHERE id = :i"),
                                {"i": ex_id})).first()
    check("the row is kept and marked, never deleted", kept is not None and kept[0] and kept[1] == USER, kept)
    check("the list is empty", (await as_admin(sx_routes.list_exclusions))["exclusions"] == [])
    try:
        await as_admin(sx_routes.restore, exclusion_id=ex_id)
        check("counting it again twice is refused", False, "accepted")
    except HTTPException as e:
        check("counting it again twice is refused", e.status_code == 404, e.detail)

    print("\n-- 5. THE AUDIT TRAIL CAN UNDO BOTH WAYS --")
    async with Session() as s:
        logs = (await s.execute(text("SELECT id, action FROM manual_edit_logs WHERE target_table = 'game_stat_exclusions' "
                                     "ORDER BY id"))).all()
    check("both changes are on the audit trail", [a for _, a in logs] == ["create", "delete"], logs)
    await as_admin(undo_edit, log_id=logs[1][0])
    check("undoing 'counted again' leaves the match out again", (await career("ALEX"))["runs"] == 90, await career("ALEX"))
    async with Session() as s:
        n_live = (await s.execute(text("SELECT COUNT(*) FROM game_stat_exclusions WHERE restored_at IS NULL"))).scalar()
    check("as a new row in force, the old one kept", n_live == 1)
    live = (await as_admin(sx_routes.list_exclusions))["exclusions"]
    async with Session() as s:
        log_id = (await s.execute(text("SELECT id FROM manual_edit_logs WHERE target_table = 'game_stat_exclusions' "
                                       "AND action = 'create' ORDER BY id LIMIT 1"))).scalar()
    # The first log's target is the first (restored) row: undoing it now is refused, the match is not in force there.
    try:
        await as_admin(undo_edit, log_id=log_id)
        check("undoing an exclusion that is no longer in force is refused", False, "accepted")
    except HTTPException as e:
        check("undoing an exclusion that is no longer in force is refused", e.status_code == 409, e.detail)
    await as_admin(sx_routes.restore, exclusion_id=live[0]["id"])
    check("and counted again, the figures are back", await career("ALEX") == before["alex"], await career("ALEX"))

    print("\n-- 6. THE VIEWS IN THE DATABASE CARRY THE CLAUSE --")
    async with Session() as s:
        for v in ("v_effective_batting_innings", "v_effective_bowling_spells", "v_effective_fielding_stats",
                  "v_effective_partnerships", "v_effective_bowler_wickets", "v_effective_fall_of_wickets",
                  "v_stat_excluded_seasons", "v_effective_player_season_stats"):
            body = (await s.execute(text("SELECT pg_get_viewdef(to_regclass(:v))"), {"v": v})).scalar() or ""
            check(f"{v} reads game_stat_exclusions", "game_stat_exclusions" in body)
        body = (await s.execute(text("SELECT pg_get_viewdef(to_regclass('v_club_sourced_seasons'))"))).scalar() or ""
        check("v_club_sourced_seasons does not: an exclusion never moves a season off CA's total",
              bool(body) and "game_stat_exclusions" not in body and "v_stat_excluded" not in body)
        body = (await s.execute(text("SELECT pg_get_viewdef(to_regclass('v_card_partnerships'))"))).scalar() or ""
        check("v_card_partnerships does not (the scorecard shows the match whole)",
              bool(body) and "game_stat_exclusions" not in body)
    await finish()


async def finish() -> None:
    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
