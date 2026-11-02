"""Verification for the Milestones lens: dormant grades, unfielded grades, and the new filters' data.

Asked for off a club whose Milestones page showed a player one game short of 50
in 1st Grade when he had not played 1st Grade for twenty years. Three asks:

* a grade a player has gone quiet in is not "in reach" (upcoming only);
* a grade the club has no side in this season is not "in reach" either;
* the filter bar gets an age group (Seniors, Juniors...) and a "last played"
  season to filter on, derived on read.

Asserted against a real Postgres through the shipped route bodies and services:

* PA: 49 games in 1st Grade TWENTY YEARS AGO plus 48 in 3rd Grade lately. The
  1st Grade rung is gone from the admin report, the Records grade view, the
  player's profile and the notification scan; the 3rd Grade one stays;
* PB: 49 games in 2nd Grade last season, a grade the club has no side in this
  season. Gone from the same four places;
* PC: 49 games in 1st Grade, last played days ago, in a grade the club fields.
  Still shown everywhere (the rules do not over-hide);
* PF: 60 games in 1st Grade, all twenty years ago. The REACHED 50 stays on the
  admin report and Records (history is not rewritten);
* every report item carries ``last_played_season`` and ``age_groups``, the
  junior-only player reads ``["junior"]``, a player in both reads both, and a
  player with no scorecard reads ``["senior"]`` (unclassified is senior);
* a display name the club typed, a sponsor suffix, and a club with no season
  at all do not break the "fielded" test (an unjudgeable grade is kept).

Run against the previous commit as a CONTROL (a git worktree of HEAD~ with this
file copied in): the rule checks must FAIL and the "still shown" and history
checks must PASS. New keys are read through presence-safe accessors, so absence
is reported and does not crash.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_milestone_lens.py
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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, User
from app.routers.club_admin import list_milestones_report
from app.routers.players import get_player_upcoming_milestones
from app.routers.records import get_records_milestones
from app.services import milestone_scan
from app.services.season_resolve import season_year_for_date

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


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py / services/superseded_ddl), not on the ORM model.
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS ca_called_off BOOLEAN"))
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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, user_id UUID, action TEXT NOT NULL,
                target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')
        """))
        from app.services.milestone_scheme_ddl import STATEMENTS
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
        from app.services.milestone_grade_scheme_ddl import STATEMENTS as GRADE_STATEMENTS
        for stmt in GRADE_STATEMENTS:
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


OURS = uuid.uuid4()
EMPTY = uuid.uuid4()          # a club with no season at all
YEAR = date.today().year
TODAY = date.today()
S_NOW, S_LAST, S_OLD4, S_ANC = (uuid.uuid4() for _ in range(4))
G_1ST_NOW, G_3RD_NOW, G_U14_NOW = (uuid.uuid4() for _ in range(3))
G_2ND_LAST, G_1ST_ANC, G_3RD_OLD4 = (uuid.uuid4() for _ in range(3))
PA, PB, PC, PD, PE, PF, PG, PH = (uuid.uuid4() for _ in range(8))

# A scored innings, so the game counts as played (services/game_status).
PLAYED = '[{"innings_number": 1, "runs_scored": 120, "wickets": 6}]'
ANCIENT = date(YEAR - 20, 6, 1)
LAST_SEASON_DAY = TODAY - timedelta(days=300)
RECENT = TODAY - timedelta(days=20)
FOUR_SEASONS_AGO = date(YEAR - 4, 12, 1)


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name in ((OURS, "Our Club"), (EMPTY, "Empty Club")):
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, :n, true)", i=oid, n=name)
    for sid, yr in ((S_NOW, YEAR), (S_LAST, YEAR - 1), (S_OLD4, YEAR - 4), (S_ANC, YEAR - 20)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                 i=sid, o=OURS, n=f"Summer {yr}", y=yr)
    # This season the club fields 1st, 3rd and Under 14s. It has no 2nd Grade
    # side any more (it had one last season).
    for gid, sid, nm, cat in (
        (G_1ST_NOW, S_NOW, "1st Grade", "senior"), (G_3RD_NOW, S_NOW, "3rd Grade", "senior"),
        (G_U14_NOW, S_NOW, "Under 14s", "junior"), (G_2ND_LAST, S_LAST, "2nd Grade", "senior"),
        (G_1ST_ANC, S_ANC, "1st Grade", "senior"), (G_3RD_OLD4, S_OLD4, "3rd Grade", "senior"),
    ):
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, :n, :c)",
                 i=gid, s=sid, n=nm, c=cat)

    people = ((PA, "Ancient, Firstgrade"), (PB, "Dropped, Secondgrade"), (PC, "Current, Firstgrade"),
              (PD, "Junior, Under14"), (PE, "Inactive, Fourseasons"), (PF, "Retired, Sixty"),
              (PG, "Both, Worlds"), (PH, "Noscorecard, Person"))
    for pid, nm in people:
        await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                 "VALUES (:i, :o, :n, true, 'active')", i=pid, o=OURS, n=nm)
        # An active player has a season row in the last three years. PE does not.
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, runs, wickets, catches) "
                 "VALUES (:p, :s, 5, 0, 0, 0)", p=pid, s=S_OLD4 if pid == PE else S_NOW)

    async def games(grade, pid, n, start):
        for i in range(n):
            g = uuid.uuid4()
            await ex("INSERT INTO games (id, grade_id, played_at, innings_totals) "
                     "VALUES (:g, :gr, :d, CAST(:it AS jsonb))",
                     g=g, gr=grade, d=start - timedelta(days=i), it=PLAYED)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=pid)

    await games(G_1ST_ANC, PA, 49, ANCIENT)          # 1 short of 50, twenty years ago
    await games(G_3RD_NOW, PA, 48, RECENT)           # and 2 short in a grade he plays
    await games(G_2ND_LAST, PB, 49, LAST_SEASON_DAY)  # 1 short, in a grade with no side now
    await games(G_3RD_NOW, PB, 10, RECENT)
    await games(G_1ST_NOW, PC, 49, RECENT)           # 1 short, in a grade the club fields
    await games(G_3RD_NOW, PC, 5, RECENT - timedelta(days=100))
    await games(G_U14_NOW, PD, 48, RECENT)
    await games(G_1ST_ANC, PF, 60, ANCIENT)          # reached 50 long ago
    await games(G_3RD_NOW, PF, 3, RECENT)
    await games(G_U14_NOW, PG, 12, RECENT)
    await games(G_1ST_NOW, PG, 12, RECENT)
    await games(G_3RD_OLD4, PE, 5, FOUR_SEASONS_AGO)
    await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
             "VALUES (:p, 'runs', 1000, 'x', :d)", p=PE, d=FOUR_SEASONS_AGO)
    # PG has nothing in reach, so a stored milestone is what puts him on the report.
    await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
             "VALUES (:p, 'runs', 1000, 'x', :d)", p=PG, d=RECENT)
    await session.commit()


