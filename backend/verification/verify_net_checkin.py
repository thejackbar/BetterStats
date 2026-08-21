"""Verification for net self check-in (migration 272), against a real Postgres.

Exercises the SHIPPED route bodies and helpers — never a re-implementation of
their logic — the way the rest of this repo's verification suites do.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_test?host=/tmp&port=5544 \
      .venv/bin/python verify_net_checkin.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Runnable from anywhere: `app` lives one level up, beside this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, NetAttendance, NetCheckInRegistration, NetSession, Organisation, Player, User,
)

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, got, want=True):
    global PASS, FAIL
    ok = (got == want)
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


class FakeRequest:
    """Enough of a Request for _client_ip / _read_session."""
    def __init__(self, cookies=None, ip="203.0.113.9"):
        self.cookies = cookies or {}
        self.headers = {"x-real-ip": ip}
        self.client = None


class FakeResponse:
    """Captures set_cookie/delete_cookie so the issued JWT can be replayed."""
    def __init__(self):
        self.cookies = {}
    def set_cookie(self, key, value, **kw):
        self.cookies[key] = value
    def delete_cookie(self, key, **kw):
        self.cookies.pop(key, None)


async def build_schema():
    async with engine.begin() as conn:
        # users and organisations reference each other, so metadata.drop_all
        # can't order them. Drop the schema outright instead.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # create_all doesn't add the server defaults some raw-SQL migrations
        # set (the local-dev quirk this repo's notes call out).
        await conn.execute(text(
            "ALTER TABLE net_checkin_registrations ALTER COLUMN id SET DEFAULT gen_random_uuid()"
        ))


async def seed():
    """A club with BetterSelect, a live session, and a small roster."""
    async with Session() as db:
        club = Organisation(
            id=uuid.uuid4(), name="Applecross Cricket Club", slug="applecross",
            short_name="ACC", module_overrides=["select"], subscription_status="active",
            net_checkin_enabled=True, net_checkin_require_pin=True,
            net_checkin_allow_registration=True,
            net_checkin_token="tok-applecross-verify",
        )
        other = Organisation(
            id=uuid.uuid4(), name="High Wycombe CC", slug="high-wycombe",
            module_overrides=["select"], subscription_status="active",
        )
        db.add_all([club, other])
        await db.flush()

        user = User(id=uuid.uuid4(), username="admin", email="a@b.com", password_hash="x")
        db.add(user)

        players = []
        for nm, phone in [
            ("Barendse, Jack", "0400 111 234"),
            ("Mant, Brad", "+61 411 222 5678"),
            ("Cole, Graeme", None),           # no mobile → cannot use the PIN
        ]:
            p = Player(id=uuid.uuid4(), organisation_id=club.id, name=nm,
                       phone=phone, status="active", is_player=True)
            players.append(p)
        # Another club's player, to prove the token can't reach them.
        foreign = Player(id=uuid.uuid4(), organisation_id=other.id,
                         name="Smith, John", phone="0499 999 9999",
                         status="active", is_player=True)
        db.add_all(players + [foreign])

        s = NetSession(id=uuid.uuid4(), organisation_id=club.id,
                       session_date=datetime.now(timezone.utc).date(),
                       label="Tuesday senior nets", status="active", version=0)
        db.add(s)
        await db.commit()
        return {
            "club": club.id, "other": other.id, "user": user.id,
            "session": s.id, "players": [p.id for p in players],
            "foreign": foreign.id,
        }


async def main():
    import app.routers.net_manager as nm
    import app.routers.public_net_checkin as pub

    await build_schema()
    ids = await seed()
    TOKEN = "tok-applecross-verify"

    print("\n── The link is resolved, and only when it should be ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        got = await pub._club_for_token(db, TOKEN)
        check("a live token resolves its club", got.id, ids["club"])

        for label, bad in [("unknown token", "nope"), ("empty token", "")]:
            try:
                await pub._club_for_token(db, bad)
                check(f"{label} refused", False)
            except Exception as e:
                check(f"{label} → 404", getattr(e, "status_code", None), 404)

        # Switched off → 404, never 403: a rotated link reveals nothing.
        club.net_checkin_enabled = False
        await db.commit()
        try:
            await pub._club_for_token(db, TOKEN)
            check("disabled link refused", False)
        except Exception as e:
            check("disabled link → 404 (not 403)", getattr(e, "status_code", None), 404)
        club.net_checkin_enabled = True

        # Entitlement is checked here, not by a require_module wrapper.
        club.module_overrides = []
        await db.commit()
        try:
            await pub._club_for_token(db, TOKEN)
            check("unentitled club refused", False)
        except Exception as e:
            check("club without BetterSelect → 404", getattr(e, "status_code", None), 404)
        club.module_overrides = ["select"]
        await db.commit()

    print("\n── Which sessions a scan joins ──")
    async with Session() as db:
        got = await nm.live_sessions(db, ids["club"])
        check("today's active session is live", len(got), 1)

        s = await db.get(NetSession, ids["session"])
        s.status = "done"
        await db.commit()
        check("a session marked done is not live", len(await nm.live_sessions(db, ids["club"])), 0)
        s.status = "active"

        # The window is narrow at BOTH ends on purpose.
        s.session_date = datetime.now(timezone.utc).date() - timedelta(days=7)
        await db.commit()
        check("last week's forgotten session is not live",
              len(await nm.live_sessions(db, ids["club"])), 0)
        s.session_date = datetime.now(timezone.utc).date() + timedelta(days=1)
        await db.commit()
        check("tomorrow's session is live (timezone slack)",
              len(await nm.live_sessions(db, ids["club"])), 1)
        s.session_date = datetime.now(timezone.utc).date()
        await db.commit()

        check("another club's sessions are never live here",
              len(await nm.live_sessions(db, ids["other"])), 0)

    print("\n── Verify: the PIN gate ──")
    cookie = None
    async with Session() as db:
        jack = ids["players"][0]
        req, resp = FakeRequest(), FakeResponse()
        try:
            await pub.verify(TOKEN, pub.VerifyBody(player_id=str(jack), pin="0000"), req, resp, db)
            check("wrong PIN refused", False)
        except Exception as e:
            check("wrong PIN → 401", getattr(e, "status_code", None), 401)

        resp = FakeResponse()
        r = await pub.verify(TOKEN, pub.VerifyBody(player_id=str(jack), pin="1234"), req, resp, db)
        check("right PIN verifies", r["status"], "ok")
        check("a cookie is issued", pub.COOKIE_NAME in resp.cookies, True)
        cookie = resp.cookies[pub.COOKIE_NAME]

        # The last 4 digits, whatever the formatting around them.
        resp2 = FakeResponse()
        r2 = await pub.verify(TOKEN, pub.VerifyBody(player_id=str(ids["players"][1]), pin="5678"),
                              FakeRequest(ip="203.0.113.10"), resp2, db)
        check("formatting in the stored number is ignored", r2["status"], "ok")

        # No number on file is actionable, not a failure — nothing they could type works.
        try:
            await pub.verify(TOKEN, pub.VerifyBody(player_id=str(ids["players"][2]), pin="1111"),
                             FakeRequest(ip="203.0.113.11"), FakeResponse(), db)
            check("player with no mobile refused", False)
        except Exception as e:
            check("no mobile on file → 409, not 401", getattr(e, "status_code", None), 409)

        # Cross-club: reads as a wrong PIN, so the link can't enumerate rosters.
        try:
            await pub.verify(TOKEN, pub.VerifyBody(player_id=str(ids["foreign"]), pin="9999"),
                             FakeRequest(ip="203.0.113.12"), FakeResponse(), db)
            check("another club's player refused", False)
        except Exception as e:
            check("another club's player → 401 (indistinguishable)",
                  getattr(e, "status_code", None), 401)

    print("\n── The cookie is scoped to its club and its purpose ──")
    async with Session() as db:
        req = FakeRequest(cookies={pub.COOKIE_NAME: cookie})
        check("cookie reads back the player", pub._read_session(req, ids["club"]), ids["players"][0])
        check("cookie is refused for another club", pub._read_session(req, ids["other"]), None)
        # A bs_avail cookie must not be replayable here: that's what `typ` is for.
        import app.routers.public_availability as pav
        aresp = FakeResponse()
        pav._issue_cookie(aresp, ids["club"], ids["players"][0])
        cross = FakeRequest(cookies={pub.COOKIE_NAME: aresp.cookies[pav.COOKIE_NAME]})
        check("an availability cookie is not a check-in cookie",
              pub._read_session(cross, ids["club"]), None)

    print("\n── Checking in ──")
    async with Session() as db:
        req = FakeRequest(cookies={pub.COOKIE_NAME: cookie})
        before = (await db.get(NetSession, ids["session"])).version
        r = await pub.check_in(TOKEN, req, db)
        check("check-in reports ok", r["status"], "ok")
        check("added to the one live session", r["added"], 1)
        check("not reported as already in", r["already_in"], False)

        rows = (await db.execute(text(
            "SELECT player_id, source FROM net_attendance WHERE session_id = :s"
        ), {"s": ids["session"]})).fetchall()
        check("one attendance row exists", len(rows), 1)
        check("the row is the player, not a guest", rows[0][0], ids["players"][0])
        check("the row is marked source='self'", rows[0][1], "self")

        after = (await db.get(NetSession, ids["session"])).version
        check("the session version moved, so other devices see it", after > before, True)

    print("\n── Checking in twice is a no-op, not an error ──")
    async with Session() as db:
        r = await pub.check_in(TOKEN, FakeRequest(cookies={pub.COOKIE_NAME: cookie}), db)
        check("second tap still reports ok", r["status"], "ok")
        check("second tap adds nobody", r["added"], 0)
        check("second tap reads as already in", r["already_in"], True)
        n = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE session_id = :s"), {"s": ids["session"]})).scalar()
        check("still exactly one row", n, 1)

    print("\n── Check-in needs a verified cookie and a live session ──")
    async with Session() as db:
        try:
            await pub.check_in(TOKEN, FakeRequest(), db)
            check("unverified check-in refused", False)
        except Exception as e:
            check("no cookie → 401", getattr(e, "status_code", None), 401)

        s = await db.get(NetSession, ids["session"])
        s.status = "done"
        await db.commit()
        try:
            await pub.check_in(TOKEN, FakeRequest(cookies={pub.COOKIE_NAME: cookie}), db)
            check("check-in with nothing running refused", False)
        except Exception as e:
            check("no session running → 409", getattr(e, "status_code", None), 409)
        s.status = "active"
        await db.commit()

    print("\n── Two sessions at once: one scan joins both ──")
    async with Session() as db:
        s2 = NetSession(id=uuid.uuid4(), organisation_id=ids["club"],
                        session_date=datetime.now(timezone.utc).date(),
                        label="Juniors", status="active", version=0)
        db.add(s2)
        await db.commit()
        resp = FakeResponse()
        await pub.verify(TOKEN, pub.VerifyBody(player_id=str(ids["players"][1]), pin="5678"),
                         FakeRequest(ip="203.0.113.20"), resp, db)
        r = await pub.check_in(TOKEN, FakeRequest(cookies={pub.COOKIE_NAME: resp.cookies[pub.COOKIE_NAME]}), db)
        check("one scan joins both live sessions", r["added"], 2)
        n = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE player_id = :p"), {"p": ids["players"][1]})).scalar()
        check("a row in each", n, 2)
        await db.delete(s2)
        await db.commit()

    print("\n── A newcomer registers ──")
    reg_id = None
    async with Session() as db:
        body = pub.RegisterBody(full_name="Tom Newcomer", phone="0455 123 456",
                                email="tom@example.com", date_of_birth=date(2008, 3, 4),
                                previous_club="Willetton CC")
        r = await pub.register(TOKEN, body, FakeRequest(ip="203.0.113.30"), db)
        check("registration reports ok", r["status"], "ok")

        row = (await db.execute(text(
            "SELECT player_id, guest_name, source FROM net_attendance "
            "WHERE session_id = :s AND guest_name IS NOT NULL"), {"s": ids["session"]})).fetchone()
        check("they are checked in", row is not None, True)
        check("as a GUEST — no player row was written", row[0], None)
        check("under the name they typed", row[1], "Tom Newcomer")
        check("marked source='self'", row[2], "self")

        reg = (await db.execute(text(
            "SELECT id, full_name, phone, email, date_of_birth, previous_club, status "
            "FROM net_checkin_registrations WHERE organisation_id = :o"), {"o": ids["club"]})).fetchone()
        reg_id = reg[0]
        check("a registration was filed", reg[1], "Tom Newcomer")
        check("phone kept", reg[2], "0455 123 456")
        check("email kept", reg[3], "tom@example.com")
        check("date of birth kept", reg[4], date(2008, 3, 4))
        check("previous club kept (it has no home on players)", reg[5], "Willetton CC")
        check("waiting for an admin", reg[6], "pending")

        n = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        check("the roster is untouched — 3 players, not 4", n, 3)

    print("\n── What registration refuses ──")
    async with Session() as db:
        for label, bad, code in [
            ("a blank name", pub.RegisterBody(full_name="   "), 422),
            ("a one-letter name", pub.RegisterBody(full_name="T"), 422),
            ("a birthday in the future",
             pub.RegisterBody(full_name="Future Person",
                              date_of_birth=date.today() + timedelta(days=1)), 422),
            ("a birthday 150 years ago",
             pub.RegisterBody(full_name="Old Person", date_of_birth=date(1875, 1, 1)), 422),
        ]:
            try:
                await pub.register(TOKEN, bad, FakeRequest(ip="203.0.113.31"), db)
                check(f"{label} refused", False)
            except Exception as e:
                check(f"{label} → {code}", getattr(e, "status_code", None), code)

        # A club can close the door without touching the PIN setting.
        club = await db.get(Organisation, ids["club"])
        club.net_checkin_allow_registration = False
        await db.commit()
        try:
            await pub.register(TOKEN, pub.RegisterBody(full_name="Nobody At All"),
                               FakeRequest(ip="203.0.113.32"), db)
            check("registration refused when switched off", False)
        except Exception as e:
            check("registration switched off → 403", getattr(e, "status_code", None), 403)
        club.net_checkin_allow_registration = True
        await db.commit()

        # Junk email is dropped rather than stored; the name still registers.
        r = await pub.register(TOKEN, pub.RegisterBody(full_name="Bad Email", email="not-an-email"),
                               FakeRequest(ip="203.0.113.33"), db)
        stored = (await db.execute(text(
            "SELECT email FROM net_checkin_registrations WHERE full_name = 'Bad Email'"))).scalar()
        check("an unusable email is dropped, not stored", stored, None)

    print("\n── An admin approves: guest becomes a player ──")
    async with Session() as db:
        user = await db.get(User, ids["user"])
        club = await db.get(Organisation, ids["club"])
        out = await nm.approve_registration(
            str(reg_id), nm.RegistrationDecision(), db, club, user,
        )
        check("approval reports ok", out["status"], "ok")
        # display_name is the stored name, and players are stored "Last, First"
        # — so the new row reads exactly like every other player on the roster.
        check("stored as 'Last, First' like every other player", out["player_name"], "Newcomer, Tom")

        pid = uuid.UUID(out["player_id"])
        p = await db.get(Player, pid)
        check("the player row carries the phone they typed", p.phone, "0455 123 456")
        check("and the email", p.email, "tom@example.com")
        check("and the date of birth", p.date_of_birth, date(2008, 3, 4))
        check("name is 'Last, First'", p.name, "Newcomer, Tom")
        check("active", p.status, "active")

        rows = (await db.execute(text(
            "SELECT player_id, guest_name FROM net_attendance "
            "WHERE session_id = :s AND (player_id = :p OR guest_name = 'Tom Newcomer')"),
            {"s": ids["session"], "p": pid})).fetchall()
        check("their check-in CONVERTED, it did not duplicate", len(rows), 1)
        check("the row now points at the player", rows[0][0], pid)
        check("and no longer reads as a guest", rows[0][1], None)

        reg = (await db.execute(text(
            "SELECT status, player_id, reviewed_by FROM net_checkin_registrations WHERE id = :i"),
            {"i": reg_id})).fetchone()
        check("the registration is approved", reg[0], "approved")
        check("and remembers who it became", reg[1], pid)
        check("and who decided", reg[2], ids["user"])

        # Deciding twice is refused rather than creating a second player.
        try:
            await nm.approve_registration(str(reg_id), nm.RegistrationDecision(), db, club, user)
            check("re-approving refused", False)
        except Exception as e:
            check("approving twice → 409", getattr(e, "status_code", None), 409)

    print("\n── Approving onto someone already on the roster ──")
    async with Session() as db:
        user = await db.get(User, ids["user"])
        club = await db.get(Organisation, ids["club"])
        await pub.register(TOKEN, pub.RegisterBody(full_name="Graeme Cole"),
                           FakeRequest(ip="203.0.113.40"), db)
        rid = (await db.execute(text(
            "SELECT id FROM net_checkin_registrations WHERE full_name = 'Graeme Cole'"))).scalar()

        before = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        out = await nm.approve_registration(
            str(rid), nm.RegistrationDecision(player_id=str(ids["players"][2])), db, club, user)
        after = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        check("no new player is minted when matched to an existing one", after, before)
        check("it resolves to the player picked", out["player_id"], str(ids["players"][2]))

        row = (await db.execute(text(
            "SELECT player_id, guest_name FROM net_attendance WHERE player_id = :p"),
            {"p": ids["players"][2]})).fetchone()
        check("their guest row moved onto the real player", row[0], ids["players"][2])

        # A foreign player id must not be accepted from a browser.
        await pub.register(TOKEN, pub.RegisterBody(full_name="Someone Else"),
                           FakeRequest(ip="203.0.113.41"), db)
        rid2 = (await db.execute(text(
            "SELECT id FROM net_checkin_registrations WHERE full_name = 'Someone Else'"))).scalar()
        try:
            await nm.approve_registration(
                str(rid2), nm.RegistrationDecision(player_id=str(ids["foreign"])), db, club, user)
            check("matching to another club's player refused", False)
        except Exception as e:
            check("another club's player → 422", getattr(e, "status_code", None), 422)

    print("\n── Dismissing ──")
    async with Session() as db:
        user = await db.get(User, ids["user"])
        club = await db.get(Organisation, ids["club"])
        rid = (await db.execute(text(
            "SELECT id FROM net_checkin_registrations WHERE full_name = 'Someone Else'"))).scalar()
        n_before = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE guest_name = 'Someone Else'"))).scalar()
        await nm.dismiss_registration(str(rid), db, club, user)
        st = (await db.execute(text(
            "SELECT status FROM net_checkin_registrations WHERE id = :i"), {"i": rid})).scalar()
        check("the registration reads dismissed", st, "dismissed")
        n_after = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE guest_name = 'Someone Else'"))).scalar()
        check("they still turned up — the guest row is left alone", n_after, n_before)

    print("\n── Cross-club: a registration id from a browser can't reach across ──")
    async with Session() as db:
        user = await db.get(User, ids["user"])
        foreign_club = await db.get(Organisation, ids["other"])
        rid = (await db.execute(text(
            "SELECT id FROM net_checkin_registrations WHERE organisation_id = :o LIMIT 1"),
            {"o": ids["club"]})).scalar()
        try:
            await nm.dismiss_registration(str(rid), db, foreign_club, user)
            check("another club's registration refused", False)
        except Exception as e:
            check("another club's registration → 404", getattr(e, "status_code", None), 404)
        for label, bad in [("junk id", "not-a-uuid"), ("unknown id", str(uuid.uuid4()))]:
            try:
                await nm.dismiss_registration(bad, db, await db.get(Organisation, ids["club"]), user)
                check(f"{label} refused", False)
            except Exception as e:
                check(f"{label} → 404", getattr(e, "status_code", None), 404)

    print("\n── The live payload tells the iPad who scanned themselves in ──")
    async with Session() as db:
        s = await db.get(NetSession, ids["session"])
        payload = await nm._live_payload(db, s)
        srcs = {a["name"]: a["source"] for a in payload["attendees"]}
        check("every attendee carries a source", all(v in ("self", "admin") for v in srcs.values()), True)
        check("a scanned-in player reads 'self'", srcs.get("Barendse, Jack"), "self")

        # An admin-added row must NOT announce itself on the screen that added it.
        club = await db.get(Organisation, ids["club"])
        await nm.check_in_person(db, s, club.id, guest_name="Walk-up Trialist", source="admin")
        await db.commit()
        payload = await nm._live_payload(db, s)
        srcs = {a["name"]: a["source"] for a in payload["attendees"]}
        check("a manager-added guest reads 'admin'", srcs.get("Walk-up Trialist"), "admin")

    print("\n── The landing payload ──")
    async with Session() as db:
        d = await pub.get_landing(TOKEN, FakeRequest(), db)
        check("names the club", d["club"]["name"], "Applecross Cricket Club")
        check("reports the live session", len(d["sessions"]), 1)
        check("offers the roster", len(d["players"]) >= 3, True)
        check("says whether a PIN is needed", d["require_pin"], True)
        check("says whether newcomers may register", d["allow_registration"], True)
        check("nobody is identified without a cookie", d["me"], None)
        check("it never says who is already checked in", "attendees" in d, False)

        who = {p["display_name"]: p["has_phone"] for p in d["players"]}
        check("a player with a mobile is marked as able to verify", who.get("Barendse, Jack"), True)
        check("a player with none is marked as not", who.get("Cole, Graeme"), False)

        d2 = await pub.get_landing(TOKEN, FakeRequest(cookies={pub.COOKIE_NAME: cookie}), db)
        check("a returning player is recognised from the cookie",
              d2["me"]["display_name"], "Barendse, Jack")
        check("and is told they are already in", d2["me"]["checked_in"], True)

    print("\n── The admin link panel ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        p = await nm.get_checkin_link(db, club)
        check("hands back a path, not a full URL", p["path"], f"/nets-checkin/{TOKEN}")
        check("reports phone coverage", p["phone_coverage"]["total"] >= 3, True)
        check("counts what is waiting for review", p["pending_registrations"] >= 0, True)

        old = club.net_checkin_token
        p2 = await nm.regenerate_checkin_link(db, club, user)
        check("regenerating changes the token", p2["token"] != old, True)
        try:
            await pub._club_for_token(db, old)
            check("the old link still works", False)
        except Exception as e:
            check("the old QR code stops working at once", getattr(e, "status_code", None), 404)

    print("\n── A token is minted only on first enable ──")
    async with Session() as db:
        fresh = Organisation(id=uuid.uuid4(), name="Fresh CC", slug="fresh-cc",
                             module_overrides=["select"], subscription_status="active")
        db.add(fresh)
        await db.commit()
        check("a club that never turned it on has no token", fresh.net_checkin_token, None)
        user = await db.get(User, ids["user"])
        out = await nm.set_checkin_link(nm.CheckInLinkUpdate(enabled=True), db, fresh, user)
        check("enabling mints one", bool(out["token"]), True)
        minted = out["token"]
        out2 = await nm.set_checkin_link(nm.CheckInLinkUpdate(require_pin=False), db, fresh, user)
        check("a later settings change keeps the same token", out2["token"], minted)
        check("and applies the change", out2["require_pin"], False)

    print("\n── Guests who are not on the roster ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        today = datetime.now(timezone.utc).date()

        # Three nights, one bloke the manager typed in each time, spelled two
        # ways; plus a one-off; plus somebody from another club entirely.
        sessions = []
        for n, lbl in enumerate(["Week 1", "Week 2", "Week 3"]):
            s = NetSession(id=uuid.uuid4(), organisation_id=ids["club"],
                           session_date=today - timedelta(days=n * 7),
                           label=lbl, status="done", version=0)
            db.add(s)
            sessions.append(s)
        old = NetSession(id=uuid.uuid4(), organisation_id=ids["club"],
                         session_date=today - timedelta(days=200),
                         label="Last season", status="done", version=0)
        foreign_s = NetSession(id=uuid.uuid4(), organisation_id=ids["other"],
                               session_date=today, label="Theirs", status="active", version=0)
        db.add_all([old, foreign_s])
        await db.commit()

        for s, nm_ in zip(sessions, ["Dave Trialist", "dave  trialist", "DAVE TRIALIST"]):
            await nm.check_in_person(db, s, ids["club"], guest_name=nm_, source="admin")
        await nm.check_in_person(db, sessions[0], ids["club"], guest_name="One Off", source="admin")
        await nm.check_in_person(db, old, ids["club"], guest_name="Ancient History", source="admin")
        await nm.check_in_person(db, foreign_s, ids["other"], guest_name="Their Guest", source="admin")
        await db.commit()

        out = await nm.list_unresolved_guests(90, db, club)
        names = {g["name"]: g for g in out["guests"]}
        check("one person, not three rows, however it was spelled",
              names["Dave Trialist"]["attended"], 3)
        # Week 1 is the most recent night, so its spelling is the one shown.
        check("the most recent spelling is the one shown", "Dave Trialist" in names, True)
        check("a one-off guest is listed too", names["One Off"]["attended"], 1)
        check("a guest outside the window is left out", "Ancient History" in names, False)
        check("another club's guest is never listed", "Their Guest" in names, False)
        check("most-seen first", out["guests"][0]["name"], "Dave Trialist")
        check("internal row ids are not handed to the browser",
              "attendance_ids" in out["guests"][0], False)

        allt = await nm.list_unresolved_guests(0, db, club)
        check("days=0 reaches all time",
              "Ancient History" in {g["name"] for g in allt["guests"]}, True)

    print("\n── Someone mid-review in Check-in is not offered twice ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        out = await nm.list_unresolved_guests(90, db, club)
        listed = {g["name"] for g in out["guests"]}
        # 'Graeme Cole' was approved earlier, 'Someone Else' dismissed — neither
        # is pending, so both are ordinary guests again if rows remain.
        pending_rows = (await db.execute(text(
            "SELECT count(*) FROM net_checkin_registrations WHERE status = 'pending'"))).scalar()
        check("the pending count is reported rather than the people",
              out["pending_registrations"], pending_rows)

        # 'Bad Email' registered earlier and nobody has decided about them yet,
        # so they are the pending case.
        check("a person waiting in Check-in is not listed here",
              "Bad Email" in listed, False)

        # The complement: settle their registration and they become an ordinary
        # guest again, because nothing is waiting on them any more.
        await db.execute(text(
            "UPDATE net_checkin_registrations SET status = 'dismissed' WHERE full_name = 'Bad Email'"))
        await db.commit()
        out2 = await nm.list_unresolved_guests(90, db, club)
        check("once nobody is waiting on them, they are listed here",
              "Bad Email" in {g["name"] for g in out2["guests"]}, True)
        check("and the pending count drops by exactly one",
              out2["pending_registrations"], out["pending_registrations"] - 1)

        # Put them back, so the later promote test starts where it expects.
        await db.execute(text(
            "UPDATE net_checkin_registrations SET status = 'pending' WHERE full_name = 'Bad Email'"))
        await db.commit()
        out3 = await nm.list_unresolved_guests(90, db, club)
        check("and they drop back out once pending again",
              "Bad Email" in {g["name"] for g in out3["guests"]}, False)

    print("\n── Promoting a guest takes their history with them ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        before = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()

        out = await nm.promote_guest(nm.GuestPromote(key="dave trialist"), db, club, user)
        check("a player is created", out["status"], "ok")
        check("named 'Last, First' like the rest of the roster", out["player_name"], "Trialist, Dave")
        check("all three nights moved, not just the latest", out["sessions_moved"], 3)
        check("nothing was dropped", out["duplicates_dropped"], 0)

        after = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        check("exactly one player was added", after, before + 1)

        pid = uuid.UUID(out["player_id"])
        n = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE player_id = :p"), {"p": pid})).scalar()
        check("their attendance is now theirs, not a guest's", n, 3)
        left = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE guest_name ILIKE 'dave%'"))).scalar()
        check("no guest rows left behind", left, 0)

        out2 = await nm.list_unresolved_guests(90, db, club)
        check("and they are gone from the list",
              "Dave Trialist" in {g["name"] for g in out2["guests"]}, False)

    print("\n── Promoting onto someone already on the roster ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        jack = ids["players"][0]
        s = NetSession(id=uuid.uuid4(), organisation_id=ids["club"],
                       session_date=datetime.now(timezone.utc).date(),
                       label="Clash night", status="done", version=0)
        db.add(s)
        await db.commit()
        # Jack is checked in properly AND typed in as a guest on the same night.
        await nm.check_in_person(db, s, ids["club"], player_id=jack, source="admin")
        await nm.check_in_person(db, s, ids["club"], guest_name="Jacko", source="admin")
        await db.commit()

        before = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        out = await nm.promote_guest(
            nm.GuestPromote(key="jacko", player_id=str(jack)), db, club, user)
        after = (await db.execute(text(
            "SELECT count(*) FROM players WHERE organisation_id = :o"), {"o": ids["club"]})).scalar()
        check("no player is minted when matched to an existing one", after, before)
        check("the duplicate row is dropped, not moved onto a clash",
              out["duplicates_dropped"], 1)
        check("and nothing was moved for that night", out["sessions_moved"], 0)
        n = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE session_id = :s AND player_id = :p"),
            {"s": s.id, "p": jack})).scalar()
        check("they are in that session exactly once", n, 1)

    print("\n── Two guest rows on one night collapse to one ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        s = NetSession(id=uuid.uuid4(), organisation_id=ids["club"],
                       session_date=datetime.now(timezone.utc).date(),
                       label="Double entry", status="done", version=0)
        db.add(s)
        await db.commit()
        await nm.check_in_person(db, s, ids["club"], guest_name="Twice Typed", source="admin")
        await nm.check_in_person(db, s, ids["club"], guest_name="twice typed", source="admin")
        await db.commit()
        out = await nm.promote_guest(nm.GuestPromote(key="twice typed"), db, club, user)
        check("one row moves and the other is dropped",
              (out["sessions_moved"], out["duplicates_dropped"]), (1, 1))
        n = (await db.execute(text(
            "SELECT count(*) FROM net_attendance WHERE session_id = :s AND player_id = :p"),
            {"s": s.id, "p": uuid.UUID(out["player_id"])})).scalar()
        check("the unique index is never violated", n, 1)

    print("\n── Promotion refuses what it should ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        other = await db.get(Organisation, ids["other"])
        user = await db.get(User, ids["user"])
        for label, body, code in [
            ("an empty key", nm.GuestPromote(key="   "), 422),
            ("a guest nobody has heard of", nm.GuestPromote(key="ghost person"), 404),
            ("another club's player",
             nm.GuestPromote(key="one off", player_id=str(ids["foreign"])), 422),
            ("a junk player id", nm.GuestPromote(key="one off", player_id="not-a-uuid"), 422),
        ]:
            try:
                await nm.promote_guest(body, db, club, user)
                check(f"{label} refused", False)
            except Exception as e:
                check(f"{label} → {code}", getattr(e, "status_code", None), code)

        # A key from one club must not reach another club's guest rows.
        try:
            await nm.promote_guest(nm.GuestPromote(key="one off"), db, other, user)
            check("a key used against the wrong club refused", False)
        except Exception as e:
            check("a key used against the wrong club → 404", getattr(e, "status_code", None), 404)

    print("\n── A promoted guest stops waiting in the Check-in queue ──")
    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        user = await db.get(User, ids["user"])
        st_before = (await db.execute(text(
            "SELECT status FROM net_checkin_registrations WHERE full_name = 'Bad Email'"))).scalar()
        check("they start out pending", st_before, "pending")
        await nm.promote_guest(nm.GuestPromote(key="bad email"), db, club, user)
        st_after = (await db.execute(text(
            "SELECT status, player_id FROM net_checkin_registrations WHERE full_name = 'Bad Email'"))).fetchone()
        check("promoting settles their registration too", st_after[0], "approved")
        check("and records who they became", st_after[1] is not None, True)

    print("\n── Migration 272 applies cleanly, three times ──")
    async with engine.begin() as conn:
        # Against a POPULATED pre-272 table: drop what 272 adds, then re-apply.
        await conn.execute(text("DROP TABLE IF EXISTS net_checkin_registrations"))
        await conn.execute(text("DROP INDEX IF EXISTS ix_organisations_net_checkin_token"))
        await conn.execute(text(
            "ALTER TABLE organisations "
            "DROP COLUMN IF EXISTS net_checkin_allow_registration, "
            "DROP COLUMN IF EXISTS net_checkin_require_pin, "
            "DROP COLUMN IF EXISTS net_checkin_enabled, "
            "DROP COLUMN IF EXISTS net_checkin_token"))
        await conn.execute(text("ALTER TABLE net_attendance DROP COLUMN IF EXISTS source"))

        stmts = [
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_token TEXT",
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_enabled BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_require_pin BOOLEAN NOT NULL DEFAULT true",
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_allow_registration BOOLEAN NOT NULL DEFAULT true",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_organisations_net_checkin_token "
            "ON organisations (net_checkin_token) WHERE net_checkin_token IS NOT NULL",
            "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'admin'",
            """CREATE TABLE IF NOT EXISTS net_checkin_registrations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
                session_id UUID REFERENCES net_sessions(id) ON DELETE SET NULL,
                attendance_id UUID REFERENCES net_attendance(id) ON DELETE SET NULL,
                full_name TEXT NOT NULL, phone TEXT, email TEXT, date_of_birth DATE,
                previous_club TEXT, status TEXT NOT NULL DEFAULT 'pending',
                player_id UUID REFERENCES players(id) ON DELETE SET NULL,
                reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT now())""",
            "CREATE INDEX IF NOT EXISTS idx_net_checkin_registrations_org_status "
            "ON net_checkin_registrations (organisation_id, status, created_at DESC)",
        ]
        for run in range(3):
            for st in stmts:
                await conn.execute(text(st))
        check("three applications leave one source column", (await conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='net_attendance' AND column_name='source'"))).scalar(), 1)
        check("existing attendance rows default to 'admin'", (await conn.execute(text(
            "SELECT count(*) FROM net_attendance WHERE source <> 'admin'"))).scalar(), 0)
        check("the registrations table is there", (await conn.execute(text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='net_checkin_registrations'"))).scalar(), 1)

    print("\n── The token index is partial, so NULLs don't collide ──")
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO organisations (id, name, slug, is_active) VALUES (gen_random_uuid(), 'A CC', 'a-cc-x', false)"))
        await conn.execute(text(
            "INSERT INTO organisations (id, name, slug, is_active) VALUES (gen_random_uuid(), 'B CC', 'b-cc-x', false)"))
        check("two clubs may both have no token", True, True)
        try:
            await conn.execute(text("UPDATE organisations SET net_checkin_token = 'dup' WHERE slug IN ('a-cc-x','b-cc-x')"))
            check("but two clubs may not share one", False)
        except Exception:
            check("but two clubs may not share one", True)

    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
