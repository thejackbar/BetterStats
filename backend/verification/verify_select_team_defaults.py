"""Verification: BetterSelect's club-wide "played within" windows and per-team
starting filters ("rules") are club settings.

Asked for (Applecross, Oct 2026): the "Played within" and "Show juniors" controls
come off the screens and live in Settings, with a "played any time" choice; and a
team can have starting filters as rules, for example a women's team that starts on
Gender = Women and a 1st XI that only sees the top 2 or 3 squads. Drives the
SHIPPED route bodies `PATCH /selection-rules/settings` and `GET
/availability/config` against a real Postgres:

  * defaults: Selection and Whiteboard 3 years, Availability any time (0), no rules
  * a window is set one screen at a time; 0 is "any time"; junk is refused (400)
  * team rules round-trip, normalised: a canonical team id, a gender, a squad
    list, top N squads, a team's own played window
  * a rule with no team, or with nothing to filter on, is never stored
  * absent leaves the rules alone; [] or null removes them all
  * the config the screens read carries the rules and the club's squads in XI order
  * other settings are untouched by any of it

CONTROL MODE: against the commit before this change the keys do not exist, so the
checks FAIL (read with .get) rather than crash.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_select_team_defaults.py
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

from app.models.db import Base, Organisation, Team
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

    org = uuid.uuid4()
    t1, t2, t3, off = (uuid.uuid4() for _ in range(4))
    async with Session() as db:
        db.add(Organisation(id=org, name="Defaults CC", slug=f"def-{org.hex[:8]}", module_overrides=["select"]))
        await db.flush()
        db.add(Team(id=t2, organisation_id=org, name="2nd XI", sequence=2))
        db.add(Team(id=t1, organisation_id=org, name="1st XI", sequence=1))
        db.add(Team(id=t3, organisation_id=org, name="Women's XI", sequence=0))
        db.add(Team(id=off, organisation_id=org, name="Old Colts", sequence=3, is_active=False))
        await db.commit()

    async def patch(**kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await sr.patch_settings(sr.SettingsBody(**kw), db=db, club=club, _=None), None
            except HTTPException as e:
                await db.rollback()
                return None, e.status_code

    async def config():
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await av.availability_config(db=db, club=club, user=None)
            except TypeError:
                return await av.availability_config(club=club, user=None)

    py = lambda o: (o or {}).get("played_years")
    td = lambda o: (o or {}).get("team_defaults")

    print("\n# defaults")
    cfg = await config()
    check("windows: Selection 3 years, Availability any time", py(cfg), {"selection": 3, "availability": 0})
    check("no team rules", td(cfg), [])

    print("\n# played windows")
    out, err = await patch(played_years_selection=0)
    check("Selection to any time (0)", py(out), {"selection": 0, "availability": 0})
    out, err = await patch(played_years_availability=5)
    check("Availability to 5 years leaves Selection alone", py(out), {"selection": 0, "availability": 5})
    out, err = await patch(played_years_selection=-1)
    check("-1 is 'this season'", py(out), {"selection": -1, "availability": 5})
    await patch(played_years_selection=0)
    for bad in (-2, 51, 999):
        out, err = await patch(played_years_selection=bad)
        check(f"{bad} years is refused", err, 400)
    check("the screens read the same", py(await config()), {"selection": 0, "availability": 5})

    print("\n# team rules round-trip")
    rules = [
        {"id": "womens", "team_ids": [str(t3)], "gender": "Women"},
        {"id": "firsts", "team_ids": [str(t1).upper(), str(t1)], "top_squads": 3, "played_years": 2},
        {"team_ids": [str(t2)], "squads": ["1st XI", " 2nd XI ", "1st XI"]},
    ]
    out, err = await patch(team_defaults=rules)
    got = td(out) or []
    check("three rules stored", len(got), 3)
    check("'Women' is stored as female", (got[0] if got else {}).get("gender"), "female")
    check("a team id is canonical and not repeated", (got[1] if len(got) > 1 else {}).get("team_ids"), [str(t1)])
    check("top N squads and the team's own window are kept", ((got[1] if len(got) > 1 else {}).get("top_squads"), (got[1] if len(got) > 1 else {}).get("played_years")), (3, 2))
    check("squad names are trimmed and not repeated", (got[2] if len(got) > 2 else {}).get("squads"), ["1st XI", "2nd XI"])
    check("a rule with no id is given one", bool((got[2] if len(got) > 2 else {}).get("id")), True)

    print("\n# half-made rules are never stored")
    out, err = await patch(team_defaults=[
        {"team_ids": [], "gender": "female"},                 # no team
        {"team_ids": [str(t1)]},                              # nothing to filter on
        {"team_ids": ["not-a-uuid"], "gender": "male"},       # no real team
        {"team_ids": [str(t1)], "gender": "other"},           # not a gender
        {"team_ids": [str(t1)], "top_squads": 0},             # not a number of squads
        "junk", 7, None,
        {"team_ids": [str(t1)], "top_squads": 2},             # the one good one
    ])
    check("only the complete rule is kept", [(r["team_ids"], r["top_squads"]) for r in (td(out) or [])], [([str(t1)], 2)])
    try:
        sr.SettingsBody(team_defaults="nope")
        refused = False
    except Exception:
        refused = True
    check("something that is not a list is refused at the API (422)", refused, True)

    print("\n# absent leaves them, empty removes them")
    await patch(team_defaults=[{"team_ids": [str(t1)], "gender": "male"}])
    out, err = await patch(played_years_selection=4)
    check("a change to something else leaves the rules", len(td(out) or []), 1)
    out, err = await patch(team_defaults=[])
    check("an empty list removes every rule", td(out), [])
    await patch(team_defaults=[{"team_ids": [str(t1)], "gender": "male"}])
    out, err = await patch(team_defaults=None)
    check("null removes them too", td(out), [])
    stored = (await (await engine.connect()).execute(text("SELECT selection_rules_config FROM organisations WHERE id=:i"), {"i": org})).scalar() or {}
    check("nothing left stored for rules", "team_defaults" in stored, False)

    print("\n# the config the screens read")
    await patch(team_defaults=[{"team_ids": [str(t3)], "gender": "female"}])
    cfg = await config()
    check("carries the rule", [(r["team_ids"], r["gender"]) for r in td(cfg) or []], [([str(t3)], "female")])
    names = [q["name"] for q in (cfg.get("squads") or [])]
    check("squads in XI order, unranked last, switched-off teams left out", names, ["1st XI", "2nd XI", "Women's XI"])
    check("windows and colours still there", (py(cfg), bool(cfg.get("half_colours"))), ({"selection": 4, "availability": 5}, True))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
