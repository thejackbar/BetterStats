"""A game stored with a SHORT fall of wickets is completed from the finished card. Real Postgres.

Reported (Applecross 10th XI v CVPCC Fourth XI): Cricket Australia's card holds four wickets for
Applecross (1-4 Abbas, 2-212 Doloswala, 3-251 Daddow, 4-280 Caporn) and seven for CVPCC, so the second
wicket stand is 208. The match page said "1 of 4 wickets recorded" and "1 of 7", the records page had
only the 4-run opening stand. `attach_innings_detail` writes an innings only where the game has NONE,
so one stored row per innings closed it off for ever, and `recent_games_without_detail` only selects a
game with no fall of wickets at all.

Drives `sync_grassroots_game_level_data` itself (an incremental run, `since` = yesterday), with the
Cricket Australia client stubbed to return the match list and COMPLETED scorecards:

  * the game stored with wicket 1 of 4 (and 1 of 7) is read again and gets every wicket and every stand,
    the 208-run second-wicket stand among them, belonging to the club's innings;
  * the stand it already held keeps its row (same id) with the batters' final scores put right;
  * a second run adds nothing and does not read the game again;
  * a card that is NOT completed adds nothing (and could: the same card, called COMPLETED, does);
  * an innings the club typed its own fall of wickets for is left alone, and its game is not selected;
  * a game older than the fortnight is not read;
  * a stand already held for a different pair at a wicket is not restated.

Run:  DATABASE_URL=postgresql+asyncpg://root@/shortfow?host=/var/run/postgresql \
      python verification/verify_short_fow_completed_card.py
Control: the same command on the commit before this change fails the stand and wicket checks.
"""
from __future__ import annotations

import asyncio
import copy
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

import verify_reread_incomplete_game as h   # its engine, schema and match listing helpers; main() is guarded
from app.services import grassroots_scores_client as gr
from app.services import participant_relink as relink
from app.services.sync import sync_grassroots_game_level_data

check = h.check
Session = h.Session
TODAY, ORG, OPP_ORG = h.TODAY, h.ORG, h.OPP_ORG

OURS = ["Abbas", "Daddow", "Doloswala", "Caporn", "Keith", "Parkin"]
PID = {n: uuid.uuid4() for n in OURS}
SHORT, TYPED, OLD, NOTDONE, OTHERPAIR = (uuid.uuid4() for _ in range(5))
THEIRS = [str(uuid.uuid4()) for _ in range(8)]      # CVPCC's eight, none held by the club
BAT = {"Abbas": 4, "Daddow": 120, "Doloswala": 88, "Caporn": 30, "Keith": 20, "Parkin": 5}
OUT = {"Abbas": 1, "Daddow": 3, "Doloswala": 2, "Caporn": 4}      # wicket each fell as
FINAL_FOW = [(1, 4, "Abbas"), (2, 212, "Doloswala"), (3, 251, "Daddow"), (4, 280, "Caporn")]


