"""Verification: a player can be picked for two games on the same date when the
games do not clash, against a real Postgres.

Reported: an Applecross player in both Colts and T20 Div 1 could not be picked
for both when the games fall on the same day and are played back to back. A
junior game and a senior game on the same day were refused the same way.

This drives the SHIPPED `assemble_selection` (the board's pool) and the SHIPPED
`set_selection` route body (the save), never a re-implementation:

  * back to back, no overlap          -> pickable, flagged `also_in`, saved in BOTH XIs
  * tight turnaround (< 60 minutes)   -> pickable, flagged tight
  * overlapping times                 -> still a clash: refused, or a call-up
  * junior vs senior                  -> pickable whatever the clock says
  * two seniors with no start time    -> still a clash (fail closed, old behaviour)
  * a two-day game                    -> still a clash
  * the old call-up (higher grade takes the player from a lower XI) is unchanged

CONTROL MODE: the same suite runs against the commit BEFORE this change. New
keys are read through `.get` so the control reports the reported behaviour as
failed checks instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_same_day.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, User, Player, Team, Grade, Season, Fixture, FixtureLineup,
)
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
HAS_CLASH_MODULE = importlib.util.find_spec("app.services.selection_clash") is not None

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

    from app.routers.selection import set_selection, LineupSet, LineupSlot
    from app.services.selection_pool import assemble_selection

    org_id, user_id, season_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # Grades: name -> (id, match_formats, categories)
    grade_spec = {
        "T20 Div 1": (["t20"], ["senior"]),
        "Colts": (["one_day"], ["senior"]),
        "Colts T20": (["t20"], ["senior"]),
        "1st Grade": (["one_day"], ["senior"]),
        "2nd Grade": (["one_day"], ["senior"]),
        "Two Day": (["two_day"], ["senior"]),
        "Under 14 Boys": (["one_day"], ["junior"]),
        "Plain A": (None, ["senior"]),
        "Plain B": (None, ["senior"]),
    }
    G = {n: uuid.uuid4() for n in grade_spec}
    # Team sequence: lower number = higher grade. Colts and Colts T20 rank BELOW T20 Div 1.
    team_spec = {
        "1st Grade": 1, "2nd Grade": 2, "T20 Div 1": 3, "Colts": 4, "Colts T20": 5,
        "Two Day": 6, "Under 14 Boys": 7, "Plain A": 8, "Plain B": 9,
    }
    T = {n: uuid.uuid4() for n in team_spec}

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Verify CC", slug=f"verify-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        for n, (formats, cats) in grade_spec.items():
            db.add(Grade(id=G[n], season_id=season_id, name=n, match_formats=formats, categories=cats))
        await db.flush()
        for n, seq in team_spec.items():
            db.add(Team(id=T[n], organisation_id=org_id, name=n, sequence=seq, grade_id=G[n]))
        await db.commit()

    day0 = date.today() + timedelta(days=30)
    counter = {"n": 0}

    async def scenario(this_name, other_name, this_time, other_time, *, this_end=None, other_end=None):
        """One date, one player already named in the OTHER game. Returns
        (club, this fixture, other fixture, player id)."""
        counter["n"] += 1
        d = day0 + timedelta(days=counter["n"])
        pid = uuid.uuid4()
        fx_this, fx_other = uuid.uuid4(), uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=org_id, name=f"Dual {counter['n']}",
                          gender="male", is_player=True, status="active"))
            for fid, nm, st, en in ((fx_this, this_name, this_time, this_end),
                                    (fx_other, other_name, other_time, other_end)):
                db.add(Fixture(id=fid, organisation_id=org_id, grade_id=G[nm], team_id=T[nm],
                               source="manual", played_on=d, end_on=en, start_time=st,
                               status="UPCOMING", label=nm))
            await db.flush()
            db.add(FixtureLineup(fixture_id=fx_other, player_id=pid, organisation_id=org_id,
                                 batting_order=1, selected_by=user_id))
            await db.commit()
        return fx_this, fx_other, pid

    async def pool_row(fx_id, pid):
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            fx = await db.get(Fixture, fx_id)
            sel = await assemble_selection(db, club, fx)
        return next(p for p in sel["pool"] if p["id"] == str(pid))

    async def save(fx_id, pid):
        """The shipped save body. Returns 'ok' or the HTTP status it refused with."""
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            user = await db.get(User, user_id)
            try:
                await set_selection(
                    str(fx_id),
                    LineupSet(players=[LineupSlot(player_id=str(pid), batting_order=1)]),
                    db, club, user,
                )
                return "ok"
            except HTTPException as e:
                return e.status_code

    async def in_lineup(fx_id, pid):
        async with Session() as db:
            n = (await db.execute(
                text("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id=:f AND player_id=:p"),
                {"f": fx_id, "p": pid})).scalar()
        return n == 1

    # ── A. Colts one-day in the morning, T20 Div 1 in the evening ────────────
    print("\n# A. Colts 9:00am + T20 Div 1 6:00pm (back to back, no overlap)")
    fx_t20, fx_colts, p = await scenario("T20 Div 1", "Colts", "18:00", "09:00")
    row = await pool_row(fx_t20, p)
    also = row.get("also_in") or []
    check("pool: not a clash", row.get("clash"), [])
    check("pool: flagged as also in Colts", [a.get("team_name") for a in also], ["Colts"])
    check("pool: carries the other game's start", [a.get("start_time") for a in also], ["9:00am"])
    check("pool: 9h gap is not tight", [a.get("tight") for a in also], [False])
    check("pool: not blocked", bool(row.get("clash_blocks")), False)
    check("save into T20 Div 1 is accepted", await save(fx_t20, p), "ok")
    check("player is in T20 Div 1", await in_lineup(fx_t20, p), True)
    check("player is STILL in Colts (no call-up)", await in_lineup(fx_colts, p), True)

    # Same pair from the lower grade's side (Colts picks a T20 player).
    fx_colts2, fx_t202, p = await scenario("Colts", "T20 Div 1", "09:00", "18:00")
    row = await pool_row(fx_colts2, p)
    check("reverse: pickable, flagged", [a.get("team_name") for a in row.get("also_in") or []], ["T20 Div 1"])
    check("reverse: save accepted", await save(fx_colts2, p), "ok")
    check("reverse: still in T20 Div 1", await in_lineup(fx_t202, p), True)

    # ── B. Overlap stays a clash ─────────────────────────────────────────────
    print("\n# B. Colts 9:00am + T20 Div 1 1:00pm (one-day Colts runs past 1pm)")
    fx_colts3, fx_t203, p = await scenario("Colts", "T20 Div 1", "09:00", "13:00")
    row = await pool_row(fx_colts3, p)
    check("overlap: still a clash", row.get("clash"), ["T20 Div 1"])
    check("overlap: blocked (T20 Div 1 is the higher grade)", row.get("clash_blocks"), True)
    check("overlap: no also_in flag", row.get("also_in") or [], [])
    check("overlap: save refused 409", await save(fx_colts3, p), 409)
    check("overlap: still only in T20 Div 1", await in_lineup(fx_t203, p), True)

    # ── C. Both T20: the case that is usually the problem ────────────────────
    print("\n# C. Colts T20 + T20 Div 1")
    fx_a, fx_b, p = await scenario("T20 Div 1", "Colts T20", "18:00", "13:00")
    row = await pool_row(fx_a, p)
    gap = [a.get("gap_minutes") for a in row.get("also_in") or []]
    check("T20 1pm then 6pm: pickable", [a.get("team_name") for a in row.get("also_in") or []], ["Colts T20"])
    check("T20 1pm then 6pm: 90 minutes between games", gap, [90])
    check("T20 1pm then 6pm: not tight", [a.get("tight") for a in row.get("also_in") or []], [False])
    check("T20 1pm then 6pm: save accepted", await save(fx_a, p), "ok")

    fx_a, fx_b, p = await scenario("T20 Div 1", "Colts T20", "16:00", "12:00")
    row = await pool_row(fx_a, p)
    check("T20 12pm then 4pm: pickable", [a.get("team_name") for a in row.get("also_in") or []], ["Colts T20"])
    check("T20 12pm then 4pm: 30 minutes between, tight",
          [(a.get("gap_minutes"), a.get("tight")) for a in row.get("also_in") or []], [(30, True)])
    check("T20 12pm then 4pm: save accepted", await save(fx_a, p), "ok")

    fx_a, fx_b, p = await scenario("T20 Div 1", "Colts T20", "14:00", "12:00")
    row = await pool_row(fx_a, p)
    check("T20 12pm then 2pm: overlap is a clash", row.get("clash"), ["Colts T20"])
    # T20 Div 1 outranks Colts T20, so an overlap is the ORIGINAL call-up, unchanged.
    check("T20 12pm then 2pm: call-up, not blocked", row.get("clash_blocks"), False)
    check("T20 12pm then 2pm: save accepted as a call-up", await save(fx_a, p), "ok")
    check("T20 12pm then 2pm: dropped from Colts T20", await in_lineup(fx_b, p), False)

    # ── D. Junior and senior ─────────────────────────────────────────────────
    print("\n# D. Junior and senior on the same day")
    fx_s, fx_j, p = await scenario("1st Grade", "Under 14 Boys", "13:00", "09:00")
    row = await pool_row(fx_s, p)
    check("junior + senior, times set: pickable",
          [a.get("team_name") for a in row.get("also_in") or []], ["Under 14 Boys"])
    check("junior + senior: reason", [a.get("reason") for a in row.get("also_in") or []], ["junior_senior"])
    check("junior + senior: save accepted", await save(fx_s, p), "ok")
    check("junior + senior: still in the junior XI", await in_lineup(fx_j, p), True)

    fx_s, fx_j, p = await scenario("1st Grade", "Under 14 Boys", None, None)
    row = await pool_row(fx_s, p)
    check("junior + senior, NO times: pickable",
          [a.get("team_name") for a in row.get("also_in") or []], ["Under 14 Boys"])
    check("junior + senior, NO times: save accepted", await save(fx_s, p), "ok")

    fx_s, fx_j, p = await scenario("Under 14 Boys", "1st Grade", "09:00", "10:00")
    row = await pool_row(fx_s, p)
    flagged = row.get("also_in") or []
    check("senior game running into a junior one: still pickable", len(flagged), 1)
    check("senior game running into a junior one: flag says so",
          "may run into" in ((flagged[0].get("text") if flagged else "") or ""), True)

    # ── E. Fail closed where nothing says they can both be played ────────────
    print("\n# E. Cannot tell: stays a clash")
    fx_a, fx_b, p = await scenario("Plain B", "Plain A", None, None)
    row = await pool_row(fx_a, p)
    check("two seniors, no times: still a clash", row.get("clash"), ["Plain A"])
    check("two seniors, no times: blocked", row.get("clash_blocks"), True)
    check("two seniors, no times: save refused 409", await save(fx_a, p), 409)

    fx_a, fx_b, p = await scenario("Plain B", "Plain A", "09:00", None)
    row = await pool_row(fx_a, p)
    check("one start time missing: still a clash", row.get("clash"), ["Plain A"])

    fx_a, fx_b, p = await scenario("T20 Div 1", "Two Day", "18:00", "09:00")
    row = await pool_row(fx_a, p)
    check("two-day game takes the whole date: clash", row.get("clash"), ["Two Day"])
    check("two-day game: save refused or a call-up, never both XIs",
          (await save(fx_a, p)) in ("ok", 409) and not (await in_lineup(fx_a, p) and await in_lineup(fx_b, p)), True)

    fx_a, fx_b, p = await scenario("T20 Div 1", "Colts T20", "18:00", "09:00", other_end=date.today() + timedelta(days=400))
    row = await pool_row(fx_a, p)
    check("multi-day end date: clash", row.get("clash"), ["Colts T20"])

    # ── F. The original call-up and block are unchanged ──────────────────────
    print("\n# F. Original behaviour kept")
    fx_1, fx_2, p = await scenario("1st Grade", "2nd Grade", None, None)
    row = await pool_row(fx_1, p)
    check("1st takes from 2nd (no times): call-up, not blocked",
          (row.get("clash"), row.get("clash_blocks")), (["2nd Grade"], False))
    check("1st takes from 2nd: save accepted", await save(fx_1, p), "ok")
    check("1st takes from 2nd: dropped from 2nd", await in_lineup(fx_2, p), False)
    fx_1, fx_2, p = await scenario("2nd Grade", "1st Grade", None, None)
    check("2nd picking a 1st XI player: refused 409", await save(fx_1, p), 409)

    # ── G. The pure classifier (new code only) ───────────────────────────────
    if HAS_CLASH_MODULE:
        print("\n# G. classifier")
        from app.services.selection_clash import classify_pair, parse_minutes, fmt_12h
        check("parse 09:30", parse_minutes("09:30"), 570)
        check("parse junk", parse_minutes("soon"), None)
        check("parse 25:00", parse_minutes("25:00"), None)
        check("12h noon", fmt_12h(720), "12:00pm")
        check("12h midnight", fmt_12h(0), "12:00am")
        t20 = frozenset({"t20"})
        sen = frozenset({"senior"})
        v = classify_pair({"start_time": "12:00", "formats": t20, "categories": sen},
                          {"start_time": "15:30", "formats": t20, "categories": sen})
        check("T20 12:00 ends 15:30, next at 15:30: back to back, gap 0", (v["compatible"], v["gap_minutes"]), (True, 0))
        v = classify_pair({"start_time": "12:00", "formats": t20, "categories": sen},
                          {"start_time": "15:29", "formats": t20, "categories": sen})
        check("one minute early: overlap", v["compatible"], False)
    else:
        print("\n# G. classifier: module absent (control run)")
        check("selection_clash module exists", HAS_CLASH_MODULE, True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
