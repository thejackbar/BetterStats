"""Verification: each team has its own side size, against a real Postgres.

Reported: some teams play 12 a side and some 11, but changing the size on the
Selection board changed it for EVERY team (it wrote the club default), so a
12-a-side side showed as unfinished ("short of XI") on the matchday board.

Drives the SHIPPED route bodies (`set_default_team_size`, `selection_overview`,
`assemble_selection`, the teams PATCH and the fixtures list):

  * changing one fixture's size saves on that fixture's team only
  * the other team and the club default are untouched
  * the overview carries a size per fixture and the pool carries the fixture's
    own size (the board and Draft table read it)
  * a team with no size follows the club default; clearing it (null) goes back
  * without a fixture the club default is written, as before
  * another club's fixture is refused, and its team is never written
  * the fixtures list `format_size` follows the team

CONTROL MODE: against the commit before this change the team column and the
`fixture_id` argument do not exist; new keys are read with `.get`/`getattr`
so the control reports failed checks rather than crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_team_side_size.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import importlib
import re

from _view_ddl import view_statements
from app.models.db import Base, Organisation, User, Team, Grade, Season, Fixture
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def _create_stmt(table):
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", MAIN.read_text())
    return m.group(1) if m else None


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Harness tables the confirm path reads (copied from the lifespan, as in
        # verify_selection_same_day.py).
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
            """CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, grade_label text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)""",
        ):
            await conn.execute(text(ddl))
        from app.services.competition_ddl import STATEMENTS as COMP_DDL
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        try:
            from app.services.junior_hiding_ddl import STATEMENTS as JUNIOR_DDL
            for stmt in JUNIOR_DDL:
                await conn.execute(text(stmt))
        except ImportError:
            pass
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for t in ("net_sessions", "net_attendance"):
            stmt = _create_stmt(t)
            if stmt:
                await conn.execute(text(stmt))
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))
        try:
            ddl = importlib.import_module("app.services.selection_draft_ddl")
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
        except ImportError:
            pass


async def main():
    await build_schema()
    async with engine.begin() as conn:
        try:
            from app.services.team_size_ddl import STATEMENTS
            for s in STATEMENTS:
                await conn.execute(text(s))
            from app.services.team_min_size_ddl import STATEMENTS as MIN_STATEMENTS
            for s in MIN_STATEMENTS:
                await conn.execute(text(s))
        except ImportError:
            pass

    import app.routers.selection as sel
    import app.routers.fixtures as fxr
    import app.routers.teams as teams_r
    from app.services.selection_pool import assemble_selection

    org, other, uid, season, g1, g2 = (uuid.uuid4() for _ in range(6))
    t1, t2, t_other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    f1, f2, f_nt, f_other = (uuid.uuid4() for _ in range(4))
    d = date.today() + timedelta(days=9)

    async with Session() as db:
        db.add(Organisation(id=org, name="Size CC", slug=f"size-{org.hex[:8]}"))
        db.add(Organisation(id=other, name="Other CC", slug=f"oth-{other.hex[:8]}"))
        db.add(User(id=uid, username=f"u{uid.hex[:8]}", email=f"{uid.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g1, season_id=season, name="1st Grade"))
        db.add(Grade(id=g2, season_id=season, name="2nd Grade"))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="1st XI", sequence=1, grade_id=g1))
        db.add(Team(id=t2, organisation_id=org, name="2nd XI", sequence=2, grade_id=g2))
        db.add(Team(id=t_other, organisation_id=other, name="Their XI", sequence=1))
        await db.flush()
        db.add(Fixture(id=f1, organisation_id=org, grade_id=g1, team_id=t1, source="manual", played_on=d, status="UPCOMING", label="a"))
        db.add(Fixture(id=f2, organisation_id=org, grade_id=g2, team_id=t2, source="manual", played_on=d, status="UPCOMING", label="b"))
        db.add(Fixture(id=f_nt, organisation_id=org, source="manual", played_on=d, status="UPCOMING", label="c"))
        db.add(Fixture(id=f_other, organisation_id=other, team_id=t_other, source="manual", played_on=d, status="UPCOMING", label="d"))
        await db.commit()

    async def call(fn, *args, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, uid)
            who = "_user" if "_user" in fn.__code__.co_varnames else "user"
            try:
                return await fn(*args, db=db, club=club, **{who: user}, **kw), None
            except HTTPException as e:
                return None, e.status_code
            except TypeError as e:
                return None, f"TypeError: {e}"

    async def overview():
        async with Session() as db:
            club = await db.get(Organisation, org)
            r = await sel.selection_overview(db, club)
        return r, {x["id"]: x for x in r["fixtures"]}

    async def pool_size(fid):
        async with Session() as db:
            club = await db.get(Organisation, org)
            fx = await db.get(Fixture, fid)
            return (await assemble_selection(db, club, fx)).get("default_team_size")

    async def scalar(sql, **kw):
        async with Session() as db:
            try:
                return (await db.execute(text(sql), kw)).scalar()
            except Exception as e:  # control: column absent
                return f"error:{type(e).__name__}"

    print("\n# A. Start: everyone follows the club default (11)")
    r, by = await overview()
    check("club default 11", r["default_team_size"], 11)
    check("both teams 11 on the overview", {by[str(f1)].get("team_size", by[str(f1)] and "absent"), by[str(f2)].get("team_size", "absent")}, {11})

    print("\n# B. Setting 12 on the 2nd XI board changes ONLY the 2nd XI")
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2))) if "fixture_id" in sel.TeamSizeSet.model_fields else (None, "no fixture_id")
    check("accepted", (res or {}).get("status", err), "ok")
    check("reports it saved on the team", (res or {}).get("scope"), "team")
    r, by = await overview()
    check("2nd XI is 12 on the overview", by[str(f2)].get("team_size"), 12)
    check("1st XI is still 11", by[str(f1)].get("team_size"), 11)
    check("club default untouched", r["default_team_size"], 11)
    check("the board's pool for the 2nd XI says 12", await pool_size(f2), 12)
    check("the board's pool for the 1st XI says 11", await pool_size(f1), 11)
    check("a fixture with no team follows the club", by[str(f_nt)].get("team_size"), 11)

    print("\n# C. The fixtures list judges 'completed XI' per team")
    async with Session() as db:
        club = await db.get(Organisation, org)
        try:
            rows = await fxr.list_fixtures(db=db, club=club) if "user" not in fxr.list_fixtures.__code__.co_varnames else await fxr.list_fixtures(db=db, club=club, user=await db.get(User, uid))
        except Exception as e:
            rows = []
            print("   (list_fixtures call:", type(e).__name__, e, ")")
    fs = {x["id"]: x for x in rows}
    check("format_size 12 for the 2nd XI", fs.get(str(f2), {}).get("format_size"), 12)
    check("format_size 11 for the 1st XI", fs.get(str(f1), {}).get("format_size"), 11)

    print("\n# D. Club default, set with no fixture, still works and leaves team numbers alone")
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=13))
    check("accepted", (res or {}).get("status", err), "ok")
    check("scope club", (res or {}).get("scope"), "club")
    r, by = await overview()
    check("club default 13", r["default_team_size"], 13)
    check("1st XI (no number of its own) follows to 13", by[str(f1)].get("team_size"), 13)
    check("2nd XI keeps its own 12", by[str(f2)].get("team_size"), 12)

    print("\n# E. Clearing a team's number goes back to the club")
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate(name="2nd XI"))
    check("PATCH without the field succeeds", (res or {}).get("name", err), "2nd XI")
    # exclude_unset: a body that never mentions the size is not a clear
    check("PATCH without the field leaves 12 alone", await scalar("SELECT default_team_size FROM teams WHERE id=:t", t=t2), 12)
    body = teams_r.TeamUpdate.model_validate({"default_team_size": None})
    res, err = await call(teams_r.update_team, str(t2), body)
    check("explicit null clears", await scalar("SELECT default_team_size FROM teams WHERE id=:t", t=t2), None)
    r, by = await overview()
    check("2nd XI follows the club (13) again", by[str(f2)].get("team_size"), 13)
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate.model_validate({"default_team_size": 99}))
    check("a size outside 0..30 is refused", err, 400)
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate.model_validate({"default_team_size": 7}))
    check("a custom 7 (women's / junior side) is accepted", (res or {}).get("default_team_size", err), 7)
    r, by = await overview()
    check("the overview carries the custom 7", by[str(f2)].get("team_size"), 7)
    check("the board's pool carries the custom 7", await pool_size(f2), 7)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=9, fixture_id=str(f2)))
    check("the board saves a custom 9 on the team", ((res or {}).get("scope"), await scalar("SELECT default_team_size FROM teams WHERE id=:t", t=t2)), ("team", 9))
    check("30 is the top of the range", (await call(sel.set_default_team_size, sel.TeamSizeSet(size=30, fixture_id=str(f2))))[1], None)
    check("31 is refused", (await call(sel.set_default_team_size, sel.TeamSizeSet(size=31, fixture_id=str(f2))))[1], 400)
    check("a negative size is refused", (await call(sel.set_default_team_size, sel.TeamSizeSet(size=-1)))[1], 400)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=7))
    check("a custom club default is accepted", (res or {}).get("scope"), "club")

    print("\n# F. Another club's fixture is refused and its team untouched")
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f_other)))
    check("404", err, 404)
    check("their team has no number", await scalar("SELECT default_team_size FROM teams WHERE id=:t", t=t_other), None)
    check("bad size refused", (await call(sel.set_default_team_size, sel.TeamSizeSet(size=99)))[1], 400)

    print("\n# G. A minimum: a side that needs 8 but may name 12")
    M = getattr(sel.TeamSizeSet, "model_fields", {})
    async def mins():
        r, by = await overview()
        return by[str(f2)].get("team_min", "absent"), by[str(f2)].get("team_size"), await pool_size(f2), (await assemble_for(f2)).get("team_min", "absent")
    async def assemble_for(fid):
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await assemble_selection(db, club, await db.get(Fixture, fid))
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2), min_size=8)) if "min_size" in M else (None, "no min_size")
    check("size 12 with a minimum of 8 is accepted", ((res or {}).get("status", err), (res or {}).get("min_size")), ("ok", 8))
    check("overview, pool and board agree: min 8, max 12", await mins(), (8, 12, 12, 8))
    check("the other team has no minimum", (await overview())[1][str(f1)].get("team_min", "absent"), None)
    async with Session() as db:
        rows = await fxr.list_fixtures(db=db, club=await db.get(Organisation, org))
    check("the fixtures list carries format_min 8", {x["id"]: x.get("format_min", "absent") for x in rows}.get(str(f2)), 8)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2)))
    check("a size write that does not mention the minimum leaves it alone", (await mins())[0], 8)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=7, fixture_id=str(f2)))
    check("lowering the size to 7 drops the now meaningless minimum", await mins(), (None, 7, 7, None))
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2), min_size=12))
    check("a minimum equal to the size is refused", err, 400)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2), min_size=0))
    check("a minimum of 0 is refused", err, 400)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2), min_size=31))
    check("a minimum of 31 is refused", err, 400)
    check("nothing was written by the refusals", (await mins())[0], None)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=0, fixture_id=str(f2), min_size=8))
    check("no limit with a minimum of 8 is accepted", ((res or {}).get("status", err), (await mins())[:2]), ("ok", (8, 0)))
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f2), min_size=8))
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet.model_validate({"size": 12, "fixture_id": str(f2), "min_size": None}))
    check("an explicit null clears it", (await mins())[0], None)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, min_size=8))
    check("a club default cannot carry a minimum", err, 400)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f_nt), min_size=8))
    check("nor can a fixture with no team", err, 400)
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate.model_validate({"default_team_size": 12, "min_team_size": 8}))
    check("PATCH team sets both", ((res or {}).get("default_team_size", err), (res or {}).get("min_team_size")), (12, 8))
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate(name="2nd XI"))
    check("PATCH without the field leaves the minimum", await scalar("SELECT min_team_size FROM teams WHERE id=:t", t=t2), 8)
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate.model_validate({"min_team_size": 12}))
    check("PATCH refuses a minimum that is not below the size", err, 400)
    res, err = await call(teams_r.update_team, str(t2), teams_r.TeamUpdate.model_validate({"default_team_size": 6}))
    check("PATCH lowering the size under the minimum clears it", await scalar("SELECT min_team_size FROM teams WHERE id=:t", t=t2), None)
    res, err = await call(sel.set_default_team_size, sel.TeamSizeSet(size=12, fixture_id=str(f_other), min_size=8))
    check("another club's fixture is still a 404", err, 404)
    check("their team has no minimum", await scalar("SELECT min_team_size FROM teams WHERE id=:t", t=t_other), None)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)

asyncio.run(main())
