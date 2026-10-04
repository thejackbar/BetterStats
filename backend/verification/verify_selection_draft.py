"""Verification: the selection board autosaves a draft and only Confirm writes
the real XI, against a real Postgres.

Reported: leaving the Selection screen after moving players in and out lost all
progress, because the only write was the Save button's full replace of
`fixture_lineups`. Progress now saves as it goes into `selection_drafts`, apart
from the confirmed XI, and the old Save button is a Confirm.

Drives the SHIPPED route bodies (`get_draft`, `save_draft`, `discard_draft`,
`set_selection`), never a re-implementation:

  * a draft round-trips (slot gaps, captain, keeper, call-up cascade)
  * saving a draft writes NO `fixture_lineups` row (the rest of the app reads it)
  * a second autosave replaces the first (one row per fixture)
  * ids that are not this club's players are dropped; a captain who is not in
    the slots is cleared
  * another club's fixture is a 404
  * Confirm writes the lineup AND removes the draft, in one transaction
  * a refused Confirm (same-date clash) leaves the draft alone
  * Discard removes the draft and leaves the confirmed XI alone
  * two selectors: a save against a stale version is refused (409) with the
    current draft and who saved it, nothing is overwritten, two simultaneous
    saves cannot both win, a stale discard is refused, a draft confirmed away
    is reported as gone rather than resurrected
  * the matchday overview flags exactly the fixtures that have a draft

CONTROL MODE: against the commit BEFORE this change the draft routes do not
exist; they are read with `getattr` so the control reports failed checks rather
than crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_draft.py
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
    get_draft = getattr(sel, "get_draft", None)
    save_draft = getattr(sel, "save_draft", None)
    discard_draft = getattr(sel, "discard_draft", None)
    DraftSet = getattr(sel, "DraftSet", None)
    DraftDemotion = getattr(sel, "DraftDemotion", None)
    set_selection, LineupSet, LineupSlot = sel.set_selection, sel.LineupSet, sel.LineupSlot

    org, other_org, user_id, user2_id, season = (uuid.uuid4() for _ in range(5))
    g_hi, g_lo, t_hi, t_lo = (uuid.uuid4() for _ in range(4))
    fx_a, fx_hi, fx_lo, fx_foreign = (uuid.uuid4() for _ in range(4))
    P = [uuid.uuid4() for _ in range(5)]
    foreign_player = uuid.uuid4()
    d = date.today() + timedelta(days=20)

    async with Session() as db:
        db.add(Organisation(id=org, name="Draft CC", slug=f"draft-{org.hex[:8]}"))
        db.add(Organisation(id=other_org, name="Other CC", slug=f"other-{other_org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(User(id=user2_id, username=f"v{user2_id.hex[:8]}", email=f"{user2_id.hex[:8]}@x.com",
                    password_hash="x", display_name="Sam Selector"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_hi, season_id=season, name="1st Grade"))
        db.add(Grade(id=g_lo, season_id=season, name="2nd Grade"))
        await db.flush()
        db.add(Team(id=t_hi, organisation_id=org, name="1st Grade", sequence=1, grade_id=g_hi))
        db.add(Team(id=t_lo, organisation_id=org, name="2nd Grade", sequence=2, grade_id=g_lo))
        await db.flush()
        for i, pid in enumerate(P):
            db.add(Player(id=pid, organisation_id=org, name=f"Player {i}", gender="male", is_player=True, status="active"))
        db.add(Player(id=foreign_player, organisation_id=other_org, name="Stranger", gender="male", is_player=True, status="active"))
        await db.flush()
        for fid, tid, gid, org_id in ((fx_a, t_hi, g_hi, org), (fx_hi, t_hi, g_hi, org), (fx_lo, t_lo, g_lo, org)):
            db.add(Fixture(id=fid, organisation_id=org_id, grade_id=gid, team_id=tid, source="manual",
                           played_on=d if fid != fx_a else d + timedelta(days=7), status="UPCOMING", label="x"))
        db.add(Fixture(id=fx_foreign, organisation_id=other_org, source="manual",
                       played_on=d, status="UPCOMING", label="theirs"))
        await db.commit()

    async def call(fn, *args, as_user=None, **kw):
        """Run a route body on its own session; return (result, None) or (None, status).
        A 409's detail is kept in LAST_DETAIL."""
        if fn is None:
            return None, "absent"
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, as_user or user_id)
            try:
                return await fn(*args, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                LAST_DETAIL[0] = e.detail
                return None, e.status_code
            except TypeError as e:    # a build whose route lacks the new argument (control run)
                return None, f"TypeError: {e}"

    async def scalar(sql, **kw):
        async with Session() as db:
            return (await db.execute(text(sql), kw)).scalar()

    async def lineup_ids(fid):
        async with Session() as db:
            rows = (await db.execute(text("SELECT player_id FROM fixture_lineups WHERE fixture_id=:f"), {"f": fid})).all()
        return {r[0] for r in rows}

    def body(**kw):
        return DraftSet(**kw) if DraftSet else None

    print("\n# A. A draft round-trips and never touches the confirmed XI")
    r, err = await call(get_draft, str(fx_a))
    check("no draft to begin with", (r or {}).get("draft", "absent"), None)
    slots = [str(P[0]), None, str(P[1]), None, str(P[2])]
    demo = DraftDemotion(player_id=str(P[3]), fixture_id=str(fx_lo), batting_order=4, callup_id=str(P[0])) if DraftDemotion else None
    r, err = await call(save_draft, str(fx_a), body(slots=slots, captain_id=str(P[0]), wicket_keeper_id=str(P[2]),
                                                   demotions=[demo] if demo else []))
    check("autosave accepted", (r or {}).get("status", err), "ok")
    r, err = await call(get_draft, str(fx_a))
    dr = (r or {}).get("draft") or {}
    check("slot gaps survive", dr.get("slots"), slots)
    check("captain survives", dr.get("captain_id"), str(P[0]))
    check("keeper survives", dr.get("wicket_keeper_id"), str(P[2]))
    check("call-up cascade survives (with its call-up id)",
          [(x.get("player_id"), x.get("callup_id")) for x in dr.get("demotions", [])], [(str(P[3]), str(P[0]))])
    check("it says when it was saved", bool((r or {}).get("updated_at")), True)
    check("NO fixture_lineups row written by a draft", await lineup_ids(fx_a), set())
    async with Session() as db:
        from app.services.selection_pool import assemble_selection
        club = await db.get(Organisation, org)
        fx = await db.get(Fixture, fx_a)
        sel = await assemble_selection(db, club, fx)
    check("the board's confirmed lineup is still empty", sel["lineup"], [])

    print("\n# B. A second autosave replaces the first")
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[4])], base_version=1))
    check("second autosave accepted", (r or {}).get("status", err), "ok")
    check("still ONE row for the fixture", await scalar("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id=:f", f=fx_a)
          if DraftSet else None, 1)
    r, _ = await call(get_draft, str(fx_a))
    check("latest save wins", ((r or {}).get("draft") or {}).get("slots"), [str(P[4])])

    print("\n# C. The server cleans what it is sent")
    r, err = await call(save_draft, str(fx_a), body(
        slots=[str(P[0]), str(foreign_player), "not-a-uuid", str(P[0]), str(P[1])],
        captain_id=str(P[2]), wicket_keeper_id=str(P[1]), base_version=2))
    check("accepted", (r or {}).get("status", err), "ok")
    r, _ = await call(get_draft, str(fx_a))
    dr = (r or {}).get("draft") or {}
    check("another club's player and junk ids become empty slots; repeats are dropped",
          dr.get("slots"), [str(P[0]), None, None, None, str(P[1])])
    check("a captain who is not in the slots is cleared", dr.get("captain_id"), None)
    check("a keeper who is in the slots is kept", dr.get("wicket_keeper_id"), str(P[1]))

    print("\n# D. Another club's fixture is not reachable")
    r, err = await call(save_draft, str(fx_foreign), body(slots=[str(P[0])]))
    check("save on a foreign fixture is a 404", err, 404)
    r, err = await call(get_draft, str(fx_foreign))
    check("read on a foreign fixture is a 404", err, 404)
    check("nothing was written for it", await scalar("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id=:f", f=fx_foreign)
          if DraftSet else None, 0)

    print("\n# E. Confirm writes the XI and clears the draft together")
    async def confirm(fid, pids):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                await set_selection(str(fid), LineupSet(players=[
                    LineupSlot(player_id=str(p), batting_order=i + 1) for i, p in enumerate(pids)]), db, club, user)
                return "ok"
            except HTTPException as e:
                return e.status_code
    check("a draft exists before confirming", await scalar("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id=:f", f=fx_a)
          if DraftSet else None, 1)
    check("confirm accepted", await confirm(fx_a, [P[0], P[1]]), "ok")
    check("the XI is now in fixture_lineups", await lineup_ids(fx_a), {P[0], P[1]})
    r, _ = await call(get_draft, str(fx_a))
    check("the draft is gone", (r or {}).get("draft", "absent"), None)

    print("\n# F. A refused confirm leaves the draft alone")
    check("P3 named in the 1st Grade game that day", await confirm(fx_hi, [P[3]]), "ok")
    r, err = await call(save_draft, str(fx_lo), body(slots=[str(P[3]), str(P[4])]))
    check("draft for the 2nd Grade game saved", (r or {}).get("status", err), "ok")
    check("confirming 2nd Grade with P3 is a same-date clash (409)", await confirm(fx_lo, [P[3], P[4]]), 409)
    r, _ = await call(get_draft, str(fx_lo))
    check("the draft survived the refusal", ((r or {}).get("draft") or {}).get("slots"), [str(P[3]), str(P[4])])
    check("and nothing reached fixture_lineups", await lineup_ids(fx_lo), set())

    print("\n# G. Discard")
    r, err = await call(discard_draft, str(fx_lo))
    check("discard accepted", (r or {}).get("status", err), "ok")
    r, _ = await call(get_draft, str(fx_lo))
    check("draft removed", (r or {}).get("draft", "absent"), None)
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[2])]))
    r, err = await call(discard_draft, str(fx_a))
    check("discard leaves the confirmed XI alone", await lineup_ids(fx_a), {P[0], P[1]})

    print("\n# H. Two selectors on one fixture")
    # fx_a has no draft now (confirmed in E, discarded in G). Sam and the
    # first user both open the board and see no draft (version 0).
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[0])], base_version=0))
    check("first selector's autosave (saw no draft) is accepted as version 1", (r or {}).get("version", err), 1)
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[1])], base_version=0), as_user=user2_id)
    check("second selector, who also saw no draft, is refused", err, 409)
    det = LAST_DETAIL[0] if isinstance(LAST_DETAIL[0], dict) else {}
    check("the refusal says it is a draft conflict", det.get("code"), "draft_conflict")
    check("it carries the current draft", (det.get("draft") or {}).get("slots"), [str(P[0])])
    check("it carries the current version", det.get("version"), 1)
    check("it says who saved it", det.get("updated_by"), f"u{user_id.hex[:8]}")
    r, _ = await call(get_draft, str(fx_a))
    check("nothing was overwritten", ((r or {}).get("draft") or {}).get("slots"), [str(P[0])])

    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[0]), str(P[1])], base_version=1), as_user=user2_id)
    check("second selector saves against the current version", (r or {}).get("version", err), 2)
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[2])], base_version=1))
    check("first selector, now stale, is refused", err, 409)
    check("and is told version 2 by Sam Selector",
          (LAST_DETAIL[0].get("version"), LAST_DETAIL[0].get("updated_by")) if isinstance(LAST_DETAIL[0], dict) else None,
          (2, "Sam Selector"))

    # Two saves at the same instant against the same version: one write wins.
    r1, r2 = await asyncio.gather(
        call(save_draft, str(fx_a), body(slots=[str(P[3])], base_version=2)),
        call(save_draft, str(fx_a), body(slots=[str(P[4])], base_version=2), as_user=user2_id),
    )
    outcomes = sorted([str((r1[0] or {}).get("version", r1[1])), str((r2[0] or {}).get("version", r2[1]))])
    check("racing saves on one version: exactly one wins, one is refused", outcomes, ["3", "409"])
    check("the version moved by exactly one", await scalar("SELECT version FROM selection_drafts WHERE fixture_id=:f", f=fx_a)
          if DraftSet else None, 3)

    r, err = await call(discard_draft, str(fx_a), base_version=2)
    check("a stale discard is refused", err, 409)
    check("and the draft survives it", await scalar("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id=:f", f=fx_a)
          if DraftSet else None, 1)
    r, err = await call(discard_draft, str(fx_a), base_version=3)
    check("discarding the version you saw works", (r or {}).get("status", err), "ok")
    r, err = await call(discard_draft, str(fx_a), base_version=3)
    check("discarding something already gone is a no-op, not an error", (r or {}).get("status", err), "ok")

    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[0])], base_version=0))
    check("a fresh draft starts again at version 1", (r or {}).get("version", err), 1)
    check("confirm (the other selector) removes it", await confirm(fx_a, [P[0], P[1]]), "ok")
    r, err = await call(save_draft, str(fx_a), body(slots=[str(P[2])], base_version=1))
    check("a board still holding the confirmed-away draft is refused", err, 409)
    check("and told there is no draft any more",
          (LAST_DETAIL[0].get("draft", "absent"), LAST_DETAIL[0].get("version")) if isinstance(LAST_DETAIL[0], dict) else None,
          (None, 0))
    check("the confirmed-away draft was not resurrected", await scalar("SELECT COUNT(*) FROM selection_drafts WHERE fixture_id=:f", f=fx_a)
          if DraftSet else None, 0)

    print("\n# I. The matchday overview flags drafts")
    async def overview():
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await importlib.import_module("app.routers.selection").selection_overview(db, club)
    r, err = await call(save_draft, str(fx_lo), body(slots=[str(P[4])], base_version=0))
    ov = await overview()
    flags = {f["id"]: (f.get("has_draft"), f.get("draft_updated_at") is not None) for f in ov["fixtures"]}
    check("fixture with a draft is flagged, with a time", flags.get(str(fx_lo)), (True, True))
    check("fixtures without one are not", [flags.get(str(fx_a)), flags.get(str(fx_hi))], [(False, False), (False, False)])
    await call(discard_draft, str(fx_lo))
    ov = await overview()
    check("discarding clears the flag", {f["id"]: f.get("has_draft") for f in ov["fixtures"]}.get(str(fx_lo)), False)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAIL:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
