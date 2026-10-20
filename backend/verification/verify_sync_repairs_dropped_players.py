"""A stored game is repaired for a player it dropped, from the scorecard sync already
holds, and a hand-added player takes the id they were matched on. Real Postgres.

The Cricket Australia fetch is not involved: `repair_stored_game` and
`adopt_identity` are the shipped functions sync calls with the scorecard in hand.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/fees_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_sync_repairs_dropped_players.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def main():
    from app.models.db import (
        Base, Game, GameAppearance, Grade, Organisation, Player, Season, engine, async_session_maker,
    )
    from app.services import participant_relink as relink
    if os.environ.get("CONTROL"):
        # The behaviour before this change: a stored game was never read again for a
        # dropped player, and a hand-added player never took the id they were matched on.
        async def _none(*a, **k):
            return None

        async def _zero(*a, **k):
            return 0
        relink.repair_stored_game, relink.adopt_identity = _none, _zero

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    org, other, sid, gid, game = (uuid.uuid4() for _ in range(5))
    p1, p2, late, opp, hand, held, imported = (uuid.uuid4() for _ in range(7))
    g1, g2, glate, gopp, gunknown = (str(uuid.uuid4()) for _ in range(5))
    async with async_session_maker() as db:
        db.add_all([Organisation(id=org, name="Applecross", slug="apple-r", is_active=True),
                    Organisation(id=other, name="CVPCC", slug="cvpcc-r", is_active=True),
                    Season(id=sid, organisation_id=org, name="Summer 2026/27", year=2026)])
        await db.flush()
        db.add(Grade(id=gid, season_id=sid, name="Colts T20"))
        await db.flush()
        db.add_all([Player(id=p1, organisation_id=org, name="One, Pat", grassroots_id=g1),
                    Player(id=p2, organisation_id=org, name="Two, Pip", grassroots_id=g2),
                    Player(id=late, organisation_id=org, name="Cowcher, Baxter", grassroots_id=glate),
                    Player(id=opp, organisation_id=other, name="Opp, Olly", grassroots_id=gopp)])
        db.add(Game(id=game, grade_id=gid, played_at=date(2026, 10, 3), home_team="CVPCC Colts",
                    away_team="Applecross Colts", status="COMPLETED"))
        await db.flush()
        db.add_all([GameAppearance(game_id=game, player_id=p1), GameAppearance(game_id=game, player_id=p2)])
        await db.commit()

    known = {g1: p1, g2: p2, glate: late}      # sync's _team_pid over the club's players
    scorecard = {
        "teams": [{"owningOrganisation": {"id": str(org)}, "displayName": "Applecross Colts",
                   "players": [{"participantId": g1, "roles": ["Captain"]}, {"participantId": g2},
                               {"participantId": glate}, {"participantId": gunknown}]},
                  {"owningOrganisation": {"id": str(other)}, "displayName": "CVPCC Colts",
                   "players": [{"participantId": gopp}]}],
        "innings": [{"inningsOrder": 1,
                     "batting": [{"participantId": glate, "dismissalTypeId": 9, "dismissalType": "Did not bat"}],
                     "bowling": [{"participantId": glate, "oversBowled": 3, "maidensBowled": 0, "runsConceded": 7,
                                  "wicketsTaken": 1, "wideBalls": 3, "noBalls": 0, "economy": 2.33},
                                 {"participantId": gopp, "oversBowled": 2, "runsConceded": 9, "wicketsTaken": 0}],
                     "fielding": []}],
    }
    resolve = lambda g: known.get(g)

    async def count(sql, **kw):
        async with async_session_maker() as db:
            return (await db.execute(text(sql), kw)).scalar()

    async with async_session_maker() as db:
        n = await relink.repair_stored_game(db, org, game, scorecard, resolve)
    check("the dropped player is attached (appearance, DNB row, spell)",
          (n or {}).get("appearances"), 1)
    check("their appearance is stored", await count(
        "SELECT count(*) FROM game_appearances WHERE game_id = :g AND player_id = :p", g=game, p=late), 1)
    check("their bowling spell is stored", await count(
        "SELECT count(*) FROM bowling_spells WHERE game_id = :g AND player_id = :p", g=game, p=late), 1)
    check("the players already there are untouched", await count(
        "SELECT count(*) FROM game_appearances WHERE game_id = :g AND player_id IN (:a, :b)", g=game, a=p1, b=p2), 2)
    check("the opposition is not attached to our side", await count(
        "SELECT count(*) FROM game_appearances WHERE game_id = :g AND player_id = :o", g=game, o=opp), 0)
    check("an id nobody holds creates nothing", await count(
        "SELECT count(*) FROM players WHERE organisation_id = :o", o=org), 3)
    async with async_session_maker() as db:
        again = await relink.repair_stored_game(db, org, game, scorecard, resolve)
    check("running it again adds nothing", again, None)
    check("and stores nothing twice", (await count("SELECT count(*) FROM game_appearances WHERE game_id = :g", g=game),
                                       await count("SELECT count(*) FROM bowling_spells WHERE game_id = :g", g=game)), (3, 1))

    # Identity adoption for a hand-added player matched by name.
    ga, gb, gc = (str(uuid.uuid4()) for _ in range(3))
    async with async_session_maker() as db:
        db.add_all([Player(id=hand, organisation_id=org, name="Casey Newman"),
                    Player(id=held, organisation_id=org, name="Held, Hal", playhq_id="ph-1"),
                    Player(id=imported, organisation_id=org, name="Ian Imported", cricketstatz_player_id="cs-1")])
        await db.commit()
    async with async_session_maker() as db:
        stamped = await relink.adopt_identity(db, org, {ga: hand, gb: held, gc: imported})
    check("only the hand-added player takes the id", stamped, 1)
    check("they now hold the Cricket Australia id", await count(
        "SELECT grassroots_id FROM players WHERE id = :p", p=hand), ga)
    check("a record with a PlayHQ id is left alone", await count(
        "SELECT grassroots_id FROM players WHERE id = :p", p=held), None)
    check("an imported record is left alone", await count(
        "SELECT grassroots_id FROM players WHERE id = :p", p=imported), None)
    newhand = uuid.uuid4()
    async with async_session_maker() as db:
        db.add(Player(id=newhand, organisation_id=org, name="Another Hand"))
        await db.commit()
    async with async_session_maker() as db:
        stamped2 = await relink.adopt_identity(db, org, {ga: newhand})
    check("an id the club already holds is never given to a second player", stamped2, 0)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
