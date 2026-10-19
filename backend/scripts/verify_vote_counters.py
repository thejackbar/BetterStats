"""Verification for a captain-only team's nominated vote counter (migration 347)
against a real Postgres.

Runs the SHIPPED statements, service functions and route bodies. New keys and
functions are read through presence-safe accessors, so the same script run
against the previous commit reports FAIL lines instead of crashing (the control
run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_counters.py
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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


PLAYED = date.today() - timedelta(days=1)

ORG, OTHER_ORG = uuid.uuid4(), uuid.uuid4()
SEASON, G_FIRSTS, G_COLTS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FX_FIRSTS, FX_COLTS = uuid.uuid4(), uuid.uuid4()
CAPTAIN, JOE, SAM, HELPER, SUPPORTER, OUTSIDER = (uuid.uuid4() for _ in range(6))
GAME_F, GAME_C = uuid.uuid4(), uuid.uuid4()


async def seed(db) -> None:
    from app.models.db import (
        Fixture, Game, GameAppearance, Grade, Organisation, Player, Season,
    )

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    db.add(Organisation(id=OTHER_ORG, name="Melville CC", short_name="MCC", slug="melville", module_overrides=["select"]))
    await db.flush()
    year = PLAYED.year if PLAYED.month >= 7 else PLAYED.year - 1
    db.add(Season(id=SEASON, organisation_id=ORG, name="Current", year=year))
    await db.flush()
    db.add(Grade(id=G_FIRSTS, season_id=SEASON, name="1st Grade"))
    db.add(Grade(id=G_COLTS, season_id=SEASON, name="Colts"))
    for pid, nm, org, is_player in (
        (CAPTAIN, "Captain Cook", ORG, True), (JOE, "Regular Joe", ORG, True), (SAM, "Sam Side", ORG, True),
        # Not in either side: the captain's helper.
        (HELPER, "Helen Helper", ORG, True),
        # Club person who is not a player (a supporter record).
        (SUPPORTER, "Sue Supporter", ORG, False),
        (OUTSIDER, "Olly Outsider", OTHER_ORG, True),
    ):
        db.add(Player(id=pid, organisation_id=org, name=nm, email=f"{nm[:3].lower()}@example.com",
                      is_player=is_player))
    await db.flush()
    for gid, grade in ((GAME_F, G_FIRSTS), (GAME_C, G_COLTS)):
        db.add(Game(id=gid, grade_id=grade))
    await db.flush()
    for pid, cap in ((CAPTAIN, True), (JOE, False), (SAM, False)):
        db.add(GameAppearance(game_id=GAME_F, player_id=pid, is_captain=cap))
        db.add(GameAppearance(game_id=GAME_C, player_id=pid, is_captain=cap))
    for fid, grade, game, opp in ((FX_FIRSTS, G_FIRSTS, GAME_F, "Melville"), (FX_COLTS, G_COLTS, GAME_C, "Melville Colts")):
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round="5",
                       played_on=PLAYED, end_on=PLAYED, home_away="H", grade_id=grade, playhq_id=str(game)))
    await db.commit()


def request(player_id=None, club_id=ORG) -> Request:
    from app.config.settings import settings
    from app.routers.public_votes import COOKIE_NAME

    headers = []
    if player_id is not None:
        tok = jwt.encode(
            {"club": str(club_id), "pid": str(player_id), "typ": "vote",
             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            settings.secret_key, algorithm=settings.algorithm,
        )
        headers.append((b"cookie", f"{COOKIE_NAME}={tok}".encode()))
    return Request({"type": "http", "headers": headers, "method": "GET", "path": "/", "query_string": b"",
                    "client": ("1.2.3.4", 1234)})


async def attempt(coro):
    """('ok', value) or ('http', status, detail) or ('err', repr)."""
    try:
        return ("ok", await coro)
    except HTTPException as e:
        return ("http", e.status_code, e.detail)
    except Exception as e:  # control run: the feature does not exist
        return ("err", f"{type(e).__name__}: {e}")


async def main() -> None:
    from app.models.db import Base, Organisation, VoteBallot
    from app.routers import public_availability as pa
    from app.routers import public_votes as pv
    from app.routers import votes as vr
    from app.services import votes as vs
    from app.services import vote_medal_ddl as ddl

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    stmts = getattr(ddl, "VOTE_GRADE_COUNTER_STATEMENTS", None)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    # ── Migration ──
    if stmts:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE vote_medals DROP COLUMN IF EXISTS grade_vote_counters"))
            for _ in range(3):
                for stmt in stmts:
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            col = (await conn.execute(text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name='vote_medals' AND column_name='grade_vote_counters'"))).first()
        check("migration adds grade_vote_counters, NOT NULL, default empty, safe to re-run",
              col is not None and col[1] == "NO" and "{}" in (col[0] or ""), str(col))
    else:
        check("migration adds grade_vote_counters", False, "no VOTE_GRADE_COUNTER_STATEMENTS")

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)

        from app.models.db import VoteMedal
        medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True,
                          link_token="tok-cc", voter_mode="players",
                          grade_voter_modes={"1st Grade": "captain"})
        db.add(medal)
        await db.commit()
        mid = str(medal.id)
        Body = vr.MedalUpdate

        async def patch(**kw):
            return await attempt(vr.update_medal(mid, Body(**kw), db=db, club=club, user=None))

        # ── Before anyone is nominated nothing changes (control for the rest) ──
        await db.refresh(medal)
        cfg0 = vs.effective_config(medal)
        fx_firsts = await db.get(__import__("app.models.db", fromlist=["Fixture"]).Fixture, FX_FIRSTS)
        cfg_f0 = await vs.cfg_for_fixture(db, cfg0, fx_firsts)
        eligible = [
            {"id": str(CAPTAIN), "name": "Captain Cook", "is_captain": True},
            {"id": str(JOE), "name": "Regular Joe", "is_captain": False},
            {"id": str(SAM), "name": "Sam Side", "is_captain": False},
        ]
        from app.models.db import Player
        helper = await db.get(Player, HELPER)
        joe = await db.get(Player, JOE)
        cook = await db.get(Player, CAPTAIN)
        check("no counter: the captain votes", pv._voter_role(cfg_f0, cook, eligible)[0] == "player")
        check("no counter: a player is told it is captain only",
              pv._voter_role(cfg_f0, joe, eligible) == ("none", "captain_only"))
        check("no counter: someone not in the side cannot vote",
              pv._voter_role(cfg_f0, helper, eligible) == ("none", "did_not_play"),
              str(pv._voter_role(cfg_f0, helper, eligible)))
        landing0 = await pv.get_landing("tok-cc", request(HELPER), db)
        check("no counter: a helper who did not play is offered no games", landing0["fixtures"] == [],
              str(landing0["fixtures"]))
        due0, _ = await pa._votes_for_player(db, club, helper)
        check("no counter: nothing due for the helper", due0 == [], str(due0))

        # ── Nominate through the shipped PATCH ──
        r = await patch(grade_vote_counters={"1st Grade": str(HELPER)})
        saved = r[1].get("grade_vote_counters") if r[0] == "ok" else r
        check("PATCH stores a counter per team", saved == {"1st Grade": str(HELPER)}, str(saved))
        names = r[1].get("vote_counter_names") if r[0] == "ok" else None
        check("the payload names the nominee", names == {"1st Grade": "Helen Helper"}, str(names))
        r2 = await patch(name="Club Champion")
        check("a PATCH that does not send counters leaves them alone",
              r2[0] == "ok" and r2[1].get("grade_vote_counters") == {"1st Grade": str(HELPER)}, str(r2))

        # ── Refused nominations ──
        for label, who in (("another club's player", OUTSIDER), ("a record that is not a player", SUPPORTER),
                           ("an unknown id", uuid.uuid4())):
            bad = await patch(grade_vote_counters={"1st Grade": str(who)})
            check(f"{label} is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad))
        bad = await patch(grade_vote_counters={"1st Grade": "not-a-uuid"})
        check("a malformed id is refused (400)", bad[0] == "http" and bad[1] == 400, str(bad))
        r3 = await patch(name="Club Champion")
        check("a refused PATCH changed nothing",
              r3[0] == "ok" and r3[1].get("grade_vote_counters") == {"1st Grade": str(HELPER)}, str(r3))

        # ── Resolution ──
        await db.refresh(medal)
        cfg = vs.effective_config(medal)
        cfg_f = await vs.cfg_for_fixture(db, cfg, fx_firsts)
        check("the captain-only team resolves to its counter", cfg_f.get("vote_counter") == str(HELPER),
              str(cfg_f.get("vote_counter")))
        Fixture = type(fx_firsts)
        fx_colts = await db.get(Fixture, FX_COLTS)
        cfg_c = await vs.cfg_for_fixture(db, cfg, fx_colts)
        check("a team with no nomination has no counter", cfg_c.get("vote_counter") is None)

        # ── The voting rule ──
        check("counter who was not in the side may vote",
              pv._voter_role(cfg_f, helper, eligible) == ("player", None), str(pv._voter_role(cfg_f, helper, eligible)))
        check("the captain no longer votes for that team (one ballot per team)",
              pv._voter_role(cfg_f, cook, eligible) == ("none", "counter_only"), str(pv._voter_role(cfg_f, cook, eligible)))
        check("another player is refused with the counter reason",
              pv._voter_role(cfg_f, joe, eligible) == ("none", "counter_only"))
        check("Colts (all players) is unaffected: a player votes", pv._voter_role(cfg_c, joe, eligible)[0] == "player")
        check("Colts: the helper is still not on that list",
              pv._voter_role(cfg_c, helper, eligible) == ("none", "did_not_play"))

        # ── Counter on a team that is not captain-only does nothing ──
        medal.grade_voter_modes = {"1st Grade": "players"}
        await db.commit()
        cfg_p = await vs.cfg_for_fixture(db, vs.effective_config(medal), fx_firsts)
        check("a counter on an all-players team is ignored",
              cfg_p.get("vote_counter") is None and pv._voter_role(cfg_p, helper, eligible)[0] == "none"
              and pv._voter_role(cfg_p, joe, eligible)[0] == "player")
        medal.grade_voter_modes = {"1st Grade": "captain"}
        await db.commit()
        cfg = vs.effective_config(medal)

        # ── Landing list and the player's reminder ──
        landing = await pv.get_landing("tok-cc", request(HELPER), db)
        ids = [f["id"] for f in landing["fixtures"]]
        check("the helper is offered that team's game", ids == [str(FX_FIRSTS)], str(ids))
        landing_joe = await pv.get_landing("tok-cc", request(JOE), db)
        check("a player in both sides still sees both games (control: list not widened for them)",
              {f["id"] for f in landing_joe["fixtures"]} == {str(FX_FIRSTS), str(FX_COLTS)})
        due, _ = await pa._votes_for_player(db, club, helper)
        check("the helper's page lists the vote as due",
              [d["fixture_id"] for d in due] == [str(FX_FIRSTS)], str(due))

        # ── Public ballot page and submit ──
        page = await attempt(pv.fixture_state("tok-cc", str(FX_FIRSTS), request(HELPER), db))
        ok = page[0] == "ok"
        check("ballot page: helper may vote and is told they are the counter",
              ok and page[1]["role"] == "player" and page[1].get("is_counter") is True, str(page))
        check("ballot page: helper is handed the team list",
              ok and len(page[1]["players"]) == 3, str(page[1]["players"]) if ok else str(page))
        page_cook = await pv.fixture_state("tok-cc", str(FX_FIRSTS), request(CAPTAIN), db)
        check("ballot page: the captain is told the counter votes",
              page_cook["role"] == "none" and page_cook["reason"] == "counter_only" and page_cook["players"] == [],
              str((page_cook["role"], page_cook["reason"])))

        BallotBody = pv.BallotBody
        # Default ballot is 3-2-1.
        picks = [str(CAPTAIN), str(JOE), str(SAM)]
        refused = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=picks), request(CAPTAIN), db))
        check("the captain's own submit is refused (403)", refused[0] == "http" and refused[1] == 403, str(refused))
        outside = await attempt(pv.submit_ballot(
            "tok-cc", str(FX_FIRSTS), BallotBody(picks=[str(HELPER), str(JOE), str(SAM)]), request(HELPER), db))
        check("the helper cannot vote for themselves (they were not in the side)",
              outside[0] == "http" and outside[1] == 400, str(outside))
        done = await attempt(pv.submit_ballot("tok-cc", str(FX_FIRSTS), BallotBody(picks=picks), request(HELPER), db))
        check("the helper's ballot is accepted", done[0] == "ok", str(done))
        rows = (await db.execute(select(VoteBallot).where(VoteBallot.fixture_id == FX_FIRSTS))).scalars().all()
        check("exactly one ballot, from the helper, recorded as a player ballot",
              len(rows) == 1 and rows[0].voter_player_id == HELPER and rows[0].voter_kind == "player",
              str([(r.voter_player_id, r.voter_kind) for r in rows]))
        due2, cast2 = await pa._votes_for_player(db, club, helper)
        check("after voting it is no longer due and shows in their own votes",
              due2 == [] and [c["fixture_id"] for c in cast2] == [str(FX_FIRSTS)], str((due2, cast2)))

        # ── Admin ──
        detail = await attempt(vr.fixture_detail(str(FX_FIRSTS), medal_id=mid, db=db, club=club, user=None))
        vc = detail[1]["settings"].get("vote_counter") if detail[0] == "ok" else detail
        check("admin game detail names the counter for the game's team",
              vc == {"id": str(HELPER), "name": "Helen Helper"}, str(vc))
        detail_c = await vr.fixture_detail(str(FX_COLTS), medal_id=mid, db=db, club=club, user=None)
        check("admin game detail has no counter for another team", detail_c["settings"].get("vote_counter") is None)

        # Paper ballot entered for the helper counts as a player ballot, not a non-player one.
        entered = await attempt(vr.admin_enter_ballot(
            str(FX_FIRSTS), vr.AdminBallot(voter_player_id=str(HELPER), picks=picks),
            medal_id=mid, db=db, club=club, user=type("U", (), {"id": None})()))
        rows = (await db.execute(select(VoteBallot).where(VoteBallot.fixture_id == FX_FIRSTS))).scalars().all()
        check("admin entry for the counter replaces their ballot and stays a player ballot",
              entered[0] == "ok" and len(rows) == 1 and rows[0].voter_kind == "player", str(entered))

        # ── Roster for the picker ──
        counter_options = getattr(vr, "counter_options", None)
        opts = await attempt(counter_options(db=db, club=club, user=None)) if counter_options else ("err", "no counter_options route")
        got = {p["id"] for p in opts[1]["players"]} if opts[0] == "ok" else set()
        check("picker offers the helper who is not in any side", str(HELPER) in got, str(opts)[:200])
        check("picker never offers another club's player", str(OUTSIDER) not in got)

        # ── Clearing ──
        r4 = await patch(grade_vote_counters={"1st Grade": None})
        check("a null removes that team's counter", r4[0] == "ok" and r4[1].get("grade_vote_counters") == {}, str(r4))
        await patch(grade_vote_counters={"1st Grade": str(HELPER)})
        r5 = await patch(grade_vote_counters={})
        check("an explicit empty map clears every counter", r5[0] == "ok" and r5[1].get("grade_vote_counters") == {}, str(r5))
        await db.refresh(medal)
        cfg_after = await vs.cfg_for_fixture(db, vs.effective_config(medal), fx_firsts)
        check("after clearing, the captain votes again",
              pv._voter_role(cfg_after, cook, eligible)[0] == "player"
              and pv._voter_role(cfg_after, helper, eligible)[0] == "none")

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
