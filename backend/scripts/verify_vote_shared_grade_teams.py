"""Verification for two of a club's teams playing ONE grade, each with its own
voters (Applecross 8th and 10th XI in One Day Grade 6 Black) against a real Postgres.

The bug: "who votes" and the people chosen to vote were stored per grade NAME, so
the two teams shared one entry and only the people chosen for one team could vote
for the other. Teams are now told apart by ``fixtures.team_id`` and stored under
"<grade name>::<team id>".

Runs the SHIPPED service functions and route bodies. New keys and functions are
read through presence-safe accessors, so the same script run against the previous
commit reports FAIL lines instead of crashing (the control run).

Usage:  cd backend && DATABASE_URL=postgresql+asyncpg://... \
            python scripts/verify_vote_shared_grade_teams.py
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
OD6 = "One Day Grade 6 Black"

ORG = uuid.uuid4()
SEASON, G_OD6, G_FIRSTS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
T8, T10, T1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
FX8, FX10, FX1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
GAME8, GAME10, GAME1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
# Chosen for the 8th XI, chosen for the 10th XI, and the sides themselves.
A1, A2, A3 = (uuid.uuid4() for _ in range(3))
B1, B2, B3 = (uuid.uuid4() for _ in range(3))
S8 = [uuid.uuid4() for _ in range(3)]
S10 = [uuid.uuid4() for _ in range(3)]
S1 = [uuid.uuid4() for _ in range(2)]


async def seed(db) -> None:
    from app.models.db import Fixture, Game, GameAppearance, Grade, Organisation, Player, Season, Team

    db.add(Organisation(id=ORG, name="Applecross CC", short_name="ACC", slug="applecross", module_overrides=["select"]))
    await db.flush()
    year = PLAYED.year if PLAYED.month >= 7 else PLAYED.year - 1
    db.add(Season(id=SEASON, organisation_id=ORG, name="Current", year=year))
    await db.flush()
    db.add(Grade(id=G_OD6, season_id=SEASON, name=OD6))
    db.add(Grade(id=G_FIRSTS, season_id=SEASON, name="1st Grade"))
    await db.flush()
    db.add(Team(id=T8, organisation_id=ORG, name="Applecross 8th XI", short_name="8th XI", sequence=8, grade_id=G_OD6))
    db.add(Team(id=T10, organisation_id=ORG, name="Applecross 10th XI", short_name="10th XI", sequence=10, grade_id=G_OD6))
    db.add(Team(id=T1, organisation_id=ORG, name="Applecross 1st XI", short_name="1st XI", sequence=1, grade_id=G_FIRSTS))
    names = {}
    for who, nm in ((A1, "Alf Eighth"), (A2, "Abe Eighth"), (A3, "Art Eighth"),
                    (B1, "Bob Tenth"), (B2, "Ben Tenth"), (B3, "Bill Tenth")):
        names[who] = nm
    for i, who in enumerate(S8):
        names[who] = f"Eighth Side {i}"
    for i, who in enumerate(S10):
        names[who] = f"Tenth Side {i}"
    for i, who in enumerate(S1):
        names[who] = f"First Side {i}"
    for pid, nm in names.items():
        db.add(Player(id=pid, organisation_id=ORG, name=nm, email=f"{pid.hex[:8]}@example.com", is_player=True))
    await db.flush()
    for gid, grade in ((GAME8, G_OD6), (GAME10, G_OD6), (GAME1, G_FIRSTS)):
        db.add(Game(id=gid, grade_id=grade))
    await db.flush()
    for game, side in ((GAME8, S8), (GAME10, S10), (GAME1, S1)):
        for i, pid in enumerate(side):
            db.add(GameAppearance(game_id=game, player_id=pid, is_captain=(i == 0)))
    for fid, grade, team, game, opp in ((FX8, G_OD6, T8, GAME8, "Bentley 3rd XI"), (FX10, G_OD6, T10, GAME10, "Bentley 4th XI"),
                                        (FX1, G_FIRSTS, T1, GAME1, "Melville")):
        db.add(Fixture(id=fid, organisation_id=ORG, opponent_name=opp, round="2", played_on=PLAYED, end_on=PLAYED,
                       home_away="H", grade_id=grade, team_id=team, playhq_id=str(game)))
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

    shared_fn = getattr(vs, "shared_grade_teams", None)
    split_fn = getattr(vs, "split_legacy_team_settings", None)

    async with Session() as db:
        await seed(db)
        club = await db.get(Organisation, ORG)
        fx8, fx10, fx1 = [await db.get(Fixture, f) for f in (FX8, FX10, FX1)]
        p = {pid: await db.get(Player, pid) for pid in (A1, A2, A3, B1, B2, B3, *S8, *S10, *S1)}

        # The club set this up while it thought of the two teams as one: one grade
        # name, three people. They were chosen for the 8th XI.
        medal = VoteMedal(organisation_id=ORG, name="Club Champion", position=0, enabled=True, link_token="tok-cc",
                          voter_mode="players",
                          grade_voter_modes={OD6: "chosen"},
                          grade_vote_counters={OD6: [str(A1), str(A2), str(A3)]})
        db.add(medal)
        await db.commit()
        mid = str(medal.id)
        Body = vr.MedalUpdate

        async def patch(**kw):
            async def run():
                return await vr.update_medal(mid, Body(**kw), db=db, club=club, user=None)
            return await attempt(run())

        async def cfg_for(fx):
            await db.refresh(medal)
            return await vs.cfg_for_fixture(db, vs.effective_config(medal), fx)

        eligible8 = [{"id": str(pid), "name": f"Eighth Side {i}", "is_captain": i == 0} for i, pid in enumerate(S8)]
        eligible10 = [{"id": str(pid), "name": f"Tenth Side {i}", "is_captain": i == 0} for i, pid in enumerate(S10)]

        # ── The two teams are found ──
        shared = await shared_fn(db, ORG) if shared_fn else None
        teams = (shared or {}).get(OD6, [])
        check("the grade two teams play is found, with both teams",
              [t["name"] for t in teams] == ["8th XI", "10th XI"], str(shared))
        check("a grade only one team plays is not listed as shared", shared is not None and "1st Grade" not in shared, str(shared))
        key8, key10 = (teams[0]["key"], teams[1]["key"]) if len(teams) == 2 else ("?8", "?10")

        # ── What the club had, before it set each team: both teams read the one entry ──
        cfg8 = await cfg_for(fx8)
        check("before it is split, the 8th XI has its chosen three", cfg8.get("vote_chosen") == [str(A1), str(A2), str(A3)],
              str(cfg8.get("vote_chosen")))
        # The report itself: with one entry for the grade, the 10th XI's game gets the 8th XI's people.
        cfg10_before = await cfg_for(fx10)
        check("the report: one entry for the grade puts the 8th XI's people on the 10th XI's game (until each team is set)",
              cfg10_before.get("vote_chosen") == [str(A1), str(A2), str(A3)], str(cfg10_before.get("vote_chosen")))

        # ── The settings screen's payload: the entry shown once per team ──
        got = await attempt(vr._one_medal_payload(db, club, medal))
        pay = got[1] if got[0] == "ok" else {}
        opts = pay.get("team_options") or []
        check("the screen is offered one row per team in the shared grade, one for any other grade",
              [(o.get("key"), o.get("name")) for o in opts] == [
                  ("1st Grade", "1st Grade"), (key8, f"{OD6} · 8th XI"), (key10, f"{OD6} · 10th XI")], str(opts))
        check("the old entry is shown on both teams and no longer under the bare grade name",
              pay.get("grade_voter_modes") == {key8: "chosen", key10: "chosen"}
              and sorted(pay.get("grade_vote_counters", {})) == sorted([key8, key10])
              and OD6 not in pay.get("vote_chosen", {}), str(pay)[:300])

        # ── The club sets the 10th XI's own voters, sending only the counters ──
        r = await patch(grade_vote_counters={key8: [str(A1), str(A2), str(A3)], key10: [str(B1), str(B2), str(B3)]})
        check("the save is accepted", r[0] == "ok", str(r)[:200])
        await db.refresh(medal)
        check("saving only the people also moved the old mode onto each team, and dropped the old key",
              medal.grade_voter_modes == {key8: "chosen", key10: "chosen"}
              and OD6 not in (medal.grade_vote_counters or {}), str((medal.grade_voter_modes, medal.grade_vote_counters)))

        cfg8, cfg10 = await cfg_for(fx8), await cfg_for(fx10)
        check("the 8th XI's game has the 8th XI's people", cfg8.get("vote_chosen") == [str(A1), str(A2), str(A3)],
              str(cfg8.get("vote_chosen")))
        check("the 10th XI's game has the 10th XI's people", cfg10.get("vote_chosen") == [str(B1), str(B2), str(B3)],
              str(cfg10.get("vote_chosen")))

        # ── The reported bug ──
        check("a person chosen for the 8th XI cannot vote for the 10th XI",
              pv._voter_role(cfg10, p[A1], eligible10) == ("none", "chosen_only"), str(pv._voter_role(cfg10, p[A1], eligible10)))
        check("a person chosen for the 10th XI CAN vote for the 10th XI",
              pv._voter_role(cfg10, p[B1], eligible10) == ("player", None), str(pv._voter_role(cfg10, p[B1], eligible10)))
        check("a person chosen for the 10th XI cannot vote for the 8th XI",
              pv._voter_role(cfg8, p[B1], eligible8) == ("none", "chosen_only"))
        check("a person chosen for the 8th XI can vote for the 8th XI",
              pv._voter_role(cfg8, p[A2], eligible8) == ("player", None))

        page10 = await attempt(pv.fixture_state("tok-cc", str(FX10), request(B2), db))
        check("ballot page: the 10th XI's chosen person is a voter on the 10th XI game",
              page10[0] == "ok" and page10[1]["role"] == "player", str(page10)[:200])
        page10_wrong = await attempt(pv.fixture_state("tok-cc", str(FX10), request(A2), db))
        check("ballot page: the 8th XI's chosen person is not a voter on the 10th XI game",
              page10_wrong[0] == "ok" and page10_wrong[1]["role"] == "none", str(page10_wrong)[:200])

        for who, label, want in ((B1, "10th XI's", [str(FX10)]), (A1, "8th XI's", [str(FX8)])):
            landing = await pv.get_landing("tok-cc", request(who), db)
            ids = [f["id"] for f in landing["fixtures"]]
            check(f"the {label} chosen person is offered only their own team's game", ids == want, str(ids))

        # ── The admin screens ──
        detail10 = await attempt(vr.fixture_detail(str(FX10), medal_id=mid, db=db, club=club, user=None))
        check("admin game detail for the 10th XI lists the 10th XI's people",
              detail10[0] == "ok" and [c["name"] for c in detail10[1]["settings"]["vote_chosen"]]
              == ["Bob Tenth", "Ben Tenth", "Bill Tenth"], str(detail10)[:200])
        listing = await attempt(vr.list_vote_fixtures(
            year=None, grade_id=None, round_key=None, q=None, medal_id=mid, db=db, club=club, user=None))
        rows = {f["id"]: f for f in listing[1]["fixtures"]} if listing[0] == "ok" else {}
        check("the Games list expects the chosen people on each team, the side on the other grade",
              rows.get(str(FX8), {}).get("voters_expected") == 3 and rows.get(str(FX10), {}).get("voters_expected") == 3
              and rows.get(str(FX1), {}).get("voters_expected") == 2,
              str({k[:4]: v.get("voters_expected") for k, v in rows.items()}))

        # ── One team changes, the other does not ──
        r = await patch(grade_voter_modes={key8: "chosen", key10: "players"})
        cfg8, cfg10 = await cfg_for(fx8), await cfg_for(fx10)
        check("the 10th XI switched to All players: the side votes, the 8th XI is still chosen only",
              r[0] == "ok" and cfg10["voter_mode"] == "players" and not cfg10["vote_chosen"]
              and cfg8["voter_mode"] == "chosen" and len(cfg8["vote_chosen"]) == 3, str((r[0], cfg8["voter_mode"], cfg10["voter_mode"])))
        check("the 10th XI's side can vote and the 8th XI's chosen person cannot",
              pv._voter_role(cfg10, p[S10[1]], eligible10)[0] == "player"
              and pv._voter_role(cfg10, p[A1], eligible10)[0] == "none")
        cfg1 = await cfg_for(fx1)
        check("a grade only one team plays is untouched (medal default, all players)",
              cfg1["voter_mode"] == "players" and pv._voter_role(cfg1, p[S1[1]], [
                  {"id": str(pid), "name": "x", "is_captain": False} for pid in S1])[0] == "player")

        # ── A one-team grade is still keyed by its name ──
        r = await patch(grade_voter_modes={key8: "chosen", "1st Grade": "captain"})
        cfg1 = await cfg_for(fx1)
        check("a one-team grade's setting is stored under its grade name and still applies",
              r[0] == "ok" and cfg1["voter_mode"] == "captain", str((r[0], cfg1["voter_mode"])))

        # ── The split is plain and repeatable ──
        if split_fn:
            once = split_fn({OD6: "chosen"}, {OD6: [str(A1)]}, shared)
            twice = split_fn(*once, shared)
            check("splitting twice changes nothing more", once == twice, str((once, twice)))
            check("splitting leaves a grade with one team alone",
                  split_fn({"1st Grade": "captain"}, {}, shared) == ({"1st Grade": "captain"}, {}))
        else:
            check("splitting is a function", False, "no split_legacy_team_settings")

        # ── A team that stops playing the grade is no longer a separate row ──
        await db.execute(text("UPDATE teams SET is_active = false WHERE id = :t"), {"t": T10})
        await db.commit()
        after = await shared_fn(db, ORG) if shared_fn else None
        check("an inactive team no longer makes the grade shared", after is not None and OD6 not in after, str(after))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
