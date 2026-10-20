"""Verification: the voting page links a verified player back to their own dashboard.

Asked for: "When you get to the voting page you should be able to link back to your
player profile dashboard section."

Drives the SHIPPED `public_votes.get_landing`, `fixture_state` and `verify` route
bodies against a real Postgres. The link is `/avail/<token>?tab=mine&player=<id>`.

  * a verified player gets `my_page` on the landing, the fixture and the verify reply
  * nobody else does: an unidentified visitor (a supporter) is never sent the
    availability token
  * no link while the club's self-service link is off, or has no token
  * the link never names another player

CONTROL MODE: against the previous commit there is no `my_page`; every read is
presence-safe so the control fails the checks rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_vote_my_page_link.py
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
from starlette.responses import Response

import verify_selection_same_day as base
from app.config.settings import settings
from app.models.db import Fixture, FixtureLineup, Organisation, Player, VoteMedal

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    import app.routers.public_votes as pv

    org = uuid.uuid4()
    sam, ann, bob, hid = (uuid.uuid4() for _ in range(4))
    vote_tok, avail_tok = "v-" + uuid.uuid4().hex, "a-" + uuid.uuid4().hex
    async with Session() as db:
        db.add(Organisation(id=org, name="Vote CC", slug=f"vote-{org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=avail_tok, availability_self_service_enabled=True))
        await db.flush()
        db.add(Player(id=sam, organisation_id=org, name="Sam Sledge", is_player=True, status="active", phone="0400000111"))
        db.add(Player(id=ann, organisation_id=org, name="Ann Anchor", is_player=True, status="active", phone="0400000222"))
        db.add(Player(id=bob, organisation_id=org, name="Bob Bare", is_player=True, status="active", photo_url="https://img.test/bob.jpg"))
        db.add(Player(id=hid, organisation_id=org, name="Hal Hidden", is_player=True, status="active", photo_url="https://img.test/hal.jpg", is_public=False))
        db.add(VoteMedal(id=uuid.uuid4(), organisation_id=org, name="Best player", link_token=vote_tok, enabled=True, require_pin=True))
        await db.commit()

    def req(pid=None):
        headers = []
        if pid:
            c = jose_jwt.encode({"club": str(org), "pid": str(pid), "typ": "vote",
                                 "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                                settings.secret_key, algorithm=settings.algorithm)
            headers = [(b"cookie", f"{pv.COOKIE_NAME}={c}".encode())]
        return Request({"type": "http", "headers": headers, "client": ("1.2.3.4", 1)})

    async def landing(pid=None):
        async with Session() as db:
            return await pv.get_landing(vote_tok, req(pid), db)

    print("\n# A. The landing")
    me = (await landing(sam)).get("me") or {}
    want = f"/avail/{avail_tok}?tab=mine&player={sam}"
    check("a verified player is given the way back to their page", me.get("my_page"), want)
    check("the link names them and nobody else", str(ann) in (me.get("my_page") or ""), False)
    check("an unidentified visitor gets no me and no availability token", (await landing()).get("me"), None)
    check("the token is not anywhere else in their landing", avail_tok in str(await landing()), False)

    print("\n# B. Verifying with the PIN")
    async with Session() as db:
        r = await pv.verify(vote_tok, pv.VerifyBody(player_id=str(sam), pin="0111"), req(), Response(), db)
    check("the verify reply carries the link too (the player may verify after the page loaded)", (r.get("player") or {}).get("my_page"), want)

    print("\n# C. The ballot page")
    fx = uuid.uuid4()
    async with Session() as db:
        db.add(Fixture(id=fx, organisation_id=org, source="manual", played_on=date.today() - timedelta(days=2),
                       status="COMPLETED", opponent_name="Rovers", label="1st", round="1"))
        await db.flush()
        for n, pid in enumerate((ann, bob, hid, sam), 1):
            db.add(FixtureLineup(fixture_id=fx, player_id=pid, organisation_id=org, batting_order=n))
        await db.commit()
    async with Session() as db:
        st = await pv.fixture_state(vote_tok, str(fx), req(sam), db)
    check("a verified player's ballot page carries the link", (st.get("me") or {}).get("my_page"), want)
    ph = {p["name"]: p.get("photo_url") for p in st.get("players", [])}
    check("the ballot lists who played", sorted(ph), ["Ann Anchor", "Bob Bare", "Hal Hidden", "Sam Sledge"])
    check("a player with a photo has it on the ballot", ph.get("Bob Bare"), "https://img.test/bob.jpg")
    check("a player with no photo has none (the page shows initials)", ph.get("Ann Anchor"), None)
    check("a player hidden from public pages has no photo here, though still listed", ph.get("Hal Hidden"), None)
    async with Session() as db:
        st = await pv.fixture_state(vote_tok, str(fx), req(), db)
    check("an unidentified visitor's ballot page does not", (st.get("me"), avail_tok in str(st)), (None, False))

    print("\n# D. Switched off")
    for label, patch in (("self-service off", {"availability_self_service_enabled": False}),
                         ("no token", {"availability_link_token": None})):
        async with Session() as db:
            o = await db.get(Organisation, org)
            saved = {k: getattr(o, k) for k in patch}
            for k, v in patch.items():
                setattr(o, k, v)
            await db.commit()
        check(f"{label}: no link, and the page still loads", ((await landing(sam)).get("me") or {}).get("my_page"), None)
        async with Session() as db:
            o = await db.get(Organisation, org)
            for k, v in saved.items():
                setattr(o, k, v)
            await db.commit()

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
