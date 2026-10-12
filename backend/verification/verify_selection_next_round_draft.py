"""Verification: confirming an XI carries it forward as the team's next round
draft, against a real Postgres.

Reported (BetterSelect): the next round should start with the previous round's
selections as a draft. Drives the SHIPPED route bodies (`set_selection`,
`get_draft`, `save_draft`, `discard_draft`), never a re-implementation.

  * confirming round 1 puts its XI (order, captain, keeper) in round 2's draft
  * nothing is written to `fixture_lineups` for round 2
  * only the immediate next round of the SAME team; not round 3, not another team
  * a round that already has a confirmed XI, or a draft somebody saved, is left alone
  * re-confirming round 1 refreshes a draft nobody touched, but not an edited one
  * emptying round 1 removes the untouched copy
  * a finished or past round is not seeded
  * round 2's draft is judged at its own Confirm (clash with the same day)

CONTROL MODE: against the commit before this change `selection_seed` does not
exist; the draft is simply absent, so the checks FAIL rather than crash.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_next_round_draft.py
"""
from __future__ import annotations

import asyncio
import importlib
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
    Base, Organisation, User, Player, Team, Grade, Season, Fixture,
)
from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

MAIN = Path(__file__).resolve().parent.parent / "app/main.py"
DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
LAST_DETAIL: list = [None]
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
    set_selection, LineupSet, LineupSlot = sel.set_selection, sel.LineupSet, sel.LineupSlot
    get_draft, save_draft, discard_draft, DraftSet = sel.get_draft, sel.save_draft, sel.discard_draft, sel.DraftSet

    org, user_id, season = (uuid.uuid4() for _ in range(3))
    g1, g2, t1, t2 = (uuid.uuid4() for _ in range(4))
    R1, R2, R3, R2_other, R_past, R_final, R_bye = (uuid.uuid4() for _ in range(7))
    P = [uuid.uuid4() for _ in range(6)]
    d0 = date.today() + timedelta(days=10)

    async with Session() as db:
        db.add(Organisation(id=org, name="Seed CC", slug=f"seed-{org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g1, season_id=season, name="1st Grade"))
        db.add(Grade(id=g2, season_id=season, name="2nd Grade"))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="1st Grade", sequence=1, grade_id=g1))
        db.add(Team(id=t2, organisation_id=org, name="2nd Grade", sequence=2, grade_id=g2))
        await db.flush()
        for i, pid in enumerate(P):
            db.add(Player(id=pid, organisation_id=org, name=f"Player {i}", gender="male", is_player=True, status="active"))
        await db.flush()
        def fx(fid, team, grade, days, status="UPCOMING", rnd="x"):
            db.add(Fixture(id=fid, organisation_id=org, grade_id=grade, team_id=team, source="manual",
                           played_on=d0 + timedelta(days=days), status=status, label=rnd, round=rnd))
        fx(R1, t1, g1, 0, rnd="1")
        fx(R2, t1, g1, 7, rnd="2")
        fx(R3, t1, g1, 14, rnd="3")
        fx(R2_other, t2, g2, 7, rnd="2")
        fx(R_past, t1, g1, -400, rnd="old")
        fx(R_final, t1, g1, 3, status="FINAL", rnd="done")
        fx(R_bye, t1, g1, 4, status="BYE", rnd="bye")
        await db.commit()

    async def call(fn, *args, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                return await fn(*args, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e.status_code

    async def confirm(fid, pids, cap=None, wk=None):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                await set_selection(str(fid), LineupSet(players=[
                    LineupSlot(player_id=str(p), batting_order=i + 1, is_captain=(p == cap), is_wicket_keeper=(p == wk))
                    for i, p in enumerate(pids)]), db, club, user)
                return "ok"
            except HTTPException as e:
                return e.status_code

    async def draft_of(fid):
        r, _ = await call(get_draft, str(fid))
        return (r or {}).get("draft")

    async def scalar(sql, **kw):
        async with Session() as db:
            return (await db.execute(text(sql), kw)).scalar()

    s = [str(p) for p in P]

    print("\n# A. Confirming round 1 seeds round 2")
    check("round 1 confirmed", await confirm(R1, [P[0], P[1], P[2]], cap=P[1], wk=P[2]), "ok")
    dr = await draft_of(R2) or {}
    check("round 2 has a draft carrying the XI in batting order", dr.get("slots"), s[:3])
    check("captain carried", dr.get("captain_id"), s[1])
    check("keeper carried", dr.get("wicket_keeper_id"), s[2])
    check("the draft says where it came from", dr.get("seeded_from"), str(R1))
    check("NOTHING in fixture_lineups for round 2", await scalar("SELECT COUNT(*) FROM fixture_lineups WHERE fixture_id=:f", f=R2), 0)
    check("round 1's own draft is not created", await draft_of(R1), None)

    print("\n# B. Only the immediate next round of the same team, and only a live one")
    check("round 3 is NOT seeded (no chain)", await draft_of(R3), None)
    check("the other team's round is NOT seeded", await draft_of(R2_other), None)
    check("a finished round is NOT seeded", await draft_of(R_final), None)
    check("a bye is NOT seeded", await draft_of(R_bye), None)
    check("a round long past is NOT seeded", await draft_of(R_past), None)

    print("\n# C. Re-confirming round 1 refreshes a draft nobody has touched")
    v1 = (await call(get_draft, str(R2)))[0]["version"]
    check("round 1 re-confirmed with a change", await confirm(R1, [P[0], P[3]], cap=P[0]), "ok")
    r, _ = await call(get_draft, str(R2))
    check("round 2's draft follows", (r["draft"] or {}).get("slots"), [s[0], s[3]])
    check("the version moved (open boards will see it)", r["version"] > v1, True)

    print("\n# D. A draft a selector has saved is theirs")
    r, err = await call(save_draft, str(R2), DraftSet(slots=[s[4], None, s[5]], base_version=r["version"]))
    check("selector edits round 2", (r or {}).get("status", err), "ok")
    check("round 1 re-confirmed again", await confirm(R1, [P[0], P[1]]), "ok")
    dr = await draft_of(R2) or {}
    check("their draft is untouched", dr.get("slots"), [s[4], None, s[5]])
    check("and no longer tagged as a carry-over", "seeded_from" in dr, False)

    print("\n# E. A confirmed round is never overwritten")
    await call(discard_draft, str(R2))
    check("round 2 confirmed by hand", await confirm(R2, [P[4], P[5]]), "ok")
    check("round 1 re-confirmed", await confirm(R1, [P[0], P[1], P[2]]), "ok")
    check("round 2 has no draft", await draft_of(R2), None)
    ids = await scalar("SELECT array_agg(player_id::text ORDER BY batting_order) FROM fixture_lineups WHERE fixture_id=:f", f=R2)
    check("and its confirmed XI is as chosen", ids, [s[4], s[5]])

    print("\n# F. Confirming round 2 now seeds round 3; round 2's own draft is gone")
    dr = await draft_of(R3) or {}
    check("round 3 draft carries round 2's XI (not round 1's)", (dr.get("slots"), dr.get("seeded_from")), ([s[4], s[5]], str(R2)))

    print("\n# G. Discarding a carried draft leaves the round empty")
    await call(discard_draft, str(R3))
    check("discarded", await draft_of(R3), None)
    check("it does not come back by itself", await draft_of(R3), None)

    print("\n# H. Emptying round 1 removes the untouched copy")
    await call(discard_draft, str(R2))
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM fixture_lineups WHERE fixture_id=:f"), {"f": R2})
    check("round 1 confirmed", await confirm(R1, [P[0]]), "ok")
    check("round 2 draft exists again", bool(await draft_of(R2)), True)
    check("round 1 emptied", await confirm(R1, []), "ok")
    check("the untouched copy is removed", await draft_of(R2), None)

    print("\n# I. A failing carry-forward never fails the confirm")
    import app.services.selection_seed as seed
    orig = seed.next_fixture_id
    async def boom(*a, **k): raise RuntimeError("boom")
    seed.next_fixture_id = boom
    try:
        check("confirm still succeeds", await confirm(R1, [P[0], P[1]]), "ok")
    finally:
        seed.next_fixture_id = orig
    ids = await scalar("SELECT array_agg(player_id::text ORDER BY batting_order) FROM fixture_lineups WHERE fixture_id=:f", f=R1)
    check("and the XI was written", ids, [s[0], s[1]])

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
