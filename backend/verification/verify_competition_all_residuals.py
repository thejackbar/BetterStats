"""A club's imported history stays in "All competitions", and out of any single one.

Reported by Kalamunda: their leading run scorer, whose career came in through
the historical stats upload, was on the Leaderboard when the page first drew
and gone a moment later. The page asks for the club's competition list, and
once it arrives "All" stops being "send nothing" and becomes the id of every
competition the club offers (`useGradeFilters`). The competition axis is an
inclusion with no tolerance for a row that has no grade, and a history-book
import has no grade, so the second request dropped every imported player. StatLab,
which was not sent the list, kept him.

Runs the SHIPPED `/leaderboard/batting` route body and the career reader against
a real Postgres over the real `v_effective_*` views, on the Kalamunda book
fixture (`verify_import_through_season`: three players typed from the printed
history book, plus one with online figures only), with two competitions, a
grade in each and one player who has a real scorecard in a grade.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_comp_all \\
      python -m verification.verify_competition_all_residuals

Run against the commit before the change, "All" drops the book players and the
checks that name them report; nothing crashes.
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
os.environ.setdefault("VERIFY_DATABASE_URL",
                      "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_comp_all")

import verify_import_through_season as v  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.routers import leaderboard as lb  # noqa: E402
from app.services import aggregations as agg  # noqa: E402
from app.services import grade_scope  # noqa: E402
from app.services.competition_ddl import STATEMENTS as COMP_DDL  # noqa: E402

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


MERCANTILE, SWAN = uuid.uuid4(), uuid.uuid4()
IN_MERC, IN_SWAN, NOWHERE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
UNGROUPED = uuid.uuid4()


async def seed_competitions() -> None:
    """Two competitions with a grade each, a scorecard player in each, and a
    third grade in no competition with a scorecard player of its own."""
    async with v.engine.begin() as conn:
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
    async with v.Session() as db:
        async def ex(sql, **kw):
            await db.execute(text(sql), kw)

        for cid, name in ((MERCANTILE, "Perth Mercantile"), (SWAN, "Perth Swan")):
            await ex("INSERT INTO club_competitions (id, organisation_id, name) VALUES (:i, :o, :n)",
                     i=cid, o=v.ORG, n=name)
        for pid, name in ((IN_MERC, "Merc Regular"), (IN_SWAN, "Swan Regular"), (NOWHERE, "Ungrouped Regular")):
            await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)", i=pid, o=v.ORG, n=name)
        for gname, comp, pid, runs in (("A Grade", MERCANTILE, IN_MERC, 50), ("B Grade", SWAN, IN_SWAN, 40),
                                       ("Social", None, NOWHERE, 30)):
            gid, game = uuid.uuid4(), uuid.uuid4()
            await ex("INSERT INTO grades (id, season_id, name, category, categories, competition_id) "
                     "VALUES (:i, :s, :n, 'senior', ARRAY['senior'], :c)",
                     i=gid, s=v.SEASON[2012], n=gname, c=comp)
            await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format) "
                     "VALUES (:g, :gr, :d, 'Home', 'WIN', 'One Day')", g=game, gr=gid, d=date(2012, 11, 1))
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=game, p=pid)
            await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, innings_number, "
                     "batting_position) VALUES (:g, :p, :r, 40, false, 1, 3)", g=game, p=pid, r=runs)
        await db.commit()


async def board(**kw) -> list:
    args = dict(org_id=str(v.ORG), season_id=None, grade_id=None, grade_name=None, sort_by="total_runs",
                limit=50, min_runs=0, min_rate_innings=None, finals_only=None, captain_only=None,
                gender=None, overseas=None, categories=None, formats=None, competitions=None, viewer=None)
    args.update(kw)
    async with v.Session() as db:
        return await lb.batting_leaderboard(db=db, **args)


def runs(rows, pid) -> int | None:
    r = next((x for x in rows if str(x["player_id"]) == str(pid)), None)
    return None if r is None else int(r["total_runs"])


async def main() -> int:
    await v.build_schema()
    await v.seed()
    await seed_competitions()
    await v.run_import("2004/05", "book")

    # What the page sends for "All" once the club's list has loaded.
    async with v.Session() as db:
        from app.services.grade_scope import org_available_competitions
        offered = [str(c["id"]) for c in await org_available_competitions(db, str(v.ORG))]
    check("the club offers two competitions (the page draws its row)", len(offered) == 2, str(offered))
    all_ids = ",".join(offered)

    print("\n-- the page's first request: no competition list yet")
    first = await board()
    check("Mark (book + online): 1839 runs", runs(first, v.M) == 1839, str(runs(first, v.M)))
    check("Tim (book + online): 1187 runs", runs(first, v.T) == 1187, str(runs(first, v.T)))

    print("\n-- the page's second request: 'All' is every competition id")
    scope = None
    async with v.Session() as db:
        scope = await grade_scope.resolve_scope(db, str(v.ORG), None, competitions=all_ids)
    check("the scope knows it is the whole set", getattr(scope, "competitions_all", None) is True,
          str(getattr(scope, "competitions_all", "no such attribute")))
    second = await board(competitions=all_ids)
    check("Mark keeps his 1839 runs (this is the reported disappearance)", runs(second, v.M) == 1839,
          str(runs(second, v.M)))
    check("Tim keeps his 1187", runs(second, v.T) == 1187, str(runs(second, v.T)))
    check("Simon (book only, nothing online) keeps his 74", runs(second, v.S) == 74, str(runs(second, v.S)))
    check("a player with a scorecard in each competition is there", runs(second, IN_MERC) == 50
          and runs(second, IN_SWAN) == 40, str([(r["name"], r["total_runs"]) for r in second]))
    check("a grade in no competition stays out of All, as designed (30 runs not counted)",
          runs(second, NOWHERE) is None, str(runs(second, NOWHERE)))
    check("a player with only CA season totals (no scorecards, no grade) is in All with his 120",
          runs(second, v.BYSTANDER) == 120, str(runs(second, v.BYSTANDER)))

    print("\n-- picking ONE competition still leaves out what cannot belong to it")
    for label, comp, present, absent in (("Perth Mercantile", MERCANTILE, IN_MERC, IN_SWAN),
                                         ("Perth Swan", SWAN, IN_SWAN, IN_MERC)):
        rows = await board(competitions=str(comp))
        check(f"{label}: its own scorecard player is on the board", runs(rows, present) is not None,
              str([r["name"] for r in rows]))
        check(f"{label}: the other competition's player is not", runs(rows, absent) is None)
        check(f"{label}: the history book and CA season totals are not counted towards it"
              f" (Mark, Tim, Simon, Pat absent)",
              all(runs(rows, p) is None for p in (v.M, v.T, v.S, v.BYSTANDER)),
              str([(r["name"], r["total_runs"]) for r in rows]))

    print("\n-- the profile reads the same rule")
    async with v.Session() as db:
        sc_all = await grade_scope.resolve_scope(db, str(v.ORG), None, competitions=all_ids)
        sc_one = await grade_scope.resolve_scope(db, str(v.ORG), None, competitions=str(MERCANTILE))
        mark_all = await agg.get_career_batting(db, str(v.M), scope=sc_all) or {}
        mark_one = await agg.get_career_batting(db, str(v.M), scope=sc_one) or {}
    check("Mark's career under All reads the book's added 758 runs on top of what is held",
          int(mark_all.get("total_runs") or 0) >= 758, str(mark_all.get("total_runs")))
    check("and under one competition it does not", int(mark_one.get("total_runs") or 0) == 0,
          str(mark_one.get("total_runs")))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
