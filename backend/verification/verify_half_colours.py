"""Verification: the two "half available" colours are a club setting.

A two-day game is answered a week at a time; a player free for one week and away
for the other is drawn in a colour of the club's choosing (BetterSelect Settings),
one for "week 1 only" and one for "week 2 only". Drives the SHIPPED route bodies
`PATCH /selection-rules/settings` and `GET /availability/config` against a real
Postgres:

  * with nothing set, both colours are the platform defaults
  * setting one leaves the other, and every other setting, alone
  * a value that is not #rrggbb is refused (400) and nothing is stored
  * upper case is stored lower case
  * an explicit null or empty string puts a colour back to its default; an ABSENT
    key leaves it (model_fields_set)
  * the screens' read (`/availability/config`) sees the same colours

CONTROL MODE: against the commit before this change the keys do not exist, so the
checks FAIL (they are read with .get) rather than crash.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_half_colours.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, User
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
    import app.routers.selection_rules as sr
    import app.routers.availability as av

    org, uid = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Organisation(id=org, name="Half CC", slug=f"half-{org.hex[:8]}", module_overrides=["select"]))
        db.add(User(id=uid, username=f"u{uid.hex[:8]}", email=f"{uid.hex[:6]}@x.com", password_hash="x"))
        await db.commit()

    async def patch(**kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                out = await sr.patch_settings(sr.SettingsBody(**kw), db=db, club=club, _=None)
                return out, None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

    async def config():
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await av.availability_config(club=club, user=None)

    halves = lambda o: (o or {}).get("half_colours")

    print("\n# defaults")
    cfg = await config()
    check("nothing set: week 1 is purple, week 2 is cyan", halves(cfg), {"w1": "#a855f7", "w2": "#06b6d4"})
    check("the screens' config still carries Maybe", cfg.get("allow_maybe"), True)

    print("\n# set, one at a time")
    out, err = await patch(half_colour_w1="#FF00AA")
    check("set week 1 (upper case in)", halves(out), {"w1": "#ff00aa", "w2": "#06b6d4"})
    check("...the screens read the same", halves(await config()), {"w1": "#ff00aa", "w2": "#06b6d4"})
    out, err = await patch(half_colour_w2="#00ff88")
    check("set week 2: week 1 is untouched", halves(out), {"w1": "#ff00aa", "w2": "#00ff88"})

    print("\n# other settings are not disturbed, and do not disturb the colours")
    out, err = await patch(default_team_size=12)
    check("a change to another setting leaves both colours", halves(out), {"w1": "#ff00aa", "w2": "#00ff88"})
    check("...and that setting took", (out or {}).get("default_team_size"), 12)
    out, err = await patch(half_colour_w1="#112233", show_fees=False)
    check("colour and another setting in one write", (halves(out), (out or {}).get("show_fees")), ({"w1": "#112233", "w2": "#00ff88"}, False))

    print("\n# bad values are refused and nothing is stored")
    for bad in ("red", "#12345", "#gggggg", "rgb(1,2,3)", "javascript:alert(1)", "#1234567"):
        out, err = await patch(half_colour_w2=bad)
        check(f"{bad!r} is refused", err, 400)
    check("week 2 kept its colour", halves(await config()), {"w1": "#112233", "w2": "#00ff88"})

    print("\n# clearing")
    out, err = await patch(half_colour_w1=None)
    check("an explicit null puts week 1 back to the default", halves(out), {"w1": "#a855f7", "w2": "#00ff88"})
    out, err = await patch(half_colour_w2="  ")
    check("an empty string does the same for week 2", halves(out), {"w1": "#a855f7", "w2": "#06b6d4"})
    stored = (await (await engine.connect()).execute(text("SELECT selection_rules_config FROM organisations WHERE id=:i"), {"i": org})).scalar()
    check("nothing but the defaults left in the stored settings for colours", "half_colours" not in (stored or {}), True)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