def card(game_id, days_ago, status="COMPLETED", fow=FINAL_FOW):
    iso = (TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    bat1 = [{"participantId": str(PID[n]), "batOrder": i, "playerShortName": n,
             "dismissalTypeId": 2 if n in OUT else 1, "dismissalType": "Bowled" if n in OUT else "Not Out",
             "runsScored": BAT[n], "ballsFaced": 60} for i, n in enumerate(OURS, 1)]
    bat2 = [{"participantId": THEIRS[i], "batOrder": i + 1, "playerShortName": f"T{i}",
             "dismissalTypeId": 2 if i < 7 else 1, "dismissalType": "Bowled" if i < 7 else "Not Out",
             "runsScored": 10 + i, "ballsFaced": 20} for i in range(8)]
    return {
        "id": str(game_id), "status": status, "matchSchedule": [{"startDateTime": iso}], "venue": {"name": "Oval"},
        "grade": {"id": h.GRADE_GUID, "name": "7th Grade"},
        "teams": [
            {"id": ours, "displayName": "ACC 10th", "owningOrganisation": {"id": str(ORG)},
             "players": [{"participantId": str(p), "roles": []} for p in PID.values()]},
            {"id": theirs, "displayName": "CVPCC 4th", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": "ACC won",
                         "teams": [{"id": ours, "displayName": "ACC 10th", "isHome": True},
                                   {"id": theirs, "displayName": "CVPCC 4th", "isHome": False}]},
        "innings": [
            {"inningsOrder": 1, "battingTeamId": ours, "fielding": [], "bowling": [], "batting": bat1,
             "fallOfWickets": [{"order": w, "runs": sc, "participantId": str(PID[n]), "playerShortName": n}
                               for w, sc, n in fow]},
            {"inningsOrder": 2, "battingTeamId": theirs, "fielding": [], "bowling": [], "batting": bat2,
             "fallOfWickets": [{"order": w, "runs": 5 * w, "participantId": THEIRS[w - 1],
                                "playerShortName": f"T{w - 1}"} for w in range(1, 8)]},
        ],
    }


def listing_entry(game_id, days_ago):
    return h.match_entry(game_id, days_ago)


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((ORG, "Applecross", "acc"), (OPP_ORG, "CVPCC", "cvpcc")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)",
                     i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, :g)", i=h.SEASON, o=ORG, g=str(h.SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '7th Grade', :g, 'senior', ARRAY['senior'])", i=h.GRADE, s=h.SEASON, g=h.GRADE_GUID)
        for n, pid in PID.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=n, g=str(pid))
        totals = json.dumps([{"innings_number": 1, "runs_scored": 301, "wickets": 4, "extras": 9},
                             {"innings_number": 2, "runs_scored": 208, "wickets": 7, "extras": 5}])
        for gid, days in ((SHORT, 5), (TYPED, 5), (OLD, 40), (NOTDONE, 5), (OTHERPAIR, 5)):
            # A winning team is set so the any-age missing-winner rule (services/game_winner) does not read these.
            await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id, status, venue, "
                     " match_format, innings_totals, winning_team) VALUES (:i, :g, :d, 'WIN', :o, NULL, 'COMPLETED', "
                     " 'Oval', 'One Day', CAST(:t AS JSONB), 'ACC 10th')", i=gid, g=h.GRADE, d=TODAY - timedelta(days=days), o=ORG, t=totals)
            for order, (name, pid) in enumerate(PID.items(), 1):
                await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=pid)
                # The club's batting is stored, so `recent_games_without_detail` has no reason to read the
                # game: only the short fall of wickets can.
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, fours, sixes, "
                         " not_out, dismissal_type, caught_behind, batting_position, did_not_bat) "
                         "VALUES (:g, :p, 1, :r, 60, 0, 0, :no, :dt, false, :o, false)",
                         g=gid, p=pid, r=BAT[name], no=name not in OUT, dt=None if name not in OUT else "bowled", o=order)
            # What the first read left: wicket 1 of each innings, and the stand it settled.
            await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, player_id, "
                     " batter_name) VALUES (:g, 1, 1, 4, :p, 'Abbas')", g=gid, p=PID["Abbas"])
            await ex("INSERT INTO fall_of_wickets (game_id, innings_number, wicket_number, score_at_fall, batter_name) "
                     "VALUES (:g, 2, 1, 5, 'T0')", g=gid)
            # Stored while the second batter had made 4: the stale figure.
            await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, "
                     " batter1_runs, batter2_runs, is_club_innings) VALUES (:g, 1, 1, :a, :d, 4, 4, 4, true)",
                     g=gid, a=PID["Abbas"], d=PID["Daddow"])
        # TYPED: the club typed its own fall of wickets for innings 1.
        await ex("INSERT INTO fow_overrides (organisation_id, game_id, innings_number, wicket_number, score_at_fall, "
                 " participant_id, batter_name) VALUES (:o, :g, 1, 1, 4, :p, 'Abbas')", o=ORG, g=TYPED, p=str(PID["Abbas"]))
        # OTHERPAIR: wicket 2 already holds a stand for a different pair (a hand correction).
        await ex("INSERT INTO partnerships (game_id, innings_number, wicket_number, batter1_id, batter2_id, runs, "
                 " batter1_runs, batter2_runs, is_club_innings) VALUES (:g, 1, 2, :a, :c, 17, 1, 2, true)",
                 g=OTHERPAIR, a=PID["Keith"], c=PID["Parkin"])
        await s.commit()


async def q(sql, **kw):
    async with Session() as s:
        return (await s.execute(text(sql), kw)).all()


async def fow(game_id, inn):
    return [(r[0], r[1]) for r in await q(
        "SELECT wicket_number, score_at_fall FROM fall_of_wickets WHERE game_id=:g AND innings_number=:i "
        "ORDER BY wicket_number", g=game_id, i=inn)]


async def stands(game_id, inn=1):
    return [tuple(r) for r in await q(
        "SELECT wicket_number, runs, batter1_runs, batter2_runs FROM partnerships "
        "WHERE game_id=:g AND innings_number=:i ORDER BY wicket_number, id", g=game_id, i=inn)]


