"""Verification: the first time a club opens Club Room Mode, nothing 500s.

Reported from production (Summer Hill CC): opening BetterStats > Club Room Mode
showed an "Internal Server Error" toast. The page fires GET /settings, two
GET /media calls and GET /public-link together. A club that has never opened
Club Room has no ``club_room_settings`` row, and every one of those handlers that
needs it ran ``_get_or_create_settings``: read the row, find none, insert,
commit. Two of them doing that at once both see "none", both insert, and the
second commit hits the primary key. The unhandled IntegrityError is the plain
"Internal Server Error" the page toasts.

Runs the SHIPPED ``get_settings`` and ``get_public_link`` route bodies on separate
sessions, concurrently, against a club with no settings row, many times over.
Every "no error" check is paired with a check that the race can bite (the
control run against the previous code fails it) and with a check that exactly
one settings row exists afterwards and that an existing club's values are kept.

CONTROL MODE. Run against the commit before the fix, the first-visit trials
raise. The raise is caught and counted, so the control does not crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/cr_first_visit?host=/var/run/postgresql \
      python verification/verify_club_room_first_visit.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, ClubRoomSettings, Organisation
from app.routers import club_room as cr

PASS = FAIL = 0
TRIALS = 25


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


async def main() -> None:
    eng = create_async_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        # The lifespan adds the unique index on link_token; copy it so the harness matches.
        await c.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_room_settings_link_token "
            "ON club_room_settings(link_token) WHERE link_token IS NOT NULL"))
    S = async_sessionmaker(eng, expire_on_commit=False)

    async def new_club(tag: str) -> uuid.UUID:
        oid = uuid.uuid4()
        async with S() as s:
            s.add(Organisation(id=oid, name=f"First visit {tag}", slug=f"fv-{tag}-{oid.hex[:8]}"))
            await s.commit()
        return oid

    async def hit(oid: uuid.UUID, fn: str):
        # One session per call, as the app gives each request its own.
        async with S() as s:
            club = await s.get(Organisation, oid)
            try:
                out = await getattr(cr, fn)(current_user=None, club=club, db=s)
                return out, None
            except Exception as exc:  # noqa: BLE001 - the control raises; report it, do not crash
                await s.rollback()
                return None, f"{fn}: {type(exc).__name__}"

    print(f"== first visit: settings + public-link (x2) at once, {TRIALS} clubs")
    bad = []
    dup_rows = 0
    for i in range(TRIALS):
        oid = await new_club(str(i))
        results = await asyncio.gather(hit(oid, "get_settings"), hit(oid, "get_public_link"), hit(oid, "get_public_link"))
        bad += [err for _, err in results if err]
        async with S() as s:
            n = await s.scalar(text("SELECT count(*) FROM club_room_settings WHERE organisation_id = :o"), {"o": oid})
        if n != 1:
            dup_rows += 1
        if i == 0:
            first = results
    check("no request raised on a club's first visit", not bad, f"{len(bad)} raised, e.g. {bad[:2]}")
    check("every club ended with exactly one settings row", dup_rows == 0, f"{dup_rows} clubs did not")
    settings_out = first[0][0] or {}
    check("settings come back with the defaults (so the pass above is not an empty answer)",
          settings_out.get("rotation_seconds") == 15 and settings_out.get("theme") == "dark"
          and settings_out.get("enabled") is False and settings_out.get("slides") == [], str(settings_out))
    link_out = first[1][0] or {}
    check("public link comes back off with no token or PIN",
          link_out.get("enabled") is False and link_out.get("link_token") is None and link_out.get("has_pin") is False,
          str(link_out))

    print("== a club that already has settings keeps them")
    oid = await new_club("kept")
    token = f"tok-{uuid.uuid4().hex}"  # unique per run: the table has a unique index on link_token
    async with S() as s:
        s.add(ClubRoomSettings(organisation_id=oid, enabled=True, rotation_seconds=42, theme="light",
                               shuffle=True, link_token=token, public_link_enabled=True, require_pin=False))
        await s.commit()
    results = await asyncio.gather(hit(oid, "get_settings"), hit(oid, "get_public_link"))
    check("no request raised", not [e for _, e in results if e], str(results))
    kept = results[0][0] or {}
    check("its saved values are returned unchanged",
          kept.get("rotation_seconds") == 42 and kept.get("theme") == "light" and kept.get("shuffle") is True
          and kept.get("enabled") is True, str(kept))
    kept_link = results[1][0] or {}
    check("its public link token and switches are returned unchanged",
          kept_link.get("link_token") == token and kept_link.get("enabled") is True
          and kept_link.get("require_pin") is False, str(kept_link))

    await eng.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
