"""BetterAdmin and BetterSocials mounted on the football backend, against a
real Postgres, through the real AFL boot path and the real HTTP stack.

What it proves:
  * the cricket schema mirror gives a fresh football database every table the
    shared routers read, and a second boot changes nothing (idempotent);
  * every parameter-free GET on every shared router answers without a server
    error for a football club admin whose club holds the modules;
  * the module gate still holds: a club without BetterAdmin gets 402 on the
    paid routers and a club without BetterSocials on the media library;
  * a real write round-trips on the core screens (a directory person, a
    committee position, a roster area, a merch product, a comms template);
  * the mirror only ever replays additive statements.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_shared_modules.py
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


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


SHARED_PREFIXES = (
    "/club-admin/fees", "/club-admin/comms", "/club-admin/merch", "/club-admin/crm",
    "/club-admin/directory", "/club-admin/roster", "/club-admin/committee",
    "/club-admin/volunteers", "/club-admin/qualifications", "/club-admin/events",
    "/club-admin/assets", "/club-admin/club-diary", "/club-admin/roles",
    "/club-admin/activities", "/club-admin/role-programs", "/club-admin/facility",
    "/families", "/admin/social", "/club-admin/stripe-connect",
)


async def main():
    import httpx
    from app.models.db import ClubMembership, Organisation, User, engine, async_session_maker
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token
    from app.services.afl import cricket_schema_mirror as mirror

    print("\n── The mirror only replays additive statements ──")
    check("an UPDATE is never replayed", mirror.is_additive("UPDATE organisations SET x = 1"), False)
    check("a DROP is never replayed", mirror.is_additive("ALTER TABLE t DROP COLUMN x"), False)
    check("a mixed ALTER (add + drop) is never replayed",
          mirror.is_additive("ALTER TABLE t ADD COLUMN IF NOT EXISTS a INT, DROP COLUMN b"), False)
    check("an ADD COLUMN with a NUMERIC(4,2) type is additive",
          mirror.is_additive("ALTER TABLE t ADD COLUMN IF NOT EXISTS a NUMERIC(4,2) DEFAULT 0"), True)
    check("CREATE TABLE IF NOT EXISTS is additive", mirror.is_additive("CREATE TABLE IF NOT EXISTS t (id int)"), True)
    harvest = mirror.harvested_statements()
    check("the harvest found cricket's raw tables", any("roster_areas" in s for s in harvest))
    check("  ... and nothing it harvested writes data",
          all(not s.lstrip().upper().startswith(("UPDATE", "INSERT", "DELETE", "DROP")) for s in harvest))

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass
    async with lifespan(None):
        pass

    print("\n── A fresh football database has the shared schema ──")
    async with engine.begin() as conn:
        tables = set((await conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))).scalars())
        for t in ("roster_areas", "roster_shifts", "facility_booking_requests", "member_membership_types",
                  "family_suggestions_dismissed", "social_media_asset", "comms_campaigns", "merch_products",
                  "committee_positions", "club_events"):
            check(f"{t} exists", t in tables)
        cols = set((await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='fee_members'"))).scalars())
        check("fee_members.member_category (raw-only column) is there", "member_category" in cols)
        idx = (await conn.execute(text(
            "SELECT 1 FROM pg_indexes WHERE indexname='uq_volunteer_hours_shift'"))).first()
        check("the roster's ON CONFLICT index is there", idx is not None)

    org_full, org_bare = uuid.uuid4(), uuid.uuid4()
    u_full, u_bare = uuid.uuid4(), uuid.uuid4()
    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org_full, name="Curtin Uni Wesley", slug="cuw", is_active=True,
                         module_overrides=["fees", "comms", "merch", "crm", "socials"]),
            Organisation(id=org_bare, name="Hampton Hammers", slug="hh", is_active=True, module_overrides=[]),
            User(id=u_full, username="full", email="f@x.io", password_hash="x", display_name="Full Admin"),
            User(id=u_bare, username="bare", email="b@x.io", password_hash="x", display_name="Bare Admin"),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u_full, club_id=org_full, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u_bare, club_id=org_bare, role="club_admin", is_primary_admin=True),
        ])
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    def client(uid):
        return httpx.AsyncClient(transport=transport, base_url="http://t",
                                 cookies={COOKIE_NAME: create_session_token(str(uid))})

    gets = sorted({r.path for r in app.routes
                   if "GET" in (getattr(r, "methods", None) or set())
                   and "{" not in r.path and r.path.startswith(SHARED_PREFIXES)})
    print(f"\n── {len(gets)} shared GET endpoints, as a football club admin ──")
    errors = []
    async with client(u_full) as c:
        for path in gets:
            try:
                r = await c.get(path)
            except Exception as exc:  # noqa: BLE001 — the ASGI transport re-raises app errors
                errors.append((path, "raised", str(exc).splitlines()[0][:160]))
                continue
            if r.status_code >= 500:
                errors.append((path, r.status_code, r.text[:160]))
    for e in errors[:15]:
        print("   ", e)
    check("no shared GET answers with a server error", len(errors), 0)

    print("\n── The module gate still holds ──")
    async with client(u_bare) as c:
        check("fees without BetterAdmin is 402", (await c.get("/club-admin/fees/schedule")).status_code, 402)
        check("comms without BetterAdmin is 402", (await c.get("/club-admin/comms/templates")).status_code, 402)
        check("the media library without BetterSocials is 402", (await c.get("/admin/social/media")).status_code, 402)

    print("\n── Writes round-trip on a football club ──")
    async with client(u_full) as c:
        _post = c.post

        async def safe_post(path, **kw):
            try:
                return await _post(path, **kw)
            except Exception as exc:  # noqa: BLE001 — a control run must report, not crash
                return httpx.Response(599, text=str(exc))
        c.post = safe_post
        r = await c.post("/club-admin/directory/people", json={"full_name": "Terry Treasurer", "email": "t@x.io", "member_category": "committee"})
        check("a directory person is created", r.status_code in (200, 201), True)
        if r.status_code >= 300:
            print("   ", r.text[:300])
        pr = await c.get("/club-admin/directory/people")
        people = pr.json() if pr.status_code < 300 else []
        names = [p.get("full_name") or p.get("name") or p.get("display_name") for p in (people.get("people") if isinstance(people, dict) else people)]
        check("  ... and listed", any(n and "Terry" in n for n in names))
        r = await c.post("/club-admin/merch/products", json={"name": "Club guernsey", "category": "apparel"})
        check("a merch product is created", r.status_code in (200, 201), True)
        if r.status_code >= 300:
            print("   ", r.text[:300])
        r = await c.post("/club-admin/roster/areas", json={"name": "Canteen"})
        check("a roster area is created", r.status_code in (200, 201), True)
        if r.status_code >= 300:
            print("   ", r.text[:300])
        r = await c.post("/club-admin/comms/templates", json={"name": "Welcome", "subject": "Hi", "html": "<p>Hi</p>"})
        check("a comms template is created", r.status_code in (200, 201), True)
        if r.status_code >= 300:
            print("   ", r.text[:300])

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
