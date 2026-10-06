"""The public player profile's Grade filter.

A person on a player's profile can pick one of the club's grades, as Manage Grades
names them (the club's rename, merged names folded together, the club's own reading
order), and every panel on the profile narrows to it.

Runs the SHIPPED route bodies in ``routers/players.py`` and ``get_org_grades`` over
the ``v_effective_*`` views pulled straight out of the migrations, on the Records
suite's Spinks fixture plus:

* an "A grade" the club renamed to "Premier" on Manage Grades,
* a later season's grade CA called "Men's First", merged into A grade,
* a fixture the OTHER club synced first, so it sits in THEIR "A grade" row,
* a hand-typed (manual) game in A grade, and one with no grade at all,
* a junior game for a player who also has senior games (the club default leaves
  juniors out; a picked "Under 14s" must not be told "nothing").

Every route is read through ``call``, which fills each ``Query`` default the way
FastAPI does and DROPS ``grades`` when the route does not take it. That is what makes
the control run (the previous commit) a control: it ignores the pick and fails the
checks, instead of crashing on an unknown keyword.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_player_grade_filter.py
"""
from __future__ import annotations

import asyncio
import inspect
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

from app.routers import organisations as orgs
from app.routers import players as pl

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
KID = str(base.KID)
SEASON2 = uuid.UUID("a1000000-0000-0000-0000-000000000002")
OPP_SEASON = uuid.UUID("a1000000-0000-0000-0000-000000000003")
A_GRADE = uuid.UUID("a2000000-0000-0000-0000-0000000000a1")
FIRST_GRADE = uuid.UUID("a2000000-0000-0000-0000-0000000000a2")
OPP_A_GRADE = uuid.UUID("a2000000-0000-0000-0000-0000000000a3")

# What is added to A grade, by source.
A_OWN = 7 + 9            # two synced games in A grade
A_MANUAL = 11            # a hand-typed game in A grade
A_MERGED = 100           # a season whose grade CA called "Men's First", merged into A
A_SHARED = 3             # a fixture sitting in the other club's "A grade" row
A_RUNS = A_OWN + A_MANUAL + A_MERGED + A_SHARED
NO_GRADE = 4             # a hand-typed game with no grade at all
MATE_JUNIOR = 5


async def call(fn, session, **kw):
    """Call a route body the way FastAPI would: Query defaults filled, and any
    keyword the route does not take (``grades``, on the control) dropped."""
    sig = inspect.signature(fn)
    args = {}
    for name, p in sig.parameters.items():
        if name == "db":
            args[name] = session
        elif name in kw:
            args[name] = kw[name]
        elif p.default is inspect.Parameter.empty:
            raise TypeError(f"{fn.__name__} needs {name}")
        else:
            d = p.default
            if type(d).__name__ == "Depends":
                args[name] = None      # an anonymous public viewer
            else:
                args[name] = getattr(d, "default", d) if hasattr(d, "default") else d
    return await fn(**args)


async def stats(pid, **kw):
    async with Session() as s:
        return await call(pl.get_player_stats, s, player_id=pid, **kw)


def runs_of(data):
    b = (data or {}).get("career_batting") or {}
    return int(b.get("total_runs") or 0)


def innings_runs(data):
    return sorted(int(i.get("runs") or 0) for i in (data.get("batting_innings") or []))


# By-opposition reads this (migration 168, copied from the lifespan column for
# column); the shared harness does not build it, and the route needs it to exist.
ORG_MERGE_LOGS_DDL = """
    CREATE TABLE IF NOT EXISTS org_merge_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        source_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
        source_org_name TEXT NOT NULL,
        target_org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        performed_by_user_id UUID,
        performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        seasons_moved INTEGER NOT NULL DEFAULT 0,
        seasons_merged INTEGER NOT NULL DEFAULT 0,
        grades_moved INTEGER NOT NULL DEFAULT 0,
        grades_merged INTEGER NOT NULL DEFAULT 0,
        games_repointed INTEGER NOT NULL DEFAULT 0,
        players_moved INTEGER NOT NULL DEFAULT 0,
        players_merged INTEGER NOT NULL DEFAULT 0
    )"""


