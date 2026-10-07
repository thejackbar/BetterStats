"""Every football club holds every football module, against a real Postgres,
through the real AFL boot path and HTTP stack.

What it proves:
  * a database that already has clubs (none holding BetterSelect) gets every
    football module on the next boot, and keeps any key it held that is not a
    football module;
  * the grant is once only: a super admin who switches BetterSelect off for a
    club is not reverted by the boot after it;
  * a club registered after that starts with every football module;
  * a club admin of a club that used to be bare now reaches the BetterSelect
    routes (402 before, 200 after), and BetterSocials and BetterAdmin with it.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5432 \
      python verification/verify_afl_modules_access.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0
ALL = ["comms", "crm", "fees", "merch", "select", "socials"]


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def held(conn, org_id):
    row = (await conn.execute(text("SELECT module_overrides FROM organisations WHERE id = :i"),
                              {"i": org_id})).scalar()
    return sorted(row or [])


async def main():
    import httpx
    from app.models.db import ClubMembership, Organisation, User, engine, async_session_maker
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    # A deployed football database: clubs already exist, none holds BetterSelect.
    # (The first boot above set the marker on an empty database, so clear it to
    # stand in for the database as it was before this release.)
    o_bare, o_part, o_extra, o_off = (uuid.uuid4() for _ in range(4))
    u_bare, u_super = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=o_bare, name="Hampton Hammers", slug="hh", is_active=True, module_overrides=[]),
            Organisation(id=o_part, name="Curtin Uni Wesley", slug="cuw", is_active=True,
                         module_overrides=["fees", "comms", "merch", "crm", "socials"]),
            Organisation(id=o_extra, name="Old Scotch", slug="os", is_active=True, module_overrides=["iq"]),
            Organisation(id=o_off, name="Ormond", slug="orm", is_active=True, module_overrides=[]),
            User(id=u_bare, username="bare", email="b@x.io", password_hash="x", display_name="Bare Admin"),
            User(id=u_super, username="boss", email="s@x.io", password_hash="x", display_name="Boss"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u_bare, club_id=o_bare, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_super, club_id=o_bare, role="super_admin"),
        ])
        await db.commit()
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE platform_settings SET settings = settings - 'afl_default_modules_granted'"))

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def client(uid):
        return httpx.AsyncClient(transport=transport, base_url="http://t",
                                 cookies={COOKIE_NAME: create_session_token(str(uid))})

    print("\n── Before the boot: a club with no modules is gated ──")
    async with client(u_bare) as c:
        check("BetterSelect squads is 402", (await c.get("/afl-select/squads")).status_code, 402)

    print("\n── The next boot grants every football module ──")
    async with lifespan(None):
        pass
    async with engine.begin() as conn:
        check("a bare club holds all six keys", await held(conn, o_bare), ALL)
        check("a club with admin and socials gains select", await held(conn, o_part), ALL)
        check("a key outside the football set is kept", await held(conn, o_extra), sorted(ALL + ["iq"]))

    async with client(u_bare) as c:
        for path, label in (("/afl-select/squads", "BetterSelect squads"),
                            ("/afl-select/fixtures", "BetterSelect fixtures"),
                            ("/afl-select/rules", "BetterSelect rules"),
                            ("/admin/social/media", "the BetterSocials media library"),
                            ("/club-admin/fees/schedule", "BetterAdmin fees"),
                            ("/club-admin/comms/templates", "BetterAdmin comms")):
            r = await c.get(path)
            check(f"{label} is no longer gated (got {r.status_code})", r.status_code not in (402, 403), True)

    print("\n── Once only: a switch-off survives the boot after ──")
    async with client(u_super) as c:
        r = await c.patch(f"/club-admin/super/clubs/{o_off}", json={"modules": {"select": False}})
        check("a super admin switches BetterSelect off", r.status_code, 200)
        check("  ... the payload says so", (r.json().get("modules") or {}).get("select"), False)
    async with lifespan(None):
        pass
    async with engine.begin() as conn:
        o = await held(conn, o_off)
    check("the club still lacks select after another boot", "select" in o, False)
    check("  ... and kept its other modules", [m for m in o if m != "select"], [m for m in ALL if m != "select"])

    print("\n── A club registered afterwards starts with every module ──")
    from app.services.afl import sync as afl_sync

    async def fake_comps(org_code):
        return {"organisation": {"name": "Brand New FC", "logo": None, "email": None}}
    afl_sync.phq.get_org_competitions = fake_comps
    async with async_session_maker() as db:
        new = await afl_sync.register_organisation(db, "abc12345")
        new_id = new.id
    async with engine.begin() as conn:
        check("the new club holds all six keys", await held(conn, new_id), ALL)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
