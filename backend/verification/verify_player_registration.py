"""Player Dashboard self-registration ("Can't find your name?"). Real Postgres.

Drives the SHIPPED public routes over HTTP (an ASGI client, so the session cookie is
checked on the wire) and the shipped admin route bodies:

  * the past-player search needs three letters, finds a hidden (inactive) past player
    and never returns someone already on the name list;
  * claiming a past record with a mobile on file needs its last four digits; the right
    ones sign them in and fill only EMPTY fields on the player (email only with consent);
  * claiming a record with no mobile waits for the club: no cookie, nothing written;
  * a brand new person is signed in at once as a non-player with no public profile, is
    NOT on the public name list until approved, and joins it once approved;
  * approving a "current player" makes them a player; approving a claim fills the mobile;
  * one mobile, one person: a mobile on file is refused, and the same person registering
    again is signed back in without a second record;
  * archiving a self-added record shuts their cookie out and takes them off the list;
    restoring undoes it;
  * the follow-up PATCH changes only the keys sent;
  * a club with registration switched off gets 404 and no button.

Control run: on the previous commit the register router does not exist (read through
getattr), so every check fails.

Run:  DATABASE_URL=postgresql+asyncpg://root@/regverify?host=/var/run/postgresql \\
      python verification/verify_player_registration.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, Player, User, get_db
from app.routers import public_availability

try:
    reg_router = importlib.import_module("app.routers.public_player_register")
except ImportError:
    reg_router = None
admin = importlib.import_module("app.routers.player_dashboard_admin")

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + str(detail)) if detail else ''}")


ORG, USER = uuid.uuid4(), uuid.uuid4()
TOKEN = "tok-" + uuid.uuid4().hex
ACTIVE, PAST_PHONE, PAST_NOPHONE, HIDDEN = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


async def setup() -> None:
    async with engine.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.run_sync(Base.metadata.create_all)
        from app.services.audit_ddl import STATEMENTS as AUDIT
        for s in AUDIT:
            await c.execute(text(s))
        try:
            from app.services.player_registration_ddl import STATEMENTS
            for s in STATEMENTS:
                await c.execute(text(s))
        except ImportError:
            pass
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Verify CC", slug="verify-cc", availability_link_token=TOKEN,
                           player_dashboard_enabled=True, availability_require_pin=True))
        await s.flush()
        s.add(User(id=USER, email="admin@example.com", password_hash="x", display_name="Verify Admin"))
        s.add_all([
            Player(id=ACTIVE, name="Current, Alex", organisation_id=ORG, phone="0400 111 222", is_player=True, status="active"),
            Player(id=PAST_PHONE, name="Oldham, Bruce", organisation_id=ORG, phone="0400 333 444", is_player=True,
                   status="inactive", email=None),
            Player(id=PAST_NOPHONE, name="Oldfield, Colin", organisation_id=ORG, phone=None, is_player=True,
                   status="inactive", email="club-typed@example.com"),
            Player(id=HIDDEN, name="Oldcastle, Hidden", organisation_id=ORG, phone="0400 777 888", is_player=True,
                   status="inactive", is_public=False),
        ])
        await s.commit()


def make_app() -> FastAPI:
    app = FastAPI()
    if reg_router is not None:
        app.include_router(reg_router.router)
    app.include_router(public_availability.router)

    async def _db():
        async with Session() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    return app


def client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")


async def landing_names(c) -> list[str]:
    r = await c.get(f"/public/availability/{TOKEN}")
    return [p["display_name"] for p in r.json().get("players", [])], r.json()


async def player(pid) -> Player:
    async with Session() as s:
        return await s.get(Player, pid)


async def admin_call(fn_name: str, *args, **kw):
    fn = getattr(admin, fn_name, None)
    if fn is None:
        return None
    async with Session() as s:
        club = await s.get(Organisation, ORG)
        user = await s.get(User, USER)
        return await fn(*args, db=s, club=club, user=user, **kw)


def form(**over) -> dict:
    base = {"first_name": "Dana", "last_name": "Newman", "role": "supporter", "phone": "0400 555 666",
            "email": "dana@example.com", "date_of_birth": "1980-03-04", "years_played": "", "grades_played": "",
            "notes": "Happy to help on canteen", "interests": ["volunteer", "nonsense"], "contact_consent": True}
    base.update(over)
    return base


async def main() -> None:
    await setup()
    app = make_app()
    base = f"/public/availability/{TOKEN}"

    print("Landing and search")
    async with client(app) as c:
        names, body = await landing_names(c)
        check("landing says registration is open", body.get("registration_open") is True, body.get("registration_open"))
        check("the active player is on the name list, the hidden past players are not",
              "Current, Alex" in names and "Oldham, Bruce" not in names, names)
        r = await c.get(f"{base}/past-players", params={"q": "ol"})
        check("search needs three letters", r.status_code == 200 and r.json().get("players") == [], r.text)
        r = await c.get(f"{base}/past-players", params={"q": "old"})
        got = {p["display_name"]: p for p in r.json().get("players", [])} if r.status_code == 200 else {}
        check("search finds both hidden past players", set(got) == {"Oldham, Bruce", "Oldfield, Colin"}, r.text)
        check("search never names a player hidden from the public site", "Oldcastle, Hidden" not in got, r.text)
        async with Session() as s:
            hid = await s.get(Player, HIDDEN)
        check("could-be-present pair: the hidden player matches 'old' and is inactive",
              hid is not None and "old" in hid.name.lower() and hid.status == "inactive")
        check("search reports who has a mobile on file",
              got.get("Oldham, Bruce", {}).get("has_phone") is True and got.get("Oldfield, Colin", {}).get("has_phone") is False)
        r = await c.get(f"{base}/past-players", params={"q": "alex"})
        check("search never returns someone already on the name list", r.status_code == 200 and r.json().get("players") == [], r.text)
        r = await c.get(f"{base}/past-players", params={"q": "e"})
        check("could-be-present pair: the active player does exist on the books", "Current, Alex" in names)

    print("Claim with a mobile on file")
    async with client(app) as c:
        claim = form(claim_player_id=str(PAST_PHONE), first_name="Bruce", last_name="Oldham", role="ex_player",
                     phone="0499 999 999", email="bruce@example.com")
        r = await c.post(f"{base}/register", json={**claim, "pin": "0000"})
        check("wrong PIN is refused", r.status_code == 401, r.status_code)
        check("no cookie after a wrong PIN", "bs_avail" not in c.cookies)
        r = await c.post(f"{base}/register", json={**claim, "pin": "3444"})
        check("right PIN signs them in", r.status_code == 200 and r.json().get("status") == "signed_in", r.text)
        check("cookie set on the wire", "bs_avail" in c.cookies)
        d = await c.get(f"{base}/me/details")
        check("their session opens their own details", d.status_code == 200, d.status_code)
        p = await player(PAST_PHONE)
        check("empty email filled (they consented)", p.email == "bruce@example.com", p.email)
        check("mobile on file NOT overwritten by the one typed", p.phone == "0400 333 444", p.phone)

    print("Claim with no mobile on file")
    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form(claim_player_id=str(PAST_NOPHONE), first_name="Colin",
                                                       last_name="Oldfield", role="current_player", phone="0477 000 111",
                                                       email="colin@example.com"))
        check("waits for the club", r.status_code == 200 and r.json().get("status") == "pending", r.text)
        check("no cookie while pending", "bs_avail" not in c.cookies)
        p = await player(PAST_NOPHONE)
        check("nothing written to the player yet", p.phone is None and p.email == "club-typed@example.com", (p.phone, p.email))

    print("Brand new person")
    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form())
        check("signed in at once", r.status_code == 200 and r.json().get("status") == "signed_in", r.text)
        check("cookie set", "bs_avail" in c.cookies)
        d = await c.get(f"{base}/me/details")
        check("they can open their own page", d.status_code == 200, d.text)
        async with Session() as s:
            has_table = (await s.execute(text("SELECT to_regclass('player_registrations')"))).scalar()
            row = (await s.execute(text("SELECT * FROM player_registrations WHERE last_name = 'Newman'"))).mappings().first() \
                if has_table else None
        new_pid = row["player_id"] if row else None
        p = await player(new_pid) if new_pid else None
        check("record is a non-player with no public profile", p is not None and p.is_player is False and p.is_public is False)
        check("stored in Last, First", p is not None and p.name == "Newman, Dana", p and p.name)
        check("unknown interests dropped", row is not None and list(row["interests"]) == ["volunteer"], row and row["interests"])
        names, _ = await landing_names(c)
        check("not on the public name list before approval", "Newman, Dana" not in names, names)
        r = await c.post(f"{base}/verify", json={"player_id": str(new_pid), "pin": "5666"})
        check("they can log back in with the PIN", r.status_code == 200, r.text)

    print("One mobile, one person")
    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form(first_name="Eve", last_name="Imposter", phone="+61 400 111 222"))
        check("a mobile on file (any format) is refused", r.status_code == 409, r.status_code)
        r = await c.post(f"{base}/register", json=form())
        check("the same person again is signed back in", r.status_code == 200 and r.json().get("existing") is True, r.text)
        async with Session() as s:
            n = (await s.execute(text("SELECT count(*) FROM players WHERE name = 'Newman, Dana'"))).scalar()
        check("no second record made", n == 1, n)

    print("Admin list, approve, archive, restore")
    lst = await admin_call("list_registrations")
    regs = {r["last_name"]: r for r in (lst or {}).get("registrations", [])}
    check("admin list has all three", set(regs) == {"Oldham", "Oldfield", "Newman"}, list(regs))
    check("pending count is three", (lst or {}).get("counts", {}).get("pending") == 3, lst and lst.get("counts"))

    if "Newman" in regs:
        await admin_call("approve_registration", regs["Newman"]["id"])
        async with client(app) as c:
            names, _ = await landing_names(c)
        check("approved supporter joins the name list", "Newman, Dana" in names, names)
        p = await player(uuid.UUID(regs["Newman"]["player_id"]))
        check("approved supporter stays a non-player", p.is_player is False)

    if "Oldfield" in regs:
        await admin_call("approve_registration", regs["Oldfield"]["id"])
        p = await player(PAST_NOPHONE)
        check("approved claim gets the mobile they gave", p.phone == "0477 000 111", p.phone)
        check("club-typed email left alone", p.email == "club-typed@example.com", p.email)
        check("current player marked no longer dormant", p.dormancy_cleared_on is not None)

    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form(first_name="Finn", last_name="Fresh", role="current_player", phone="0411 222 333"))
        lst = await admin_call("list_registrations")
        fresh = next((x for x in (lst or {}).get("registrations", []) if x["last_name"] == "Fresh"), None)
        if fresh:
            await admin_call("approve_registration", fresh["id"])
            p = await player(uuid.UUID(fresh["player_id"]))
            check("approved current player becomes a player", p.is_player is True and p.is_public is True)
        else:
            check("approved current player becomes a player", False, "not registered")

        # Archive: the cookie set above (Finn) is shut out, and he leaves the name list.
        if fresh:
            await admin_call("archive_registration", fresh["id"])
            d = await c.get(f"{base}/me/details")
            check("archived person's cookie is refused", d.status_code == 401, d.status_code)
            names, _ = await landing_names(c)
            check("archived person is off the name list", "Fresh, Finn" not in names, names)
            p = await player(uuid.UUID(fresh["player_id"]))
            check("archived record kept and marked inactive", p is not None and p.status == "inactive")
            await admin_call("restore_registration", fresh["id"])
            d = await c.get(f"{base}/me/details")
            check("restored: cookie works again", d.status_code == 200, d.status_code)
            names, _ = await landing_names(c)
            check("restored: back on the name list", "Fresh, Finn" in names, names)

    print("Follow-up")
    if "Newman" in regs and getattr(admin, "FollowUpBody", None):
        B = admin.FollowUpBody
        await admin_call("update_registration", regs["Newman"]["id"], body=B(admin_note="Called, keen for canteen"))
        out = await admin_call("update_registration", regs["Newman"]["id"], body=B(contacted=True))
        check("contacted stamped", bool(out and out["contacted_at"]))
        check("note kept when only contacted was sent", out and out["admin_note"] == "Called, keen for canteen", out and out["admin_note"])
        out = await admin_call("update_registration", regs["Newman"]["id"], body=B(admin_note=""))
        check("an empty note clears it", out and out["admin_note"] == "", out and out["admin_note"])
    else:
        check("follow-up route exists", False)

    print("Switched off")
    async with Session() as s:
        o = await s.get(Organisation, ORG)
        o.player_registration_enabled = False if hasattr(o, "player_registration_enabled") else None
        await s.commit()
    async with client(app) as c:
        _, body = await landing_names(c)
        check("no button when switched off", body.get("registration_open") is False, body.get("registration_open"))
        r = await c.post(f"{base}/register", json=form(first_name="Gus", last_name="Late", phone="0422 333 444"))
        check("register refused when switched off", r.status_code == 404, r.status_code)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