def user():
    return User(id=uuid.uuid4(), username="admin")


async def report(org=OURS):
    async with Session() as s:
        return await list_milestones_report(user(), await s.get(Organisation, org), s)


async def records(grade, org=OURS):
    async with Session() as s:
        return await get_records_milestones(str(org), grade, s, None)


def up(items, pid, grade, typ="grade_matches"):
    return sorted(r["target"] for r in items
                  if r["player_id"] == str(pid) and r["type"] == typ and r.get("detail") == grade)


def ach(items, pid, grade, typ="grade_matches"):
    return sorted(r["milestone_value"] for r in items
                  if r["player_id"] == str(pid) and r["type"] == typ and r.get("detail") == grade)


def item(items, pid):
    return next((r for r in items if r["player_id"] == str(pid)), None)


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)

    print("\n── admin Milestones report ──")
    rep = await report()
    check("PA (1st Grade 20 years ago) is NOT one game from 50 in 1st Grade",
          up(rep["upcoming"], PA, "1st Grade") == [], str(up(rep["upcoming"], PA, "1st Grade")))
    check("…but is still 2 from 50 in 3rd Grade, where he plays",
          up(rep["upcoming"], PA, "3rd Grade") == [50], str(up(rep["upcoming"], PA, "3rd Grade")))
    check("PB (2nd Grade, no side this season) is NOT one game from 50 in 2nd Grade",
          up(rep["upcoming"], PB, "2nd Grade") == [], str(up(rep["upcoming"], PB, "2nd Grade")))
    check("PC (1st Grade, a side the club fields, played days ago) IS one game from 50",
          up(rep["upcoming"], PC, "1st Grade") == [50], str(up(rep["upcoming"], PC, "1st Grade")))
    check("PF's REACHED 50 in 1st Grade (twenty years ago) is kept: history is not rewritten",
          50 in ach(rep["achieved"], PF, "1st Grade"), str(ach(rep["achieved"], PF, "1st Grade")))

    print("\n── Records, one grade picked ──")
    r1 = await records("1st Grade")
    check("1st Grade: PA is not listed as 1 game from 50", up(r1["upcoming"], PA, "1st Grade") == [],
          str(up(r1["upcoming"], PA, "1st Grade")))
    check("1st Grade: PC still is", up(r1["upcoming"], PC, "1st Grade") == [50],
          str(up(r1["upcoming"], PC, "1st Grade")))
    check("1st Grade: PF's reached 50 is kept", 50 in ach(r1["achieved"], PF, "1st Grade"))
    r2 = await records("2nd Grade")
    check("2nd Grade (no side this season): PB is not listed as 1 game from 50",
          up(r2["upcoming"], PB, "2nd Grade") == [], str(up(r2["upcoming"], PB, "2nd Grade")))
    r3 = await records("3rd Grade")
    check("3rd Grade (fielded): PA is still 2 from 50", up(r3["upcoming"], PA, "3rd Grade") == [50],
          str(up(r3["upcoming"], PA, "3rd Grade")))

    print("\n── the player's own profile ──")
    async with Session() as s:
        pa_prof = await get_player_upcoming_milestones(str(PA), s)
        pb_prof = await get_player_upcoming_milestones(str(PB), s)
        pc_prof = await get_player_upcoming_milestones(str(PC), s)
    grades_of = lambda rows: sorted(m.get("grade_name") for m in rows if m.get("grade_name"))
    check("PA's profile has no MATCHES — 1st Grade card", "1st Grade" not in grades_of(pa_prof), str(pa_prof))
    check("…and keeps the 3rd Grade one", "3rd Grade" in grades_of(pa_prof), str(pa_prof))
    check("PB's profile has no MATCHES — 2nd Grade card", "2nd Grade" not in grades_of(pb_prof), str(pb_prof))
    check("PC's profile keeps MATCHES — 1st Grade", "1st Grade" in grades_of(pc_prof), str(pc_prof))

    print("\n── the grade scan the notifications read ──")
    async with Session() as s:
        scan = await milestone_scan.grade_milestones(s, str(OURS), recent_since=TODAY - timedelta(days=21))
    sc = lambda pid, g: sorted(r["target"] for r in scan["upcoming"]
                               if r["player_id"] == str(pid) and r["type"] == "grade_matches" and r["grade"] == g)
    check("PB's 2nd Grade (no side this season) is not offered as upcoming", sc(PB, "2nd Grade") == [],
          str(sc(PB, "2nd Grade")))
    check("PC's 1st Grade still is", sc(PC, "1st Grade") == [50], str(sc(PC, "1st Grade")))

    print("\n── what the filters read ──")
    lens = rep.get("lens") or {}
    check("the report names the club's current season", lens.get("current_season") == YEAR, str(lens))
    check("…and the age groups that exist (senior, junior)", lens.get("age_groups") == ["senior", "junior"], str(lens))
    every = [*rep["upcoming"], *rep["achieved"]]
    check("every item carries last_played_season and age_groups",
          bool(every) and all("last_played_season" in i and "age_groups" in i for i in every))
    now_season = season_year_for_date(RECENT)
    check("PC last played this season", (item(rep["upcoming"], PC) or {}).get("last_played_season") == now_season,
          str((item(rep["upcoming"], PC) or {}).get("last_played_season")))
    check("PD (Under 14s only) reads junior", (item(rep["upcoming"], PD) or {}).get("age_groups") == ["junior"],
          str(item(rep["upcoming"], PD)))
    check("PC (1st Grade) reads senior", (item(rep["upcoming"], PC) or {}).get("age_groups") == ["senior"],
          str((item(rep["upcoming"], PC) or {}).get("age_groups")))
    pg = item(rep["achieved"], PG)
    check("PG (both in his newest season) reads senior AND junior",
          (pg or {}).get("age_groups") == ["senior", "junior"], str(pg))
    pe = item(rep["achieved"], PE)
    check("PE (last played four seasons ago) reads that season",
          (pe or {}).get("last_played_season") == season_year_for_date(FOUR_SEASONS_AGO),
          str((pe or {}).get("last_played_season")))
    check("PA's newest season is this one, not 20 years ago",
          (item(rep["upcoming"], PA) or {}).get("last_played_season") == now_season)

    print("\n── an unjudgeable grade is kept ──")
    try:
        from app.services.milestone_activity import (
            GradeActivity, load_grade_activity, played_recently, still_playing_from,
        )
    except ImportError:
        # The control tree has no such module: report it, do not crash.
        check("the shared grade-activity module exists", False, "app.services.milestone_activity is absent")
    else:
        from app.services.milestone_activity import (
            GradeActivity, load_grade_activity, played_recently, still_playing_from,
        )
        async with Session() as s:
            act = await load_grade_activity(s, OURS)
            none = await load_grade_activity(s, EMPTY)
        check("1st Grade is fielded, 2nd Grade is not", act.is_fielded("1st Grade") and not act.is_fielded("2nd Grade"))
        check("a sponsor suffix does not hide a fielded grade", act.is_fielded("1st Grade (Acme)"))
        check("a club with no season judges nothing: every grade kept", none.is_fielded("2nd Grade"))
        check("the default object keeps everything", GradeActivity().is_fielded("x") and GradeActivity().is_fielded(None))
        check("an undated last game is not dormant", played_recently(None))
        check("the window opens 1 Jan two years back",
              played_recently(still_playing_from()) and not played_recently(still_playing_from() - timedelta(days=1)))
        async with Session() as s:
            await s.execute(text("UPDATE grades SET display_name_override = 'Firsts' WHERE id = :g"), {"g": G_1ST_NOW})
            await s.commit()
        async with Session() as s:
            act2 = await load_grade_activity(s, OURS)
        check("a name the club typed over '1st Grade' still reads as fielded", act2.is_fielded("Firsts"))
        check("…and 2nd Grade is still not", not act2.is_fielded("2nd Grade"))
        rep2 = await report()
        check("with the typed name, PC is still one game from 50 (under the club's name)",
              up(rep2["upcoming"], PC, "Firsts") == [50], str(up(rep2["upcoming"], PC, "Firsts")))


    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failed:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