async def seed_extras(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex(ORG_MERGE_LOGS_DDL)

    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 1997/98', 1997)", i=SEASON2, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 1996/97', 1996)", i=OPP_SEASON, o=OPPONENT)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'A grade', :g, 'senior', ARRAY['senior'])",
             i=A_GRADE, s=base.SEASON, g=str(A_GRADE))
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'Men''s First', :g, 'senior', ARRAY['senior'])",
             i=FIRST_GRADE, s=SEASON2, g=str(FIRST_GRADE))
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, 'A grade', :g, 'senior', ARRAY['senior'])",
             i=OPP_A_GRADE, s=OPP_SEASON, g=str(OPP_A_GRADE))
    await ex("INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name) "
             "VALUES (:o, 'A grade', 'Men''s First')", o=ORG)

    async def game(day, grade, *, month=11, year=1996, owner=None, home=ORG, away=OPPONENT):
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, "
                 " match_format, status, innings_totals) "
                 "VALUES (:i, :g, :d, 'WIN', :h, :a, 'One Day', 'COMPLETED', "
                 " CAST(:t AS JSONB))",
                 i=gid, g=grade, d=date(year, month, day), h=home, a=away,
                 t='[{"innings_number": 1, "runs_scored": 150, "wickets": 5, "extras": 3}]')
        return gid

    async def bat(gid, pid, runs, pos=3):
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, sixes, "
                 " not_out, dismissal_type, did_not_bat, batting_position) "
                 "VALUES (:g, :p, :r, :b, 1, 0, false, 'c', false, :pos)",
                 g=gid, p=pid, r=runs, b=runs + 10, pos=pos)
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)",
                 g=gid, p=pid)

    a1 = await game(21, A_GRADE, owner=ORG)
    await bat(a1, base.SPINKS, 7)
    await ex("INSERT INTO bowling_spells (game_id, player_id, overs, maidens, runs, wickets) "
             "VALUES (:g, :p, 4.0, 0, 20, 2)", g=a1, p=base.SPINKS)
    a2 = await game(22, A_GRADE, owner=ORG)
    await bat(a2, base.SPINKS, 9)
    await bat(await game(5, FIRST_GRADE, month=12, year=1997, owner=ORG), base.SPINKS, A_MERGED)
    # The fixture the OTHER club synced first: its grade row, its season.
    await bat(await game(23, OPP_A_GRADE, owner=OPPONENT), base.SPINKS, A_SHARED)

    # A hand-typed game in A grade, and one with no grade at all.
    for day, grade, runs in ((3, A_GRADE, A_MANUAL), (4, None, NO_GRADE)):
        mid = uuid.uuid4()
        await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, "
                 " opposition, result, winning_team) "
                 "VALUES (:i, :o, :s, :g, :d, 'Rivals CC', 'WIN', 'Timing CC')",
                 i=mid, o=ORG, s=base.SEASON, g=grade, d=date(1996, 12, day + 10))
        await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, "
                 " batting_position, runs, not_out, did_not_bat) "
                 "VALUES (:m, :p, 1, 3, :r, false, false)", m=mid, p=base.SPINKS, r=runs)

    # MATE has senior games, so the club default leaves a junior game OUT for him
    # and does not widen. Picking the junior grade has to bring it back.
    gj = await game(24, base.JUNIOR, owner=ORG)
    await bat(gj, base.MATE, MATE_JUNIOR)
    await session.commit()


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await base.seed(session)

    base_all = await stats(SPINKS)
    base_runs = runs_of(base_all)
    base_matches = int((base_all["career_batting"] or {}).get("matches") or 0)
    base_innings = innings_runs(base_all)
    mate_base = runs_of(await stats(MATE))

    async with Session() as session:
        await seed_extras(session)

    print("\n-- no pick changes nothing about how the profile adds up --")
    every = await stats(SPINKS)
    check("no grade picked: every grade counts, A grade's runs included",
          runs_of(every) == base_runs + A_RUNS + NO_GRADE,
          f"{runs_of(every)} vs {base_runs + A_RUNS + NO_GRADE}")

    print("\n-- picking a grade narrows the career to that grade --")
    b = await stats(SPINKS, grades=["B grade"])
    check("B grade: only B grade's runs (no A grade, no grade-less game)",
          runs_of(b) == base_runs - 0 and runs_of(b) != runs_of(every),
          f"{runs_of(b)} vs B-only {base_runs}")
    check("B grade: matches are the matches in B grade",
          int((b["career_batting"] or {}).get("matches") or 0) == base_matches,
          f"{(b['career_batting'] or {}).get('matches')} vs {base_matches}")
    check("B grade: the innings list holds only B grade innings",
          innings_runs(b) == base_innings, f"{innings_runs(b)} vs {base_innings}")

    a = await stats(SPINKS, grades=["A grade"])
    check(f"A grade: its own, hand-typed, merged-in and shared-fixture runs ({A_RUNS})",
          runs_of(a) == A_RUNS, str(runs_of(a)))
    check("A grade: the hand-typed game with no grade is NOT in it",
          runs_of(a) == A_RUNS, str(runs_of(a)))
    check("A grade: wickets are the A grade spell's two",
          int(((a.get("career_bowling") or {}).get("total_wickets")) or 0) == 2,
          str((a.get("career_bowling") or {}).get("total_wickets")))

    print("\n-- the name is the one Manage Grades gives it --")
    async with Session() as session:
        await session.execute(text(
            "UPDATE grades SET display_name_override = 'Premier' WHERE id = :g"), {"g": A_GRADE})
        await session.execute(text(
            "UPDATE grades SET display_order = 0 WHERE id = :g"), {"g": A_GRADE})
        await session.execute(text(
            "UPDATE grades SET display_order = 1 WHERE id = :g"), {"g": base.SENIOR})
        await session.commit()
    async with Session() as session:
        offered = await orgs.get_org_grades(str(ORG), None, session, None)
    names = [g["name"] for g in offered]
    check("the picker offers the renamed grade, not A grade", "Premier" in names
          and "A grade" not in names, str(names))
    check("a merged name is not offered separately", "Men's First" not in names, str(names))
    order = {g["name"]: g.get("display_order") for g in offered}
    check("the picker carries the club's order (Premier 0, B grade 1)",
          order.get("Premier") == 0 and order.get("B grade") == 1, str(order))
    check("a grade the club has not placed carries no order (and the server's order is kept)",
          all(g.get("display_order") is None for g in offered if g["name"] == "Under 14s"),
          str(offered))

    prem = await stats(SPINKS, grades=["Premier"])
    check("picking the display name finds the same games as A grade",
          runs_of(prem) == A_RUNS, str(runs_of(prem)))
    canon = await stats(SPINKS, grades=["A grade"])
    check("the canonical name a saved link carries still works",
          runs_of(canon) == A_RUNS, str(runs_of(canon)))
    both = await stats(SPINKS, grades=["Premier", "B grade"])
    check("two grades add up",
          runs_of(both) == A_RUNS + base_runs, f"{runs_of(both)} vs {A_RUNS + base_runs}")
    nothing = await stats(SPINKS, grades=["Nonsense"])
    check("a grade the club does not have matches nothing, never everything",
          runs_of(nothing) == 0 and not nothing.get("batting_innings"),
          f"{runs_of(nothing)}")
    check("all-junk is an ACTIVE filter the page can say so about",
          (nothing.get("grade_scope") or {}).get("active") is True,
          str(nothing.get("grade_scope")))
    allpick = await stats(SPINKS, grades=["all"])
    check("'all' is no filter", runs_of(allpick) == runs_of(every), str(runs_of(allpick)))

    print("\n-- a picked grade beats the club's default grade-type exclusion --")
    mate_every = await stats(MATE)
    check("with no pick the default leaves MATE's junior game out",
          runs_of(mate_every) == mate_base, f"{runs_of(mate_every)} vs {mate_base}")
    mate_jr = await stats(MATE, grades=["Under 14s"])
    check("picking Under 14s shows it", runs_of(mate_jr) == MATE_JUNIOR, str(runs_of(mate_jr)))
    mate_sr = await stats(MATE, grades=["B grade"])
    check("and picking a senior grade is untouched by the junior game",
          runs_of(mate_sr) == mate_base, f"{runs_of(mate_sr)} vs {mate_base}")

    print("\n-- every panel on the profile answers to it --")
    async with Session() as s:
        by_grade = await call(pl.get_player_by_grade, s, player_id=SPINKS, grades=["Premier"])
        bowl_by_grade = await call(pl.get_player_bowling_by_grade, s, player_id=SPINKS,
                                   grades=["Premier"])
        seasons = await call(pl.get_player_seasons, s, player_id=SPINKS, grades=["Premier"])
        team = await call(pl.get_player_team_breakdown_endpoint, s, player_id=SPINKS,
                          grades=["Premier"])
        capt = await call(pl.get_player_captain_stats, s, player_id=SPINKS, grades=["Premier"])
        venue = await call(pl.get_player_by_venue_endpoint, s, player_id=SPINKS, grades=["Premier"])
        opp = await call(pl.get_player_by_opposition_endpoint, s, player_id=SPINKS,
                         grades=["Premier"])
        dism = await call(pl.get_player_dismissals, s, player_id=SPINKS, grades=["Premier"])
        part = await call(pl.get_player_partnerships_endpoint, s, player_id=SPINKS,
                          grades=["Premier"])
        tm = await call(pl.get_player_teammates, s, player_id=SPINKS, grades=["Premier"])
    check("batting by grade lists only the picked grade",
          {r["grade_name"] for r in by_grade} <= {"Premier", "A grade"} and bool(by_grade),
          str([r.get("grade_name") for r in by_grade]))
    check("bowling by grade lists only the picked grade",
          {r["grade_name"] for r in bowl_by_grade} <= {"Premier", "A grade"} and bool(bowl_by_grade),
          str([r.get("grade_name") for r in bowl_by_grade]))
    team_grades = {r["grade_name"] for r in team.get("rows", []) if r.get("grade_name")}
    check("matches by grade holds only the picked grade",
          bool(team_grades) and team_grades <= {"Premier", "A grade"}, str(team_grades))
    check("season by season sums to the picked grade's runs",
          sum(int(r.get("total_runs") or 0) for r in seasons) == A_RUNS,
          str([(r.get("season_name"), r.get("total_runs")) for r in seasons]))
    check("captain stats take the pick (Spinks captained B grade games only)",
          int((capt or {}).get("games_captained") or 0) == 0, str(capt))
    check("by-venue, by-opposition, dismissals, partnerships, teammates answer without error",
          all(x is not None for x in (venue, opp, dism, part, tm)))
    opp_games = sum(int(r.get("games") or 0) for r in (opp or []))
    opp_runs = sum(int(r.get("total_runs") or 0) for r in (opp or []))
    check("by-opposition: the 4 synced games plus the hand-typed one, and exactly A grade's runs",
          opp_games == 5 and opp_runs == A_RUNS, f"{opp_games} games, {opp_runs} runs")

    print("\n-- the Competition and Match Type halves still ride with a picked grade --")
    t20 = await stats(SPINKS, grades=["B grade"], formats="t20")
    check("a grade and a format together are a real intersection (no T20 games, so nothing)",
          runs_of(t20) == 0, str(runs_of(t20)))

    print("\n-- a hidden junior grade stays hidden whatever is picked --")
    from app.services import grade_scope
    try:
        async with Session() as s:
            sc = await grade_scope.resolve_scope(
                s, str(ORG), None, grades=["Under 14s"], hidden_grade_ids=[base.JUNIOR])
        hidden_kept = base.JUNIOR in sc.excluded_ids
    except TypeError as e:   # the control: the keyword does not exist yet
        hidden_kept = False
        print("   (", e, ")")
    check("picking a hidden grade still leaves it excluded", hidden_kept)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
