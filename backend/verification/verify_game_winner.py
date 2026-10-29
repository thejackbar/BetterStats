"""A finished game with a WIN or LOSS and no winner is read again and gets its winner. Real Postgres.

Reported by Shoalwater Bay: the Ladies B Grade Grand Final (2025/26) reads as a loss on BetterCricket and
a win on Play-Cricket. The row was created by the other club's sync (Secret Harbour Dockers), so it is filed
under their season and `games.result` is THEIR verdict (LOSS). `winning_team` was empty, so every reader fell
back to that LOSS, and Shoalwater is recorded as the home side, so it was read as Shoalwater's own. CA's card
names Shoalwater as the winner. The sync fills a missing winner only on a game it reads, and an incremental run
reads only fixtures inside its window, so a game that old was never visited again.

Drives `sync_grassroots_game_level_data` itself with Cricket Australia stubbed, as an incremental run
(`since` = yesterday), then reads the club's record through the shipped `_club_results` and `_result_for_club`.

  G_OLD      Grand Final 90 days ago, LOSS (the other club's verdict), no winner   -> read again, winner named
  G_RECENT   3 days ago, same shape                                                -> inside the window, named
  G_NAMED    90 days ago, LOSS with its winner already stored (the other side)     -> NOT read again, untouched
  G_DRAW     90 days ago, DRAW, no winner (a draw names none)                       -> NOT read again
  G_STRANGER 90 days ago, another pair of clubs, LOSS, no winner                    -> NOT read for this club

CONTROL MODE. Run against the commit BEFORE this change, `services/game_winner` does not exist; the checks
for the old game fail and the reader checks keep showing the loss (nothing crashes).

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/winner_verify?host=/tmp&port=5439 \\
  python verification/verify_game_winner.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text

import verify_reread_incomplete_game as h   # its engine, schema and match helpers; main() is guarded
from app.services import grassroots_scores_client as gr
from app.services.sync import sync_grassroots_game_level_data

check = h.check
Session = h.Session

US, THEM = "SBCC Ladies B Grade", "SHDCC Senior Women"
THIRD_ORG, FOURTH_ORG = uuid.uuid4(), uuid.uuid4()
THEIR_SEASON, THEIR_GRADE = uuid.uuid4(), uuid.uuid4()
G_OLD, G_RECENT, G_NAMED, G_DRAW, G_STRANGER = (uuid.uuid4() for _ in range(5))
DAYS = {G_OLD: 90, G_RECENT: 3, G_NAMED: 90, G_DRAW: 90, G_STRANGER: 90}


def card(game_id):
    """The card as CA has it NOW: our side won, we are the home side."""
    iso = (h.TODAY - timedelta(days=DAYS[game_id])).isoformat() + "T10:00:00Z"
    ours, theirs = str(uuid.uuid4()), str(uuid.uuid4())
    return {
        "id": str(game_id), "matchSchedule": [{"startDateTime": iso}], "venue": {"name": "Oval"},
        "status": "COMPLETED", "grade": {"id": h.GRADE_GUID, "name": "Senior Female B Grade"},
        "teams": [
            {"id": ours, "displayName": US, "owningOrganisation": {"id": str(h.ORG)},
             "players": [{"participantId": str(h.DON), "roles": []}]},
            {"id": theirs, "displayName": THEM, "owningOrganisation": {"id": str(h.OPP_ORG)}, "players": []},
        ],
        "matchSummary": {"resultText": f"{US} won by 32 runs",
                         "teams": [{"id": ours, "displayName": US, "isHome": True, "isWinner": True, "resultType": "WON"},
                                   {"id": theirs, "displayName": THEM, "isHome": False, "isWinner": False,
                                    "resultType": "LOST"}]},
        "innings": [{"inningsOrder": 1, "battingTeamId": ours, "fielding": [], "bowling": [],
                     "batting": [{"participantId": str(h.DON), "batOrder": 1, "dismissalTypeId": 2,
                                  "dismissalType": "Bowled", "runsScored": 10, "ballsFaced": 20,
                                  "playerShortName": "Don"}]}],
    }


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)
        for oid, nm, slug in ((h.ORG, "Shoalwater Bay", "sb"), (h.OPP_ORG, "Secret Harbour", "sh"),
                              (THIRD_ORG, "Third CC", "third"), (FOURTH_ORG, "Fourth CC", "fourth")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
        # Our own season and grade (what the sync discovers), and the OTHER club's, which holds the shared rows.
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2025/26', 2025, :g)", i=h.SEASON, o=h.ORG, g=str(h.SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, 'Senior Female B Grade', :g, 'senior', ARRAY['senior'])",
                 i=h.GRADE, s=h.SEASON, g=h.GRADE_GUID)
        await ex("INSERT INTO seasons (id, organisation_id, name, year, grassroots_id) "
                 "VALUES (:i, :o, 'Summer 2025/26', 2025, :g)", i=THEIR_SEASON, o=h.OPP_ORG, g=str(h.SEASON))
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                 "VALUES (:i, :s, 'Senior Female B Grade', :g, 'senior', ARRAY['senior'])",
                 i=THEIR_GRADE, s=THEIR_SEASON, g=h.GRADE_GUID)
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, 'Stewart, Don', :g, 'active')", i=h.DON, o=h.ORG, g=str(h.DON))
        shared = ((G_OLD, "LOSS", None), (G_RECENT, "LOSS", None), (G_NAMED, "LOSS", THEM), (G_DRAW, "DRAW", None))
        for gid, result, winner in shared:
            # Created by the other club's sync: filed under THEIR grade, result is THEIR verdict. We are the home side.
            await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_club, away_club, "
                     " result, winning_team, status, venue, match_format, home_org_id, away_org_id, round_name, is_final) "
                     "VALUES (:i, :g, :d, :h, :a, 'SBCC', 'SHDCC', :r, :w, 'COMPLETED', 'Oval', 'One Day', :ho, :ao, "
                     " 'Grand Final', true)",
                     i=gid, g=THEIR_GRADE, d=h.TODAY - timedelta(days=DAYS[gid]), h=US, a=THEM, r=result, w=winner,
                     ho=h.ORG, ao=h.OPP_ORG)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=gid, p=h.DON)
        await ex("INSERT INTO games (id, grade_id, played_at, home_team, away_team, result, winning_team, status, "
                 " home_org_id, away_org_id) VALUES (:i, :g, :d, 'X', 'Y', 'LOSS', NULL, 'COMPLETED', :ho, :ao)",
                 i=G_STRANGER, g=THEIR_GRADE, d=h.TODAY - timedelta(days=90), ho=THIRD_ORG, ao=FOURTH_ORG)
        await s.commit()


async def winner_of(game_id):
    async with Session() as s:
        return (await s.execute(text("SELECT winning_team FROM games WHERE id = :g"), {"g": game_id})).scalar()


async def stored(game_id):
    async with Session() as s:
        return (await s.execute(text(
            "SELECT result, home_org_id, away_org_id FROM games WHERE id = :g"), {"g": game_id})).one()


async def club_record():
    from app.services import aggregations
    async with Session() as s:
        return await aggregations._club_results(s, str(h.ORG))


async def scorecard_result(game_id):
    """What the scorecard page reads for our club: the shipped `_result_for_club` on the stored row."""
    from app.routers import games as games_router
    async with Session() as s:
        r = (await s.execute(text(
            "SELECT home_team, away_team, home_org_id, away_org_id, result, winning_team FROM games WHERE id = :g"),
            {"g": game_id})).one()
    game = SimpleNamespace(home_team=r[0], away_team=r[1], home_org_id=r[2], away_org_id=r[3],
                           result=r[4], winning_team=r[5])
    club = SimpleNamespace(id=h.ORG, name="Shoalwater Bay", slug="sb")
    return games_router._result_for_club(game, club)


async def main() -> None:
    await h.build_schema()
    await seed()

    cards = {str(g): card(g) for g in (G_OLD, G_RECENT, G_NAMED, G_DRAW, G_STRANGER)}
    listing = [h.match_entry(g, DAYS[g]) for g in (G_OLD, G_RECENT, G_NAMED, G_DRAW)]
    fetched: list[str] = []

    async def fake_matches(grade_guid, *a, **k):
        return listing

    async def fake_card(match_id, *a, **k):
        fetched.append(str(match_id))
        return cards.get(str(match_id))

    gr.get_grade_matches = fake_matches
    gr.get_match_scorecard = fake_card

    print("\n-- BEFORE: the reported shape --")
    check("the Grand Final holds the other club's LOSS and no winner",
          (await stored(G_OLD))[0] == "LOSS" and await winner_of(G_OLD) is None)
    rec = await club_record()
    check("the club's record shows it as a loss (the bug, as reported)",
          rec["losses"] >= 1 and rec["wins"] == 0, str(rec))
    check("and the scorecard reads it as a loss", await scorecard_result(G_OLD) == "LOSS")

    print("\n-- AN INCREMENTAL RUN, since = yesterday (the Grand Final is 90 days old) --")
    await sync_grassroots_game_level_data(str(h.ORG), since=h.TODAY - timedelta(days=1))
    check("the old game was read again", str(G_OLD) in fetched, f"fetched={fetched}")
    check("its winner is now the side CA names", await winner_of(G_OLD) == US, str(await winner_of(G_OLD)))
    check("a game inside the window gets its winner too", await winner_of(G_RECENT) == US)
    check("the stored result and sides are untouched (readers work from the winner's name)",
          (await stored(G_OLD)) == ("LOSS", h.ORG, h.OPP_ORG), str(await stored(G_OLD)))
    check("a game with its winner stored is not read again", str(G_NAMED) not in fetched, str(fetched))
    check("and keeps the winner it had", await winner_of(G_NAMED) == THEM)
    check("a draw is not read again for this", str(G_DRAW) not in fetched and await winner_of(G_DRAW) is None, str(fetched))
    check("another pair of clubs' game is not read for this club",
          str(G_STRANGER) not in fetched and await winner_of(G_STRANGER) is None)

    print("\n-- WHAT THE CLUB SEES NOW --")
    check("the scorecard reads the Grand Final as a win", await scorecard_result(G_OLD) == "WIN",
          str(await scorecard_result(G_OLD)))
    rec = await club_record()
    check("the club's record counts it as a win: 2 wins (old, recent) and 1 loss (the named one)",
          (rec["wins"], rec["losses"], rec["draws"]) == (2, 1, 1), str(rec))

    print("\n-- A SECOND RUN CHANGES NOTHING --")
    fetched.clear()
    await sync_grassroots_game_level_data(str(h.ORG), since=h.TODAY - timedelta(days=1))
    check("the old game, now named, is not read again", str(G_OLD) not in fetched, str(fetched))
    check("and its winner is still the same", await winner_of(G_OLD) == US)
    check("the recent one is inside the window so it is read, and keeps the same winner",
          str(G_RECENT) in fetched and await winner_of(G_RECENT) == US)

    print(f"\n{h.PASS} passed, {h.FAIL} failed")
    await h.engine.dispose()
    sys.exit(1 if h.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
