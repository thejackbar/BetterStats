"""The partnership boards on the records page name each partnership's grade once per
GRADE, not once per partnership row.

`partnerships_by_wicket_rows` and `partnerships_by_grade_rows` resolved a grade's
display name (the merge-alias lookup and the display-name-override lookup) in two
LATERAL subqueries, which Postgres runs once per partnership row. The override
lookup scans every grade the club has ever had, so a club with a long history and
tens of thousands of partnerships paid rows x grades: Payneham's page took 100s,
47s of it in each of those two boards, and the browser gave up first.

This builds that shape (hundreds of grades, tens of thousands of partnerships)
and runs the SHIPPED route body over the ``v_effective_*`` views taken from the
migrations. It checks the two boards come back fast AND that the names, ranks and
rows are exactly what the per-row form returned (DUMP=path writes the payload so a
control run on the previous commit can be diffed against it).

Run:
  DATABASE_URL=postgresql+asyncpg://root@/pl_verify?host=/var/run/postgresql \
  python verification/verify_records_partnership_grade_names.py

Control (previous commit): CONTROL=1 only relaxes the speed bound, so the old code
still runs to completion and writes its dump for comparison.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.routers.records import get_records
from app.services.competition_ddl import STATEMENTS as COMP_DDL

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


DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
OPP = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN = uuid.UUID("77777777-7777-7777-7777-777777777777")

SEASONS = 60
GRADES_PER_SEASON = 10
NAMES = 40            # grade names recur across seasons, as a club's do
GAMES = 30000         # one partnership each


class Viewer:
    def __init__(self, user_id):
        self.id = user_id


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name, slug in ((ORG, "Long History CC", "long"), (OPP, "Rivals CC", "rivals")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=name, s=slug)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "SELECT gen_random_uuid(), :o, 'Season ' || (1950 + s), 1950 + s "
             "FROM generate_series(0, :n - 1) s", o=ORG, n=SEASONS)
    # Names recur across seasons. Every 7th name carries a display override on ONE of
    # its grades (the lookup takes any grade of the club with that name), and two
    # names are aliases merged into another.
    await ex("""
        INSERT INTO grades (id, season_id, name, grassroots_id, category, categories,
                            display_name_override)
        SELECT gen_random_uuid(), s.id, 'Grade ' || (g % :names),
               gen_random_uuid()::text, 'senior', ARRAY['senior'],
               CASE WHEN (g % :names) % 7 = 0 AND s.year = 1950
                    THEN 'Premier ' || (g % :names) END
          FROM seasons s, generate_series(0, :gps - 1) g
         WHERE s.organisation_id = :o
    """, o=ORG, names=NAMES, gps=GRADES_PER_SEASON)
    await ex("INSERT INTO grade_merge_logs (org_id, canonical_name, alias_name) VALUES "
             "(:o, 'Grade 1', 'Grade 2'), (:o, 'Grade 14', 'Grade 3')", o=ORG)
    await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
             "SELECT gen_random_uuid(), :o, 'Player, N' || i, gen_random_uuid()::text, 'active' "
             "FROM generate_series(1, 40) i", o=ORG)
    await ex("INSERT INTO users (id, username, password_hash, failed_login_count) "
             "VALUES (:i, 'boss', 'x', 0)", i=ADMIN)
    await ex("INSERT INTO club_memberships (id, user_id, club_id, role) "
             "VALUES (gen_random_uuid(), :u, :o, 'super_admin')", u=ADMIN, o=ORG)
    # GAMES games over the grades, one partnership each. runs is unique per row so a
    # rank never rests on a tie and two plans cannot order it differently.
    await ex("""
        INSERT INTO games (id, grade_id, played_at, result, home_org_id, away_org_id,
                           match_format, status)
        SELECT gen_random_uuid(), gr.id, DATE '1950-10-01' + (n % 9000), 'WIN',
               :o, :x, 'One Day', 'COMPLETED'
          FROM generate_series(1, :n) n
          JOIN LATERAL (SELECT id FROM grades ORDER BY id OFFSET (n % :gcount) LIMIT 1) gr ON TRUE
    """, o=ORG, x=OPP, n=GAMES, gcount=SEASONS * GRADES_PER_SEASON)
    await ex("""
        WITH ps AS (SELECT id, row_number() OVER (ORDER BY id) rn FROM players
                     WHERE organisation_id = :o),
             gs AS (SELECT id, row_number() OVER (ORDER BY id) rn FROM games)
        INSERT INTO partnerships (game_id, innings_number, wicket_number, runs,
                                  batter1_id, batter2_id, is_club_innings)
        SELECT gs.id, 1, 1 + (gs.rn % 10), gs.rn,
               (SELECT id FROM ps WHERE ps.rn = 1 + (gs.rn % 39)),
               (SELECT id FROM ps WHERE ps.rn = 2 + (gs.rn % 39)), true
          FROM gs
    """, o=ORG)
    await session.commit()
    await session.execute(text("ANALYZE"))
    await session.commit()


async def main() -> None:
    import time

    await build_schema()
    async with Session() as session:
        await seed(session)

    async with Session() as session:
        t0 = time.perf_counter()
        out = await get_records(
            str(ORG), db=session, season_id=None, grade_id=None, grade_name=None,
            finals_only=False, captain_only=False, gender=None, categories=None,
            formats=None, competitions=None, debug_timing=True, viewer=Viewer(ADMIN))
        wall = time.perf_counter() - t0

    timings = {q["label"]: q["ms"] for q in out["_query_timings"]["queries"]}
    by_wicket_ms = timings.get("partnerships_by_wicket_rows", -1)
    by_grade_ms = timings.get("partnerships_by_grade_rows", -1)
    print(f"\n  partnerships_by_wicket_rows {by_wicket_ms:.0f} ms, "
          f"partnerships_by_grade_rows {by_grade_ms:.0f} ms, request {wall:.1f} s")

    part = out["partnerships"]
    dump_path = os.environ.get("DUMP")
    if dump_path:
        Path(dump_path).write_text(json.dumps(part, sort_keys=True, default=str))

    print("\n-- the boards hold the rows and the resolved names --")
    wickets = [k for k in part if k.startswith("wicket_")]
    check("every wicket has a board", len(wickets) == 10, str(sorted(wickets)))
    check("each wicket board holds its ten best", all(len(part[k]) == 10 for k in wickets))
    by_grade = part["by_grade"]
    check("there is a best partnership per wicket for every resolved grade name",
          len(by_grade) > 10, str(len(by_grade)))
    names = set(by_grade)
    check("a grade with a display override shows the override",
          any(n.startswith("Premier ") for n in names), str(sorted(names)[:8]))
    check("an alias merged into another grade shows the canonical name, not its own",
          "Grade 2" not in names and "Grade 3" not in names
          and "Grade 1" in names, str(sorted(names)[:8]))

    print("\n-- speed --")
    limit = 5000 if not os.environ.get("CONTROL") else 10 ** 9
    check("the wicket board does not scale with rows x grades",
          0 <= by_wicket_ms < limit, f"{by_wicket_ms:.0f} ms")
    check("nor does the best-per-grade board",
          0 <= by_grade_ms < limit, f"{by_grade_ms:.0f} ms")

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
