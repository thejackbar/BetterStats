"""Football player profile fields (date of birth, shirt number, positions, the
action photo), against a real Postgres, through the real AFL boot path and HTTP
stack.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_player_profile.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d69ea40000000049454e44ae426082")


async def main():
    import httpx
    from app.models.db import ClubMembership, Organisation, Player, User, engine, async_session_maker
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    org, other, u, u_other = (uuid.uuid4() for _ in range(4))
    p1, p_other = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True),
            Organisation(id=other, name="Hampton", slug="hh", is_active=True),
            User(id=u, username="a", email="a@x.io", password_hash="x"),
            User(id=u_other, username="b", email="b@x.io", password_hash="x"),
            Player(id=p1, organisation_id=org, name="Kick, Kim"),
            Player(id=p_other, organisation_id=other, name="Other, Oz"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_other, club_id=other, role="club_admin", is_primary_admin=True),
        ])
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    c = httpx.AsyncClient(transport=transport, base_url="http://t",
                          cookies={COOKIE_NAME: create_session_token(str(u))})

    def J(r):
        return r.json() if r.status_code < 300 else {}

    print("\n── Profile fields ──")
    r = await c.patch(f"/club-admin/players/{p1}", json={
        "date_of_birth": "2008-03-04", "shirt_number": "07", "positions": ["mid", "FF", "BAT", "FF"]})
    check("the fields save", r.status_code, 200)
    got = J(await c.get(f"/club-admin/players/{p1}"))
    check("the date of birth is stored", got.get("date_of_birth"), "2008-03-04")
    today = date.today()
    want_age = today.year - 2008 - ((today.month, today.day) < (3, 4))
    check("  ... and the age is worked out from it", got.get("age"), want_age)
    check("a shirt number keeps its leading zero", got.get("shirt_number"), "07")
    check("positions are football's own, upper-cased, a cricket one dropped, no repeats",
          got.get("positions"), ["MID", "FF"])
    listed = next((p for p in J(await c.get("/club-admin/players")) if p["id"] == str(p1)), {})
    check("the player list carries them too", (listed.get("shirt_number"), listed.get("positions")), ("07", ["MID", "FF"]))

    print("\n── A present null clears, an absent key leaves alone ──")
    await c.patch(f"/club-admin/players/{p1}", json={"email": "k@x.io"})
    got = J(await c.get(f"/club-admin/players/{p1}"))
    check("an edit that does not name them leaves them", (got.get("date_of_birth"), got.get("shirt_number")), ("2008-03-04", "07"))
    await c.patch(f"/club-admin/players/{p1}", json={"date_of_birth": None, "shirt_number": ""})
    got = J(await c.get(f"/club-admin/players/{p1}"))
    check("a null date and a blank number clear them", (got.get("date_of_birth"), got.get("shirt_number"), got.get("age")), (None, None, None))

    print("\n── Refusals ──")
    future = date(today.year + 1, 1, 1).isoformat()
    check("a date of birth in the future is refused",
          (await c.patch(f"/club-admin/players/{p1}", json={"date_of_birth": future})).status_code, 422)
    check("  ... and nothing was stored", J(await c.get(f"/club-admin/players/{p1}")).get("date_of_birth"), None)
    check("another club's player cannot be edited",
          (await c.patch(f"/club-admin/players/{p_other}", json={"shirt_number": "9"})).status_code, 404)

    print("\n── The public profile ──")
    await c.patch(f"/club-admin/players/{p1}", json={"date_of_birth": "2008-03-04", "shirt_number": "7", "positions": ["RUCK"]})
    pub = J(await c.get(f"/afl-players/{p1}"))
    check("shows the shirt number and positions", (pub.get("shirt_number"), pub.get("positions")), ("7", ["RUCK"]))
    check("never the date of birth", "date_of_birth" in pub or "age" in pub, False)

    print("\n── Action photo ──")
    r = await c.post(f"/club-admin/players/{p1}/hero-photo", files={"file": ("a.png", PNG, "image/png")})
    check("an action photo uploads", r.status_code, 200)
    url = J(r).get("hero_photo_url") or ""
    check("  ... stored API-relative for the /afl app", url.startswith(f"images/players/{p1}/hero-photo"), True)
    img = await c.get("/" + url.split("?")[0]) if url else None
    check("  ... and served", img.status_code if img else None, 200)
    check("the player list carries it for the post designer",
          bool(next((p for p in J(await c.get("/club-admin/players")) if p["id"] == str(p1)), {}).get("hero_photo_url")), True)
    check("a non-image is refused",
          (await c.post(f"/club-admin/players/{p1}/hero-photo", files={"file": ("a.exe", b"MZ", "x/y")})).status_code, 400)
    r = await c.delete(f"/club-admin/players/{p1}/hero-photo")
    check("it can be removed", (r.status_code, J(await c.get(f"/club-admin/players/{p1}")).get("hero_photo_url")), (200, None))
    check("another club's player's action photo cannot be set",
          (await c.post(f"/club-admin/players/{p_other}/hero-photo", files={"file": ("a.png", PNG, "image/png")})).status_code, 404)

    await c.aclose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
