"""Verification: the player's own page reminds them to vote.

Asked for: "In the player page, can we also add votes so if they're due to vote in
a game they've played that's still open they get reminded to do so through here."

Drives the SHIPPED `public_availability.get_my_profile` against a real Postgres
with a real voting medal, fixtures, lineups and ballots. A vote is DUE when the
game is open under an enabled medal with a link, the player is on that game's
votable list, and they have no ballot yet.

CONTROL MODE: against the previous commit the profile has no `votes`; every read is
presence-safe so the control fails the checks rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_votes_reminder.py
"""
from __future__ import annotations

import asyncio
import json
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
from app.models.db import Fixture, FixtureLineup, Organisation, Player, VoteBallot, VoteFixtureOverride, VoteMedal

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from sqlalchemy import text
    async with engine.begin() as conn:
        for mod in ("fines_ddl", "fines_cap_ddl"):
            try:
                import importlib
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
    import app.routers.public_availability as pa
    import app.services.player_dashboard as pd

    org = uuid.uuid4()
    sam, ann, bob = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    atok, vtok = "a-" + uuid.uuid4().hex, "v-" + uuid.uuid4().hex
    medal = uuid.uuid4()
    today = date.today()
    f1, f2, f3, f4 = (uuid.uuid4() for _ in range(4))
    async with Session() as db:
        db.add(Organisation(id=org, name="Vote CC", slug=f"vr-{org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=atok, availability_self_service_enabled=True))
        await db.flush()
        for pid, nm in ((sam, "Sam Sledge"), (ann, "Ann Anchor"), (bob, "Bob Bystander")):
            db.add(Player(id=pid, organisation_id=org, name=nm, is_player=True, status="active", phone="0400000111"))
        db.add(VoteMedal(id=medal, organisation_id=org, name="Dunslow Medal", link_token=vtok, enabled=True, require_pin=True))
        await db.flush()
        # f1: open, Sam and Ann played. f2: open, only Ann played. f3: too old to be open. f4: open, Sam played, he has voted.
        for fid, days, opp in ((f1, 2, "Rovers"), (f2, 1, "Saints"), (f3, 30, "Ancients"), (f4, 3, "Done Deal")):
            db.add(Fixture(id=fid, organisation_id=org, source="manual", played_on=today - timedelta(days=days),
                           status="COMPLETED", opponent_name=opp, label=opp, round="1"))
        await db.flush()
        for fid, pid in ((f1, sam), (f1, ann), (f2, ann), (f3, sam), (f4, sam), (f4, ann)):
            db.add(FixtureLineup(fixture_id=fid, player_id=pid, organisation_id=org, batting_order=1))
        await db.commit()
        db.add(VoteBallot(organisation_id=org, medal_id=medal, fixture_id=f4, voter_player_id=sam, voter_kind="player"))
        await db.commit()

    def req_for(pid):
        c = jose_jwt.encode({"club": str(org), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

    async def profile(pid):
        async with Session() as db:
            return await pa.get_my_profile(atok, req_for(pid), None, db)

    async def set_org(**kw):
        async with Session() as db:
            o = await db.get(Organisation, org)
            for k, v in kw.items():
                setattr(o, k, v)
            await db.commit()

    async def set_medal(**kw):
        async with Session() as db:
            m = await db.get(VoteMedal, medal)
            for k, v in kw.items():
                setattr(m, k, v)
            await db.commit()

    print("\n# A. Who is reminded")
    prof = await profile(sam)
    votes = prof.get("votes") or []
    check("Sam is reminded about the one open game he played and has not voted on", [v.get("opponent") for v in votes], ["Rovers"])
    check("the module is on his page", "votes" in (prof.get("modules") or []), True)
    v = (votes or [{}])[0]
    check("the reminder links to that game's ballot, with him already picked", v.get("link"), f"/vote/{vtok}?fixture={f1}&player={sam}")
    check("it says which medal, the round and when voting closes", (v.get("medal"), v.get("round"), v.get("closes_on")),
          ("Dunslow Medal", "Round 1", (today - timedelta(days=2) + timedelta(days=7)).isoformat()))
    check("a game he did not play is not listed (Saints)", "Saints" in [x.get("opponent") for x in votes], False)
    check("a game too old to be open is not listed", "Ancients" in [x.get("opponent") for x in votes], False)
    check("a game he has already voted on is not listed", "Done Deal" in [x.get("opponent") for x in votes], False)
    blob = json.dumps(prof)
    check("nobody else's name or id is in his page", any(n in blob for n in ("Ann Anchor", "Bob Bystander", str(ann), str(bob))), False)
    prof_ann = await profile(ann)
    check("Ann owes three (she played Done Deal too, and has not voted there), the one that closes first on top", [x.get("opponent") for x in prof_ann.get("votes") or []], ["Done Deal", "Rovers", "Saints"])
    prof_bob = await profile(bob)
    check("a player who played nothing gets no reminder and no module", (prof_bob.get("votes"), "votes" in (prof_bob.get("modules") or [])), ([], False))

    print("\n# B. It clears when the vote is cast")
    async with Session() as db:
        db.add(VoteBallot(organisation_id=org, medal_id=medal, fixture_id=f1, voter_player_id=sam, voter_kind="player"))
        await db.commit()
    prof = await profile(sam)
    check("once he has voted nothing is due and the module drops out", (prof.get("votes"), "votes" in (prof.get("modules") or [])), ([], False))
    check("Ann is unaffected by Sam's ballots", len((await profile(ann)).get("votes") or []), 3)

    print("\n# C. When voting is not on")
    await set_medal(enabled=False)
    check("a medal that is switched off reminds nobody", (await profile(ann)).get("votes"), [])
    await set_medal(enabled=True, link_token=None)
    check("a medal with no link reminds nobody (there is nowhere to send them)", (await profile(ann)).get("votes"), [])
    await set_medal(link_token=vtok)
    async with Session() as db:
        db.add(VoteFixtureOverride(medal_id=medal, fixture_id=f2, organisation_id=org, status="locked"))
        await db.commit()
    check("a game the club has locked is not offered", [x.get("opponent") for x in (await profile(ann)).get("votes") or []], ["Done Deal", "Rovers"])
    await set_medal(voter_mode="captain")
    check("in captain-only mode a player who is not captain is not reminded", (await profile(ann)).get("votes"), [])
    async with Session() as db:
        lu = await db.get(FixtureLineup, (f1, ann))
        lu.is_captain = True
        await db.commit()
    check("the captain is", [x.get("opponent") for x in (await profile(ann)).get("votes") or []], ["Rovers"])
    await set_medal(voter_mode="players")

    print("\n# D. The club's choice of modules")
    await set_org(player_dashboard_modules=["fines"])
    prof = await profile(ann)
    check("with Votes left off the page, it is not queried or shown", (prof.get("votes"), prof.get("modules")), ([], []))
    await set_org(player_dashboard_modules=None)
    check("a club that never chose gets Votes in the default page", pd.DEFAULT_MODULES[:2], ["availability", "votes"])
    async with Session() as db:
        club = await db.get(Organisation, org)
        cat = {m["key"]: m for m in pd.catalogue_for(club)} if hasattr(pd, "catalogue_for") else {}
    check("the admin list offers it", "votes" in cat, True)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
