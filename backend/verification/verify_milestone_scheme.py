"""Verification for a club choosing its own run and wicket milestone increments.

Asked for on the Milestones screen: runs have been 500 then every 1,000 and
wickets 50 then every 100 for every club. A club can now pick runs every 250,
500 or 1,000 and wickets every 25, 50 or 100.

Asserted against a real Postgres through the shipped route bodies and services:

* a club on the default sees exactly what it saw before;
* picking a step changes what is "in reach" on all three surfaces together
  (the admin report, the public Records page, the dashboard list), and what is
  "achieved" (the stored rows are filled in by the save);
* the rungs a new step adds are filled in UNDATED, so a veteran is not emailed
  that he "just reached" 250 runs, even though he played last week;
* an unsent key leaves an increment alone, an explicit null clears it, a value
  that is not offered is refused;
* going back hides the extra rungs without deleting them.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_milestone_scheme.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, User
from app.routers import club_admin
from app.routers.club_admin import (
    MilestoneSchemeUpdate, list_milestones_report, update_milestone_scheme,
)
from app.routers.records import get_records_milestones
from app.routers.players import get_player_milestones_endpoint
from app.services import notification_scan
from app.services.aggregations import get_upcoming_milestones_for_org

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


OURS = uuid.uuid4()
OTHER = uuid.uuid4()          # a second club that never touches its setting
YEAR = date.today().year
S_NOW = uuid.uuid4(); S_OTHER = uuid.uuid4()
G_NOW = uuid.uuid4(); G_OTHER = uuid.uuid4()
GAME_RECENT = uuid.uuid4()

P_740 = uuid.uuid4()       # 740 runs: 10 short of 750 (not in reach by default)
P_1100 = uuid.uuid4()      # 1,100 runs and played last week
P_73W = uuid.uuid4()       # 73 wickets: 2 short of 75
P_48W = uuid.uuid4()       # 48 wickets: 2 short of 50 on every scheme
P_493 = uuid.uuid4()       # 493 runs: 7 short of 500 on every scheme
P_OTHER = uuid.uuid4()     # 740 runs at the other club, default scheme


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS import_effective_deltas (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                organisation_id uuid, player_id uuid, season_id uuid,
                scope text, matches int, batting_innings int, runs int,
                not_outs int, balls_faced int, fifties int, hundreds int,
                ducks int, high_score int, is_hs_not_out boolean,
                fours int, sixes int, batting_minutes int,
                bowling_innings int, wickets int, overs numeric,
                bowling_balls int, runs_conceded int, maidens int,
                best_bowling_wickets int, best_bowling_figures text,
                five_wicket_innings int, wides int, no_balls int,
                catches int, catches_wk int, catches_non_wk int,
                run_outs int, assisted_run_outs int, unassisted_run_outs int,
                stumpings int)
        """))
        # Lifespan DDL (main.py), copied column for column: the player profile's
        # team breakdown reads it.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                user_id UUID,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                details JSONB DEFAULT '{}'
            )
        """))
        # The lifespan adds these; alembic 321 and main.py both run this list.
        from app.services.milestone_scheme_ddl import STATEMENTS
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name in ((OURS, "Our Club"), (OTHER, "Other Club")):
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, :n, true)", i=oid, n=name)
    for sid, org in ((S_NOW, OURS), (S_OTHER, OTHER)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                 i=sid, o=org, n=f"Summer {YEAR}/{str(YEAR + 1)[2:]}", y=YEAR)
    for gid, sid in ((G_NOW, S_NOW), (G_OTHER, S_OTHER)):
        await ex("INSERT INTO grades (id, season_id, name, category) "
                 "VALUES (:i, :s, 'Men''s First Grade', 'senior')", i=gid, s=sid)

    for pid, org, nm in ((P_740, OURS, "Seven, Forty"), (P_1100, OURS, "Eleven, Hundred"),
                         (P_73W, OURS, "Seventy, Three"), (P_48W, OURS, "Forty, Eight"),
                         (P_493, OURS, "Four, Ninety"), (P_OTHER, OTHER, "Other, Seven")):
        await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                 "VALUES (:i, :o, :n, true, 'active')", i=pid, o=org, n=nm)

    async def stats(pid, sid, *, matches=20, runs=0, wickets=0, catches=0):
        await ex("""INSERT INTO player_season_stats (player_id, season_id, matches, runs, wickets, catches)
                    VALUES (:p, :s, :m, :r, :w, :c)""", p=pid, s=sid, m=matches, r=runs, w=wickets, c=catches)

    await stats(P_740, S_NOW, runs=740)
    await stats(P_1100, S_NOW, runs=1100)
    await stats(P_73W, S_NOW, wickets=73)
    await stats(P_48W, S_NOW, wickets=48)
    await stats(P_493, S_NOW, runs=493)
    await stats(P_OTHER, S_OTHER, runs=740)

    # P_1100 played last week: the only thing that could get a catch-up rung
    # dated today and announced.
    await ex("INSERT INTO games (id, grade_id, played_at) VALUES (:g, :gr, :d)",
             g=GAME_RECENT, gr=G_NOW, d=date.today() - timedelta(days=5))
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=GAME_RECENT, p=P_1100)

    # What the sync wrote under the default scheme for the veteran.
    for mt, mv in (("runs", 500), ("runs", 1000)):
        await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
                 "VALUES (:p, :t, :v, 'x', '2020-01-01')", p=P_1100, t=mt, v=mv)
    await session.commit()


def rows(items, stat, pid):
    return [r for r in items if r["type"] == stat and r["player_id"] == str(pid)]


def targets(items, stat, pid):
    return sorted(r["target"] for r in rows(items, stat, pid))


async def surfaces(club_id):
    org_id = str(club_id)
    async with Session() as s:
        club = await s.get(Organisation, club_id)
        admin = await list_milestones_report(User(id=uuid.uuid4(), username="a"), club, s)
        recs = await get_records_milestones(org_id, None, s, None)
        dash = await get_upcoming_milestones_for_org(s, org_id, 500)
    return admin, recs, dash


async def save(**body):
    async with Session() as s:
        club = await s.get(Organisation, OURS)
        out = await update_milestone_scheme(
            MilestoneSchemeUpdate(**body), BackgroundTasks(),
            User(id=uuid.uuid4(), username="admin"), club, s)
    # The route fills new rungs after the response; run that step the way the
    # background task would.
    await club_admin._fill_milestone_rungs(OURS)
    return out


async def stored(pid):
    async with Session() as s:
        return {(r[0], r[1]): r[2] for r in (await s.execute(text(
            "SELECT milestone_type, milestone_value, achieved_at FROM milestones WHERE player_id = :p"),
            {"p": pid})).all()}


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)

    print("\n── a club on the default sees what it always saw ──")
    admin, recs, dash = await surfaces(OURS)
    check("the report says runs every 1,000 and wickets every 100",
          admin["scheme"] == {"runs_step": 1000, "wickets_step": 100}, str(admin.get("scheme")))
    check("the report lists the options it offers",
          admin["scheme_options"] == {"runs_steps": [250, 500, 1000], "wickets_steps": [25, 50, 100]})
    check("740 runs is NOT in reach (next rung 1,000, 260 away)", not rows(admin["upcoming"], "runs", P_740))
    check("73 wickets is NOT in reach (next rung 100, 27 away)", not rows(admin["upcoming"], "wickets", P_73W))
    check("493 runs is 7 from 500", targets(admin["upcoming"], "runs", P_493) == [500])
    check("48 wickets is 2 from 50", targets(admin["upcoming"], "wickets", P_48W) == [50])
    check("the veteran's stored 500 and 1,000 show as achieved",
          {r["milestone_value"] for r in rows(admin["achieved"], "runs", P_1100)} == {500, 1000})

    print("\n── runs every 250 ──")
    out = await save(runs_step=250)
    check("the route returns the saved steps", out == {"runs_step": 250, "wickets_step": 100}, str(out))
    admin, recs, dash = await surfaces(OURS)
    check("the report now reads 250", admin["scheme"]["runs_step"] == 250)
    check("740 runs is now 10 from 750 on the report", targets(admin["upcoming"], "runs", P_740) == [750])
    check("…on the public Records page", targets(recs["upcoming"], "runs", P_740) == [750])
    check("…and on the dashboard list", targets(dash, "runs", P_740) == [750])
    check("493 runs is still 7 from 500", targets(admin["upcoming"], "runs", P_493) == [500])
    check("wickets are untouched: 73 is still out of reach", not rows(admin["upcoming"], "wickets", P_73W))
    got = {r["milestone_value"] for r in rows(admin["achieved"], "runs", P_1100)}
    check("the veteran's 250 and 750 were filled in beside his 500 and 1,000",
          got == {250, 500, 750, 1000}, str(sorted(got)))
    st = await stored(P_1100)
    check("the filled rungs are undated, though he played five days ago",
          st.get(("runs", 250), "missing") is None and st.get(("runs", 750), "missing") is None, str(st))
    check("…his original dates are kept", str(st.get(("runs", 500))) == "2020-01-01", str(st))
    async with Session() as s:
        due = await notification_scan._src_milestone_achieved(s, OURS, {})
    check("…so no email says he just reached 250 runs",
          not [d for d in due if d["payload"]["player_id"] == str(P_1100)], str(due))
    async with Session() as s:
        prof = await get_player_milestones_endpoint(str(P_1100), s)
    check("his profile lists 250 and 750 too",
          {m["milestone_value"] for m in prof if m["milestone_type"] == "runs"} == {250, 500, 750, 1000})

    print("\n── another club is unaffected ──")
    a2, r2, d2 = await surfaces(OTHER)
    check("its scheme is still the default", a2["scheme"] == {"runs_step": 1000, "wickets_step": 100})
    check("its 740 runs is still out of reach", not rows(a2["upcoming"], "runs", P_OTHER))

    print("\n── wickets every 25, runs left alone by an unsent key ──")
    out = await save(wickets_step=25)
    check("runs stayed 250 (key not sent)", out == {"runs_step": 250, "wickets_step": 25}, str(out))
    admin, recs, dash = await surfaces(OURS)
    check("73 wickets is now 2 from 75", targets(admin["upcoming"], "wickets", P_73W) == [75])
    check("…on the dashboard too", targets(dash, "wickets", P_73W) == [75])
    check("48 wickets is 2 from 50, and not also chasing 75",
          targets(admin["upcoming"], "wickets", P_48W) == [50])

    print("\n── a value that is not offered is refused ──")
    for bad in ({"runs_step": 300}, {"wickets_step": 10}, {"runs_step": 100}):
        try:
            await save(**bad)
            check(f"{bad} refused", False, "accepted")
        except HTTPException as e:
            check(f"{bad} refused with 422", e.status_code == 422, str(e.status_code))
    admin, _, _ = await surfaces(OURS)
    check("…and nothing was saved by the refusals", admin["scheme"] == {"runs_step": 250, "wickets_step": 25})

    print("\n── going back hides the extra rungs without deleting them ──")
    await save(runs_step=None, wickets_step=None)
    admin, recs, dash = await surfaces(OURS)
    check("an explicit null puts both back to the default",
          admin["scheme"] == {"runs_step": 1000, "wickets_step": 100}, str(admin["scheme"]))
    check("the 250 and 750 rungs are no longer shown",
          {r["milestone_value"] for r in rows(admin["achieved"], "runs", P_1100)} == {500, 1000})
    check("…on the public Records page too",
          {r["milestone_value"] for r in rows(recs["achieved"], "runs", P_1100)} == {500, 1000})
    check("…but the rows are still stored", ("runs", 250) in await stored(P_1100))
    check("740 runs is out of reach again", not rows(admin["upcoming"], "runs", P_740))

    print("\n── control: without catch_up the same rungs WOULD be dated and announced ──")
    # Proves the undated check above can fail. A sync writes a rung dated today
    # when the player has played inside the notification window.
    from app.services.sync import _compute_milestones
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET milestone_runs_step = 250 WHERE id = :o"), {"o": OURS})
        await s.execute(text("DELETE FROM milestones WHERE player_id = :p AND milestone_value IN (250, 750)"),
                        {"p": P_1100})
        await s.commit()
        await _compute_milestones(s, [str(P_1100)], OURS)
    st = await stored(P_1100)
    check("a plain sync dates the 250 rung today (so the catch-up check is meaningful)",
          st.get(("runs", 250)) == date.today(), str(st))
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET milestone_runs_step = NULL WHERE id = :o"), {"o": OURS})
        await s.commit()

    print("\n── runs every 500, wickets every 50 ──")
    await save(runs_step=500, wickets_step=50)
    admin, _, _ = await surfaces(OURS)
    check("500 steps: the veteran has 500 and 1,000 and no 250",
          {r["milestone_value"] for r in rows(admin["achieved"], "runs", P_1100)} == {500, 1000})
    check("1,100 runs is 400 from 1,500: not in reach", not rows(admin["upcoming"], "runs", P_1100))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failed:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
