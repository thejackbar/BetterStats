"""Picking a grade on the Leaderboard must not change what M means, and StatLab's
Grade picker must find a renamed grade.

Reported by Shoalwater Bay: the numbers StatLab gives for A, B and C grade differ
from the Club Leaderboard when A grade, B grade and so on are toggled, "similar
to R Spinks: 435 matches on Records vs 465 on his profile".

Two causes, both reproduced here through the SHIPPED code:

* The Leaderboard's picked-grade branches (batting, bowling and fielding, by
  grade name and by grade id) counted ``COUNT(DISTINCT game_id)`` over their own
  per-innings rows, so M under "B Grade" was the matches a player BATTED (or
  bowled, or fielded) in. The all-grades board, the profile and StatLab count
  matches PLAYED, so the same player read 11 in one place and 6 in another. The
  scoped all-grades branch was fixed in v9.62.2 and the Records boards in
  v9.100.3; v9.62.2 listed these branches as noticed, not fixed.
* StatLab's Grade picker is fed by /organisations/{org}/grades, which lists a
  grade under its display name. The filter compared only the canonical name, so
  a grade the club had renamed ("B grade" shown as "Premier") returned no rows.

Runs the SHIPPED route bodies and ``statlab.run_query`` over the ``v_effective_*``
views pulled straight out of the migrations that define them. The fixture is the
Records suite's Spinks in miniature (batted, bowled-only, fielded-only,
named-only, DNB-row on the synced tables, plus two scorebook matches on the
manual ones), then one more season whose grade is merged into B grade.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_leaderboard_grade_matches.py
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

import verify_records_matches_played as base
from verify_records_timing import ORG, OPPONENT, Session, build_schema, engine

from app.routers import leaderboard as lb
from app.services import statlab

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


SPINKS = str(base.SPINKS)
MATE = str(base.MATE)
GRADE = base.SENIOR
# base.SPINKS_PLAYED (11) all sit in B grade; the merged season adds one more.
MERGED_SEASON_GAME = 1
SPINKS_PLAYED_IN_B = base.SPINKS_PLAYED + MERGED_SEASON_GAME


async def seed_merged_season(session) -> None:
    """A later season whose grade CA renamed, merged into B grade."""
    sid, gid, game = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await session.execute(text(
        "INSERT INTO seasons (id, organisation_id, name, year) "
        "VALUES (:i, :o, 'Summer 1997/98', 1997)"), {"i": sid, "o": ORG})
    await session.execute(text(
        "INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
        "VALUES (:i, :s, 'Men''s Second', :g, 'senior', ARRAY['senior'])"),
        {"i": gid, "s": sid, "g": str(gid)})
    await session.execute(text(
        "INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
        " match_format, status) VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')"),
        {"i": game, "g": gid, "d": date(1997, 11, 1), "o": ORG, "x": OPPONENT})
    await session.execute(text(
        "INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, "
        " not_out, dismissal_type, did_not_bat, batting_position) "
        "VALUES (:g, :p, 50, 60, 2, 0, false, 'c', false, 3)"), {"g": game, "p": base.SPINKS})
    await session.execute(text(
        "INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)"),
        {"g": game, "p": base.SPINKS})
    await session.execute(text(
        "INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name) "
        "VALUES (:o, 'B grade', 'Men''s Second')"), {"o": ORG})
    await session.commit()


async def board(fn, **kw):
    async with Session() as s:
        args = dict(
            org_id=str(ORG), season_id=None, grade_id=None, grade_name=None,
            finals_only=None, captain_only=None, gender=None, overseas=None,
            categories=None, formats=None, competitions=None, db=s, viewer=None)
        args.update(kw)
        return await fn(**args)


def games_for(rows, pid):
    r = next((x for x in rows if x.get("player_id") == pid), None)
    return None if r is None else r.get("games")


async def three_boards(**kw):
    bat = await board(lb.batting_leaderboard, sort_by="total_runs", limit=50, min_runs=0,
                      min_rate_innings=0, **kw)
    bowl = await board(lb.bowling_leaderboard, sort_by="total_wickets", limit=50, min_overs=0,
                       min_wickets=0, min_rate_spells=0, **kw)
    field = await board(lb.fielding_leaderboard, sort_by="total_dismissals", limit=50, **kw)
    return bat, bowl, field


async def statlab_rows(target, ctx):
    async with Session() as s:
        res = await statlab.run_query(
            s, org_id=str(ORG), target=target, sort_by="runs", sort_dir="desc", limit=200,
            metric_filters=None, filter_tree=None, context=ctx)
    return [r for r in res["rows"] if str(r.get("player_id")) == SPINKS]


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await base.seed(session)

    print("\n-- the reference: the all-grades board and StatLab agree on matches played --")
    bat, bowl, field = await three_boards()
    for name, rows in (("batting", bat), ("bowling", bowl), ("fielding", field)):
        check(f"all grades, {name}: Spinks reads {base.SPINKS_PLAYED} matches",
              games_for(rows, SPINKS) == base.SPINKS_PLAYED, str(games_for(rows, SPINKS)))
    sl = await statlab_rows("player_grade", {"grade_names": ["B grade"]})
    check(f"StatLab, B grade: {base.SPINKS_PLAYED} matches",
          bool(sl) and sl[0].get("matches") == base.SPINKS_PLAYED,
          str([r.get("matches") for r in sl]))

    print("\n-- toggling a grade on the Leaderboard keeps M as matches played (the report) --")
    for how, kw in (("by grade name", {"grade_name": "B grade"}),
                    ("by grade id", {"grade_id": str(GRADE)})):
        bat, bowl, field = await three_boards(**kw)
        for name, rows in (("batting", bat), ("bowling", bowl), ("fielding", field)):
            check(f"B grade {how}, {name}: Spinks reads {base.SPINKS_PLAYED}, as on every other screen",
                  games_for(rows, SPINKS) == base.SPINKS_PLAYED,
                  f"got {games_for(rows, SPINKS)} (batted {base.SPINKS_BATTED})")
    bat, _, _ = await three_boards(grade_name="B grade")
    check("a player who bats in every match he plays does not move",
          games_for(bat, MATE) == 5, str(games_for(bat, MATE)))
    check("and the runs on the row are untouched",
          next(r for r in bat if r["player_id"] == SPINKS)["total_runs"]
          == 1005 + 60 + 15 + 3 * (20 + 15) + 40)

    print("\n-- only the picked grade's matches count --")
    bat, _, _ = await three_boards(grade_name="Under 14s")
    check("the junior grade lists the kid on his one match",
          games_for(bat, str(base.KID)) == 1, str(games_for(bat, str(base.KID))))
    check("and does not list Spinks, who never played in it",
          games_for(bat, SPINKS) is None, str(games_for(bat, SPINKS)))

    print("\n-- a grade merged from another season counts too --")
    async with Session() as session:
        await seed_merged_season(session)
    bat, bowl, field = await three_boards(grade_name="B grade")
    check(f"batting, merged: {SPINKS_PLAYED_IN_B} matches",
          games_for(bat, SPINKS) == SPINKS_PLAYED_IN_B, str(games_for(bat, SPINKS)))
    sl = await statlab_rows("player_grade", {"grade_names": ["B grade"]})
    check("and StatLab says the same number",
          bool(sl) and sl[0].get("matches") == SPINKS_PLAYED_IN_B, str([r.get("matches") for r in sl]))
    one_season = await board(lb.batting_leaderboard, sort_by="total_runs", limit=50, min_runs=0,
                             min_rate_innings=0, grade_name="B grade",
                             season_id=str(base.SEASON))
    check("a season filter narrows it to that season's matches",
          games_for(one_season, SPINKS) == base.SPINKS_PLAYED, str(games_for(one_season, SPINKS)))

    print("\n-- StatLab finds a grade the club has renamed --")
    async with Session() as session:
        await session.execute(text(
            "UPDATE grades SET display_name_override = 'Premier' WHERE id = :g"), {"g": GRADE})
        await session.commit()
    from app.routers.organisations import get_org_grades
    async with Session() as session:
        offered = [g["name"] for g in await get_org_grades(str(ORG), None, session, None)]
    check("the picker offers the display name", "Premier" in offered, str(offered))
    for target in ("player_grade", "player_career"):
        rows = await statlab_rows(target, {"grade_names": ["Premier"]})
        check(f"{target}: grade_names=Premier finds Spinks",
              bool(rows), "no rows")
        rows_single = await statlab_rows(target, {"grade_name": "Premier"})
        check(f"{target}: the single-value grade_name finds him too",
              bool(rows_single), "no rows")
    by_display = await statlab_rows("player_grade", {"grade_names": ["Premier"]})
    by_canonical = await statlab_rows("player_grade", {"grade_names": ["B grade"]})
    check("and the canonical name a saved report carries still works",
          bool(by_canonical), "no rows")
    check("both spellings give the same matches",
          bool(by_display) and bool(by_canonical)
          and by_display[0].get("matches") == by_canonical[0].get("matches"),
          f"{[r.get('matches') for r in by_display]} vs {[r.get('matches') for r in by_canonical]}")
    check("a name that is no grade at all still finds nobody",
          await statlab_rows("player_grade", {"grade_names": ["Nonsense"]}) == [])
    bat, _, _ = await three_boards(grade_name="Premier")
    check("and the Leaderboard agrees under the renamed grade",
          games_for(bat, SPINKS) == SPINKS_PLAYED_IN_B, str(games_for(bat, SPINKS)))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
