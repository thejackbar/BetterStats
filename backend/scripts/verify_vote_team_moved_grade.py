"""Verification for a team that Cricket Australia moved to another grade, and the
votes page (Applecross 8th XI, One Day Grade 6 to Grade 5, Hullett Medal) against
a real Postgres.

The report: a player chosen to vote for the 8th XI was offered "Round 3 vs Swan Ath
OD6" (the old grade) and could not vote on the 8th XI's real Grade 5 game. Two
causes, both about what hangs off a team when its grade changes:

  1. A fixture the sync kept as CANCELLED (the club had picked an XI on it) stayed
     OPEN for voting under its old grade and opponent, because the vote state never
     read the fixture's status and a saved XI alone made it look ready.
  2. "Who votes" and "the people chosen" are stored under the grade name, or
     "<grade name>::<team id>" while two teams share a grade. Once the team plays
     Grade 5 its games look under "One Day Grade 5", find nothing, and fall back to
     the medal default, so its chosen people lose the right to vote for it.

Runs the SHIPPED service functions and route bodies. New names are read through
presence-safe accessors, so the same script against the previous commit reports
FAIL lines instead of crashing (the control run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_team_moved_grade.py
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


PLAYED = date.today() - timedelta(days=1)
EARLIER = date.today() - timedelta(days=15)
OD6, OD5 = "One Day Grade 6", "One Day Grade 5"

ORG = uuid.uuid4()
SEASON, G_OD6, G_OD5 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
T8, T10 = uuid.uuid4(), uuid.uuid4()
# 8th XI: round 1 played in OD6 (before the move), round 3 in OD5 (after), and the
# round 3 row the sync kept as CANCELLED under the old grade. 10th XI: round 3 in OD6.
FX8_R1, FX8_NEW, FX8_OLD, FX10 = (uuid.uuid4() for _ in range(4))
GAME8_R1, GAME8_NEW, GAME10 = (uuid.uuid4() for _ in range(3))
PRASH = uuid.uuid4()                      # chosen for the 8th XI, not in its side
S8 = [uuid.uuid4() for _ in range(3)]
S10 = [uuid.uuid4() for _ in range(3)]


async def seed(db) -> None:
    from app.models.db import (
        Fixture, FixtureLineup, Game, GameAppearance, Grade, Organisation, Player, Season, Team,
    )

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    await db.flush()
    year = PLAYED.year if PLAYED.month >= 7 else PLAYED.year - 1
    db.add(Season(id=SEASON, organisation_id=ORG, name="Current", year=year))
    await db.flush()
    db.add(Grade(id=G_OD6, season_id=SEASON, name=OD6))
    db.add(Grade(id=G_OD5, season_id=SEASON, name=OD5))
    await db.flush()
    db.add(Team(id=T8, organisation_id=ORG, name="Applecross 8th XI", short_name="8th XI", sequence=8, grade_id=G_OD5))
    db.add(Team(id=T10, organisation_id=ORG, name="Applecross 10th XI", short_name="10th XI", sequence=10, grade_id=G_OD6))
    names = {PRASH: "Prashant Madan"}
    names.update({pid: f"Eighth Side {i}" for i, pid in enumerate(S8)})
    names.update({pid: f"Tenth Side {i}" for i, pid in enumerate(S10)})
    for pid, nm in names.items():
        db.add(Player(id=pid, organisation_id=ORG, name=nm, email=f"{pid.hex[:8]}@example.com", is_player=True))
    await db.flush()
    for gid, grade in ((GAME8_R1, G_OD6), (GAME8_NEW, G_OD5), (GAME10, G_OD6)):
        db.add(Game(id=gid, grade_id=grade))
    await db.flush()
    for game, side in ((GAME8_R1, S8), (GAME8_NEW, S8), (GAME10, S10)):
        for i, pid in enumerate(side):
            db.add(GameAppearance(game_id=game, player_id=pid, is_captain=(i == 0)))
    rows = (
        (FX8_R1, G_OD6, T8, GAME8_R1, "Bentley OD6", "1", EARLIER, "FINAL"),
        (FX8_NEW, G_OD5, T8, GAME8_NEW, "Swan Ath Senior Men OD5", "3", PLAYED, "FINAL"),
        (FX10, G_OD6, T10, GAME10, "Melville OD6", "3", PLAYED, "FINAL"),
    )
    for fid, grade, team, game, opp, rnd, day, status in rows:
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round=rnd, played_on=day, end_on=day,
                       home_away="H", grade_id=grade, team_id=team, playhq_id=str(game), status=status))
    # The row CA dropped when the team moved. The club had picked an XI on it, so the
    # sync kept it (CANCELLED) with its old grade, opponent and team, and no game.
    db.add(Fixture(id=FX8_OLD, organisation_id=ORG, opponent_name="Swan Ath Senior Men OD6", round="3",
                   played_on=PLAYED, end_on=PLAYED, home_away="H", grade_id=G_OD6, team_id=T8,
                   playhq_id=str(uuid.uuid4()), status="CANCELLED"))
    await db.flush()
    for i, pid in enumerate(S8):
        db.add(FixtureLineup(fixture_id=FX8_OLD, player_id=pid, organisation_id=ORG, batting_order=i + 1))
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
    except Exception as e:  # control run: the feature does not exist
        return ("err", f"{type(e).__name__}: {e}")


async def main() -> None:
    from app.models.db import Base, Fixture, Organisation, Player, VoteMedal
    from app.routers import public_votes as pv
    from app.routers import votes as vr
    from app.services import votes as vs

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)
        fx = {k: await db.get(Fixture, v) for k, v in
              (("r1", FX8_R1), ("new", FX8_NEW), ("old", FX8_OLD), ("t10", FX10))}
        prash = await db.get(Player, PRASH)
        side8 = await db.get(Player, S8[1])
        side10 = await db.get(Player, S10[1])

        # The club set the 8th XI's chosen voter while both teams played Grade 6, so the
        # entry is under "<grade>::<team id>". The 10th XI plays everyone.
        k8, k10 = f"{OD6}::{T8}", f"{OD6}::{T10}"
        medal = VoteMedal(organisation_id=ORG, name="Hullett Medal", position=0, enabled=True, link_token="tok-h",
                          voter_mode="players",
                          grade_voter_modes={k8: "chosen", k10: "players"},
                          grade_vote_counters={k8: [str(PRASH)]})
        db.add(medal)
        await db.commit()
        cfg0 = vs.effective_config(medal)

        elig8 = [{"id": str(pid), "name": f"Eighth Side {i}", "is_captain": i == 0} for i, pid in enumerate(S8)]
        elig10 = [{"id": str(pid), "name": f"Tenth Side {i}", "is_captain": i == 0} for i, pid in enumerate(S10)]

        # ── 1. The cancelled row is not a game ──────────────────────────────────
        state_old = vs.fixture_vote_state(fx["old"], cfg0, None, True)   # a saved XI makes it "ready"
        check("a CANCELLED fixture with a saved XI is not open for voting", state_old == "cancelled", state_old)
        check("a deliberate reopen still brings it back (admin's call)",
              vs.fixture_vote_state(fx["old"], cfg0, "reopened", True) == "open")
        check("a CANCELLED fixture that is also locked reads cancelled, not locked",
              vs.fixture_vote_state(fx["old"], cfg0, "locked", True) == "cancelled")
        check("a played, FINAL fixture is open as before",
              vs.fixture_vote_state(fx["new"], cfg0, None, True) == "open")
        check("an UPCOMING-status fixture dated in the past is open as before (no false positives)",
              vs.fixture_vote_state(fx["t10"], cfg0, None, True) == "open")

        land = await attempt(pv.get_landing("tok-h", request(PRASH), db=db))
        listed = {f["id"] for f in land[1]["fixtures"]} if land[0] == "ok" else set()
        check("the vote page does not list the cancelled Grade 6 game to the 8th XI's chosen person",
              land[0] == "ok" and str(FX8_OLD) not in listed, str(land)[:200])
        check("the vote page lists the 8th XI's real Grade 5 game to them (the point of the report)",
              land[0] == "ok" and str(FX8_NEW) in listed, str(land)[:200] if land[0] != "ok" else str(sorted(listed)))
        check("the 10th XI's Grade 6 game is not offered to the 8th XI's chosen person",
              land[0] == "ok" and str(FX10) not in listed, str(sorted(listed)))

        body = pv.BallotBody(picks=[str(S8[0]), str(S8[1]), str(S8[2])])
        sub = await attempt(pv.submit_ballot("tok-h", str(FX8_OLD), body, request(PRASH), db=db))
        check("a ballot on the cancelled game is refused (409)", sub[0] == "http" and sub[1] == 409, str(sub))
        check("the refusal says the game is off the draw", sub[0] == "http" and "no longer on the draw" in str(sub[2]), str(sub))

        bulk = await attempt(vr.bulk_state(
            vr.BulkStateBody(fixture_ids=[str(FX8_OLD), str(FX8_NEW)], action="open", medal_id=str(medal.id)),
            db=db, club=club, user=type("U", (), {"id": None})()))
        skipped = {x["fixture_id"]: x["reason"] for x in bulk[1]["skipped"]} if bulk[0] == "ok" else {}
        check("a bulk Open does not quietly revive the cancelled game", skipped.get(str(FX8_OLD)) == "cancelled", str(bulk)[:200])

        # ── 2. The team's own setting follows it into Grade 5 ───────────────────
        cfg_new = await vs.cfg_for_fixture(db, cfg0, fx["new"])
        check("the 8th XI's Grade 5 game is still on 'chosen'", cfg_new.get("voter_mode") == "chosen", str(cfg_new.get("voter_mode")))
        check("…with the same chosen person", cfg_new.get("vote_chosen") == [str(PRASH)], str(cfg_new.get("vote_chosen")))
        check("the chosen person can vote on the 8th XI's Grade 5 game",
              pv._voter_role(cfg_new, prash, elig8)[0] == "player")
        check("a member of the side who is not chosen still cannot (chosen means chosen)",
              pv._voter_role(cfg_new, side8, elig8) == ("none", "chosen_only"))

        cfg_r1 = await vs.cfg_for_fixture(db, cfg0, fx["r1"])
        check("the 8th XI's played Grade 6 round still reads its own setting",
              cfg_r1.get("voter_mode") == "chosen" and cfg_r1.get("vote_chosen") == [str(PRASH)])

        cfg10 = await vs.cfg_for_fixture(db, cfg0, fx["t10"])
        check("the 10th XI's Grade 6 game keeps its own setting (all players), not the 8th XI's",
              cfg10.get("voter_mode") == "players" and not cfg10.get("vote_chosen"), str(cfg10.get("voter_mode")))
        check("a 10th XI player votes on it and the 8th XI's chosen person does not",
              pv._voter_role(cfg10, side10, elig10)[0] == "player" and pv._voter_role(cfg10, prash, elig10)[0] == "none")

        chosen_ids = await vs.chosen_fixture_ids(db, cfg0, PRASH, [fx["new"], fx["t10"], fx["r1"]])
        check("the 'games a chosen person may vote on' read finds the Grade 5 game and not the 10th XI's",
              FX8_NEW in chosen_ids and FX10 not in chosen_ids, str(chosen_ids))

        # ── 3. Precedence: a setting made for the new grade beats the carried one ──
        override = {**cfg0, "grade_voter_modes": {**cfg0["grade_voter_modes"], OD5: "captain"}}
        cfg_o = await vs.cfg_for_fixture(db, override, fx["new"])
        check("a setting the club saves for Grade 5 wins over the one carried from Grade 6",
              cfg_o.get("voter_mode") == "captain" and not cfg_o.get("vote_chosen"), str(cfg_o.get("voter_mode")))

        # ── 4. A team with nothing set anywhere is untouched ─────────────────────
        bare = {**cfg0, "grade_voter_modes": {}, "grade_vote_counters": {}}
        cfg_b = await vs.cfg_for_fixture(db, bare, fx["new"])
        check("with nothing set the medal default applies", cfg_b.get("voter_mode") == "players")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
