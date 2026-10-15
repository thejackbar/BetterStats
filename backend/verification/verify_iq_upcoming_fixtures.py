"""Verification: Ask BetterIQ can find an upcoming fixture beyond the first ten,
against a real Postgres.

Reported: asked to check the PSWL A game against Cockburn Blue, BetterIQ said it
could not see the game and "Here are all 10 upcoming fixtures", though the club
holds about 160. `upcoming_fixtures` returned the first ten by date and called
them all. Anything past that was invisible, and a game the sync had marked
CANCELLED was indistinguishable from one that never existed.

This drives the SHIPPED `iq_ask._tool_upcoming_fixtures` (and through it
`iq.list_opponents`). Checks:

  * unfiltered: a page, the true total, and a note that it is NOT the whole draw
  * opponent filter finds a game weeks past the first page
  * grade/team filter and a date window narrow the list
  * a CANCELLED game stays out of the list but is reported when asked about
  * a small draw carries no "partial" note
  * `limit` is clamped, a bad date is ignored rather than crashing

CONTROL MODE: run against the commit BEFORE this change. The old tool takes no
arguments, so each call is made through `call()`, which turns a TypeError into
an empty result and lets the control report the old behaviour as failed checks
instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_iq_upcoming_fixtures.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("ANTHROPIC_API_KEY", "")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, Team, Grade, Season, Fixture
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

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
    src = MAIN.read_text()
    m = re.search(r"(CREATE TABLE IF NOT EXISTS " + table + r" \([\s\S]*?\n\s*\))", src)
    return m.group(1) if m else None


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
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


async def main():
    await build_schema()
    from app.services import iq_ask

    org_id, season_id = uuid.uuid4(), uuid.uuid4()
    grade_id, w_grade_id = uuid.uuid4(), uuid.uuid4()
    team_1, team_w = uuid.uuid4(), uuid.uuid4()
    today = date.today()
    sat = today + timedelta(days=(5 - today.weekday()) % 7 or 7)

    async def club(name, n_filler):
        oid = uuid.uuid4()
        async with Session() as db:
            sid = uuid.uuid4()
            db.add(Organisation(id=oid, name=name, slug=f"{name.lower()[:6]}-{oid.hex[:8]}"))
            db.add(Season(id=sid, organisation_id=oid, name="Summer 2026/27", year=2026))
            await db.flush()
            gid, wid = uuid.uuid4(), uuid.uuid4()
            db.add(Grade(id=gid, season_id=sid, name="1st Grade"))
            db.add(Grade(id=wid, season_id=sid, name="PSWL A"))
            await db.flush()
            t1, tw = uuid.uuid4(), uuid.uuid4()
            db.add(Team(id=t1, organisation_id=oid, name="1st XI", sequence=1, grade_id=gid))
            db.add(Team(id=tw, organisation_id=oid, name="Applecross A", sequence=2, grade_id=wid))
            await db.flush()
            for i in range(n_filler):
                db.add(Fixture(id=uuid.uuid4(), organisation_id=oid, source="grassroots", grade_id=gid,
                               team_id=t1, played_on=sat + timedelta(days=i // 12 * 7), start_time="12:00",
                               status="UPCOMING", opponent_name=f"Filler {i:02d}", home_away="HOME",
                               round=str(1 + i // 12)))
            await db.commit()
        return oid, wid, tw

    async def call(oid, **kw):
        async with Session() as db:
            try:
                return await iq_ask._tool_upcoming_fixtures(db, str(oid), **kw)
            except TypeError as e:           # control: the old tool takes no arguments
                return {"error": str(e)}

    # A big club: 40 filler games over 4 weekends, then the game the user asked about.
    big, wid, tw = await club("Bigclub", 40)
    async with Session() as db:
        db.add(Fixture(id=uuid.uuid4(), organisation_id=big, source="grassroots", grade_id=wid, team_id=tw,
                       played_on=sat + timedelta(days=28), start_time="14:00", status="UPCOMING",
                       opponent_name="Cockburn Blue", home_away="HOME", round="5", venue="Shirley Strickland"))
        db.add(Fixture(id=uuid.uuid4(), organisation_id=big, source="grassroots", grade_id=wid, team_id=tw,
                       played_on=sat, start_time="14:00", status="CANCELLED",
                       opponent_name="Wanderers Blue", home_away="HOME", round="2"))
        await db.commit()

    r = await call(big)
    check("unfiltered: returns a page, not the whole list", 0 < r.get("count", 0) < 41)
    check("unfiltered: reports the true total", r.get("total_matching"), 41)
    check("unfiltered: says it is not the whole draw", "NOT the whole" in (r.get("note") or ""))
    check("unfiltered: a cancelled game is not in the list",
          not any(f["opponent"] == "Wanderers Blue" for f in r.get("fixtures", [])))
    check("unfiltered: soonest first", [f["date"] for f in r.get("fixtures", [])] == sorted(f["date"] for f in r.get("fixtures", [])))

    r = await call(big, opponent="cockburn")
    check("opponent filter finds a game past the first page",
          [f["opponent"] for f in r.get("fixtures", [])], ["Cockburn Blue"])
    check("opponent filter: no partial-list note when everything is shown", not r.get("note"))
    check("opponent filter carries the venue", (r.get("fixtures") or [{}])[0].get("venue"), "Shirley Strickland")

    r = await call(big, grade="PSWL A")
    check("grade filter matches the grade name", [f["opponent"] for f in r.get("fixtures", [])], ["Cockburn Blue"])
    r = await call(big, grade="applecross a")
    check("grade filter matches the team name, any case", [f["opponent"] for f in r.get("fixtures", [])], ["Cockburn Blue"])

    window = (sat + timedelta(days=27)).isoformat(), (sat + timedelta(days=29)).isoformat()
    r = await call(big, from_date=window[0], to_date=window[1])
    check("date window returns only that window", [f["opponent"] for f in r.get("fixtures", [])], ["Cockburn Blue"])
    r = await call(big, from_date="not-a-date")
    check("an unreadable date is ignored, not a crash", r.get("count", 0) > 0 and "error" not in r)

    r = await call(big, opponent="wanderers")
    check("cancelled game: not listed as upcoming", r.get("count"), 0)
    check("cancelled game: reported when asked about",
          [c["opponent_name"] for c in r.get("cancelled", [])], ["Wanderers Blue"])
    check("cancelled game: says Cricket Australia no longer lists it", "no longer lists" in (r.get("cancelled_note") or ""))

    r = await call(big, opponent="zzz-nobody")
    check("no match: says so and offers no cancelled game", (r.get("count"), bool(r.get("cancelled")), bool(r.get("note"))), (0, False, True))

    r = await call(big, limit=500)
    check("limit is clamped to 40", r.get("count"), 40)
    r = await call(big, limit=3)
    check("limit is honoured", (r.get("count"), r.get("total_matching")), (3, 41))

    # A small club: the whole draw fits, so nothing is called partial.
    small, _, _ = await club("Smallclub", 6)
    r = await call(small)
    check("small draw: everything returned", (r.get("count"), r.get("total_matching")), (6, 6))
    check("small draw: no partial note", not r.get("note"))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("\n".join(" - " + f for f in FAILURES))
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
