"""Verification for the voting portal's game list against a real Postgres.

The voting page signs a player in and takes them to the next game they played that
is open for voting and that they have not voted on. That needs the list the server
sends a verified player to hold only games they can vote on, each flagged ``voted``.
On a team set to captain only, the rest of the side must not be offered its games
(the page would take them to "only the captain submits votes").

Runs the SHIPPED route bodies. Usage:
    cd backend && DATABASE_URL=postgresql+asyncpg://... python scripts/verify_vote_portal_landing.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


TODAY = date.today()
ORG, SEASON, GRADE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
CAPTAIN, JOE, SAM, DAVE, AWAY = (uuid.uuid4() for _ in range(5))
FX_OLD, FX_NEW, FX_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
GAME_OLD, GAME_NEW, GAME_OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def seed(db) -> None:
    from app.models.db import Fixture, Game, GameAppearance, Grade, Organisation, Player, Season

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    await db.flush()
    year = TODAY.year if TODAY.month >= 7 else TODAY.year - 1
    db.add(Season(id=SEASON, organisation_id=ORG, name="Current", year=year))
    await db.flush()
    db.add(Grade(id=GRADE, season_id=SEASON, name="OD6"))
    for pid, nm in ((CAPTAIN, "Captain Cook"), (JOE, "Regular Joe"), (SAM, "Sam Side"), (DAVE, "Dave Deep"),
                    (AWAY, "Al Away")):
        db.add(Player(id=pid, organisation_id=ORG, name=nm, email=f"{nm[:3].lower()}@example.com", is_player=True))
    await db.flush()
    for gid in (GAME_OLD, GAME_NEW, GAME_OTHER):
        db.add(Game(id=gid, grade_id=GRADE))
    await db.flush()
    for gid in (GAME_OLD, GAME_NEW):
        for pid, cap in ((CAPTAIN, True), (JOE, False), (SAM, False), (DAVE, False)):
            db.add(GameAppearance(game_id=gid, player_id=pid, is_captain=cap))
    # A game Joe did not play.
    db.add(GameAppearance(game_id=GAME_OTHER, player_id=AWAY, is_captain=True))
    for fid, game, days, opp in ((FX_OLD, GAME_OLD, 4, "Bentley 3rd XI"), (FX_NEW, GAME_NEW, 1, "Bentley 4th XI"),
                                 (FX_OTHER, GAME_OTHER, 2, "Melville")):
        d = TODAY - timedelta(days=days)
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round="2", played_on=d, end_on=d,
                       home_away="H", grade_id=GRADE, playhq_id=str(game)))
    await db.commit()


def request(player_id=None) -> Request:
    from app.config.settings import settings
    from app.routers.public_votes import COOKIE_NAME

    headers = []
    if player_id is not None:
        tok = jwt.encode(
            {"club": str(ORG), "pid": str(player_id), "typ": "vote",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.secret_key, algorithm=settings.algorithm,
        )
        headers.append((b"cookie", f"{COOKIE_NAME}={tok}".encode()))
    return Request({"type": "http", "headers": headers, "method": "GET", "path": "/", "query_string": b"",
                    "client": ("1.2.3.4", 1234)})


async def attempt(coro):
    try:
        return ("ok", await coro)
    except HTTPException as e:
        return ("http", e.status_code, e.detail)
    except Exception as e:
        return ("err", f"{type(e).__name__}: {e}")


async def main() -> None:
    from app.models.db import Base, Organisation, VoteMedal
    from app.routers import public_votes as pv

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as db:
        await seed(db)
        medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True, link_token="tok-cc",
                          voter_mode="players", require_pin=False)
        db.add(medal)
        await db.commit()

        async def landing(who):
            r = await attempt(pv.get_landing("tok-cc", request(who), db))
            return r[1] if r[0] == "ok" else {"fixtures": [], "error": r}

        def rows(d):
            return {f["id"]: f for f in d["fixtures"]}

        # ── Everyone votes: the player's own games, newest first, none voted ──
        d = await landing(JOE)
        ids = [f["id"] for f in d["fixtures"]]
        check("a player is offered the two games they played, newest first, and not one they did not play",
              ids == [str(FX_NEW), str(FX_OLD)], str(ids))
        check("nothing is flagged voted yet, and both are open",
              all(not f["voted"] and f["state"] == "open" for f in d["fixtures"]), str(d["fixtures"]))
        first_unvoted = next((f["id"] for f in d["fixtures"] if f["state"] == "open" and not f["voted"]), None)
        check("the next game to vote on is the newest", first_unvoted == str(FX_NEW), str(first_unvoted))

        # ── Voting on it moves them on to the next ──
        sub = await attempt(pv.submit_ballot(
            "tok-cc", str(FX_NEW), pv.BallotBody(picks=[str(CAPTAIN), str(SAM), str(DAVE)]), request(JOE), db))
        check("the ballot is accepted", sub[0] == "ok", str(sub)[:200])
        d = await landing(JOE)
        r = rows(d)
        check("the game voted on is flagged voted and the other is not",
              r.get(str(FX_NEW), {}).get("voted") is True and r.get(str(FX_OLD), {}).get("voted") is False, str(r))
        nxt = next((f["id"] for f in d["fixtures"] if f["state"] == "open" and not f["voted"]), None)
        check("the next game to vote on is now the older one", nxt == str(FX_OLD), str(nxt))
        sub2 = await attempt(pv.submit_ballot(
            "tok-cc", str(FX_OLD), pv.BallotBody(picks=[str(CAPTAIN), str(SAM), str(DAVE)]), request(JOE), db))
        d = await landing(JOE)
        check("with both voted there is nothing left to take them to",
              sub2[0] == "ok" and not any(f["state"] == "open" and not f["voted"] for f in d["fixtures"]), str(d["fixtures"]))

        # Another player's ballots do not count as theirs.
        d = await landing(SAM)
        check("another player's list is not marked voted by Joe's ballots",
              all(not f["voted"] for f in d["fixtures"]) and len(d["fixtures"]) == 2, str(d["fixtures"]))

        # ── Captain only: the rest of the side has nothing to vote on ──
        medal.voter_mode = "captain"
        await db.commit()
        d_joe = await landing(JOE)
        d_cap = await landing(CAPTAIN)
        check("captain only: a player who is not the captain is offered no games", d_joe["fixtures"] == [], str(d_joe["fixtures"]))
        check("captain only: the captain is still offered both games",
              [f["id"] for f in d_cap["fixtures"]] == [str(FX_NEW), str(FX_OLD)], str(d_cap["fixtures"]))
        d_anon = await landing(None)
        check("someone who has not said who they are still gets the club's list (to find their name)",
              len(d_anon["fixtures"]) >= 2 and len(d_anon["players"]) == 5, str(len(d_anon["fixtures"])))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
