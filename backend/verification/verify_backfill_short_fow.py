"""`backfill_partnerships --short` completes OLD games stored with a short fall of wickets. Real Postgres.

The sync's own fix (`participant_relink.complete_innings_detail`) only reaches games from the last 14
days, and the script's default walk never offers a game that already holds a stand of the club's own
players (wicket 1 of 4 gives one). `--short` walks those older games through the script's machinery:
`run()` and `undo_club()` themselves, with the Cricket Australia fetch stubbed.

  * candidates: finished synced games short by `innings_totals`, or (no totals) short by the club's own
    batting rows; a full game, a typed game and another club's run are not offered;
  * a dry run writes nothing; `--apply` adds the wickets and stands and logs exactly the inserted ids;
  * it only INSERTS: a held stand keeps its (stale) figures, a stand of another pair is untouched;
  * a card not finished adds nothing; a second run adds nothing;
  * a limited walk resumed with its token asks every candidate once and none twice;
  * `--undo` removes exactly what the run wrote and the games are short again;
  * the default (no `--short`) walk is unchanged: it offers none of these games.

Run:  DATABASE_URL=postgresql+asyncpg://root@/backfillshort?host=/var/run/postgresql \
      python verification/verify_backfill_short_fow.py
Control: the commit before this change has no `short` option, so every `--short` check fails.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_short_fow_completed_card as sf   # its cards, players and seed; main() is guarded
from app.scripts import backfill_partnerships as bf

h = sf.h
check = h.check
Session = h.Session
TODAY, ORG, OPP_ORG, PID = sf.TODAY, sf.ORG, sf.OPP_ORG, sf.PID

OLD400, NOTOTALS, FULL = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def extra_games() -> None:
    """Older games on top of `sf.seed`: short by totals at 400 days, short by batting rows only (no
    totals) at 300, and a complete one at 200."""
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        totals = json.dumps([{"innings_number": 1, "runs_scored": 301, "wickets": 4, "extras": 9},
                             {"innings_number": 2, "runs_scored": 208, "wickets": 7, "extras": 5}])
        for gid, days, tot in ((OLD400, 400, totals), (NOTOTALS, 300, None), (FULL, 200, totals)):
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, status, venue, "
                     " match_format, innings_totals, winning_team) VALUES (:i, :g, :d, 'WIN', :o, NULL, 'COMPLETED', "
                     " 'Oval', 'One Day', CAST(:t AS JSONB), 'ACC 10th')",
                     i=gid, g=h.GRADE, d=TODAY - timedelta(days=days), o=ORG, t=tot)
            for order, (name, pid) in enumerate(sf.PID.items(), 1):
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=pid)
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                         " not_out, dismissal_type, caught_behind, batting_position, did_not_bat) "
                         "VALUES (:g, :p, 1, :r, 60, 0, 0, :no, :dt, false, :o, false)",
                         g=gid, p=pid, r=sf.BAT[name], no=name not in sf.OUT,
                         dt=None if name not in sf.OUT else "bowled", o=order)
            if gid == FULL:
                for w, sc, n in sf.FINAL_FOW:
                    await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, "
                             " player_id, batter_name) VALUES (:g, 1, :w, :s, :p, :n)", g=gid, w=w, s=sc, p=PID[n], n=n)
                for w in range(1, 8):
                    await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, "
                             " batter_name) VALUES (:g, 2, :w, :s, :n)", g=gid, w=w, s=5 * w, n=f"T{w - 1}")
            else:
                await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id, "
                         " batter_name) VALUES (:g, 1, 1, 4, :p, 'Abbas')", g=gid, p=PID["Abbas"])
                await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, "
                         " batter_name) VALUES (:g, 2, 1, 5, 'T0')", g=gid)
            await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, "
                     " batter1_runs, batter2_runs, is_club_innings) VALUES (:g, 1, 1, :a, :d, 4, 4, 4, true)",
                     g=gid, a=PID["Abbas"], d=PID["Daddow"])
        await s.commit()


async def snapshot(ids) -> dict:
    """Every wicket and stand row of the games, as comparable tuples."""
    out = {}
    async with Session() as s:
        for g in ids:
            out[g] = (
                [tuple(r) for r in (await s.execute(text(
                    "SELECT id, innings_number, wicket_number, score_at_fall FROM fall_of_wickets "
                    "WHERE game_id=:g ORDER BY id"), {"g": g})).all()],
                [tuple(r) for r in (await s.execute(text(
                    "SELECT id, innings_number, wicket_number, runs, batter1_runs, batter2_runs FROM partnerships "
                    "WHERE game_id=:g ORDER BY id"), {"g": g})).all()])
    return out


async def one(sql, **kw):
    async with Session() as s:
        return (await s.execute(text(sql), kw)).scalar()


async def main() -> None:
    await h.build_schema()
    from app.services.audit_ddl import STATEMENTS as AUDIT_DDL
    from app.services.fow_override_ddl import STATEMENTS as FOW_OVERRIDE_DDL
    from app.services.partnership_backfill_ddl import STATEMENTS as PBF_LOG_DDL   # migration 359
    async with h.engine.begin() as conn:
        for stmt in AUDIT_DDL + FOW_OVERRIDE_DDL + PBF_LOG_DDL:
            await conn.execute(text(stmt))
    await sf.seed()
    await extra_games()
    bf.async_session_maker = Session

    games = {"short": sf.SHORT, "typed": sf.TYPED, "old": sf.OLD, "notdone": sf.NOTDONE, "otherpair": sf.OTHERPAIR,
             "old400": OLD400, "nototals": NOTOTALS, "full": FULL}
    ages = {sf.SHORT: 5, sf.TYPED: 5, sf.OLD: 40, sf.NOTDONE: 5, sf.OTHERPAIR: 5, OLD400: 400, NOTOTALS: 300, FULL: 200}
    cards = {str(g): sf.card(g, ages[g], status="LIVE" if g == sf.NOTDONE else "COMPLETED") for g in ages}
    asked: list[str] = []

    async def fetch(match_id: str):
        asked.append(match_id)
        return cards.get(match_id)

    candidates = {sf.SHORT, sf.NOTDONE, sf.OTHERPAIR, sf.OLD, OLD400, NOTOTALS}
    writes = candidates - {sf.NOTDONE}
    all_ids = list(ages)
    start = await snapshot(all_ids)

    if "short" not in inspect.signature(bf.run).parameters:
        check("the script has a --short mode (absent on the commit before this change)", False, "run() has no `short`")
        print(f"\n{h.PASS} passed, {h.FAIL} failed")
        await h.engine.dispose()
        sys.exit(1)

    print("\n-- THE DEFAULT WALK IS UNCHANGED --")
    t = await bf.run("acc", fetch=fetch, pause=0)
    check("without --short none of these games is offered (each holds a stand of the club's own)",
          t["asked"] == 0 and not asked, str(asked))

    print("\n-- DRY RUN --")
    asked.clear()
    t = await bf.run("acc", fetch=fetch, pause=0, short=True)
    check("the six short finished games are asked for, and the full and the typed ones are not",
          {uuid.UUID(a) for a in asked} == candidates and len(asked) == 6, str(asked))
    check("would add 14 stands and 45 wickets, across 5 games with something to add",
          t["stands_added"] == 14 and t["fow_added"] == 45 and t["refused"] == 1, str(t))
    check("a dry run writes nothing", await snapshot(all_ids) == start)
    check("and no log or audit row", await one("SELECT count(*) FROM partnership_backfill_log") == 0
          and await one("SELECT count(*) FROM audit_events WHERE action='backfill_partnerships'") == 0)

    print("\n-- A LIMITED WALK, RESUMED --")
    asked.clear()
    seen: list[str] = []
    t = await bf.run("acc", fetch=fetch, pause=0, short=True, limit=2)
    seen += asked
    hops = 0
    while t["resume"] and hops < 10:
        asked.clear()
        t = await bf.run("acc", fetch=fetch, pause=0, short=True, limit=2, resume=t["resume"])
        seen += asked
        hops += 1
    check("every candidate is asked once across the resumed walk, none twice",
          len(seen) == 6 and {uuid.UUID(a) for a in seen} == candidates, str(seen))

    print("\n-- APPLY --")
    asked.clear()
    t = await bf.run("acc", fetch=fetch, pause=0, short=True, apply=True)
    check("14 stands and 45 wickets added", t["stands_added"] == 14 and t["fow_added"] == 45, str(t))
    check("the 400 day old game now holds all four wickets and the 208 stand",
          [r[3] for r in (await snapshot([OLD400]))[OLD400][0] if r[1] == 1] == [4, 212, 251, 280]
          and (2, 208) in [(r[2], r[3]) for r in (await snapshot([OLD400]))[OLD400][1]])
    check("so does the game with no totals (found by the club's own batting rows)",
          len([r for r in (await snapshot([NOTOTALS]))[NOTOTALS][0] if r[1] == 1]) == 4)
    after = await snapshot(all_ids)
    check("the held stand keeps its row AND its figures (the script only inserts)",
          all(row in after[g][1] for g in writes for row in start[g][1]))
    other = [(r[2], r[3], r[4], r[5]) for r in (await snapshot([sf.OTHERPAIR]))[sf.OTHERPAIR][1]]
    check("a stand held for another pair is untouched (wicket 2 is still 17, not the card's 208)",
          (2, 17, 1, 2) in other and (2, 208, 120, 88) not in other, str(other))
    check("the unfinished card, the typed game and the full game are unchanged",
          all(after[g] == start[g] for g in (sf.NOTDONE, sf.TYPED, FULL)))
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT game_id, partnership_ids, fow_ids FROM partnership_backfill_log WHERE undone_at IS NULL"))).all()
    logged = {r[0]: (set(r[1]), set(r[2])) for r in rows}
    exact = all(logged.get(g) == ({r[0] for r in after[g][1]} - {r[0] for r in start[g][1]},
                                  {r[0] for r in after[g][0]} - {r[0] for r in start[g][0]}) for g in writes)
    check("the log holds exactly the inserted ids, one row per game written to",
          exact and set(logged) == writes, str(sorted(map(str, logged))))
    check("the club's audit trail has a short-fall-of-wickets entry",
          await one("SELECT count(*) FROM audit_events WHERE action='backfill_partnerships' "
                    "AND summary LIKE '%short fall of wickets%'") == 1)

    print("\n-- A SECOND RUN ADDS NOTHING --")
    before = await snapshot(all_ids)
    asked.clear()
    t = await bf.run("acc", fetch=fetch, pause=0, short=True, apply=True)
    check("only the unfinished game is still a candidate, and nothing is added",
          {uuid.UUID(a) for a in asked} == {sf.NOTDONE} and t["stands_added"] == 0 and t["fow_added"] == 0, str(asked))
    check("no row changed or doubled", await snapshot(all_ids) == before)

    print("\n-- ANOTHER CLUB --")
    asked.clear()
    t = await bf.run("cvpcc", fetch=fetch, pause=0, short=True, apply=True)
    check("the opposing club has no game of its own to complete", t["asked"] == 0 and not asked, str(asked))

    print("\n-- UNDO --")
    d = await bf.undo_club("acc", apply=False)
    check("a dry undo reports 14 stands and 45 wickets and deletes nothing",
          d["stands"] == 14 and d["fow"] == 45 and await snapshot(all_ids) == before, str(d))
    d = await bf.undo_club("acc", apply=True)
    check("undo removes exactly what the run wrote", d["stands"] == 14 and d["fow"] == 45 and d["gone"] == 0, str(d))
    check("every game is back as it started", await snapshot(all_ids) == start)
    asked.clear()
    await bf.run("acc", fetch=fetch, pause=0, short=True)
    check("and the short games are candidates again", {uuid.UUID(a) for a in asked} == candidates, str(asked))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
