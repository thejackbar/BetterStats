"""Captain and keeper stats must see hand-entered games too, against a real Postgres.

Reported by Shoalwater Bay (Oct 2026): the captains and wicket keepers added to their hand-entered and imported
matches show on the match, but Records > Captains > Batting (all seasons, and A grade) does not list them. Every
captain and keeper lens joined `game_appearances.is_captain`, a table only a synced game has rows in, so a
hand-entered game could never have a captain as far as any stat was concerned.

`v_game_roles` (migration 378) unions the synced flags with `manual_game_roles`; the Records captain boards,
the Leaderboard captain filter, a player's captain record and StatLab's captain / keeper filters join it.

Seeds a synced game and three hand-entered games and reads each lens through the shipped route bodies:

  G1  synced, A Grade, Anne captain, 50 runs
  M1  hand-entered, A Grade, Beth captain, 80 runs; Cath keeps
  M2  hand-entered, B Grade, Anne captain, 30 runs
  M3  hand-entered, A Grade, Beth captain, NO batting row (a captain who did not bat)

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/captain_verify?host=/tmp&port=5439 \\
  python verification/verify_captain_stats_manual.py

Control run: check out the previous commit and run it again. Every read is presence-safe, so it REPORTS what is
missing instead of crashing.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_board_games_match_profile as b            # its schema, club and helpers; main() is guarded
from app.routers.leaderboard import batting_leaderboard
from app.routers.players import get_player_captain_stats
from app.routers.records import get_records
from app.services import grade_scope, statlab

ORG, OPP = b.ORG, b.OPP
Session, check = b.Session, b.check
ANNE, BETH, CATH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
S_ID, G_A, G_B = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G1, M1, M2, M3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def load(name):
    try:
        return importlib.import_module(name)
    except Exception as e:  # noqa: BLE001 - reported, not raised
        print(f"  (absent: {name}: {e})")
        return None


async def build() -> None:
    await b.build_schema()
    # b.build_schema() builds the views, v_game_roles among them (verification/_view_ddl.py).
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, nm, slug in ((ORG, "Captain Club", "captain"), (OPP, "Opposition CC", "opp")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2000/01', 2000)", i=S_ID, o=ORG)
        for gid, nm in ((G_A, "A Grade"), (G_B, "B Grade")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])", i=gid, s=S_ID, n=nm, g=str(gid))
        for pid, nm in ((ANNE, "Alpha, Anne"), (BETH, "Bravo, Beth"), (CATH, "Charlie, Cath")):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))

        # G1: a synced game, Anne captain, 50 runs.
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, match_format, status) "
                 "VALUES (:i, :g, '2000-10-07', 'WIN', :o, :x, 'One Day', 'COMPLETED')", i=G1, g=G_A, o=ORG, x=OPP)
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, not_out, "
                 "dismissal_type, did_not_bat) VALUES (:g, :p, 1, 50, 60, 4, 0, false, 'caught', false)", g=G1, p=ANNE)
        await ex("INSERT INTO game_appearances (game_id, player_id, is_captain) VALUES (:g, :p, true)", g=G1, p=ANNE)

        async def manual(mid, grade, played, result):
            await ex("INSERT INTO manual_games (id, organisation_id, season_id, grade_id, played_at, opposition, result) "
                     "VALUES (:i, :o, :s, :g, :d, 'Rival', :r)", i=mid, o=ORG, s=S_ID, g=grade, d=played, r=result)

        async def bat(mid, pid, runs):
            await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, innings_number, runs, balls, "
                     "not_out, dismissal_type, did_not_bat) VALUES (:m, :p, 1, :r, 50, false, 'caught', false)",
                     m=mid, p=pid, r=runs)

        await manual(M1, G_A, date(2000, 10, 14), "WIN")
        await bat(M1, BETH, 80)
        await bat(M1, CATH, 5)
        await manual(M2, G_B, date(2000, 10, 21), "LOSS")
        await bat(M2, ANNE, 30)
        await manual(M3, G_A, date(2000, 10, 28), "WIN")
        await bat(M3, CATH, 9)                    # Beth captained but did not bat
        await s.commit()

        has_roles = (await s.execute(text("SELECT to_regclass('manual_game_roles') IS NOT NULL"))).scalar()
        if has_roles:
            for mid, pid, cap, keep in ((M1, BETH, True, False), (M1, CATH, False, True), (M2, ANNE, True, False),
                                        (M3, BETH, True, False)):
                await ex("INSERT INTO manual_game_roles (manual_game_id, player_id, is_captain, is_wicket_keeper) "
                         "VALUES (:m, :p, :c, :k)", m=mid, p=pid, c=cap, k=keep)
            await s.commit()


def on(rows, pid):
    return next((r for r in rows or [] if str(r.get("player_id")) == str(pid)), None)


async def records(**kw):
    args = dict(season_id=None, grade_id=None, grade_name=None, finals_only=False, captain_only=True,
                gender=None, categories=None, formats=None, competitions=None, debug_timing=False, viewer=None)
    args.update(kw)
    async with Session() as s:
        return await get_records(str(ORG), db=s, **args)


async def board(**kw):
    params = dict(org_id=str(ORG), season_id=None, grade_id=None, grade_name=None, limit=50, finals_only=None,
                  captain_only=True, gender=None, overseas=None, categories=None, formats=None, competitions=None,
                  sort_by="total_runs", min_runs=0, min_rate_innings=0)
    params.update(kw)
    async with Session() as s:
        return await batting_leaderboard(db=s, viewer=None, **params)


def runs(rows, pid):
    r = on(rows, pid)
    return None if r is None else r.get("total_runs", r.get("runs"))


async def main() -> None:
    await build()

    print("\n-- RECORDS > CAPTAINS > BATTING (all seasons) --")
    rec = await records()
    top = (rec.get("batting") or {}).get("top_career_runs")
    check("Anne's captain runs are her synced 50 and her hand-entered 30 together (80)", runs(top, ANNE) == 80, str(runs(top, ANNE)))
    check("Beth's are the hand-entered 80", runs(top, BETH) == 80, str(runs(top, BETH)))
    check("Cath never captained, so she is not on a captain board", on(top, CATH) is None)
    check("the same captain-only pick without the filter would list her (so the check can fail)",
          on(((await records(captain_only=False)).get("batting") or {}).get("top_career_runs"), CATH) is not None)

    print("\n-- ... AND IN A PICKED GRADE --")
    a_grade = ((await records(grade_name="A Grade")).get("batting") or {}).get("top_career_runs")
    check("A Grade: Anne 50 (G1 only; her B Grade 30 is not here)", runs(a_grade, ANNE) == 50, str(runs(a_grade, ANNE)))
    check("A Grade: Beth 80 (a hand-entered game)", runs(a_grade, BETH) == 80, str(runs(a_grade, BETH)))
    b_grade = ((await records(grade_name="B Grade")).get("batting") or {}).get("top_career_runs")
    check("B Grade: Anne 30 and nobody else", runs(b_grade, ANNE) == 30 and on(b_grade, BETH) is None, str(runs(b_grade, ANNE)))

    print("\n-- RECORDS > CAPTAINS > MATCHES AS CAPTAIN --")
    most = ((rec.get("team") or {}).get("most_matches"))
    check("Anne captained 2 matches (one synced, one hand-entered)", (on(most, ANNE) or {}).get("matches") == 2, str(on(most, ANNE)))
    check("Beth captained 2 (one of them a game she did not bat in)", (on(most, BETH) or {}).get("matches") == 2, str(on(most, BETH)))

    print("\n-- THE LEADERBOARD'S CAPTAIN FILTER --")
    lb = await board()
    check("batting board, captain only: Anne 80, Beth 80, no Cath",
          runs(lb, ANNE) == 80 and runs(lb, BETH) == 80 and on(lb, CATH) is None,
          f"{runs(lb, ANNE)} {runs(lb, BETH)} {on(lb, CATH) is not None}")

    print("\n-- A PLAYER'S CAPTAIN RECORD --")
    async with Session() as s:
        cap = await get_player_captain_stats(player_id=str(BETH), categories=None, formats=None, competitions=None,
                                             grades=None, db=s)
    summ = cap.get("summary") or cap
    games = summ.get("games_captained")
    check("Beth has captained 2 matches, both won", games == 2 and summ.get("wins") == 2, str(summ))
    bat = cap.get("batting_as_captain") or {}
    check("her runs as captain are the 80 in M1", (bat.get("runs") or 0) == 80, str(bat))
    notcap = cap.get("batting_not_captain") or {}
    check("and none of the hand-entered games she captained is counted as one she did not",
          (notcap.get("runs") or 0) == 0, str(notcap))
    async with Session() as s:
        cath = await get_player_captain_stats(player_id=str(CATH), categories=None, formats=None, competitions=None,
                                              grades=None, db=s)
    check("Cath's 5 and 9 are runs as a non-captain (she kept, never captained)",
          ((cath.get("batting_not_captain") or {}).get("runs") or 0) == 14
          and ((cath.get("summary") or {}).get("games_captained") or 0) == 0, str(cath.get("batting_not_captain")))

    print("\n-- STATLAB'S CAPTAIN-ONLY AND KEEPER-ONLY FILTERS --")
    async def statlab_rows(context):
        async with Session() as s:
            scope = await grade_scope.resolve_scope(s, str(ORG), None)
            ctx = {statlab._SCOPE_KEY: scope, **context}
            out = await statlab.run_query(
                s, org_id=str(ORG), target="player_career", sort_by="runs", sort_dir="desc", limit=100,
                page=1, metric_filters=[], filter_tree=None, context=ctx)
        return {r["player_id"]: r for r in out["rows"]}

    cap_rows = await statlab_rows({"captain_only": True})
    check("captain only: Anne 80 runs over 2 matches, Beth 80 over 2, Cath absent",
          (cap_rows.get(str(ANNE)) or {}).get("runs") == 80 and (cap_rows.get(str(BETH)) or {}).get("runs") == 80
          and str(CATH) not in cap_rows,
          str({k: (v.get("runs"), v.get("matches")) for k, v in cap_rows.items()}))
    keep_rows = await statlab_rows({"keeper_only": True})
    check("keeper only: Cath alone, with the 5 runs from the one hand-entered game she kept in",
          list(keep_rows) == [str(CATH)] and (keep_rows.get(str(CATH)) or {}).get("runs") == 5,
          str({k: (v.get("runs"), v.get("matches")) for k, v in keep_rows.items()}))

    print("\n-- THE VIEW ITSELF --")
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT game_id::text, player_id::text, is_captain, is_wicket_keeper FROM v_game_roles"))).all() \
            if (await s.execute(text("SELECT to_regclass('v_game_roles') IS NOT NULL"))).scalar() else None
    check("v_game_roles exists and holds the synced captain and the manual roles (G1 + M1 x2 + M2 + M3)",
          rows is not None and len(rows) == 5, str(None if rows is None else len(rows)))
    check("the keeper is there too", rows is not None and any(r[1] == str(CATH) and r[3] for r in rows))

    print(f"\n{b.PASS} passed, {b.FAIL} failed")
    await b.engine.dispose()
    sys.exit(1 if b.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
