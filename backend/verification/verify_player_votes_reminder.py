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
from app.models.db import Fixture, FixtureLineup, Game, GameAppearance, Grade, Organisation, Player, Season, VoteBallot, VoteBallotPick, VoteFixtureOverride, VoteMedal

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
        ballot_f4 = uuid.uuid4()
        db.add(VoteBallot(id=ballot_f4, organisation_id=org, medal_id=medal, fixture_id=f4, voter_player_id=sam, voter_kind="player"))
        await db.flush()
        db.add(VoteBallotPick(ballot_id=ballot_f4, position=1, player_id=ann))
        db.add(VoteBallotPick(ballot_id=ballot_f4, position=2, player_id=bob))
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
    blob = json.dumps({k: v for k, v in prof.items() if k != "votes_cast"})   # his own picks name others; that is his own data
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
    check("once he has voted nothing is due, but the module stays to show what he cast", (prof.get("votes"), "votes" in (prof.get("modules") or [])), ([], True))
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
    await set_org(player_dashboard_modules=pd.store(["fines"]))
    prof = await profile(ann)
    check("with Votes left off the page (saved with Votes on offer), it is not queried or shown", (prof.get("votes"), prof.get("modules")), ([], []))
    await set_org(player_dashboard_modules=None)
    check("a club that never chose gets Votes in the default page", pd.DEFAULT_MODULES[:2], ["availability", "votes"])
    async with Session() as db:
        club = await db.get(Organisation, org)
        cat = {m["key"]: m for m in pd.catalogue_for(club)} if hasattr(pd, "catalogue_for") else {}
    check("the admin list offers it", "votes" in cat, True)

    print("\n# E. A big club: many open games, the player's is not among the newest")
    await set_org(player_dashboard_modules=None)
    await set_medal(enabled=True, link_token=vtok, voter_mode="players")
    async with Session() as db:
        # 14 other grades' games, all newer than Sam's and Ann's, none involving them.
        for i in range(14):
            fid = uuid.uuid4()
            db.add(Fixture(id=fid, organisation_id=org, source="manual", played_on=today, status="COMPLETED",
                           opponent_name=f"Other {i}", label=f"Other {i}", round="1"))
            await db.flush()
            db.add(FixtureLineup(fixture_id=fid, player_id=bob, organisation_id=org, batting_order=1))
        db.add(FixtureLineup(fixture_id=f1, player_id=sam, organisation_id=org, batting_order=1)) if False else None
        await db.commit()
        # Sam's Rovers ballot from section B stands; remove it so he has a vote due again.
        await db.execute(text("DELETE FROM vote_ballots WHERE fixture_id = :f AND voter_player_id = :p"), {"f": f1, "p": sam})
        await db.commit()
    prof = await profile(sam)
    check("Sam is still reminded though 14 newer games are open for other players", [v.get("opponent") for v in prof.get("votes") or []], ["Rovers"])
    prof_bob = await profile(bob)
    check("and Bob, who played all 14, is reminded of all of them", len(prof_bob.get("votes") or []), 14)

    print("\n# F. A club that saved its own module list before Votes existed")
    async with Session() as db:
        o = await db.get(Organisation, org)
        o.player_dashboard_modules = ["season", "fines"]   # the old shape: a bare list, no record of what it knew
        await db.commit()
    prof = await profile(sam)
    check("a list saved before Votes existed gets Votes added, since a club cannot have turned off what it never saw",
          ("votes" in (prof.get("modules") or []), [v.get("opponent") for v in prof.get("votes") or []]), (True, ["Rovers"]))
    check("it is added after Availability, or first when Availability is off", (prof.get("modules") or [None])[0], "votes")
    if hasattr(pd, "store"):
        async with Session() as db:
            o = await db.get(Organisation, org)
            o.player_dashboard_modules = pd.store(["season", "fines"])   # saved now, with Votes on offer and left off
            await db.commit()
        prof = await profile(sam)
        check("a list saved now that leaves Votes off keeps it off", ("votes" in (prof.get("modules") or []), prof.get("votes")), (False, []))
        async with Session() as db:
            o = await db.get(Organisation, org)
            o.player_dashboard_modules = pd.store([])
            await db.commit()
        check("an explicit empty list still means everything off", (await profile(sam)).get("modules"), [])
    else:
        check("a list saved now records what it was offered", False)

    print("\n# G. Games voted from the synced scorecard (what most clubs use)")
    await set_org(player_dashboard_modules=None)
    season, grade, game, fsync = (uuid.uuid4() for _ in range(4))
    async with Session() as db:
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="8th Grade"))
        await db.flush()
        db.add(Game(id=game, grade_id=grade, played_at=datetime.now(timezone.utc) - timedelta(days=1), home_team="Vote CC 8th XI", away_team="SMCC 8th XI"))
        await db.flush()
        # A synced fixture: its own random PK, the real match GUID in playhq_id. Sam played; Ann did not.
        db.add(Fixture(id=fsync, organisation_id=org, grade_id=grade, source="grassroots", playhq_id=str(game),
                       played_on=today - timedelta(days=1), status="COMPLETED", opponent_name="SMCC 8th XI", label="SMCC 8th XI", round="1"))
        await db.flush()
        db.add(GameAppearance(game_id=game, player_id=sam, team_name="Vote CC 8th XI"))
        await db.commit()
    prof = await profile(sam)
    check("Sam, on the synced scorecard, is reminded of that game among 14 newer ones", "SMCC 8th XI" in [v.get("opponent") for v in prof.get("votes") or []], True)
    prof_ann = await profile(ann)
    check("Ann, who is not on that scorecard, is not", "SMCC 8th XI" in [v.get("opponent") for v in prof_ann.get("votes") or []], False)
    link = next((v["link"] for v in prof.get("votes") or [] if v.get("opponent") == "SMCC 8th XI"), "")
    check("its link opens that fixture (the fixture's id, not the match GUID)", f"fixture={fsync}" in link and str(game) not in link, True)

    print("\n# H. What they have already cast, for reference")
    await set_org(player_dashboard_modules=None)
    async with Session() as db:
        b3 = uuid.uuid4()
        db.add(VoteBallot(id=b3, organisation_id=org, medal_id=medal, fixture_id=f3, voter_player_id=sam, voter_kind="player"))
        await db.flush()
        db.add(VoteBallotPick(ballot_id=b3, position=1, player_id=bob))
        await db.commit()
    prof = await profile(sam)
    cast = {c.get("opponent"): c for c in prof.get("votes_cast") or []}
    d4 = cast.get("Done Deal") or {}
    check("a game he has voted on shows his picks, 3 then 2", d4.get("picks"), [{"points": 3, "name": "Ann Anchor"}, {"points": 2, "name": "Bob Bystander"}])
    check("an open game says so, with when it closes and a link to change the vote", (d4.get("open"), bool(d4.get("closes_on")), d4.get("link")),
          (True, True, f"/vote/{vtok}?fixture={f4}&player={sam}"))
    anc = cast.get("Ancients") or {}
    check("a closed game still shows his vote, but with no link (it cannot be changed)", (anc.get("open"), anc.get("link"), anc.get("picks")), (False, None, [{"points": 3, "name": "Bob Bystander"}]))
    check("newest game first", [c.get("opponent") for c in prof.get("votes_cast") or []][:2], ["Done Deal", "Ancients"])
    check("nothing of his is in the to-cast list", "Done Deal" in [v.get("opponent") for v in prof.get("votes") or []], False)
    prof_ann = await profile(ann)
    check("Ann sees none of Sam's votes", [c.get("opponent") for c in prof_ann.get("votes_cast") or []], [])
    check("...and no player's ballot is anywhere in her page but hers", "Bob Bystander" in json.dumps(prof_ann), False)
    await set_medal(ballot_values=[5, 3, 1])
    check("the points follow the medal's own ballot values", [p["points"] for p in ((await profile(sam)).get("votes_cast") or [{}])[0].get("picks", [])], [5, 3])
    await set_medal(ballot_values=[3, 2, 1])

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