async def main() -> None:
    await h.build_schema()
    from app.services.fow_override_ddl import STATEMENTS as FOW_OVERRIDE_DDL   # the lifespan's own list
    async with h.engine.begin() as conn:
        for stmt in FOW_OVERRIDE_DDL:
            await conn.execute(text(stmt))
    await seed()

    cards = {str(SHORT): card(SHORT, 5), str(TYPED): card(TYPED, 5), str(OLD): card(OLD, 40),
             str(NOTDONE): card(NOTDONE, 5, status="LIVE"), str(OTHERPAIR): card(OTHERPAIR, 5)}
    games = (SHORT, TYPED, OLD, NOTDONE, OTHERPAIR)
    fetched: list[str] = []

    async def fake_matches(grade_guid, *a, **k):
        return [listing_entry(g, 40 if g == OLD else 5) for g in games]

    async def fake_card(match_id, *a, **k):
        fetched.append(str(match_id))
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    print("\n-- BEFORE: the reported shape --")
    check("innings 1 holds wicket 1 of 4", await fow(SHORT, 1) == [(1, 4)])
    check("innings 2 holds wicket 1 of 7", await fow(SHORT, 2) == [(1, 5)])
    check("only the 4-run opening stand is held", await stands(SHORT) == [(1, 4, 4, 4)])
    async with Session() as s:
        sel = await relink.recent_games_short_fow(s, ORG) if hasattr(relink, "recent_games_short_fow") else set()
    check("the short game is selected for a re-read (and the typed, old and shorter-than-card ones are not)",
          str(SHORT) in sel and str(TYPED) not in sel and str(OLD) not in sel, str(sorted(sel)))
    stand_id = (await q("SELECT id FROM partnerships WHERE game_id=:g", g=SHORT))[0][0]

    print("\n-- AN INCREMENTAL RUN, since = yesterday (the game is 5 days old, outside its window) --")
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=1))
    check("the run read the short game", str(SHORT) in fetched, str(fetched))
    check("innings 1 now holds all four wickets", await fow(SHORT, 1) == [(1, 4), (2, 212), (3, 251), (4, 280)],
          str(await fow(SHORT, 1)))
    check("innings 2 now holds all seven wickets", [w for w, _ in await fow(SHORT, 2)] == [1, 2, 3, 4, 5, 6, 7],
          str(await fow(SHORT, 2)))
    got = await stands(SHORT)
    check("the second wicket stand is 208 (Daddow 120, Doloswala 88)", (2, 208, 120, 88) in got, str(got))
    check("and the stands are 4, 208, 39, 29 in wicket order", [g[1] for g in got] == [4, 208, 39, 29], str(got))
    check("the opening stand kept its row and has the batters' final scores",
          (await q("SELECT id FROM partnerships WHERE game_id=:g AND wicket_number=1", g=SHORT))[0][0] == stand_id
          and got[0] == (1, 4, 4, 120), str(got))
    check("the stands belong to the club's innings",
          (await q("SELECT bool_and(is_club_innings) FROM partnerships WHERE game_id=:g", g=SHORT))[0][0] is True)
    check("no stand is written for the other side's innings (none of their batters is ours)",
          await stands(SHORT, 2) == [])
    check("the opposition's wickets carry no player id",
          (await q("SELECT COUNT(*) FROM fall_of_wickets WHERE game_id=:g AND innings_number=2 AND player_id IS NOT NULL",
                   g=SHORT))[0][0] == 0)

    print("\n-- LEFT ALONE --")
    check("a card still LIVE adds nothing", await fow(NOTDONE, 1) == [(1, 4)] and await stands(NOTDONE) == [(1, 4, 4, 4)])
    check("an innings the club typed is not completed from the card (and its game is not read for it)",
          await fow(TYPED, 1) == [(1, 4)] and str(TYPED) not in fetched, f"{await fow(TYPED, 1)} {fetched}")
    check("a game past the fortnight is not read and stays short",
          str(OLD) not in fetched and await fow(OLD, 1) == [(1, 4)])
    other = await stands(OTHERPAIR)
    check("a stand held for another pair is not restated", (2, 17, 1, 2) in other and (2, 208, 120, 88) not in other,
          str(other))
    check("the rest of that game's stands are still filled in", [g[0] for g in other] == [1, 2, 3, 4], str(other))

    print("\n-- THE CARD, CALLED COMPLETED, COULD ADD TO THE LIVE GAME --")
    complete = getattr(relink, "complete_innings_detail", None)   # absent on the commit before this change
    if complete is None:
        check("LIVE: 0 rows; COMPLETED: wickets and stands would be added", False, "complete_innings_detail is absent")
    else:
        async with Session() as s:
            n_live = await complete(s, ORG, NOTDONE, cards[str(NOTDONE)], lambda g: _resolve(g))
            await s.rollback()
            done_card = dict(cards[str(NOTDONE)], status="COMPLETED")
            n_done = await complete(s, ORG, NOTDONE, done_card, lambda g: _resolve(g))
            await s.rollback()
        check("LIVE: 0 rows; COMPLETED: wickets and stands would be added",
              sum(n_live.values()) == 0 and n_done["fow"] == 9 and n_done["partnerships"] == 3, f"{n_live} {n_done}")

    print("\n-- A SECOND RUN CHANGES NOTHING --")
    before = (await fow(SHORT, 1), await fow(SHORT, 2), await stands(SHORT), await stands(OTHERPAIR))
    fetched.clear()
    await sync_grassroots_game_level_data(str(ORG), since=TODAY - timedelta(days=1))
    after = (await fow(SHORT, 1), await fow(SHORT, 2), await stands(SHORT), await stands(OTHERPAIR))
    check("same wickets and stands, none doubled", before == after)
    check("the completed game is no longer selected for a re-read", str(SHORT) not in fetched, str(fetched))

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


_BY = {str(v): v for v in PID.values()}


def _resolve(guid):
    return _BY.get(str(guid))


if __name__ == "__main__":
    asyncio.run(main())
