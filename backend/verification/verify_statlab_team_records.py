"""StatLab team records: chases, defended totals, and both sides' runs in a match.

Hand-built games with known answers, run through the SHIPPED `statlab.run_query`
over the real `v_effective_*` views. The rule under test: a chase is the LAST
innings of a match that its batting side won, and the target is the other side's
runs, less the chasing side's own earlier runs, plus one.

  G1  one-day, we bat second and win:           Them 250, Us 251/4        -> our chase, target 251
  G2  one-day, they bat second and win:         Us 180, Them 181/5        -> THEIR chase, target 181
  G3  one-day, we defend:                       Us 150, Them 120          -> our defended total 150
  G4  two-day, they win in the 4th innings:     Us 200, Them 250, Us 150, Them 102/2
                                                -> THEIR chase, target 101 (350 - 250 + 1)
  G5  one-day, we fall short:                   Them 220, Us 200          -> no chase either side, their 220 defended
  G6  two-day draw:                             four innings, nobody wins -> no chase, nothing defended

Control: on the previous commit `target` is not a metric, so every read below
reports a failure instead of crashing (answers are read through `.get`).

Run:  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
      python verification/verify_statlab_team_records.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_records_partnership_grade_names as base
from app.services import statlab

check = base.check
ORG = base.ORG
P1, P2 = uuid.uuid4(), uuid.uuid4()


async def seed(session) -> dict:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Us CC', 'us', true)", i=ORG)
    season, grade = uuid.uuid4(), uuid.uuid4()
    await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s, :o, 'Season 2025', 2025)", s=season, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:g, :s, '1st Grade', 'g1', 'senior', ARRAY['senior'])", g=grade, s=season)
    for pid, nm in ((P1, "Bat, One"), (P2, "Bowl, Two")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:p, :o, :n, :gid, 'active')", p=pid, o=ORG, n=nm, gid=str(pid))

    games: dict[str, uuid.UUID] = {}

    async def game(label, day, winner, fmt, innings):
        """innings: [(number, 'us'|'them', runs, wickets, extras)]"""
        gid = uuid.uuid4()
        games[label] = gid
        totals = [{"innings_number": n, "runs_scored": r, "wickets": w, "extras": e}
                  for n, _side, r, w, e in innings]
        await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, away_org_id, "
                 "winning_team, result, match_format, status, innings_totals) "
                 "VALUES (:g, :gr, :d, 'Us', 'Them', :o, NULL, :w, :res, :f, 'COMPLETED', CAST(:t AS jsonb))",
                 g=gid, gr=grade, d=date(2025, 10, day), o=ORG, w=winner,
                 res={"Us": "WIN", "Them": "LOSS"}.get(winner, "DRAW"), f=fmt, t=json.dumps(totals))
        for pid in (P1, P2):
            await ex("INSERT INTO game_appearances (game_id, player_id, team_name, is_reserve) "
                     "VALUES (:g, :p, 'Us', false)", g=gid, p=pid)
        for n, side, r, w, e in innings:
            if side == "us":
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, "
                         "dismissal_type, not_out, batting_position, did_not_bat) "
                         "VALUES (:g, :p, :n, :r, 100, 'caught', false, 1, false)",
                         g=gid, p=P1, n=n, r=max(r - e, 0))
            else:
                await ex("INSERT INTO bowling_spells (game_id, player_id, innings_number, overs, maidens, runs, wickets) "
                         "VALUES (:g, :p, :n, 10, 0, :r, :w)", g=gid, p=P2, n=n, r=r, w=w)

    await game("G1", 1, "Us", "One Day", [(1, "them", 250, 8, 5), (2, "us", 251, 4, 6)])
    await game("G2", 2, "Them", "One Day", [(1, "us", 180, 10, 4), (2, "them", 181, 5, 3)])
    await game("G3", 3, "Us", "One Day", [(1, "us", 150, 7, 4), (2, "them", 120, 10, 2)])
    await game("G4", 4, "Them", "Two Day",
               [(1, "us", 200, 10, 4), (2, "them", 250, 10, 5), (3, "us", 150, 10, 3), (4, "them", 102, 2, 2)])
    await game("G5", 5, "Them", "One Day", [(1, "them", 220, 6, 4), (2, "us", 200, 10, 3)])
    await game("G6", 6, None, "Two Day",
               [(1, "us", 220, 10, 4), (2, "them", 180, 10, 4), (3, "us", 90, 3, 2), (4, "them", 60, 2, 1)])
    await session.commit()
    await session.execute(text("ANALYZE"))
    await session.commit()
    return games


async def run(session, target, sort_by, filters, context=None, sort_dir="desc"):
    return (await statlab.run_query(
        session, org_id=str(ORG), target=target, sort_by=sort_by, sort_dir=sort_dir, limit=100,
        metric_filters=filters, filter_tree=None, context=dict(context or {})))["rows"]


async def safe(session, *a, **kw):
    """The rows, or [] with the reason printed, so a control run reports instead of crashing."""
    try:
        return await run(session, *a, **kw)
    except Exception as e:  # noqa: BLE001 - the control run on the old code lands here
        await session.rollback()
        print(f"      (query failed: {str(e)[:90]})")
        return []


def innings_of(rows, gid):
    return sorted(((r.get("innings_number"), r.get("runs"), r.get("target")) for r in rows
                   if str(r.get("game_id")) == str(gid)), key=lambda t: (t[0] or 0))


async def main() -> None:
    await base.build_schema()
    async with base.Session() as session:
        games = await seed(session)

    async with base.Session() as session:
        print("\n-- every innings carries the chase fields --")
        allrows = await safe(session, "team_innings_list", "runs", [])
        by = {k: [r for r in allrows if str(r.get("game_id")) == str(v)] for k, v in games.items()}
        check("each game has one row per innings", [len(by[k]) for k in ("G1", "G2", "G3", "G4", "G5", "G6")]
              == [2, 2, 2, 4, 2, 4], str({k: len(v) for k, v in by.items()}))

        print("\n-- our successful chases --")
        ours = await safe(session, "team_innings_list", "target", ["is_ours:eq:1", "is_chase:eq:1"])
        check("exactly one chase of ours: G1", [str(r.get("game_id")) for r in ours] == [str(games["G1"])],
              str([(r.get("runs"), r.get("target")) for r in ours]))
        check("G1's target is the other side's 250 plus one", [r.get("target") for r in ours] == [251])
        check("and it was 251 for 4", [(r.get("runs"), r.get("wickets")) for r in ours] == [(251, 4)])
        check("the row names who batted and who they played",
              [(r.get("batting_team"), r.get("against")) for r in ours] == [("Us", "Them")],
              str([(r.get("batting_team"), r.get("against")) for r in ours]))

        print("\n-- chases against us --")
        theirs = await safe(session, "team_innings_list", "target", ["is_ours:eq:0", "is_chase:eq:1"])
        got = {(str(r.get("game_id")), r.get("target")) for r in theirs}
        check("G2 and the two-day G4 are the chases against us",
              got == {(str(games["G2"]), 181), (str(games["G4"]), 101)}, str(got))
        check("G4's target counts their own first innings: 200 + 150 - 250 + 1 = 101",
              (str(games["G4"]), 101) in got)
        check("biggest first", [r.get("target") for r in theirs] == [181, 101])
        check("their rows read as against us, not for us",
              all(r.get("batting_team") == "Them" and r.get("against") == "Us" for r in theirs))

        print("\n-- a chase that fell short, a draw, and the first innings are not chases --")
        every = await safe(session, "team_innings_list", "runs", ["is_chase:eq:1"])
        check("only three chases in the whole book", len(every) == 3, str(len(every)))
        g5 = innings_of(allrows, games["G5"])
        check("G5: we fell 20 short, the target is still worked out (221) but it is no chase",
              (2, 200, 221) in g5 and all(r.get("is_chase") == 0 for r in by["G5"]), str(g5))
        check("the drawn two-day game has no chase", all(r.get("is_chase") == 0 for r in by["G6"]))
        check("first innings have no target", all(r.get("target") is None
                                                  for r in allrows if r.get("innings_number") == 1))

        print("\n-- defended totals --")
        dfn = await safe(session, "team_innings_list", "runs", ["is_ours:eq:1", "is_defended:eq:1"], sort_dir="asc")
        check("we defended 150 in G3 and nothing else", [(str(r.get("game_id")), r.get("runs")) for r in dfn]
              == [(str(games["G3"]), 150)], str([(r.get("runs")) for r in dfn]))
        dfn_against = await safe(session, "team_innings_list", "runs", ["is_ours:eq:0", "is_defended:eq:1"],
                                 sort_dir="asc")
        check("they defended 220 against us in G5", [(str(r.get("game_id")), r.get("runs")) for r in dfn_against]
              == [(str(games["G5"]), 220)], str([(r.get("runs")) for r in dfn_against]))
        check("a two-day first innings is never 'defended'",
              all(r.get("is_defended") == 0 for r in by["G4"] + by["G6"]))

        print("\n-- both sides' runs in one match --")
        m = await safe(session, "match_list", "match_runs", [], sort_dir="desc")
        top = {str(r.get("game_id")): r.get("match_runs") for r in m}
        check("G4 is 200+150 for us and 250+102 for them: 702", top.get(str(games["G4"])) == 702, str(top))
        check("G1 is 251 + 250 = 501", top.get(str(games["G1"])) == 501)
        check("biggest first", [r.get("match_runs") for r in m] == sorted((r.get("match_runs") or 0 for r in m), reverse=True))

        print("\n-- the existing totals reports are unchanged --")
        hi = await safe(session, "team_innings_list", "runs", ["is_ours:eq:1"])
        check("highest innings total of ours is still 251", bool(hi) and hi[0].get("runs") == 251)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  FAILED:", f)
    await base.engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
