"""A NEW club's first sync picks up partnerships, short fall of wickets included. Real Postgres.

Asked: for a club that has never synced, will its partnerships now be picked up during the sync,
with no backfill? Reported card: six wickets fell and Cricket Australia held four fall-of-wicket
rows (1, 3, 4, 5).

Drives `sync_grassroots_game_level_data` itself (the code a first sync and a Full Rebuild run), with
the Cricket Australia client stubbed to return the match list and scorecards. The club starts with
its players, season and grade and NO games, as sync's earlier phases leave a new club:

  * the short card gives the stands its figures settle (1st, 4th, 5th: 73, 25, 25) and no others;
  * a complete card in the same sync gives every stand (the original path, unchanged);
  * the stands belong to the club's own players and the innings is marked the club's;
  * a second sync adds nothing and doubles nothing.

Run:  DATABASE_URL=postgresql+asyncpg://root@/newclub?host=/var/run/postgresql \
      python verification/verify_new_club_partial_fow_sync.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_reread_incomplete_game as h   # its engine, schema and match listing helpers; main() is guarded
from app.services import grassroots_scores_client as gr
from app.services.sync import sync_grassroots_game_level_data

check = h.check
Session = h.Session

NAMES = ["Payne", "Hall", "Bivens", "Sweet", "Cox", "Menezes", "Ito", "Lee"]
PID = {n: uuid.uuid4() for n in NAMES}
OUT = {"Payne", "Hall", "Bivens", "Sweet", "Menezes", "Cox"}            # six wickets; Ito and Lee not out
RUNS = {"Payne": 40, "Hall": 33, "Bivens": 160, "Sweet": 12, "Cox": 60, "Menezes": 14, "Ito": 20, "Lee": 5}
SHORT_GAME, FULL_GAME = uuid.uuid4(), uuid.uuid4()
SHORT_FOW = [(1, 73, "Payne"), (3, 331, "Bivens"), (4, 356, "Sweet"), (5, 381, "Menezes")]
FULL_FOW = [(1, 73, "Payne"), (2, 150, "Hall"), (3, 331, "Bivens"), (4, 356, "Sweet"),
            (5, 381, "Menezes"), (6, 400, "Cox")]


def card(game_id, days_ago, fow):
    iso = (h.TODAY - timedelta(days=days_ago)).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    return {
        "id": str(game_id), "matchSchedule": [{"startDateTime": iso}], "venue": {"name": "Oval"},
        "grade": {"id": h.GRADE_GUID, "name": "1st Grade"},
        "teams": [
            {"id": ours, "displayName": "New Club 1st", "owningOrganisation": {"id": str(h.ORG)},
             "players": [{"participantId": str(p), "roles": []} for p in PID.values()]},
            {"id": theirs, "displayName": "Them 1st", "owningOrganisation": {"id": str(h.OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": "New Club won",
                         "teams": [{"id": ours, "displayName": "New Club 1st", "isHome": True},
                                   {"id": theirs, "displayName": "Them 1st", "isHome": False}]},
        "innings": [{
            "inningsOrder": 1, "battingTeamId": ours, "fielding": [], "bowling": [],
            "fallOfWickets": [{"order": w, "runs": s, "participantId": str(PID[n]), "playerShortName": n}
                              for w, s, n in fow],
            "batting": [{"participantId": str(PID[n]), "batOrder": i,
                         "dismissalTypeId": 2 if n in OUT else 1, "dismissalType": "Bowled" if n in OUT else "Not Out",
                         "runsScored": RUNS[n], "ballsFaced": 50, "playerShortName": n}
                        for i, n in enumerate(NAMES, 1)],
        }],
    }


async def seed_new_club() -> None:
    """A club that has never synced a game: players, a season and a grade, and nothing else."""
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((h.ORG, "New Club", "new-club"), (h.OPP_ORG, "Them CC", "them")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2026/27', 2026, :g)", i=h.SEASON, o=h.ORG, g=str(h.SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])", i=h.GRADE, s=h.SEASON, g=h.GRADE_GUID)
        for n, pid in PID.items():
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=h.ORG, n=n, g=str(pid))
        await s.commit()


async def stands(game):
    async with Session() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT wicket_number, runs FROM partnerships WHERE game_id = :g ORDER BY wicket_number"), {"g": game})).all()]


async def main() -> None:
    await h.build_schema()
    from app.services.fow_override_ddl import STATEMENTS as FOW_DDL   # migration 357, as the lifespan makes it
    async with h.engine.begin() as conn:
        for stmt in FOW_DDL:
            await conn.execute(text(stmt))
    await seed_new_club()
    cards = {str(SHORT_GAME): card(SHORT_GAME, 9, SHORT_FOW), str(FULL_GAME): card(FULL_GAME, 10, FULL_FOW)}
    listing = [h.match_entry(SHORT_GAME, 9), h.match_entry(FULL_GAME, 10)]

    async def fake_matches(grade_guid, *a, **k):
        return listing

    async def fake_card(match_id, *a, **k):
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    print("\n-- BEFORE: a new club with no games --")
    async with Session() as s:
        check("nothing is stored for the club yet", (await s.execute(text("SELECT count(*) FROM games"))).scalar() == 0)

    print("\n-- ITS FIRST SYNC --")
    await sync_grassroots_game_level_data(str(h.ORG))
    async with Session() as s:
        games = (await s.execute(text("SELECT count(*) FROM games"))).scalar()
        bat = (await s.execute(text("SELECT count(*) FROM batting_innings"))).scalar()
    check("both games are stored with their batting", games == 2 and bat == 16, f"games={games} batting={bat}")
    got = await stands(SHORT_GAME)
    check("the short card gives its 1st, 4th and 5th wicket stands (73, 25, 25)",
          got == [(1, 73), (4, 25), (5, 25)], str(got))
    check("the complete card gives all six", await stands(FULL_GAME) == [(1, 73), (2, 77), (3, 181), (4, 25), (5, 25), (6, 19)],
          str(await stands(FULL_GAME)))
    async with Session() as s:
        row = (await s.execute(text("""
            SELECT p.is_club_innings, p1.organisation_id = :o AND p2.organisation_id = :o AS ours
            FROM partnerships p JOIN players p1 ON p1.id = p.batter1_id JOIN players p2 ON p2.id = p.batter2_id
            WHERE p.game_id = :g AND p.wicket_number = 4"""), {"g": SHORT_GAME, "o": h.ORG})).first()
    check("a stand is the club's own innings, between two of its players", row is not None and row[0] is True and row[1] is True, str(row))
    async with Session() as s:
        fow = (await s.execute(text("SELECT count(*) FROM fall_of_wickets WHERE game_id = :g"), {"g": SHORT_GAME})).scalar()
    check("the short game's four recorded wickets are stored as they are (no invented ones)", fow == 4, str(fow))

    print("\n-- A SECOND SYNC --")
    await sync_grassroots_game_level_data(str(h.ORG))
    check("changes nothing and doubles nothing",
          await stands(SHORT_GAME) == [(1, 73), (4, 25), (5, 25)] and len(await stands(FULL_GAME)) == 6)

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
