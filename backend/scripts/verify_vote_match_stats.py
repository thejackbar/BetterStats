"""Verification for the match-stat line shown under each player on the vote ballot
and in the player's own page, and for the club's name format on the public pages.

Runs the SHIPPED helper (services.votes.match_stat_lines) and the SHIPPED route
bodies (public_votes.fixture_state, public_availability._votes_for_player) over a
real Postgres schema built from the ORM models.

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... python scripts/verify_vote_match_stats.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + str(detail)) if detail and not cond else ''}")


ORG, OTHER = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
A, B, C, D, E, V = (uuid.uuid4() for _ in range(6))   # E is the other club's, V is the voter
GAME, GAME_UNSCORED = uuid.uuid4(), uuid.uuid4()
FX, FX_UNSCORED = uuid.uuid4(), uuid.uuid4()
MEDAL = uuid.uuid4()
TOKEN = "medal-token-1"
PLAYED = date.today() - timedelta(days=1)


def request_for(club_id, player_id) -> Request:
    from app.config.settings import settings
    tok = jwt.encode({"club": str(club_id), "pid": str(player_id), "typ": "vote",
                      "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                     settings.secret_key, algorithm=settings.algorithm)
    return Request({"type": "http", "headers": [(b"cookie", f"bs_vote={tok}".encode())],
                    "client": ("1.2.3.4", 1), "method": "GET", "path": "/", "query_string": b""})


async def main() -> None:
    from app.models.db import (
        Base, BattingInnings, BowlingSpell, FieldingStat, Fixture, Game, GameAppearance, Grade,
        Organisation, Player, Season, VoteBallot, VoteBallotPick, VoteMedal,
    )
    from app.routers import public_availability as pa, public_votes as pvt
    from app.services import votes as vs

    engine = create_async_engine(DSN)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as db:
        db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross",
                            module_overrides=["select"], player_name_format="first_last"))
        db.add(Organisation(id=OTHER, name="Swanbourne CC", short_name="SCC", slug="swan"))
        db.add(Season(id=SEASON, organisation_id=ORG, name="Summer", year=PLAYED.year))
        db.add(Grade(id=GRADE, season_id=SEASON, name="T20 Div 2"))
        for pid, nm, org, hidden in ((A, "Barendse, Jack", ORG, False), (B, "Smith, Sam", ORG, False),
                                     (C, "Jones, Kim", ORG, False), (D, "Hidden, Hal", ORG, True),
                                     (E, "Other, Olly", OTHER, False), (V, "Voter, Vic", ORG, False)):
            db.add(Player(id=pid, organisation_id=org, name=nm, is_public=not hidden,
                          phone="0400000001"))
        await db.flush()
        for g in (GAME, GAME_UNSCORED):
            db.add(Game(id=g, grade_id=GRADE))
        await db.flush()
        for fid, g in ((FX, GAME), (FX_UNSCORED, GAME_UNSCORED)):
            db.add(Fixture(id=fid, organisation_id=ORG, playhq_id=str(g), opponent_name="Swanbourne",
                           round="5", played_on=PLAYED, end_on=PLAYED, home_away="H", grade_id=GRADE))
        for g in (GAME, GAME_UNSCORED):
            for pid in (A, B, C, D, V):
                db.add(GameAppearance(game_id=g, player_id=pid, is_captain=False))
        await db.flush()
        # Game 1 is scored.
        db.add(BattingInnings(game_id=GAME, player_id=A, innings_number=1, runs=45, balls=32, not_out=True))
        db.add(BowlingSpell(game_id=GAME, player_id=A, innings_number=1, overs=4.0, maidens=0, runs=18, wickets=2))
        db.add(FieldingStat(game_id=GAME, player_id=A, catches=1, catches_wk=1, run_outs=0, stumpings=0))
        db.add(BattingInnings(game_id=GAME, player_id=C, innings_number=1, runs=12, balls=10, not_out=False))
        db.add(BattingInnings(game_id=GAME, player_id=C, innings_number=2, runs=30, balls=28, not_out=False))
        db.add(BowlingSpell(game_id=GAME, player_id=C, innings_number=1, overs=3.4, maidens=0, runs=25, wickets=0))
        db.add(FieldingStat(game_id=GAME, player_id=C, catches=0, catches_wk=0, run_outs=1, stumpings=1))
        db.add(BattingInnings(game_id=GAME, player_id=D, innings_number=1, runs=99, balls=50, not_out=False))
        db.add(BattingInnings(game_id=GAME, player_id=E, innings_number=1, runs=77, balls=40, not_out=False))
        db.add(BattingInnings(game_id=GAME, player_id=B, innings_number=1, runs=None, balls=None, did_not_bat=True))
        db.add(VoteMedal(id=MEDAL, organisation_id=ORG, name="Club Champion", enabled=True,
                         link_token=TOKEN, require_pin=False, ballot_values=[3, 2, 1], auto_close_days=30))
        await db.flush()
        ballot = VoteBallot(id=uuid.uuid4(), organisation_id=ORG, medal_id=MEDAL, fixture_id=FX, voter_player_id=V)
        db.add(ballot)
        await db.flush()
        for pos, pid in ((1, A), (2, C), (3, B)):
            db.add(VoteBallotPick(ballot_id=ballot.id, position=pos, player_id=pid))
        await db.commit()

    # Presence-safe, so a run against the code before this change reports FAILs
    # instead of crashing (a control that crashes is not a control).
    async def stat_lines(db, game, ids):
        fn = getattr(vs, "match_stat_lines", None)
        return await fn(db, ORG, game, ids) if fn else {}

    async with Session() as db:
        lines = await stat_lines(db, GAME, [A, B, C, D, E])
        check("batting not out, bowling and fielding in one line", lines.get(str(A)) == "45* (32) · 2/18 (4 ov) · 2 ct", lines.get(str(A)))
        check("two innings listed in order, partial overs, stumping and run out",
              lines.get(str(C)) == "12 (10), 30 (28) · 0/25 (3.4 ov) · 1 st, 1 ro", lines.get(str(C)))
        check("played but did not bat or bowl says so", lines.get(str(B)) == "Did not bat or bowl", lines.get(str(B)))
        check("a player hidden from the public pages gets no line", str(D) not in lines, lines.get(str(D)))
        check("the other club's player in a shared game is never read", str(E) not in lines, lines.get(str(E)))
        check("an unscored game gives no lines (not 'Did not bat' for everyone)",
              await stat_lines(db, GAME_UNSCORED, [A, B, C]) == {})
        check("no ids, no lines", await stat_lines(db, GAME, []) == {})

        club = await db.get(Organisation, ORG)
        # The ballot page: stats ride on each player; branding carries the name format.
        out = await pvt.fixture_state(TOKEN, str(FX), request_for(ORG, V), db)
        by = {p["id"]: p for p in out["players"]}
        check("ballot players carry stats", by.get(str(A), {}).get("stats") == "45* (32) · 2/18 (4 ov) · 2 ct", by.get(str(A)))
        check("ballot hidden player has a name but no stats line", str(D) in by and by[str(D)].get("stats") is None, by.get(str(D)))
        check("ballot carries the club's name format", (out.get("club") or {}).get("player_name_format") == "first_last", out["club"])
        out2 = await pvt.fixture_state(TOKEN, str(FX_UNSCORED), request_for(ORG, V), db)
        check("unscored game's ballot has no stats on anyone", all(p.get("stats") is None for p in out2["players"]), out2["players"][:2])

        # The player's own page: the picks they cast carry the same lines.
        voter = await db.get(Player, V)
        due, cast = await pa._votes_for_player(db, club, voter)
        picks = cast[0]["picks"] if cast else []
        check("dashboard cast picks carry stats in pick order",
              [p.get("stats") for p in picks] == ["45* (32) · 2/18 (4 ov) · 2 ct", "12 (10), 30 (28) · 0/25 (3.4 ov) · 1 st, 1 ro", "Did not bat or bowl"],
              [p.get("stats") for p in picks])
        check("dashboard payload still names the picks", [p["name"] for p in picks] == ["Barendse, Jack", "Jones, Kim", "Smith, Sam"], [p["name"] for p in picks])
        check("availability branding carries the name format", pa._club_branding(club).get("player_name_format") == "first_last")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
