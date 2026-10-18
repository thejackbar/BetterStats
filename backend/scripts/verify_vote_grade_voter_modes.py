"""Verification for the vote settings picker (active grades only) and the
per-team voter mode (migration 345) against a real Postgres.

Runs the SHIPPED statements, service functions and route bodies. New keys are
read through presence-safe accessors, so the same script run against the
previous commit reports FAIL lines instead of crashing (the control run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_grade_voter_modes.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

DSN = os.environ["DATABASE_URL"]
PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


TODAY = date.today()
YEAR = TODAY.year if TODAY.month >= 7 else TODAY.year - 1
PLAYED = date(YEAR, 10, 1) if date(YEAR, 10, 1) <= TODAY else date(YEAR, 7, 15)

ORG = uuid.uuid4()
S_OLD, S_CUR, S_EMPTY = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_FIRSTS_OLD, G_COLTS_OLD, G_LADIES_OLD = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
G_FIRSTS, G_COLTS, G_U12 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FX_FIRSTS, FX_COLTS_OLDROW, FX_NOGRADE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
CAPTAIN, PLAYER = uuid.uuid4(), uuid.uuid4()
GAME = uuid.uuid4()


async def seed(db) -> None:
    from app.models.db import Fixture, Game, GameAppearance, Grade, Organisation, Player, Season

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    # An old season with a team the club no longer fields, the current season,
    # and a newer season whose grades have not synced yet (falls back).
    db.add(Season(id=S_OLD, organisation_id=ORG, name="Old", year=YEAR - 2))
    db.add(Season(id=S_CUR, organisation_id=ORG, name="Current", year=YEAR))
    db.add(Season(id=S_EMPTY, organisation_id=ORG, name="Just started", year=YEAR + 1))
    await db.flush()
    for gid, nm in ((G_FIRSTS_OLD, "1st Grade"), (G_COLTS_OLD, "Colts"), (G_LADIES_OLD, "Old Ladies")):
        db.add(Grade(id=gid, season_id=S_OLD, name=nm))
    for gid, nm in ((G_FIRSTS, "1st Grade"), (G_COLTS, "Colts"), (G_U12, "Under 12")):
        db.add(Grade(id=gid, season_id=S_CUR, name=nm))
    db.add(Player(id=CAPTAIN, organisation_id=ORG, name="Captain Cook", email="c@example.com"))
    db.add(Player(id=PLAYER, organisation_id=ORG, name="Regular Joe", email="j@example.com"))
    await db.flush()
    db.add(Game(id=GAME, grade_id=G_FIRSTS))
    await db.flush()
    db.add(GameAppearance(game_id=GAME, player_id=CAPTAIN, is_captain=True))
    db.add(GameAppearance(game_id=GAME, player_id=PLAYER, is_captain=False))
    for fid, grade, opp in (
        (FX_FIRSTS, G_FIRSTS, "Melville"),
        # Stored against the OLD season's Colts row: the per-team setting is
        # keyed by name, so it must still resolve to "Colts".
        (FX_COLTS_OLDROW, G_COLTS_OLD, "Melville Colts"),
        (FX_NOGRADE, None, "Mystery"),
    ):
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round="5",
                       played_on=PLAYED, end_on=PLAYED, home_away="H", grade_id=grade,
                       playhq_id=str(GAME) if fid == FX_FIRSTS else None))
    await db.commit()


def request() -> Request:
    return Request({"type": "http", "headers": [], "method": "GET", "path": "/", "query_string": b""})


async def main() -> None:
    from app.models.db import Base, Organisation, VoteMedal
    from app.routers import public_votes as pv
    from app.routers import votes as vr
    from app.services import votes as vs
    from app.services import vote_medal_ddl as ddl

    engine = create_async_engine(DSN, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    has_feature = hasattr(ddl, "VOTE_GRADE_MODE_STATEMENTS")

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    # ── Migration ──
    if has_feature:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE vote_medals DROP COLUMN IF EXISTS grade_voter_modes"))
            for _ in range(3):
                for stmt in ddl.VOTE_GRADE_MODE_STATEMENTS:
                    await conn.execute(text(stmt))
        async with engine.connect() as conn:
            col = (await conn.execute(text(
                "SELECT column_default, is_nullable FROM information_schema.columns "
                "WHERE table_name='vote_medals' AND column_name='grade_voter_modes'"))).first()
        check("migration adds grade_voter_modes, NOT NULL, default empty, safe to re-run",
              col is not None and col[1] == "NO" and "{}" in (col[0] or ""), str(col))
    else:
        check("migration adds grade_voter_modes", False, "no VOTE_GRADE_MODE_STATEMENTS")

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)

        # ── Active grades only ──
        opts = await vs.club_grade_options(db, ORG)
        names = {o["name"] for o in opts}
        check("picker offers the current season's grades",
              {"1st Grade", "Colts", "Under 12"} <= names, str(names))
        check("picker drops a grade only an old season had", "Old Ladies" not in names, str(names))
        check("a newer season with no grades yet does not empty the picker", len(opts) == 3, str(names))
        cur_ids = {str(G_FIRSTS), str(G_COLTS), str(G_U12)}
        check("each option carries the current season's id",
              {o["id"] for o in opts} == cur_ids, str(opts))

        # ── A medal still ticking an inactive grade ──
        medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True,
                          link_token="tok-cc", grade_ids=[str(G_LADIES_OLD), str(G_COLTS_OLD)])
        db.add(medal)
        await db.commit()
        payloads = await vr._medals_payload(db, club)
        p = payloads[0]
        inactive = [g["name"] for g in (p.get("inactive_grades") or [])]
        check("a ticked grade no longer played is reported as inactive", inactive == ["Old Ladies"], str(inactive))
        check("a ticked grade that is still played is not reported inactive",
              "Colts" not in inactive and "Colts" in p["grade_names"], str(p.get("grade_names")))
        # The medal keeps counting it until the club unticks it.
        allowed = await vs.medal_grade_ids(db, ORG, medal)
        check("an inactive ticked grade still counts until unticked",
              str(G_LADIES_OLD) in (allowed or set()), str(allowed))

        # ── Per-team voter mode: write through the shipped PATCH body ──
        Body = vr.MedalUpdate
        body_kwargs = {"grade_voter_modes": {"1st Grade": "captain", "Colts": "players"}}
        try:
            out = await vr.update_medal(str(medal.id), Body(**body_kwargs), db=db, club=club, user=None)
            saved = out.get("grade_voter_modes")
        except Exception as e:  # control run: the field does not exist
            saved = f"{type(e).__name__}: {e}"
        check("PATCH stores a mode per team",
              saved == {"1st Grade": "captain", "Colts": "players"}, str(saved))
        check("medal default is untouched by a team setting", (out or {}).get("voter_mode") == "players"
              if isinstance(saved, dict) else False)

        out2 = await vr.update_medal(str(medal.id), Body(name="Club Champion"), db=db, club=club, user=None)
        check("a PATCH that does not send teams leaves them alone",
              out2.get("grade_voter_modes") == {"1st Grade": "captain", "Colts": "players"},
              str(out2.get("grade_voter_modes")))

        bad_status = None
        try:
            await vr.update_medal(str(medal.id), Body(grade_voter_modes={"1st Grade": "everyone"}),
                                  db=db, club=club, user=None)
        except HTTPException as e:
            bad_status = e.status_code
        except Exception as e:
            bad_status = type(e).__name__
        check("an unknown mode for a team is refused (400)", bad_status == 400, str(bad_status))
        out3 = await vr.update_medal(str(medal.id), Body(name="Club Champion"), db=db, club=club, user=None)
        check("a refused PATCH changed nothing",
              out3.get("grade_voter_modes") == {"1st Grade": "captain", "Colts": "players"})

        # ── Resolution per fixture ──
        await db.refresh(medal)
        cfg = vs.effective_config(medal)
        cfg_for = getattr(vs, "cfg_for_fixture", None)

        async def mode_of(fid):
            from app.models.db import Fixture
            fx = await db.get(Fixture, fid)
            if cfg_for is None:
                return cfg["voter_mode"]
            return (await cfg_for(db, cfg, fx))["voter_mode"]

        check("a captain-only team resolves to captain", await mode_of(FX_FIRSTS) == "captain")
        check("another team on 'players' stays players", await mode_of(FX_COLTS_OLDROW) == "players")
        # Flip the medal default to captain: Colts has its own setting so it must not follow.
        medal.voter_mode = "captain"
        await db.commit()
        cfg = vs.effective_config(medal)
        check("a team's own setting beats the medal default (Colts stays players)",
              await mode_of(FX_COLTS_OLDROW) == "players")
        check("a fixture with no resolvable team follows the medal default",
              await mode_of(FX_NOGRADE) == "captain")
        medal.voter_mode = "players"
        medal.grade_voter_modes = {"1st Grade": "captain"}
        await db.commit()
        cfg = vs.effective_config(medal)
        check("a team with no setting follows the medal default",
              await mode_of(FX_COLTS_OLDROW) == "players")

        # ── The voting rule itself, through the public page's role function ──
        from app.models.db import Fixture, Player
        joe = await db.get(Player, PLAYER)
        cook = await db.get(Player, CAPTAIN)
        eligible = [{"id": str(PLAYER), "name": "Regular Joe", "is_captain": False},
                    {"id": str(CAPTAIN), "name": "Captain Cook", "is_captain": True}]
        fx_firsts = await db.get(Fixture, FX_FIRSTS)
        fx_colts = await db.get(Fixture, FX_COLTS_OLDROW)
        cfg_f = (await cfg_for(db, cfg, fx_firsts)) if cfg_for else cfg
        cfg_c = (await cfg_for(db, cfg, fx_colts)) if cfg_for else cfg
        check("1st Grade: a non-captain player may not vote",
              pv._voter_role(cfg_f, joe, eligible) == ("none", "captain_only"),
              str(pv._voter_role(cfg_f, joe, eligible)))
        check("1st Grade: the captain may vote", pv._voter_role(cfg_f, cook, eligible)[0] == "player")
        check("Colts: every player may vote (control: same player, other team)",
              pv._voter_role(cfg_c, joe, eligible)[0] == "player")

        # ── Route bodies: admin game detail and the public ballot page ──
        detail = await vr.fixture_detail(str(FX_FIRSTS), medal_id=str(medal.id), db=db, club=club, user=None)
        check("admin game detail reports this game's team mode",
              detail["settings"]["voter_mode"] == "captain", str(detail["settings"]["voter_mode"]))
        pub_f = await pv.fixture_state("tok-cc", str(FX_FIRSTS), request(), db)
        pub_c = await pv.fixture_state("tok-cc", str(FX_COLTS_OLDROW), request(), db)
        check("public ballot page reports 1st Grade as captain only", pub_f["voter_mode"] == "captain", str(pub_f["voter_mode"]))
        check("public ballot page reports Colts as all players", pub_c["voter_mode"] == "players", str(pub_c["voter_mode"]))

        # ── Clearing ──
        out4 = await vr.update_medal(str(medal.id), Body(grade_voter_modes={}), db=db, club=club, user=None)
        check("an explicit empty map clears every team setting", out4.get("grade_voter_modes") == {},
              str(out4.get("grade_voter_modes")))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
