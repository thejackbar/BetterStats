"""Verification: the two weeks of a two-day game have the club's own names.

A club that calls the weeks A and B should read "A Only" and "B OUT", not W1 and
W2. The names are one club setting (`selection_rules_config.week_names`, no
migration) written through `PATCH /selection-rules/settings` and read by every
screen through `GET /availability/config` and by the player's own page through
the public landing and `/me`. Drives the SHIPPED route bodies against a real
Postgres:

  * with nothing set, the names are W1 and W2
  * setting one leaves the other, and every other setting, alone
  * trimmed, inner spaces collapsed, control characters dropped, capped at ten
  * an explicit null or blank puts a name back to its default; an ABSENT key
    leaves it (model_fields_set)
  * the screens' read and the public landing carry the same names

CONTROL MODE: against the commit before this change the keys do not exist, so the
checks FAIL (they are read with .get) rather than crash.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_week_names.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation
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
    import app.routers.availability as av
    import app.routers.public_availability as pa
    import app.routers.selection_rules as sr

    org = uuid.uuid4()
    token = f"tok-{org.hex}"
    async with Session() as db:
        db.add(Organisation(id=org, name="Names CC", slug=f"names-{org.hex[:8]}", module_overrides=["select"],
                            availability_link_token=token, availability_self_service_enabled=True))
        await db.commit()

    async def patch(**kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await sr.patch_settings(sr.SettingsBody(**kw), db=db, club=club, _=None)

    async def config():
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await av.availability_config(db=db, club=club, user=None)

    async def landing():
        async with Session() as db:
            return await pa.get_landing(token, db=db)

    names = lambda o: (o or {}).get("week_names")

    print("\n# defaults")
    check("nothing set: W1 and W2 on the screens' read", names(await config()), {"w1": "W1", "w2": "W2"})
    check("...and on the public landing", names(await landing()), {"w1": "W1", "w2": "W2"})
    check("the screens' config still carries the colours", bool((await config()).get("half_colours")))

    print("\n# set, one at a time")
    out = await patch(week_name_w1="A")
    check("set the first week to A", names(out), {"w1": "A", "w2": "W2"})
    out = await patch(week_name_w2="B")
    check("set the second: the first is untouched", names(out), {"w1": "A", "w2": "B"})
    check("the screens read the same", names(await config()), {"w1": "A", "w2": "B"})
    check("the public landing reads the same", names(await landing()), {"w1": "A", "w2": "B"})

    print("\n# other settings do not disturb the names, and the names do not disturb them")
    out = await patch(default_team_size=12)
    check("another setting leaves both names", names(out), {"w1": "A", "w2": "B"})
    out = await patch(half_colour_w1="#112233", week_name_w2="Sat 2")
    check("a colour and a name in one write", (out["half_colours"]["w1"], names(out)), ("#112233", {"w1": "A", "w2": "Sat 2"}))

    print("\n# cleaning")
    out = await patch(week_name_w1="   Day   One   ")
    check("trimmed and inner spaces collapsed", (names(out) or {}).get("w1"), "Day One")
    out = await patch(week_name_w1="x" * 40)
    check("capped at ten characters", (names(out) or {}).get("w1"), "x" * 10)
    out = await patch(week_name_w1="A\x00\x07\nB")
    check("control characters are dropped, not stored", (names(out) or {}).get("w1"), "A B")

    print("\n# clearing")
    out = await patch(week_name_w1=None)
    check("an explicit null puts the first week back to W1", names(out), {"w1": "W1", "w2": "Sat 2"})
    out = await patch(week_name_w2="   ")
    check("a blank string does the same for the second", names(out), {"w1": "W1", "w2": "W2"})
    stored = (await (await engine.connect()).execute(text("SELECT selection_rules_config FROM organisations WHERE id=:i"), {"i": org})).scalar()
    check("nothing but the defaults is left in the stored settings", "week_names" not in (stored or {}), True)
    out = await patch(week_name_w1="A")
    out = await patch(show_fees=False)
    check("an ABSENT key leaves a name alone", names(out), {"w1": "A", "w2": "W2"})

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
