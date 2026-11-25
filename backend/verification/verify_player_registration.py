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
RUSS, NIGEL = uuid.uuid4(), uuid.uuid4()


async def setup() -> None:
    async with engine.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.run_sync(Base.metadata.create_all)
        from app.services.audit_ddl import STATEMENTS as AUDIT
        for s in AUDIT:
            await c.execute(text(s))
        # The real notification tables, so the bell raised on sign-up can be read back.
        from app.services import notification_ddl
        for s in getattr(notification_ddl, "STATEMENTS", []):
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
            # The Applecross case: Russell is on the books (inactive) with his mobile and email.
            Player(id=RUSS, name="Kingdon, Russell", organisation_id=ORG, phone="0433 331 162", is_player=True,
                   status="inactive", email="club-typed-russ@example.com", batting_hand="LEFT"),
            Player(id=NIGEL, name="Kingdon, Nigel", organisation_id=ORG, phone=None, is_player=True, status="inactive"),
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
        r = await c.post(f"{base}/register", json=claim)
        check("a different mobile and no PIN asks for the old number's digits",
              r.status_code == 200 and r.json().get("status") == "need_pin", r.text)
        check("no cookie while asking for the PIN", "bs_avail" not in c.cookies)
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
        async with Session() as s:
            row = (await s.execute(text("SELECT * FROM player_registrations WHERE last_name = 'Oldham'"))).mappings().first() \
                if (await s.execute(text("SELECT to_regclass('player_registrations')"))).scalar() else None
        check("PIN-proven claim needs no review: approved, matched by PIN",
              row is not None and row["status"] == "approved" and row.get("matched_by") == "pin", row and dict(row))
        check("the new number they typed is kept for the club to see", row is not None and row["phone"] == "0499 999 999")

    print("Claim with no mobile on file")
    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form(claim_player_id=str(PAST_NOPHONE), first_name="Colin",
                                                       last_name="Oldfield", role="current_player", phone="0477 000 111",
                                                       email="colin@example.com", playing={"player_role": "Bowler"}))
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

    print("Smart matching")
    async with client(app) as c:
        # Russ signs up WITHOUT finding himself in the past-player list, as a nickname, with
        # the mobile the club has for him: it is him.
        r = await c.post(f"{base}/register", json=form(
            first_name="Russ", last_name="Kingdon", role="ex_player", phone="0433331162", email="russ@new.example.com",
            notes="No", playing={"player_role": "Batter", "batting_hand": "RIGHT", "bowling_action": "RIGHT_ARM",
                                 "bowling_type": "FINGER_SPIN", "is_overseas": True, "overseas_country": "England",
                                 "is_opening_batsman": "yes please", "nonsense": 1}))
        body = r.json() if r.status_code == 200 else {}
        check("mobile and name on a record: matched and signed in", body.get("status") == "signed_in" and body.get("matched") is True, r.text)
        check("matched: cookie set", "bs_avail" in c.cookies)
        d = await c.get(f"{base}/me/details")
        check("matched: it is Russell's own page", d.status_code == 200, d.text)
        async with Session() as s:
            n = (await s.execute(text("SELECT count(*) FROM players WHERE name ILIKE 'Kingdon%'"))).scalar()
            row = (await s.execute(text("SELECT * FROM player_registrations WHERE last_name = 'Kingdon' AND first_name = 'Russ'"))).mappings().first() \
                if (await s.execute(text("SELECT to_regclass('player_registrations')"))).scalar() else None
        check("no second Kingdon record made", n == 2, n)
        check("matched registration is approved, by mobile, linked to Russell",
              row is not None and row["status"] == "approved" and row.get("matched_by") == "mobile" and row["player_id"] == RUSS,
              row and {k: row.get(k) for k in ("status", "player_id")})
        check("a bare 'No' to Anything else? is not kept as a note", row is not None and row["notes"] is None, row and row["notes"])
        check("unknown and non-boolean playing values dropped",
              row is not None and set(row.get("playing") or {}) == {"player_role", "batting_hand", "bowling_action", "bowling_type", "is_overseas", "overseas_country"},
              row and row.get("playing"))
        p = await player(RUSS)
        check("empty fields filled: role, bowling, overseas", p.player_role == "Batter" and p.bowling_type == "FINGER_SPIN"
              and p.is_overseas is True and p.overseas_country == "England", (p.player_role, p.bowling_type, p.is_overseas))
        check("role sets the skill positions", list(p.skill_positions or []) == ["BAT"], p.skill_positions)
        check("the club's own batting hand is NOT overwritten", p.batting_hand == "LEFT", p.batting_hand)
        check("the club's own email is NOT overwritten", p.email == "club-typed-russ@example.com", p.email)
        check("what was added is recorded", row is not None and "role" in (row.get("applied") or []) and "batting hand" not in (row.get("applied") or []),
              row and row.get("applied"))
        check("a past player is not put back for selection", p.dormancy_cleared_on is None)
        await asyncio.sleep(1.0)
        async with Session() as s:
            bell = (await s.execute(text(
                "SELECT title, body FROM notifications WHERE organisation_id = :o AND event_key = 'player_registered' "
                "AND title LIKE 'Russ Kingdon%'"), {"o": ORG})).mappings().all()
        check("the club's bell has it straight away, once", len(bell) == 1 and "Matched to their record" in bell[0]["body"], bell)

    async with client(app) as c:
        r = await c.post(f"{base}/register", json=form(first_name="Nigel", last_name="Kingdon", role="supporter", phone="0455 000 999"))
        body = r.json() if r.status_code == 200 else {}
        names = [x["display_name"] for x in body.get("players", [])]
        check("name on the books, no mobile match: asks 'is one of these you?'",
              body.get("status") == "possible_matches" and "Kingdon, Nigel" in names, r.text)
        check("possible matches never include another first name", "Kingdon, Russell" not in names, names)
        check("possible matches: no cookie, no record made", "bs_avail" not in c.cookies)
        r = await c.post(f"{base}/register", json=form(first_name="Nigel", last_name="Kingdon", role="supporter",
                                                       phone="0455 000 999", confirmed_new=True))
        check("'None of these are me' then makes a new record", r.status_code == 200 and r.json().get("status") == "signed_in", r.text)
        async with Session() as s:
            n = (await s.execute(text("SELECT count(*) FROM players WHERE name = 'Kingdon, Nigel'"))).scalar()
            row = (await s.execute(text("SELECT * FROM player_registrations WHERE first_name = 'Nigel'"))).mappings().first()
        check("two Nigel Kingdon records only because they said so", n == 2, n)
        check("a supporter's form stores no playing details", row is not None and "playing" in row and dict(row["playing"] or {}) == {}, row and row.get("playing"))

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
    check("admin list has everyone", {"Oldham", "Oldfield", "Newman", "Kingdon"} <= set(regs), list(regs))
    pend = {r["first_name"] for r in (lst or {}).get("registrations", []) if r["status"] == "pending"}
    check("only the unproven claim and the new people wait for review", pend == {"Colin", "Dana", "Nigel"}, pend)
    russ = next((r for r in (lst or {}).get("registrations", []) if r["first_name"] == "Russ"), None)
    check("admin row says how Russell was matched and shows him inactive",
          russ is not None and russ.get("matched_by") == "mobile" and russ.get("player_status") == "inactive", russ)
    check("admin row drops the bare 'No'", russ is not None and russ["notes"] == "", russ and russ["notes"])

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
        check("approved claim gets the role they gave", p.player_role == "Bowler", p.player_role)

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

    print("Make active again, and telling the club")
    if russ:
        out = await admin_call("reactivate_registered_player", russ["id"])
        p = await player(RUSS)
        check("make active again: status active and back for selection", p.status == "active" and p.dormancy_cleared_on is not None, p.status)
        check("the row reflects it", out is not None and out.get("player_status") == "active")
    else:
        check("make active again", False, "no Russ row")
    try:
        from app.services import notification_scan as ns
        src = getattr(ns, "_src_player_registered", None)
    except Exception:
        src = None
    if src:
        async with Session() as s:
            items = await src(s, ORG, {})
        by_title = {i["title"]: i for i in items}
        rus = next((i for i in items if i["title"].startswith("Russ Kingdon")), None)
        check("club is told Russ signed up, matched to his record", rus is not None and "Matched to their record" in rus["body"], list(by_title))
        col = next((i for i in items if i["title"].startswith("Colin Oldfield")), None)
        check("an admin-confirmed claim says so, not 'by their PIN'", col is not None and "Confirmed as" in col["body"], col)
        dana = next((i for i in items if i["title"].startswith("Dana Newman")), None)
        check("a new person's notice says what it is", dana is not None and "New to the club" in dana["body"], dana)
        check("one notice per registration", len({i["dedupe_key"] for i in items}) == len(items) and len(items) >= 5, len(items))
    else:
        check("notification source exists", False)

    print("One-off fix for v9.152.0 claims")
    try:
        from app.services.player_registration_ddl import FIX_399
    except ImportError:
        FIX_399 = None
    if FIX_399:
        old_proven, old_unproven, later = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with Session() as s:
            from datetime import datetime as _dt, timezone as _tz
            before, after = _dt(2026, 11, 25, 5, tzinfo=_tz.utc), _dt(2026, 11, 27, 5, tzinfo=_tz.utc)
            for rid, pid, when in ((old_proven, PAST_PHONE, before), (old_unproven, NIGEL, before), (later, PAST_PHONE, after)):
                await s.execute(text(
                    "INSERT INTO player_registrations (id, organisation_id, player_id, kind, role, last_name, status, created_at) "
                    "VALUES (:id, :o, :p, 'claim', 'ex_player', 'Legacy', 'pending', :w)"),
                    {"id": rid, "o": ORG, "p": pid, "w": when})
            # What v9.152.0 wrote after a PIN matched; Nigel's record has none.
            await s.execute(text(
                "INSERT INTO audit_events (organisation_id, via, area, action, player_id, summary) "
                "VALUES (:o, 'player link', 'details', 'registration_claimed', :p, 'legacy claim')"), {"o": ORG, "p": PAST_PHONE})
            for st in FIX_399:
                await s.execute(text(st))
            await s.commit()
            got = {r[0]: (r[1], r[2]) for r in (await s.execute(text(
                "SELECT id, status, matched_by FROM player_registrations WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [str(old_proven), str(old_unproven), str(later)]})).all()}
        check("fix: an old PIN-proven claim becomes approved, matched by PIN", got.get(old_proven) == ("approved", "pin"), got.get(old_proven))
        check("fix: an old claim with no PIN proof stays for review", got.get(old_unproven) == ("pending", None), got.get(old_unproven))
        check("fix: never touches a row from after the release", got.get(later) == ("pending", None), got.get(later))
    else:
        check("one-off fix exists", False)

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
