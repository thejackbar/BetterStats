"""The record book's MATCHES column counts matches PLAYED, and the scorecard
draws its fielding.

Reported by Shoalwater Bay off two screens:

* Records -> Most Career Runs read R Spinks 7,045 runs, 435 matches, 438
  innings, while his own profile reads 465 matches. Neither figure is wrong:
  the board's game-level branch counted ``COUNT(DISTINCT bi.game_id)`` over its
  own batting rows, i.e. matches he BATTED in, and the profile counts matches
  he PLAYED in (batted, bowled, fielded or was named). The 30 in between are
  matches he was picked for and did not bat in.
* A 1992-93 scorecard showed no catches. The archive records catches as a
  per-player tally per match, never which batter each one dismissed, so the
  dismissal reads a bare ``c``; the tally itself was imported, and the API has
  always returned it as ``fielding``, but the page never drew it.

Runs the SHIPPED ``get_records`` and ``get_scorecard`` bodies over the
``v_effective_*`` views pulled straight out of the migrations that define them.
The fixture is Spinks's shape in miniature: games he batted in, and one each
where he only bowled, only fielded, was only named, or was a did-not-bat row,
on both the synced tables and the manual (scorebook import) ones.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_records_matches_played.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

# The schema, engine and session factory are the timing suite's own, so the two
# cannot build the same tables two different ways.
from verify_records_timing import ORG, OPPONENT, Session, build_schema, engine, records

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


SEASON = uuid.UUID("a1000000-0000-0000-0000-000000000001")
SENIOR = uuid.UUID("a2000000-0000-0000-0000-000000000001")
JUNIOR = uuid.UUID("a2000000-0000-0000-0000-000000000002")
SPINKS = uuid.UUID("a3000000-0000-0000-0000-000000000001")
MATE = uuid.UUID("a3000000-0000-0000-0000-000000000002")
KID = uuid.UUID("a3000000-0000-0000-0000-000000000003")
KEEPER = uuid.UUID("a3000000-0000-0000-0000-000000000004")

# What the fixture is built to give R Spinks (see seed()).
SPINKS_BATTED = 6      # g1-g5 and manual m1
SPINKS_INNINGS = 10    # g1 once, g2-g5 twice (two-day matches), m1 once
SPINKS_PLAYED = 11     # the six above + bowled-only, fielded-only, named-only,
                       # DNB-row, and manual m2 (a DNB row and a spell, no bat)


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name, slug in ((ORG, "Timing CC", "timing"), (OPPONENT, "Rivals CC", "rivals")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=name, s=slug)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 1996/97', 1996)", i=SEASON, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'B grade', :g, 'senior', ARRAY['senior'])",
             i=SENIOR, s=SEASON, g=str(SENIOR))
    # A junior grade is what makes a Men's/senior selection an ACTIVE scope, so
    # the board takes its game-level branch, as Shoalwater's does.
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'Under 14s', :g, 'junior', ARRAY['junior'])",
             i=JUNIOR, s=SEASON, g=str(JUNIOR))
    for pid, nm in ((SPINKS, "Spinks, Ray"), (MATE, "Baker, Ken"),
                    (KID, "Young, Sam"), (KEEPER, "Gloves, Gary")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

    async def game(day: int, grade=SENIOR) -> uuid.UUID:
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, "
                 " away_org_id, match_format, status) "
                 "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                 i=gid, g=grade, d=date(1996, 11, day), o=ORG, x=OPPONENT)
        return gid

    async def bat(gid, pid, runs, *, dnb=False, pos=3):
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, "
                 " sixes, not_out, dismissal_type, did_not_bat, batting_position) "
                 "VALUES (:g, :p, :r, :b, 2, 0, false, :d, :n, :pos)",
                 g=gid, p=pid, r=None if dnb else runs, b=None if dnb else runs + 10,
                 d=None if dnb else "c", n=dnb, pos=pos)

    async def bowl(gid, pid, wickets):
        await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, "
                 " wickets) VALUES (:g, :p, 8.0, 1, 30, :w)", g=gid, p=pid, w=wickets)

    async def field(gid, pid, catches=1, wk=0):
        await ex("INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, "
                 " stumpings, run_outs) VALUES (:g, :p, :c, :w, 0, 0)",
                 g=gid, p=pid, c=catches, w=wk)

    async def named(gid, pid, captain=False):
        await ex("INSERT INTO game_appearances (game_id, player_id, is_captain) "
                 "VALUES (:g, :p, :c)", g=gid, p=pid, c=captain)

    # g1: a hundred and the wickets that make him an all-rounder, batting once.
    g1 = await game(1)
    await bat(g1, SPINKS, 1005); await bowl(g1, SPINKS, 100)
    await field(g1, SPINKS); await named(g1, SPINKS, captain=True)
    # g2-g5: two-day matches, two innings each. Ten dismissals in all, so the
    # batting-average board (which wants ten) carries him too.
    for d in (2, 3, 4, 5):
        g = await game(d)
        await bat(g, SPINKS, 60 if d == 2 else 20); await bat(g, SPINKS, 15)
        await bowl(g, SPINKS, 1); await field(g, SPINKS)
        await named(g, SPINKS, captain=(d == 2))
    # Matches he was in and did NOT bat in, one of each kind.
    g6 = await game(6); await bowl(g6, SPINKS, 2)              # bowled only
    g7 = await game(7); await field(g7, SPINKS)                # fielded only
    g8 = await game(8); await named(g8, SPINKS)                # named only
    g9 = await game(9); await bat(g9, SPINKS, 0, dnb=True)     # a DNB row only
    # A control who bats in every match he plays: nothing may move for him.
    with_games = (await session.execute(
        text("SELECT id FROM games WHERE grade_id = :g ORDER BY played_at LIMIT 5"),
        {"g": SENIOR})).scalars().all()
    for g in with_games:
        await bat(g, MATE, 25, pos=4)
        await named(g, MATE)
    # A keeper, for the fielding block.
    await field(g1, KEEPER, catches=0, wk=3)
    await named(g1, KEEPER)

    # Two scorebook-import matches, on the manual tables. The archive is a
    # manual import at Shoalwater, so the fix has to hold for these too.
    async def manual(day: int) -> uuid.UUID:
        mid = uuid.uuid4()
        await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
                 " played_at, opposition, result, winning_team) "
                 "VALUES (:i, :o, :s, :g, :d, 'Rivals CC', 'WIN', 'Timing CC')",
                 i=mid, o=ORG, s=SEASON, g=SENIOR, d=date(1996, 12, day))
        return mid

    m1 = await manual(1)
    await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
             " batting_position, runs, balls, fours, sixes, not_out, dismissal_type, did_not_bat) "
             "VALUES (:m, :p, 1, 3, 40, NULL, 3, 0, false, 'c', false)", m=m1, p=SPINKS)
    await ex("INSERT INTO manual_fielding_stats (manual_game_id, player_id, catches, catches_wk, "
             " run_outs, stumpings) VALUES (:m, :p, 2, 0, 0, 0)", m=m1, p=SPINKS)
    m2 = await manual(2)
    await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
             " batting_position, runs, not_out, did_not_bat) "
             "VALUES (:m, :p, 1, 9, 0, false, true)", m=m2, p=SPINKS)
    await ex("INSERT INTO manual_bowling_spells (manual_game_id, player_id, innings_number, "
             " overs, maidens, runs, wickets) VALUES (:m, :p, 1, 6.0, 0, 21, 1)",
             m=m2, p=SPINKS)
    # The keeper's tally, as the scorebook converter writes it: the keeper's
    # catches in catches_wk and nothing in catches.
    await ex("INSERT INTO manual_fielding_stats (manual_game_id, player_id, catches, catches_wk, "
             " run_outs, stumpings) VALUES (:m, :p, 0, 2, 0, 1)", m=m1, p=KEEPER)
    await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
             " batting_position, runs, not_out, did_not_bat) "
             "VALUES (:m, :p, 1, 10, 5, true, false)", m=m1, p=KEEPER)

    # A junior-grade game only the kid played: the senior selection drops it,
    # which is what activates the scope.
    gj = await game(20, grade=JUNIOR)
    await bat(gj, KID, 12); await named(gj, KID)

    # CA's own season aggregate for the unfiltered path (source 'api').
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, batting_innings, "
             " runs, not_outs, wickets, source) VALUES (:p, :s, 20, 25, 1400, 2, 110, 'api')",
             p=SPINKS, s=SEASON)
    await session.commit()


def row(board, pid):
    return next((r for r in board if r["player_id"] == str(pid)), None)


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)

    print("\n-- the reported case: a senior selection takes the game-level branch --")
    async with Session() as session:
        scoped = await records(session, categories="senior")
    check("the selection is an active scope (the game-level branch)",
          scoped["grade_scope"].get("active") is True, str(scoped["grade_scope"]))
    bat = scoped["batting"]
    runs_row = row(bat["top_career_runs"], SPINKS)
    check("Spinks is on Most Career Runs", runs_row is not None)
    if runs_row:
        check("his innings are still his batting innings",
              runs_row["innings"] == SPINKS_INNINGS, str(runs_row))
        check(f"his matches are matches PLAYED ({SPINKS_PLAYED}), not batted in ({SPINKS_BATTED})",
              runs_row["matches"] == SPINKS_PLAYED, f"got {runs_row['matches']}")
        check("so matches can now sit either side of innings, as on his profile",
              runs_row["matches"] > 0)

    print("\n-- every career board reads the same figure --")
    mates = {
        "top_career_runs": row(bat["top_career_runs"], SPINKS),
        "top_batting_avg": row(bat["top_batting_avg"], SPINKS),
        "most_fifties": row(bat["most_fifties"], SPINKS),
        "most_hundreds": row(bat["most_hundreds"], SPINKS),
        "top_career_wickets": row(scoped["bowling"]["top_career_wickets"], SPINKS),
        "top_bowling_avg": row(scoped["bowling"]["top_bowling_avg"], SPINKS),
        "top_allrounders": row(scoped["allrounders"]["top_allrounders"], SPINKS),
        "most_matches": row(scoped["team"]["most_matches"], SPINKS),
    }
    for name, r in mates.items():
        check(f"{name}: Spinks is on it and reads {SPINKS_PLAYED} matches",
              r is not None and r["matches"] == SPINKS_PLAYED,
              str(None if r is None else r.get("matches")))

    print("\n-- a player who bats in every match he plays does not move --")
    mate = row(bat["top_career_runs"], MATE)
    check("the control still reads the five matches he batted in",
          mate is not None and mate["matches"] == 5, str(mate))
    check("and his innings are untouched", mate is not None and mate["innings"] == 5)

    print("\n-- nothing else about a row changes --")
    check("runs are untouched", runs_row is not None and runs_row["runs"] == 1005 + 60 + 15 + 3 * (20 + 15) + 40,
          str(runs_row))
    check("the junior game stays out of a senior selection",
          row(bat["top_career_runs"], KID) is None)

    print("\n-- a named grade reads the same way --")
    async with Session() as session:
        graded = await records(session, categories="senior", grade_name="B grade")
    gr = row(graded["batting"]["top_career_runs"], SPINKS)
    check("filtered to the grade, matches are still matches played",
          gr is not None and gr["matches"] == SPINKS_PLAYED, str(gr))

    print("\n-- the views that mean something else are left alone --")
    async with Session() as session:
        captain = await records(session, categories="senior", captain_only=True)
    cap = row(captain["batting"]["top_career_runs"], SPINKS)
    check("captain-only counts matches as captain, not matches played",
          cap is not None and cap["matches"] == 2, str(cap))
    async with Session() as session:
        everything = await records(session, categories="senior,junior")
    check("every category is no scope at all",
          everything["grade_scope"].get("active") is False, str(everything["grade_scope"]))
    agg = row(everything["batting"]["top_career_runs"], SPINKS)
    async with Session() as session:
        view_total = (await session.execute(text(
            "SELECT SUM(matches) FROM v_effective_player_season_stats "
            "WHERE player_id = :p"), {"p": SPINKS})).scalar()
    check("so the unfiltered board still reads the season stats view, untouched",
          agg is not None and agg["matches"] == view_total, f"{agg} vs view {view_total}")
    check("and that is not the played figure the game-level branch reads",
          agg is not None and agg["matches"] != SPINKS_PLAYED)

    print("\n-- the scorecard hands the page its fielding --")
    from app.routers.games import get_scorecard
    async with Session() as session:
        gid = (await session.execute(text(
            "SELECT id FROM manual_games ORDER BY played_at LIMIT 1"))).scalar()
        card = await get_scorecard(str(gid), session)
    fielding = card.get("fielding") or []
    names = {f["player_name"]: f for f in fielding}
    check("the fielding tally is on the payload", bool(fielding), str(card.keys()))
    spinks_f = next((f for f in fielding if f["player_id"] == str(SPINKS)), None)
    check("Spinks's two catches are there", spinks_f is not None and spinks_f["catches"] == 2,
          str(spinks_f))
    keeper_f = next((f for f in fielding if f["player_id"] == str(KEEPER)), None)
    check("a keeper's catches ride in catches_wk",
          keeper_f is not None and keeper_f.get("catches_wk") == 2, str(keeper_f))
    check("and stumpings are there too", keeper_f is not None and keeper_f["stumpings"] == 1)
    check("the payload names catches_wk on every row, not only keepers'",
          all("catches_wk" in f for f in fielding), str(fielding))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
