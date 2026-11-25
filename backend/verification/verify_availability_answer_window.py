"""Verification: a club limits how many weeks ahead players answer for themselves,
against a real Postgres.

Asked for (Nov 2026): some clubs want players to say Available only for the next
4 weeks, while still letting them say Unavailable up to 8 weeks out (holidays).

Drives the SHIPPED code: the admin `POST /availability/self-service` route body
(`update_self_service`), the public `GET /public/availability/{token}/me`
(`get_me`) and `POST /public/availability/{token}/me` (`set_me`).

CONTROL MODE: against the commit before this change the window checks FAIL (the
admin body ignores the new keys, payload keys are read with `.get`, and a write
past the window is accepted) rather than crash. Every "refused" check is paired
with one that proves the same write is accepted inside the window.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_availability_answer_window.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from jose import jwt as jose_jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.config.settings import settings
from app.models.db import Base, Fixture, Grade, Organisation, Player, PlayerAvailability, Season, Team, User

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        # The player page reads player_registrations on every name list and session (migration 398).
        try:
            from app.services.player_registration_ddl import STATEMENTS as _REG_DDL
            for stmt in _REG_DDL:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        # Lifespan tables the fixture reads touch (copied as verify_two_day_availability.py does).
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(ddl))
        for mod in ("app.services.audit_ddl", "app.services.junior_hiding_ddl", "app.services.team_sides_ddl",
                    "app.services.competition_ddl", "app.services.availability_window_ddl"):
            try:
                for stmt in importlib.import_module(mod).STATEMENTS:
                    await conn.execute(text(stmt))
            except (ImportError, AttributeError):
                print(f"  (no {mod}: control run)")


async def main():
    await build_schema()
    import app.routers.availability as av
    import app.routers.public_availability as pa

    org, season, grade, team, user_id, ann = (uuid.uuid4() for _ in range(6))
    token = "tok-" + uuid.uuid4().hex
    today = date.today()
    # Fixture days counted from today: inside 4 weeks, on the 4-week line, just past
    # it, inside 8 weeks, on the 8-week line, just past it, well past both.
    offsets = [7, 28, 29, 42, 56, 57, 70]
    day = {n: today + timedelta(days=n) for n in offsets}

    async with Session() as db:
        db.add(Organisation(id=org, name="Window CC", slug=f"win-{org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=token, availability_self_service_enabled=True,
                            availability_require_pin=False))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:6]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="1st Grade"))
        await db.flush()
        db.add(Team(id=team, organisation_id=org, name="1st XI", sequence=1, grade_id=grade))
        db.add(Player(id=ann, organisation_id=org, name="Ann", gender="female", is_player=True, status="active",
                      phone="0400111222"))
        await db.flush()
        for n in offsets:
            db.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=grade, team_id=team, source="manual",
                           status="UPCOMING", played_on=day[n], start_time="12:30", opponent_name=f"Opp {n}",
                           label=f"Round {n}"))
        # A selector already recorded Ann as available 10 weeks out.
        db.add(PlayerAvailability(organisation_id=org, player_id=ann, avail_date=day[70], status="AVAILABLE",
                                  source="admin"))
        await db.commit()

    cookie = jose_jwt.encode({"club": str(org), "pid": str(ann), "typ": "avail",
                              "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                             settings.secret_key, algorithm=settings.algorithm)
    req = Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={cookie}".encode())],
                   "client": ("1.2.3.4", 1)})

    async def setme(n, status):
        try:
            async with Session() as db:
                r = await pa.set_me(token, pa.SetBody(date=day[n], status=status), req, db=db)
            return r.get("status")
        except HTTPException as e:
            return f"{e.status_code}: {e.detail}"

    async def admin(**body):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                return await av.update_self_service(av.SelfServiceUpdate(**body), db=db, club=club, user=user)
            except HTTPException as e:
                return {"error": e.status_code, "detail": e.detail}

    async def stored(n):
        async with Session() as db:
            r = (await db.execute(text("SELECT status FROM player_availability WHERE player_id=:p AND avail_date=:d"),
                                  {"p": ann, "d": day[n]})).first()
        return r[0] if r else None

    print("\n# A. No limit set (every existing club): any upcoming date can be answered")
    check("Available 8 weeks + 1 day out is accepted", await setme(57, "AVAILABLE"), "ok")
    check("...and stored", await stored(57), "AVAILABLE")

    print("\n# B. The admin sets the two windows")
    p = await admin(weeks_available=4, weeks_unavailable=8)
    check("payload echoes weeks_available", p.get("weeks_available"), 4)
    check("payload echoes weeks_unavailable", p.get("weeks_unavailable"), 8)
    p = await admin(require_pin=False)
    check("a body without the keys leaves both alone", (p.get("weeks_available"), p.get("weeks_unavailable")), (4, 8))
    p = await admin(weeks_available=0)
    check("0 weeks is refused", p.get("error"), 400)
    p = await admin(weeks_unavailable=53)
    check("53 weeks is refused", p.get("error"), 400)
    p = await admin()
    check("...and a refused value changed nothing", (p.get("weeks_available"), p.get("weeks_unavailable")), (4, 8))

    print("\n# C. The player's page is told the windows")
    async with Session() as db:
        me = await pa.get_me(token, req, db=db)
    win = me.get("answer_window") or {}
    check("available_weeks", win.get("available_weeks"), 4)
    check("available_until is 28 days on", win.get("available_until"), day[28].isoformat())
    check("unavailable_until is 56 days on", win.get("unavailable_until"), day[56].isoformat())
    check("dates past both windows are still listed", day[70].isoformat() in [d["date"] for d in me["dates"]], True)
    check("the selector's answer 10 weeks out still shows", (me["availability"].get(day[70].isoformat()) or {}).get("status"),
          "AVAILABLE")

    print("\n# D. The player's own writes respect the windows")
    check("Available 1 week out: accepted", await setme(7, "AVAILABLE"), "ok")
    check("Available exactly 4 weeks out: accepted", await setme(28, "AVAILABLE"), "ok")
    r = await setme(29, "AVAILABLE")
    check("Available 4 weeks + 1 day out: refused", str(r).startswith("400"), True)
    check("...saying when it opens", "from " + (today + timedelta(days=1)).strftime("%a %-d %b") in str(r), True)
    check("...and nothing stored", await stored(29), None)
    check("Maybe 4 weeks + 1 day out: refused (sits with Available)", str(await setme(29, "MAYBE")).startswith("400"), True)
    check("Maybe exactly 4 weeks out: accepted", await setme(28, "MAYBE"), "ok")
    check("Unavailable 6 weeks out: accepted", await setme(42, "UNAVAILABLE"), "ok")
    check("Unavailable exactly 8 weeks out: accepted", await setme(56, "UNAVAILABLE"), "ok")
    check("Unavailable 8 weeks + 1 day out: refused", str(await setme(57, "UNAVAILABLE")).startswith("400"), True)
    check("Available 6 weeks out: refused", str(await setme(42, "AVAILABLE")).startswith("400"), True)
    check("...and the Unavailable answer there is kept", await stored(42), "UNAVAILABLE")
    check("Taking an answer back is always allowed (10 weeks out)", await setme(70, "NO_RESPONSE"), "ok")

    print("\n# E. Clearing a window (explicit null) lifts it")
    p = await admin(weeks_available=None)
    check("weeks_available cleared", p.get("weeks_available", "absent"), None)
    check("weeks_unavailable untouched", p.get("weeks_unavailable"), 8)
    check("Available 6 weeks out: accepted again", await setme(42, "AVAILABLE"), "ok")
    check("Unavailable past 8 weeks: still refused", str(await setme(70, "UNAVAILABLE")).startswith("400"), True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
