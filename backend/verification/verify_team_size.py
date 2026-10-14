"""Verification: a team carries its own number of players, against a real Postgres.

Reported: the selection board's 11/12/13 picker saved ONE club-wide default, so
setting a side to 12 turned every grade into 12. A women's grade names ten, an
OD6s side twelve. The size now lives on the team (`teams.team_size`, NULL = follow
the club, 0 = no limit) and the board writes to the fixture's team.

Drives the SHIPPED route bodies and services (`set_fixture_team_size`,
`selection_overview`, `assemble_selection`, `list_fixtures`, `update_team`,
`create_team`), never a re-implementation:

  * the DDL is idempotent (the lifespan re-runs it every boot) and adds one
    nullable column; the downgrade drops only that column
  * a team with no size follows the club; one with a size does not, and moving
    the club default moves only the teams that have none
  * setting one team leaves every other team alone (the reported bug)
  * 0 (no limit) is a real answer, not "absent"
  * null puts a team back on the club default
  * a size nobody plays (3, 40) is refused; a fixture with no team is a 409; a
    foreign club's fixture is a 404
  * the Selection overview, the board payload (also read by BetterIQ) and the
    fixtures list all report the team's size
  * the Teams PATCH leaves a size alone when the body does not send it, and
    clears it on an explicit null

CONTROL MODE: against the commit BEFORE this change the route and column do not
exist; they are read with `getattr` so the control reports failed checks rather
than crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_team_size.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text

from _view_ddl import view_statements
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
import re
from app.models.db import Base
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS
from app.models.db import Organisation, User, Player, Team, Grade, Season, Fixture

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
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
    import app.routers.selection as sel
    import app.routers.teams as teams_router
    import app.routers.fixtures as fixtures_router
    from app.services.selection_pool import assemble_selection

    set_size = getattr(sel, "set_fixture_team_size", None)
    SizeBody = getattr(sel, "FixtureTeamSizeSet", None)
    TeamUpdate, TeamCreate = teams_router.TeamUpdate, teams_router.TeamCreate

    try:
        ddl = importlib.import_module("app.services.team_size_ddl")
    except ImportError:
        ddl = None

    org, other_org, user_id, season = (uuid.uuid4() for _ in range(4))
    g_w, g_od, g_a = (uuid.uuid4() for _ in range(3))
    t_w, t_od, t_a, t_nosize = (uuid.uuid4() for _ in range(4))
    fx_w, fx_od, fx_a, fx_none, fx_foreign = (uuid.uuid4() for _ in range(5))
    d = date.today() + timedelta(days=20)

    async with Session() as db:
        db.add(Organisation(id=org, name="Size CC", slug=f"size-{org.hex[:8]}"))
        db.add(Organisation(id=other_org, name="Other CC", slug=f"osize-{other_org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_w, season_id=season, name="Womens Div 1"))
        db.add(Grade(id=g_od, season_id=season, name="OD6"))
        db.add(Grade(id=g_a, season_id=season, name="A Grade"))
        await db.flush()
        db.add(Team(id=t_w, organisation_id=org, name="Womens Div 1", sequence=60, grade_id=g_w))
        db.add(Team(id=t_od, organisation_id=org, name="OD6s", sequence=6, grade_id=g_od))
        db.add(Team(id=t_a, organisation_id=org, name="1st XI", sequence=1, grade_id=g_a))
        await db.flush()
        for fid, tid, gid in ((fx_w, t_w, g_w), (fx_od, t_od, g_od), (fx_a, t_a, g_a)):
            db.add(Fixture(id=fid, organisation_id=org, grade_id=gid, team_id=tid, source="manual",
                           played_on=d, status="UPCOMING", label="x"))
        db.add(Fixture(id=fx_none, organisation_id=org, grade_id=g_a, source="manual",
                       played_on=d, status="UPCOMING", label="no team"))
        db.add(Fixture(id=fx_foreign, organisation_id=other_org, source="manual",
                       played_on=d, status="UPCOMING", label="theirs"))
        await db.commit()

    async def call(fn, *args, **kw):
        if fn is None:
            return None, "absent"
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                if fn in (set_size, teams_router.update_team, teams_router.create_team):
                    extra = {"user": user} if fn is set_size else {"_user": user}
                    return await fn(*args, db=db, club=club, **extra, **kw), None
                return await fn(*args, db=db, club=club, **kw), None
            except HTTPException as e:
                return None, e.status_code
            except Exception as e:     # a control build without the new argument or column
                return None, f"{type(e).__name__}: {str(e)[:80]}"

    async def scalar(sql, **kw):
        # Read presence-safely: a control build has no teams.team_size column.
        try:
            async with Session() as db:
                return (await db.execute(text(sql), kw)).scalar()
        except Exception as e:
            return f"<{type(e).__name__}>"

    async def board_size(fid):
        async with Session() as db:
            club = await db.get(Organisation, org)
            fx = await db.get(Fixture, fid)
            sel_ = await assemble_selection(db, club, fx)
        return sel_.get("default_team_size"), sel_.get("team_size_info", {})

    async def overview_sizes():
        r, _ = await call(sel.selection_overview)
        return {f["id"]: f.get("team_size", "absent") for f in (r or {}).get("fixtures", [])}

    async def set_club(n):
        async with Session() as db:
            await db.execute(text("UPDATE organisations SET default_team_size=:n WHERE id=:o"), {"n": n, "o": org})
            await db.commit()

    def body(**kw):
        return SizeBody(**kw) if SizeBody else None

    print("\n# A. The DDL")
    if ddl:
        async with engine.begin() as conn:
            for _ in range(2):
                for stmt in ddl.STATEMENTS:
                    await conn.execute(text(stmt))
        check("re-running the DDL is harmless", True)
        col = await scalar("SELECT is_nullable FROM information_schema.columns WHERE table_name='teams' AND column_name='team_size'")
        check("teams.team_size exists and is nullable", col, "YES")
        check("nothing was backfilled: no team has a size", await scalar("SELECT COUNT(*) FROM teams WHERE team_size IS NOT NULL"), 0)
        check("the downgrade drops only that column", [s for s in ddl.DOWNGRADE], ["ALTER TABLE teams DROP COLUMN IF EXISTS team_size"])
    else:
        check("team_size_ddl exists", False)

    print("\n# B. Nothing changes until a size is set")
    await set_club(11)
    for name, fid in (("women's", fx_w), ("OD6s", fx_od), ("1st XI", fx_a)):
        size, info = await board_size(fid)
        check(f"{name} follows the club default (11)", size, 11)
    check("the board says the team has no size of its own", (await board_size(fx_w))[1].get("own", "absent"), None)

    print("\n# C. Setting one team leaves the others alone (the reported bug)")
    r, err = await call(set_size, str(fx_od), body(size=12))
    check("OD6s set to 12", (r or {}).get("team_size", err), 12)
    r, err = await call(set_size, str(fx_w), body(size=10))
    check("women's set to 10", (r or {}).get("team_size", err), 10)
    check("OD6s board reads 12", (await board_size(fx_od))[0], 12)
    check("women's board reads 10", (await board_size(fx_w))[0], 10)
    check("the 1st XI is still the club's 11", (await board_size(fx_a))[0], 11)
    check("the club default itself was not touched", await scalar("SELECT default_team_size FROM organisations WHERE id=:o", o=org), 11)
    info = (await board_size(fx_w))[1]
    check("the board names the team and its own size", (info.get("team_name"), info.get("own"), info.get("club")), ("Womens Div 1", 10, 11))

    print("\n# D. Moving the club default moves only teams without a size")
    await set_club(13)
    check("1st XI follows the club to 13", (await board_size(fx_a))[0], 13)
    check("OD6s keeps 12", (await board_size(fx_od))[0], 12)
    check("women's keeps 10", (await board_size(fx_w))[0], 10)
    await set_club(11)

    print("\n# E. Zero is an answer; null clears")
    r, err = await call(set_size, str(fx_a), body(size=0))
    check("1st XI set to no limit", (r or {}).get("team_size", err), 0)
    check("no limit reads 0, not the club's 11", (await board_size(fx_a))[0], 0)
    check("and it is stored as 0, not NULL", await scalar("SELECT team_size FROM teams WHERE id=:t", t=t_a), 0)
    r, err = await call(set_size, str(fx_a), body(size=None))
    check("null puts it back on the club default", (r or {}).get("team_size", err), 11)
    check("stored as NULL again", await scalar("SELECT (team_size IS NULL) FROM teams WHERE id=:t", t=t_a), True)

    print("\n# F. What is refused")
    for bad in (3, 40, -1):
        r, err = await call(set_size, str(fx_od), body(size=bad))
        check(f"a side of {bad} is refused (400)", err, 400)
    check("a refused size changed nothing", (await board_size(fx_od))[0], 12)
    r, err = await call(set_size, str(fx_none), body(size=12))
    check("a fixture with no team is a 409", err, 409)
    r, err = await call(set_size, str(fx_foreign), body(size=12))
    check("another club's fixture is a 404", err, 404)

    print("\n# G. The screens that read it")
    ov = await overview_sizes()
    check("overview: women's 10", ov.get(str(fx_w)), 10)
    check("overview: OD6s 12", ov.get(str(fx_od)), 12)
    check("overview: 1st XI follows the club (11)", ov.get(str(fx_a)), 11)
    check("overview: a fixture with no team follows the club (11)", ov.get(str(fx_none)), 11)
    r, err = await call(fixtures_router.list_fixtures, upcoming_only=False)
    fs = {f["id"]: f.get("format_size") for f in (r or [])}
    check("fixtures list: women's format_size 10", fs.get(str(fx_w)), 10)
    check("fixtures list: OD6s format_size 12", fs.get(str(fx_od)), 12)
    check("fixtures list: 1st XI format_size 11", fs.get(str(fx_a)), 11)

    print("\n# H. The Teams screen")
    r, err = await call(teams_router.update_team, str(t_a), TeamUpdate(team_size=9))
    check("PATCH sets a size", (r or {}).get("team_size", err), 9)
    r, err = await call(teams_router.update_team, str(t_a), TeamUpdate(short_name="Firsts"))
    check("PATCH without team_size leaves it alone", (r or {}).get("team_size", err), 9)
    r, err = await call(teams_router.update_team, str(t_a), TeamUpdate(team_size=None))
    check("PATCH with an explicit null clears it", (r or {}).get("team_size", err), None)
    r, err = await call(teams_router.update_team, str(t_a), TeamUpdate(team_size=2))
    check("PATCH refuses a size of 2", err, 400)
    r, err = await call(teams_router.create_team, TeamCreate(name="New side", team_size=10))
    check("a new team can start with a size", (r or {}).get("team_size", err), 10)
    r, err = await call(teams_router.list_teams)
    check("the team list carries the size", {t["name"]: t.get("team_size", "absent") for t in (r or [])}.get("OD6s"), 12)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:\n - " + "\n - ".join(FAILURES))
        sys.exit(1)


asyncio.run(main())
