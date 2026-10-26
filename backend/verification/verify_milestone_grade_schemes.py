"""Verification for a club giving one grade its own milestone increments.

Asked for: lots of clubs want smaller increments for A Grade and larger ones
for the rest of the club, and want to type their own step as well as pick a
preset.

What a grade's increments cover is the milestones INSIDE that grade (games, runs,
wickets, catches in "A Grade"): the Records page with a grade picked, the admin
report's and the profile's per-grade matches, and the grade notices. A player's
career milestones keep the club's scheme, and that is asserted here too.

Asserted against a real Postgres through the shipped route bodies and services:

* a club with no grade settings sees exactly what it saw before, and the report
  lists its grades with nothing set;
* A Grade on its own matches step changes A Grade's rungs on the admin report,
  the profile (achieved and upcoming), and the grade scan the notifications
  read, while B Grade, the career figures and ANOTHER club's "A Grade" do not;
* a grade's runs step reaches the Records page with that grade picked and not
  the career-wide view;
* a grade is its name across seasons (the sponsor-suffixed row of last season
  is the same grade) and a display name the club typed reads as the same grade;
* an unsent key leaves a step alone, an explicit null follows the club again,
  a step outside the limits and an unknown grade are refused, and a refusal
  saves nothing;
* a club-wide custom step works end to end (the rungs are filled in undated).

CONTROL=1 runs the same checks with the per-grade lookup switched off (every
grade reads the club's scheme, which is how the code behaved before): the
default-behaviour checks must still pass and the per-grade ones must fail.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_milestone_grade_schemes.py
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
from app.routers import club_admin, players as players_router, records as records_router
from app.routers.club_admin import (
    MilestoneGradeSchemeUpdate, MilestoneSchemeUpdate, list_milestones_report,
    update_milestone_grade_scheme, update_milestone_scheme,
)
from app.routers.players import get_player_milestones_endpoint, get_player_upcoming_milestones
from app.routers.records import get_records_milestones
from app.services import grade_milestone_schemes, milestone_scan

CONTROL = os.environ.get("CONTROL") == "1"
if CONTROL:
    _real_load_book = grade_milestone_schemes.load_book

    async def _club_only(db, org_id):
        book = await _real_load_book(db, org_id)
        return grade_milestone_schemes.SchemeBook(club=book.club)

    grade_milestone_schemes.load_book = _club_only
    milestone_scan.load_book = _club_only
    players_router.load_book = _club_only

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
        # Migration 330: matches/catches steps and the per-grade table.
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
OTHER = uuid.uuid4()          # another club with a grade of the same name
YEAR = date.today().year
S_NOW, S_OLD, S_OTH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
A_NOW, A_OLD, B_NOW, A_OTH = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

P1 = uuid.uuid4()     # 60 games in A Grade (30 under last season's sponsored name) + 20 in B
P2 = uuid.uuid4()     # 72 games in A Grade
P3 = uuid.uuid4()     # 48 games in B Grade + 2 in A
P4 = uuid.uuid4()     # 740 runs in A Grade
P5 = uuid.uuid4()     # 740 runs in B Grade
P6 = uuid.uuid4()     # 22 old A Grade games, then 4 in the last few days, and one B game
P7 = uuid.uuid4()     # the OTHER club's player: 72 games in its own "A Grade"
P8 = uuid.uuid4()     # a 1,100-run veteran who played five days ago
P9 = uuid.uuid4()     # 77 wickets

# A scored innings, so the game counts as played (services/game_status).
PLAYED = '[{"innings_number": 1, "runs_scored": 120, "wickets": 6}]'
LONG_AGO = date.today() - timedelta(days=500)
RECENT = [date.today() - timedelta(days=d) for d in (1, 2, 3, 4)]


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name in ((OURS, "Our Club"), (OTHER, "Other Club")):
        await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, :n, true)", i=oid, n=name)
    for sid, org, yr in ((S_NOW, OURS, YEAR), (S_OLD, OURS, YEAR - 1), (S_OTH, OTHER, YEAR)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                 i=sid, o=org, n=f"Summer {yr}", y=yr)
    for gid, sid, nm in ((A_NOW, S_NOW, "A Grade"), (A_OLD, S_OLD, "A Grade (Acme)"),
                         (B_NOW, S_NOW, "B Grade"), (A_OTH, S_OTH, "A Grade")):
        await ex("INSERT INTO grades (id, season_id, name, category) VALUES (:i, :s, :n, 'senior')",
                 i=gid, s=sid, n=nm)
    # The club merged last season's sponsored spelling into A Grade.
    await ex("INSERT INTO grade_merge_logs (org_id, alias_name, canonical_name) "
             "VALUES (:o, 'A Grade (Acme)', 'A Grade')", o=OURS)

    people = ((P1, OURS, "Sixty, Alpha"), (P2, OURS, "Seventy, Two"), (P3, OURS, "Forty, Eight"),
              (P4, OURS, "Runs, Ay"), (P5, OURS, "Runs, Bee"), (P6, OURS, "Fresh, TwentySix"),
              (P7, OTHER, "Other, SeventyTwo"), (P8, OURS, "Vet, Eran"), (P9, OURS, "Wicket, Seventyseven"))
    for pid, org, nm in people:
        await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                 "VALUES (:i, :o, :n, true, 'active')", i=pid, o=org, n=nm)
        await ex("INSERT INTO player_season_stats (player_id, season_id, matches, runs, wickets, catches) "
                 "VALUES (:p, :s, 5, :r, :w, 0)", p=pid, s=S_OTH if org == OTHER else S_NOW,
                 r=1100 if pid == P8 else 0, w=77 if pid == P9 else 0)

    async def games(grade, pid, n, when, *, runs=None):
        for i in range(n):
            g = uuid.uuid4()
            d = when[i % len(when)] if isinstance(when, list) else when - timedelta(days=i)
            await ex("INSERT INTO games (id, grade_id, played_at, innings_totals) "
                     "VALUES (:g, :gr, :d, CAST(:it AS jsonb))", g=g, gr=grade, d=d, it=PLAYED)
            await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=pid)
            if runs is not None:
                await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, did_not_bat, "
                         "dismissal_type) VALUES (:g, :p, 1, :r, false, 'bowled')", g=g, p=pid, r=runs)

    old = date.today() - timedelta(days=60)
    await games(A_OLD, P1, 30, old - timedelta(days=400))
    await games(A_NOW, P1, 30, old)
    await games(B_NOW, P1, 20, old)
    await games(A_NOW, P2, 72, old)
    await games(B_NOW, P3, 48, old)
    await games(A_NOW, P3, 2, old)
    await games(A_NOW, P4, 10, old, runs=74)
    await games(B_NOW, P5, 10, old, runs=74)
    await games(A_OLD, P6, 22, LONG_AGO)
    await games(A_NOW, P6, 4, RECENT)
    await games(B_NOW, P6, 1, RECENT)
    await games(A_OTH, P7, 72, old)
    await games(B_NOW, P8, 1, [date.today() - timedelta(days=5)])
    await ex("INSERT INTO milestones (player_id, milestone_type, milestone_value, detail, achieved_at) "
             "VALUES (:p, 'runs', 1000, 'x', '2020-01-01')", p=P8)
    await session.commit()


def user():
    return User(id=uuid.uuid4(), username="admin")


async def report(club_id=OURS):
    async with Session() as s:
        return await list_milestones_report(user(), await s.get(Organisation, club_id), s)


async def records(grade=None, org=OURS):
    async with Session() as s:
        return await get_records_milestones(str(org), grade, s, None)


async def grade_save(grade, **steps):
    async with Session() as s:
        return await update_milestone_grade_scheme(
            MilestoneGradeSchemeUpdate(grade=grade, **steps), user(), await s.get(Organisation, OURS), s)


async def club_save(**body):
    async with Session() as s:
        out = await update_milestone_scheme(
            MilestoneSchemeUpdate(**body), BackgroundTasks(), user(), await s.get(Organisation, OURS), s)
    await club_admin._fill_milestone_rungs(OURS)
    return out


async def grade_scan():
    async with Session() as s:
        return await milestone_scan.grade_milestones(
            s, str(OURS), recent_since=date.today() - timedelta(days=21))


def vals(items, pid, typ, grade=None):
    return sorted(r["milestone_value"] for r in items
                  if r["player_id"] == str(pid) and r["type"] == typ
                  and (grade is None or r.get("detail") == grade or r.get("grade") == grade))


def ups(items, pid, typ, grade=None):
    return sorted(r["target"] for r in items
                  if r["player_id"] == str(pid) and r["type"] == typ
                  and (grade is None or r.get("detail") == grade))


def steps_of(rep, key):
    return next((g["steps"] for g in rep["grade_schemes"] if g["key"] == key), None)


NONE4 = {"runs": None, "wickets": None, "matches": None, "catches": None}


async def main() -> None:
    from app.services.milestone_rules import Scheme, reach_window, next_threshold, crossed_thresholds

    await build_schema()
    async with Session() as s:
        await seed(s)

    print("\n── a club that sets nothing sees what it always saw ──")
    rep = await report()
    check("the report lists the club's grades once each, A Grade across both seasons",
          sorted(g["key"] for g in rep["grade_schemes"]) == ["a grade", "b grade"],
          str([g["key"] for g in rep["grade_schemes"]]))
    check("…with nothing set", all(g["steps"] == NONE4 for g in rep["grade_schemes"]))
    check("the club-wide scheme has all four steps at the default",
          rep["scheme"] == {"runs_step": 1000, "wickets_step": 100, "matches_step": 50, "catches_step": 50},
          str(rep["scheme"]))
    check("P1's 60 games in A Grade show the 50 rung only",
          vals(rep["achieved"], P1, "grade_matches", "A Grade") == [50],
          str(vals(rep["achieved"], P1, "grade_matches", "A Grade")))
    # Dated by the 50th game in date order: P1's 30 older A Grade games come first, so the 50th is
    # the 20th of the 30 recent ones (seeded `old` back to `old` minus 29 days), `old` minus 10 days.
    fiftieth = [r["achieved_at"] for r in rep["achieved"]
                if r["player_id"] == str(P1) and r["type"] == "grade_matches"
                and r["detail"] == "A Grade" and r["milestone_value"] == 50]
    check("…and that rung carries the date of the 50th game played in the grade, not a blank",
          fiftieth == [(date.today() - timedelta(days=70)).isoformat()], str(fiftieth))
    check("P3's 48 games in B Grade are 2 from 50",
          ups(rep["upcoming"], P3, "grade_matches", "B Grade") == [50])
    check("P2's 72 games in A Grade are not in reach of anything",
          not ups(rep["upcoming"], P2, "grade_matches", "A Grade"))
    rec_a = await records("A Grade")
    check("Records, A Grade: P4's 740 runs show the 500 rung and nothing upcoming",
          vals(rec_a["achieved"], P4, "grade_runs") == [500] and not ups(rec_a["upcoming"], P4, "grade_runs"),
          str((vals(rec_a["achieved"], P4, "grade_runs"), ups(rec_a["upcoming"], P4, "grade_runs"))))
    scan = await grade_scan()
    check("the grade scan has nothing to announce for P6 on the default",
          not [a for a in scan["achieved"] if a["player_id"] == str(P6)], str(scan["achieved"]))

    print("\n── A Grade on its own matches step (every 25) ──")
    out = await grade_save("A Grade", matches_step=25)
    check("the route returns the grade's steps",
          out["key"] == "a grade" and out["steps"] == {**NONE4, "matches": 25}, str(out))
    rep = await report()
    check("the report shows A Grade's matches step and B Grade untouched",
          steps_of(rep, "a grade") == {**NONE4, "matches": 25} and steps_of(rep, "b grade") == NONE4,
          str([(g["key"], g["steps"]) for g in rep["grade_schemes"]]))
    check("P1 now has 25 and 50 in A Grade",
          vals(rep["achieved"], P1, "grade_matches", "A Grade") == [25, 50],
          str(vals(rep["achieved"], P1, "grade_matches", "A Grade")))
    check("P2 (72) is 3 from 75 in A Grade",
          ups(rep["upcoming"], P2, "grade_matches", "A Grade") == [75])
    check("B Grade did not move: P3 is still 2 from 50",
          ups(rep["upcoming"], P3, "grade_matches", "B Grade") == [50])
    check("B Grade still shows no 25 for P1 (20 games)",
          not vals(rep["achieved"], P1, "grade_matches", "B Grade"))
    check("the club's own matches step is still 50 (career milestones keep the club's scheme)",
          rep["scheme"]["matches_step"] == 50)
    async with Session() as s:
        prof = await get_player_milestones_endpoint(str(P1), s)
        up = await get_player_upcoming_milestones(str(P2), s)
    check("P1's profile lists A Grade at 25 and 50",
          sorted(m["milestone_value"] for m in prof
                 if m["milestone_type"] == "grade_matches" and m["detail"] == "A Grade") == [25, 50])
    check("P2's profile has MATCHES — A Grade at 75",
          [m["target"] for m in up if m.get("grade_name") == "A Grade"] == [75], str(up))
    scan = await grade_scan()
    check("the grade scan announces P6 reaching 25 games in A Grade (the 26th was this week)",
          [(a["milestone_value"], a["grade"]) for a in scan["achieved"]
           if a["player_id"] == str(P6) and a["type"] == "grade_matches"] == [(25, "A Grade")],
          str([a for a in scan["achieved"] if a["player_id"] == str(P6)]))
    other = await report(OTHER)
    check("another club's own 'A Grade' still reads the default (no 25 for its 72-game player)",
          vals(other["achieved"], P7, "grade_matches", "A Grade") == [50]
          and other["grade_schemes"][0]["steps"] == NONE4,
          str(vals(other["achieved"], P7, "grade_matches", "A Grade")))

    print("\n── A Grade's runs step reaches the grade view and not the career view ──")
    out = await grade_save("A Grade", runs_step=250)
    check("an unsent key is left alone: matches is still 25",
          out["steps"] == {**NONE4, "matches": 25, "runs": 250}, str(out))
    rec_a = await records("A Grade")
    check("Records, A Grade: P4's 740 runs show 250 and 500, and 750 is 10 away",
          vals(rec_a["achieved"], P4, "grade_runs") == [250, 500] and ups(rec_a["upcoming"], P4, "grade_runs") == [750],
          str((vals(rec_a["achieved"], P4, "grade_runs"), ups(rec_a["upcoming"], P4, "grade_runs"))))
    rec_b = await records("B Grade")
    check("Records, B Grade: P5's 740 runs are untouched (500 only, nothing upcoming)",
          vals(rec_b["achieved"], P5, "grade_runs") == [500] and not ups(rec_b["upcoming"], P5, "grade_runs"))
    rec_c = await records(None)
    check("Records, career view: P4's 740 runs follow the club (nothing in reach at 1,000)",
          not [r for r in rec_c["upcoming"] if r["player_id"] == str(P4) and r["type"] == "runs"],
          str([r for r in rec_c["upcoming"] if r["player_id"] == str(P4)]))

    print("\n── an explicit null follows the club again ──")
    out = await grade_save("A Grade", matches_step=None)
    check("matches is cleared, runs is kept", out["steps"] == {**NONE4, "runs": 250}, str(out))
    rep = await report()
    check("P1 is back to 50 only in A Grade", vals(rep["achieved"], P1, "grade_matches", "A Grade") == [50])
    scan = await grade_scan()
    check("…and the grade scan has nothing for P6 again",
          not [a for a in scan["achieved"] if a["player_id"] == str(P6)])

    print("\n── refusals save nothing ──")
    for label, call in (
        ("runs 130 (not a multiple of 25)", lambda: grade_save("A Grade", runs_step=130)),
        ("matches 3 (below the smallest)", lambda: grade_save("A Grade", matches_step=3)),
        ("wickets 7 (not a multiple of 5)", lambda: grade_save("A Grade", wickets_step=7)),
        ("catches 9000 (above the largest)", lambda: grade_save("A Grade", catches_step=9000)),
        ("a grade the club does not have", lambda: grade_save("Z Grade", matches_step=25)),
        ("a blank grade", lambda: grade_save("  ", matches_step=25)),
    ):
        try:
            await call()
            check(f"{label} refused", False, "accepted")
        except HTTPException as e:
            check(f"{label} refused with 422", e.status_code == 422, str(e.status_code))
    rep = await report()
    check("…and A Grade's steps are as they were",
          steps_of(rep, "a grade") == {**NONE4, "runs": 250}, str(steps_of(rep, "a grade")))
    check("…and no Z Grade appeared", [g["key"] for g in rep["grade_schemes"]] == ["a grade", "b grade"]
          or sorted(g["key"] for g in rep["grade_schemes"]) == ["a grade", "b grade"])

    print("\n── the club's own display name for the grade is the same grade ──")
    async with Session() as s:
        await s.execute(text("UPDATE grades SET display_name_override = 'Premier Grade' WHERE id = :g"),
                        {"g": A_NOW})
        await s.commit()
    await grade_save("A Grade", matches_step=25)
    rep = await report()
    a_rows = [g for g in rep["grade_schemes"] if g["key"] == "a grade"]
    check("the list still has one entry for it, under the name the club reads",
          len(a_rows) == 1 and a_rows[0]["name"] == "Premier Grade", str(a_rows))
    check("the report's per-grade rows read the club's name and the A Grade steps",
          vals(rep["achieved"], P1, "grade_matches", "Premier Grade") == [25, 50],
          str(vals(rep["achieved"], P1, "grade_matches", "Premier Grade")))
    rec_p = await records("Premier Grade")
    check("Records with 'Premier Grade' picked uses the same increments (750 is 10 away)",
          ups(rec_p["upcoming"], P4, "grade_runs") == [750], str(ups(rec_p["upcoming"], P4, "grade_runs")))
    out = await grade_save("Premier Grade", catches_step=25)
    check("saving by the display name lands on the same grade",
          out["key"] == "a grade" and out["steps"]["catches"] == 25 and out["steps"]["runs"] == 250, str(out))
    await grade_save("a grade", catches_step=None)

    print("\n── B Grade can go the other way ──")
    await grade_save("B Grade", matches_step=100)
    rep = await report()
    check("P3's 48 games in B Grade are no longer near anything",
          not ups(rep["upcoming"], P3, "grade_matches", "B Grade"))
    check("A Grade kept its own",
          ups(rep["upcoming"], P2, "grade_matches", "Premier Grade") == [75])
    await grade_save("B Grade", matches_step=None)

    print("\n── a club-wide step of its own ──")
    out = await club_save(runs_step=300, wickets_step=40)
    check("the route accepts and returns a typed step",
          out["runs_step"] == 300 and out["wickets_step"] == 40, str(out))
    rep = await report()
    check("the report reads them back", rep["scheme"]["runs_step"] == 300 and rep["scheme"]["wickets_step"] == 40)
    check("the veteran's 1,100 runs show 300, 600 and 900 (1,000 is not on this ladder)",
          vals(rep["achieved"], P8, "runs") == [300, 600, 900], str(vals(rep["achieved"], P8, "runs")))
    async with Session() as s:
        st = {(r[0], r[1]): r[2] for r in (await s.execute(text(
            "SELECT milestone_type, milestone_value, achieved_at FROM milestones WHERE player_id = :p"),
            {"p": P8})).all()}
    check("the rungs the step added are undated, though he played five days ago",
          all(st.get(("runs", v), "missing") is None for v in (300, 600, 900)), str(st))
    check("77 wickets is 3 from 80 on a 40 step", ups(rep["upcoming"], P9, "wickets") == [80],
          str(ups(rep["upcoming"], P9, "wickets")))
    check("a grade's own runs step (250) was not disturbed by the club's 300",
          steps_of(rep, "a grade")["runs"] == 250)
    rec_a = await records("Premier Grade")
    check("…and Records for the grade still uses 250 for grade runs",
          ups(rec_a["upcoming"], P4, "grade_runs") == [750])
    for bad in ({"runs_step": 310}, {"wickets_step": 8}, {"matches_step": 600}, {"catches_step": 0}):
        try:
            await club_save(**bad)
            check(f"{bad} refused", False, "accepted")
        except HTTPException as e:
            check(f"{bad} refused with 422", e.status_code == 422, str(e.status_code))
    out = await club_save(runs_step=None, wickets_step=None)
    check("an explicit null puts the club back to the defaults",
          out == {"runs_step": 1000, "wickets_step": 100, "matches_step": 50, "catches_step": 50}, str(out))

    print("\n── the rules for a typed step ──")
    s100 = Scheme(runs_step=100)
    check("runs every 100: 740 is 60 from 800, out of reach; 790 is 10 from 800, in reach",
          (800 - 740 > reach_window("runs", 800, s100)) and (800 - 790 <= reach_window("runs", 800, s100)))
    check("a window never reaches past half a step (wickets every 10: 5)",
          reach_window("wickets", 50, Scheme(wickets_step=10)) == 5)
    check("the ladder for matches every 25 is 25, 50, 75",
          crossed_thresholds("matches", 80, Scheme(matches_step=25)) == [25, 50, 75]
          and next_threshold("matches", 80, Scheme(matches_step=25)) == 100)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("failed:")
        for f in FAILURES:
            print("  -", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
