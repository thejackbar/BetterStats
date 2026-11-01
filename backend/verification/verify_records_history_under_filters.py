"""Records keeps a club's history and hand-typed figures under the default filters.

Reported by Kalamunda (1 Nov 2026), a week after the Leaderboard fix for the same
players: on Records, under Stats, their top run scorer and wicket takers are
missing, and the highest individual score and highest partnerships the club typed
in do not show.

Why. Kalamunda runs juniors and seniors, so the default grade lens (juniors out)
is ACTIVE for every viewer, and the page sends the whole competition list once it
loads. An active scope sends Records down its per-innings path, which has no
pass for the totals that exist only as totals: the club's history-book import,
a hand-typed season adjustment and the career lump. The Leaderboard reads those
back (`aggregations._residual_totals_cte`); Records said so in a comment and
never did.

Runs the SHIPPED `get_records` route body against a real Postgres over the real
`v_effective_*` views, on the Kalamunda history-book fixture plus a junior grade
(so the default lens is active), two competitions, a hand-typed season
adjustment carrying a high score, and a hand-typed partnership record.

    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/verify_records_kcc \\
      python -m verification.verify_records_history_under_filters

Run against the commit before the change, the history players are absent and the
typed high score is missing; nothing crashes.
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
                      "postgresql+asyncpg://postgres:postgres@localhost:5432/verify_records_kcc")

import verify_import_through_season as v  # noqa: E402
import verify_competition_all_residuals as c  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.routers import records as rec  # noqa: E402
from app.services import grade_scope  # noqa: E402

check = v.check


def pick(rows, pid):
    return next((r for r in rows if str(r.get("player_id")) == str(pid)), None)


async def seed_junior_and_typed() -> None:
    """A junior grade with one junior-only scorer (turns the default lens on), a
    hand-typed season adjustment with a high score, and a typed partnership."""
    async with v.Session() as db:
        async def ex(sql, **kw):
            await db.execute(text(sql), kw)

        gid, game = uuid.uuid4(), uuid.uuid4()
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, 'Junior Jim')",
                 i=JUNIOR, o=v.ORG)
        await ex("INSERT INTO grades (id, season_id, name, category, categories, competition_id) "
                 "VALUES (:i, :s, 'Under 13', 'junior', ARRAY['junior'], :c)",
                 i=gid, s=v.SEASON[2012], c=c.MERCANTILE)
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format) "
                 "VALUES (:g, :gr, :d, 'Home', 'WIN', 'One Day')", g=game, gr=gid, d=date(2012, 11, 8))
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=game, p=JUNIOR)
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, innings_number, "
                 "batting_position) VALUES (:g, :p, 12, 20, false, 1, 3)", g=game, p=JUNIOR)

        # "Highest individual scorer", typed under Manual Entries -> Adjustments.
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, 'Hal Typed')",
                 i=TYPED, o=v.ORG)
        await ex("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, "
                 "games_played, batting_innings, batting_runs, batting_high_score) "
                 "VALUES (:o, :p, :s, 5, 5, 300, 187)", o=v.ORG, p=TYPED, s=v.SEASON[2013])
        # "Highest partnership", typed under Admin -> Partnerships.
        await ex("INSERT INTO manual_partnership_records (org_id, batter1_id, batter1_name, batter2_id, "
                 "batter2_name, grade_name, season_year, wicket_number, runs) "
                 "VALUES (:o, :a, 'Mark Travcich', :b, 'Hal Typed', 'A Grade', 2013, 2, 241)",
                 o=v.ORG, a=v.M, b=TYPED)
        await db.commit()


JUNIOR, TYPED = uuid.uuid4(), uuid.uuid4()


async def records(**kw) -> dict:
    args = dict(org_id=str(v.ORG), season_id=None, grade_id=None, grade_name=None, finals_only=False,
                captain_only=False, gender=None, categories=None, formats=None, competitions=None,
                debug_timing=False, viewer=None)
    args.update(kw)
    async with v.Session() as db:
        return await rec.get_records(db=db, **args)


async def main() -> int:
    await v.build_schema()
    await v.seed()
    await c.seed_competitions()
    await v.run_import("2004/05", "book")
    await seed_junior_and_typed()

    from app.services import aggregations as agg
    from app.services import records_residuals as rr
    check("Records and the profile/Leaderboard read the same residual sources",
          tuple(rr.RESIDUAL_SOURCES) == tuple(agg._RESIDUAL_SOURCES),
          f"{rr.RESIDUAL_SOURCES} vs {agg._RESIDUAL_SOURCES}")
    async with v.Session() as db:
        scope = await grade_scope.resolve_scope(db, str(v.ORG), None)
        offered = [str(x["id"]) for x in await grade_scope.org_available_competitions(db, str(v.ORG))]
    check("the default lens is active for this club (a junior grade exists)",
          bool(scope is not None and scope.active))
    all_ids = ",".join(offered)

    for label, kw in (("the page's first request (no competition list yet)", {}),
                      ("the page's second request ('All' = every competition id)", {"competitions": all_ids})):
        print(f"\n-- {label}")
        data = await records(**kw)
        bat, bowl, part = data["batting"], data["bowling"], data["partnerships"]
        runs = {r["player_id"]: int(r["runs"]) for r in bat["top_career_runs"]}
        mark = runs.get(str(v.M))
        check("Mark (history book + online) is on the career runs board with 1839",
              mark == 1839, str(mark))
        check("Tim (history book + online) is there with 1187", runs.get(str(v.T)) == 1187, str(runs.get(str(v.T))))
        check("Simon (history book only) is there with 74", runs.get(str(v.S)) == 74, str(runs.get(str(v.S))))
        check("a plain scorecard player is still there too", runs.get(str(c.IN_MERC)) == 50,
              str(runs.get(str(c.IN_MERC))))
        check("the junior-only scorer is NOT on the senior board", str(JUNIOR) not in runs)
        wk = {r["player_id"]: int(r["wickets"]) for r in bowl["top_career_wickets"]}
        check("Tim's wickets (history book + online) are on the career wickets board",
              wk.get(str(v.T), 0) > 12, str(wk.get(str(v.T))))
        hs = [(r["name"], int(r["runs"])) for r in bat["top_high_scores"]]
        check("the hand-typed 187 is on Highest Individual Scores", ("Hal Typed", 187) in hs, str(hs[:6]))
        top = part["top_partnerships"]
        check("the hand-typed 241 partnership is on the board",
              any(int(r["runs"]) == 241 for r in top), str([(r["player1_name"], r["runs"]) for r in top]))

    print("\n-- no duplicates and the figures are the Leaderboard's")
    data = await records(competitions=all_ids)
    ids = [r["player_id"] for r in data["batting"]["top_career_runs"]]
    check("nobody is listed twice on the career runs board", len(ids) == len(set(ids)), str(ids))
    wk = {r["player_id"]: int(r["wickets"]) for r in data["bowling"]["top_career_wickets"]}
    check("Tim's wickets are his online 12 plus the book's (more than 12, and the same on the Leaderboard)",
          wk.get(str(v.T), 0) > 12, str(wk))
    from app.routers import leaderboard as lb
    async with v.Session() as db:
        lbw = await lb.bowling_leaderboard(
            db=db, org_id=str(v.ORG), season_id=None, grade_id=None, grade_name=None, sort_by="total_wickets",
            limit=50, min_overs=0, min_wickets=0, min_rate_spells=None, finals_only=None, captain_only=None, gender=None,
            overseas=None, categories=None, formats=None, competitions=all_ids, viewer=None) \

    lb_t = next((int(r.get("total_wickets") or r.get("wickets") or 0) for r in lbw
                 if str(r["player_id"]) == str(v.T)), None)
    check("Records and the Leaderboard agree on Tim's wickets", lb_t is not None and lb_t == wk.get(str(v.T)),
          f"leaderboard {lb_t} records {wk.get(str(v.T))}")

    print("\n-- no lens at all (every grade type): the typed high score is still listed once")
    data = await records(categories="all")
    hs = [(r["name"], int(r["runs"])) for r in data["batting"]["top_high_scores"]]
    check("the typed 187 is there", ("Hal Typed", 187) in hs, str(hs[:6]))
    check("and only once", hs.count(("Hal Typed", 187)) == 1, str(hs))

    print("\n-- one competition: totals that belong to no competition stay out, as on the Leaderboard")
    data = await records(competitions=str(c.MERCANTILE))
    runs = {r["player_id"]: int(r["runs"]) for r in data["batting"]["top_career_runs"]}
    check("the competition's own scorecard player is there", runs.get(str(c.IN_MERC)) == 50, str(runs))
    check("the history book is not counted towards one competition",
          all(str(x) not in runs for x in (v.M, v.T, v.S)), str(runs))
    hs = [(r["name"], int(r["runs"])) for r in data["batting"]["top_high_scores"]]
    check("nor is a high score typed against no grade", ("Hal Typed", 187) not in hs, str(hs))

    print(f"\n{v.PASS} passed, {v.FAIL} failed")
    for f in v.FAILURES:
        print("  FAILED:", f)
    return 1 if v.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
