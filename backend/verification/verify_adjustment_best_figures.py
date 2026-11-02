"""The season adjustment's best bowling is one entry, and the profile shows wickets and runs.

Reported by Hamilton Veterans (Oct 2026): best bowling read "1 wicket", "4wickets" and the like.
Typed games were one cause (fixed: v9.137.2). The adjustment form was the other: it asked for
"Best, wickets" and "Best figures" in two boxes, and a person who filled only the first left the
profile with nothing but a wicket count to print.

Now the form has ONE box, "Best bowling (wickets/runs, e.g. 4/13)", and the server reads the
wickets off the figures so the two can never disagree. Runs the SHIPPED route bodies
(`create_season_adjustment`, `import_season_adjustments`) and reads the result back through the
career reader the profile uses.

THE CONTROL RUN is this file against the previous commit: a figures-only entry saves with no
wickets and the profile says "N wickets" (here: best_figures_wickets None, figures None).

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pw@127.0.0.1:5432/bstest \
  python verification/verify_adjustment_best_figures.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import UploadFile
from sqlalchemy import text

import verify_records_timing as base
from app.models.db import Organisation, User
from app.routers import manual_entries as me
from app.services import aggregations as agg
from app.services import superseded_ddl

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label + (f" -- {detail}" if detail else ""))
        print(f"  FAIL {label}" + (f" -- {detail}" if detail else ""))


ORG = uuid.UUID("e1000000-0000-0000-0000-000000000001")
SEASON = uuid.UUID("e2000000-0000-0000-0000-000000000001")
USER = uuid.UUID("e3000000-0000-0000-0000-000000000001")
P_FIG, P_STALE, P_LEGACY, P_CSV, P_OLDFIG = (uuid.UUID(f"e4000000-0000-0000-0000-00000000000{n}") for n in (1, 2, 3, 4, 5))
NAMES = {P_FIG: "Figures, Fred", P_STALE: "Stale, Sam", P_LEGACY: "Legacy, Len", P_CSV: "Csv, Cass", P_OLDFIG: "Oldfig, Ola"}


async def career(pid) -> dict:
    async with base.Session() as s:
        return await agg.get_career_bowling(s, str(pid)) or {}


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as s:
        await s.execute(text("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, 'Hamilton Veterans Cricket Club', 'hvcc', true)"), {"i": ORG})
        await s.execute(text("INSERT INTO users (id, username, password_hash, failed_login_count) VALUES (:i, 'boss', 'x', 0)"), {"i": USER})
        await s.execute(text("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, 'Summer 2013/14', 2013)"), {"i": SEASON, "o": ORG})
        for pid, nm in NAMES.items():
            await s.execute(text("INSERT INTO players (id, organisation_id, name, grassroots_id, status) VALUES (:i, :o, :n, :g, 'active')"),
                            {"i": pid, "o": ORG, "n": nm, "g": str(pid)})
        await s.commit()

    club = Organisation(id=ORG, name="Hamilton Veterans Cricket Club", slug="hvcc")
    user = User(id=USER, username="boss")

    def body(pid, **kw):
        return me.SeasonAdjustmentIn(player_id=str(pid), season_id=str(SEASON), bowling_innings=1, bowling_wickets=4,
                                     bowling_runs=60, bowling_overs=10, **kw)

    print("\n-- the model --")
    m = me.SeasonAdjustmentIn(player_id="x", season_id="y", bowling_best_figures="4/13")
    check("figures alone give the wickets", m.bowling_best_wickets == 4 and m.bowling_best_figures == "4-13",
          f"{m.bowling_best_wickets!r} {m.bowling_best_figures!r}")
    m = me.SeasonAdjustmentIn(player_id="x", season_id="y", bowling_best_figures="4-13", bowling_best_wickets=9)
    check("figures win over a stale wickets box", m.bowling_best_wickets == 4, f"{m.bowling_best_wickets!r}")
    m = me.SeasonAdjustmentIn(player_id="x", season_id="y", bowling_best_wickets=3)
    check("wickets alone are still accepted (older rows)", m.bowling_best_wickets == 3 and m.bowling_best_figures is None)
    m = me.SeasonAdjustmentIn(player_id="x", season_id="y")
    check("nothing entered stays nothing", m.bowling_best_wickets is None and m.bowling_best_figures is None)
    try:
        me.SeasonAdjustmentIn(player_id="x", season_id="y", bowling_best_figures="four for thirteen")
        check("figures that are not figures are refused", False, "accepted")
    except ValueError:
        check("figures that are not figures are refused", True)

    print("\n-- saved through the shipped create route, read back as the profile reads it --")
    async with base.Session() as s:
        await me.create_season_adjustment(body(P_FIG, bowling_best_figures="4/13"), user, club, s)
        await me.create_season_adjustment(body(P_STALE, bowling_best_figures="5-20", bowling_best_wickets=2), user, club, s)
        await me.create_season_adjustment(body(P_LEGACY, bowling_best_wickets=4), user, club, s)
    c = await career(P_FIG)
    check("figures only: the profile prints 4-13", c.get("best_bowling_figures") == "4-13", f"{c.get('best_bowling_figures')!r}")
    check("and the wicket count agrees", c.get("best_figures_wickets") == 4, f"{c.get('best_figures_wickets')!r}")
    c = await career(P_STALE)
    check("a stale wickets box is overruled: 5-20, 5 wickets", c.get("best_bowling_figures") == "5-20" and c.get("best_figures_wickets") == 5,
          f"{c.get('best_bowling_figures')!r} {c.get('best_figures_wickets')!r}")
    c = await career(P_LEGACY)
    check("an older wickets-only row still reads as a wicket count, as it should",
          c.get("best_figures_wickets") == 4 and c.get("best_bowling_figures") is None,
          f"{c.get('best_figures_wickets')!r} {c.get('best_bowling_figures')!r}")

    print("\n-- rows the OLD form already saved: figures typed, wickets box left empty --")
    async with base.Session() as s:
        await s.execute(text("INSERT INTO manual_season_adjustments (organisation_id, player_id, season_id, bowling_best_figures, "
                             " bowling_wickets, bowling_innings) VALUES (:o, :p, :s, '6-12', 6, 1)"),
                        {"o": ORG, "p": P_OLDFIG, "s": SEASON})
        await s.commit()
    c = await career(P_OLDFIG)
    check("their figures still print (6-12)", c.get("best_bowling_figures") == "6-12", f"{c.get('best_bowling_figures')!r}")
    check("and the wicket count is read off them", c.get("best_figures_wickets") == 6, f"{c.get('best_figures_wickets')!r}")

    print("\n-- the CSV import of adjustments --")
    header = "player_name,season_name,bowling_innings,bowling_overs,bowling_wickets,bowling_runs,bowling_best_figures\n"
    csv_text = header + "\"Csv, Cass\",Summer 2013/14,1,10,3,50,3/21\n"
    up = UploadFile(filename="adj.csv", file=io.BytesIO(csv_text.encode()))
    async with base.Session() as s:
        res = await me.import_season_adjustments(up, user, club, s)
    check("the sheet imported", (res or {}).get("created", 0) + (res or {}).get("updated", 0) >= 1, f"{res}")
    c = await career(P_CSV)
    check("a sheet that gives only figures prints 3-21", c.get("best_bowling_figures") == "3-21" and c.get("best_figures_wickets") == 3,
          f"{c.get('best_bowling_figures')!r} {c.get('best_figures_wickets')!r}")

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
