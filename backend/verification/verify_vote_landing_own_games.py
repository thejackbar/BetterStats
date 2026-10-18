"""Verification: the public voting page only offers a verified player the games they played.

Reported: "From that voting page, if I click 'back to games' I can see all the other
games. None of these should even be viewable if you haven't played in them."

Drives the SHIPPED `public_votes.get_landing` and `fixture_state` against a real
Postgres with a real medal, fixtures, saved XIs, a synced scorecard and ballots.

CONTROL MODE: against the previous commit the landing lists every game to a verified
player; every read here is presence-safe so the control fails the checks, not crashes.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_vote_landing_own_games.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

import verify_selection_same_day as base
from app.config.settings import settings
from app.models.db import Fixture, FixtureLineup, Game, GameAppearance, Grade, Organisation, Player, Season, VoteBallot, VoteBallotPick, VoteMedal

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    import app.routers.public_votes as pv

    org = uuid.uuid4()
    sam, ann, bob = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    vtok = "v-" + uuid.uuid4().hex
    medal = uuid.uuid4()
    today = date.today()
    f1, f2, f3 = (uuid.uuid4() for _ in range(3))
    season, g_a, g_b, game, fsync = (uuid.uuid4() for _ in range(5))
    async with Session() as db:
        db.add(Organisation(id=org, name="Land CC", slug=f"lc-{org.hex[:8]}", module_overrides=["select"]))
        await db.flush()
        for pid, nm in ((sam, "Sam Sledge"), (ann, "Ann Anchor"), (bob, "Bob Bystander")):
            db.add(Player(id=pid, organisation_id=org, name=nm, is_player=True, status="active", phone="0400000111"))
        db.add(VoteMedal(id=medal, organisation_id=org, name="Dunslow Medal", link_token=vtok, enabled=True, require_pin=True))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_a, season_id=season, name="1st Grade"))
        db.add(Grade(id=g_b, season_id=season, name="2nd Grade"))
        await db.flush()
        # f1 (1st Grade, Round 1): Sam and Ann. f2 (2nd Grade, Round 2): Ann only. f3 (1st Grade, Round 3): Sam, on the synced scorecard.
        for fid, days, opp, gid, rnd in ((f1, 3, "Rovers", g_a, "1"), (f2, 2, "Saints", g_b, "2")):
            db.add(Fixture(id=fid, organisation_id=org, grade_id=gid, source="manual", played_on=today - timedelta(days=days),
                           status="COMPLETED", opponent_name=opp, label=opp, round=rnd))
        await db.flush()
        for fid, pid in ((f1, sam), (f1, ann), (f2, ann)):
            db.add(FixtureLineup(fixture_id=fid, player_id=pid, organisation_id=org, batting_order=1))
        db.add(Game(id=game, grade_id=g_a, played_at=datetime.now(timezone.utc) - timedelta(days=1), home_team="Land CC 1st", away_team="Wanderers"))
        await db.flush()
        db.add(Fixture(id=fsync, organisation_id=org, grade_id=g_a, source="grassroots", playhq_id=str(game),
                       played_on=today - timedelta(days=1), status="COMPLETED", opponent_name="Wanderers", label="Wanderers", round="3"))
        await db.flush()
        db.add(GameAppearance(game_id=game, player_id=sam, team_name="Land CC 1st"))
        await db.commit()

    def req_for(pid):
        if pid is None:
            return Request({"type": "http", "headers": []})
        c = jose_jwt.encode({"club": str(org), "pid": str(pid), "typ": "vote",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pv.COOKIE_NAME}={c}".encode())]})

    async def landing(pid, **kw):
        async with Session() as db:
            return await pv.get_landing(vtok, req_for(pid), db, **kw)

    async def fixture_page(pid, fid):
        async with Session() as db:
            return await pv.fixture_state(vtok, str(fid), req_for(pid), db)

    opp = lambda d: sorted(f.get("opponent") for f in (d.get("fixtures") or []))

    print("\n# A. Who is offered which games")
    d = await landing(None)
    check("someone who has not said who they are sees the club's list (they have to find their game)", opp(d), ["Rovers", "Saints", "Wanderers"])
    d = await landing(sam)
    check("Sam sees only the two he played: a saved XI and a synced scorecard", opp(d), ["Rovers", "Wanderers"])
    d = await landing(ann)
    check("Ann sees the two she played", opp(d), ["Rovers", "Saints"])
    d = await landing(bob)
    check("Bob played nothing and is offered nothing", opp(d), [])

    print("\n# B. The filter lists follow the same cut")
    d = await landing(sam)
    check("Sam's team list holds only 1st Grade, not 2nd", sorted(g.get("name") for g in d.get("grades") or []), ["1st Grade"])
    check("his rounds are 1 and 3 and not 2", sorted(r.get("label") for r in d.get("rounds") or []), ["Round 1", "Round 3"])
    d_all = await landing(None)
    check("the unidentified list still carries both teams (the control that the cut is not just missing data)", len(d_all.get("grades") or []), 2)
    d = await landing(sam, team=str(g_b))
    check("asking for a team he is not in gives him nothing, not that team's games", opp(d), [])

    print("\n# C. A game he has voted on is marked, and still listed so he can change it")
    async with Session() as db:
        b = uuid.uuid4()
        db.add(VoteBallot(id=b, organisation_id=org, medal_id=medal, fixture_id=f1, voter_player_id=sam, voter_kind="player"))
        await db.flush()
        db.add(VoteBallotPick(ballot_id=b, position=1, player_id=ann))
        await db.commit()
    d = await landing(sam)
    voted = {f.get("opponent"): f.get("voted") for f in d.get("fixtures") or []}
    check("Rovers reads voted and Wanderers does not", voted, {"Rovers": True, "Wanderers": False})
    d = await landing(ann)
    check("Ann's list is unmarked: Sam's ballot is not hers", {f.get("opponent"): f.get("voted") for f in d.get("fixtures") or []}, {"Rovers": False, "Saints": False})

    print("\n# D. The ballot page does not hand a team list to someone who cannot vote on it")
    page = await fixture_page(bob, f1)
    check("Bob opening Rovers is told he did not play", (page.get("role"), page.get("reason")), ("none", "did_not_play"))
    check("and gets no team list", page.get("players"), [])
    page = await fixture_page(sam, f1)
    check("Sam opening Rovers gets the team list", sorted(p.get("name") for p in page.get("players") or []), ["Ann Anchor", "Sam Sledge"])
    check("and his own ballot", (page.get("my_ballot") or [None])[0], str(ann))

    print("\n# E. A club that lets coaches and supporters vote")
    async with Session() as db:
        m = await db.get(VoteMedal, medal)
        m.allow_non_participants = True
        await db.commit()
    check("an unidentified visitor still sees the club's list", opp(await landing(None)), ["Rovers", "Saints", "Wanderers"])
    page = await fixture_page(None, f1)
    check("and can still open a ballot", (page.get("role"), len(page.get("players") or [])), ("non_player", 2))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  -", f)
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
