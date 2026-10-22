"""A partnership on the Records page opens the match it was made in. Real Postgres.

Asked for: on the partnerships leaderboard a row should take you to the scorecard. The records
route sent no match id with a stand, so there was nothing for a row to open.

This drives the SHIPPED `routers/records.get_records` route body and the shipped `get_scorecard`
over a real Postgres:

  * every board that lists a stand carries the id of the game it was made in: the top 25, each
    wicket's top 10, and the best-per-grade table;
  * the id is the right one (the 150 is in game 1, the 80 in game 2), not merely present;
  * a hand-typed record (it names no match) carries None, and when a typed record and a real stand
    are the same figure the real one, with its match, is the row that stays;
  * the id opens: the shipped scorecard route answers for it.

Run:  DATABASE_URL=postgresql+asyncpg://root@/reclink?host=/var/run/postgresql \
      python verification/verify_records_partnership_game_link.py
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

import verify_club_records as base   # its engine, schema and views; main() is guarded
from app.routers.games import get_scorecard
from app.routers.records import get_records
from app.services import grassroots_scores_client as gr

Session, engine = base.Session, base.engine
OURS = base.OURS
check = base.check

S, G = uuid.uuid4(), uuid.uuid4()
GAME1, GAME2 = uuid.uuid4(), uuid.uuid4()
PIDS = {k: uuid.uuid4() for k in "ABCD"}


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        await ex("INSERT INTO organisations (id, name, is_active, slug) VALUES (:i, 'Our Club', true, 'our-club')", i=OURS)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2017/18', 2017)", i=S, o=OURS)
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, 'Grade D', 'senior')", i=G, s=S)
        for k in "ABCD":
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id) VALUES (:i, :o, :n, :g)",
                     i=PIDS[k], o=OURS, n=f"Player {k}", g=str(uuid.uuid4()))
        for gid, d in ((GAME1, date(2017, 12, 16)), (GAME2, date(2017, 12, 9))):
            await ex(
                "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
                " opp_club_name, result, home_org_id, away_org_id, venue, match_format, is_final) "
                "VALUES (:i, :g, :d, 'Our Club', 'Opp', 'Our Club', 'Opp', 'Opp', 'WIN', :ho, NULL, 'Oval', "
                " 'One Day', false)", i=gid, g=G, d=d, ho=OURS)
        for gid, w, runs, a, b in ((GAME1, 1, 150, "A", "B"), (GAME1, 2, 100, "B", "C"), (GAME2, 1, 80, "C", "D")):
            await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, "
                     " batter1_runs, batter2_runs, is_club_innings) VALUES (:g, 1, :w, :a, :b, :r, 90, 90, true)",
                     g=gid, w=w, a=PIDS[a], b=PIDS[b], r=runs)
        # Hand-typed records: one nobody played (no match), and one that is the SAME stand as the real 150.
        await ex("INSERT INTO manual_partnership_records (org_id, batter1_name, batter2_name, grade_name, season_year, "
                 " wicket_number, runs) VALUES (:o, 'Old Timer', 'Other Timer', 'Grade D', 2017, 1, 300)", o=OURS)
        await ex("INSERT INTO manual_partnership_records (org_id, batter1_id, batter1_name, batter2_id, batter2_name, "
                 " grade_name, season_year, wicket_number, runs) VALUES (:o, :a, 'Player A', :b, 'Player B', "
                 " 'Grade D', 2017, 1, 150)", o=OURS, a=PIDS["A"], b=PIDS["B"])
        await s.commit()


async def records() -> dict:
    async with Session() as s:
        p = await get_records(
            str(OURS), season_id=None, grade_id=None, grade_name=None, finals_only=False,
            captain_only=False, gender=None, categories="all", formats=None, competitions=None,
            debug_timing=False, db=s, viewer=None)
    return p["partnerships"]


async def main() -> None:
    await base.build_schema()
    async with engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, org_id UUID, keep_player_id UUID, removed_player_id UUID, undone_at TIMESTAMPTZ)"""))
    await seed()
    gr.get_match_scorecard = lambda *a, **k: _none()
    part = await records()

    def gid(row):
        return row.get("game_id", "<absent>")   # presence-safe, so the control REPORTS rather than crashes

    top = part["top_partnerships"]
    by_runs = {r["runs"]: r for r in top}
    print("Top 25")
    check("the top 25 lists the real stands and the hand-typed 300", {300, 150, 100, 80} <= set(by_runs), str(sorted(by_runs)))
    check("the 150 names game 1", gid(by_runs.get(150, {})) == str(GAME1), str(gid(by_runs.get(150, {}))))
    check("the 100 names game 1", gid(by_runs.get(100, {})) == str(GAME1), str(gid(by_runs.get(100, {}))))
    check("the 80 names game 2 (not game 1)", gid(by_runs.get(80, {})) == str(GAME2), str(gid(by_runs.get(80, {}))))
    check("a hand-typed record names no match", by_runs.get(300, {}).get("game_id", "<absent>") is None,
          str(by_runs.get(300)))
    check("the hand-typed copy of a real stand is dropped and the real one (with its match) stays",
          sum(1 for r in top if r["runs"] == 150) == 1 and gid(by_runs.get(150, {})) == str(GAME1))

    print("By wicket")
    w1 = part.get("wicket_1", [])
    w1_by = {r["runs"]: r for r in w1}
    check("1st wicket: 150 names game 1, 80 names game 2",
          gid(w1_by.get(150, {})) == str(GAME1) and gid(w1_by.get(80, {})) == str(GAME2), str(w1_by))
    check("2nd wicket: 100 names game 1", gid((part.get("wicket_2") or [{}])[0]) == str(GAME1))

    print("By grade")
    grade_rows = {r["wicket_number"]: r for r in part["by_grade"].get("Grade D", [])}
    check("best 2nd wicket in the grade names game 1", gid(grade_rows.get(2, {})) == str(GAME1), str(grade_rows.get(2)))
    check("best 1st wicket in the grade is the hand-typed 300, which names no match",
          grade_rows.get(1, {}).get("runs") == 300 and grade_rows[1].get("game_id", "<absent>") is None, str(grade_rows.get(1)))

    print("The id opens")
    async with Session() as s:
        sc = await get_scorecard(game_id=str(GAME1), db=s, viewer=None, org_param=None)
    check("the shipped scorecard route answers for the id a row carries",
          sc.get("id") == str(GAME1), str(sc.get("id")))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


async def _none():
    return None


if __name__ == "__main__":
    asyncio.run(main())
