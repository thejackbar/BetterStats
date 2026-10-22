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
still runs to completion and writes its dump for comparison. Build with the new code,
then `git stash` the fix and run CONTROL=1 REUSE=1 DUMP=old.json on the same database;
the two dumps must be byte-identical.
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
from app.services.grade_name_index_ddl import STATEMENTS as GRADE_NAME_INDEX_DDL

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
        # Migration 358. NO_INDEX=1 is the control: the schema as it was before.
        if not os.environ.get("NO_INDEX"):
            for stmt in GRADE_NAME_INDEX_DDL:
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
    # Every OTHER club's grades sit in the same table. The override lookup cannot use an
    # index on a name, so it reads all of them for every partnership row: Payneham's
    # server holds ~31,000 grades and that is what turned 53,000 rows into 46s.
    await ex("INSERT INTO organisations (id, name, slug, is_active) "
             "SELECT gen_random_uuid(), 'Club ' || i, 'club-' || i, true "
             "FROM generate_series(1, 300) i")
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "SELECT gen_random_uuid(), o.id, 'S' || y, 2000 + y FROM organisations o, "
             "generate_series(1, 10) y WHERE o.slug LIKE 'club-%'")
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "SELECT gen_random_uuid(), s.id, 'Grade ' || (g % :names), gen_random_uuid()::text, "
             "'senior', ARRAY['senior'] FROM seasons s, generate_series(0, 9) g "
             "WHERE s.name LIKE 'S%'", names=NAMES)
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
          JOIN LATERAL (SELECT g.id FROM grades g JOIN seasons se ON se.id = g.season_id
                         WHERE se.organisation_id = :o ORDER BY g.id OFFSET (n % :gcount) LIMIT 1) gr ON TRUE
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

    # REUSE=1 runs against the database a previous run built, so two commits can be
    # compared on IDENTICAL rows (ids are random per build).
    if not os.environ.get("REUSE"):
        await build_schema()
        async with Session() as session:
            await seed(session)

    async with Session() as session:
        # Production's planner did NOT cache the lookup (its plan shows the grades table
        # scanned 53,475 times). Whether it does is the planner's call, so the fix must
        # not lean on it: switch the cache off here to make the slow plan the one tested.
        await session.execute(text("SET enable_memoize = off"))
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

    # The picked-grade, picked-season and finals-only forms add their own conditions to the
    # same two queries (the grade filter reads merge logs and other grades inside them),
    # so each is run too and dumped for the old-vs-new comparison.
    variants = {"unfiltered": part}
    variant_secs: dict[str, float] = {}
    async with Session() as session:
        await session.execute(text("SET enable_memoize = off"))
        season_id = (await session.execute(text(
            "SELECT id::text FROM seasons WHERE organisation_id = :o AND year = 1960"),
            {"o": ORG})).scalar()
        for label, kw in (("grade_name", {"grade_name": "Grade 1"}),
                          ("alias_grade_name", {"grade_name": "Premier 7"}),
                          ("season", {"season_id": season_id}),
                          ("finals", {"finals_only": True})):
            args = dict(season_id=None, grade_id=None, grade_name=None, finals_only=False,
                        captain_only=False, gender=None, categories=None, formats=None,
                        competitions=None, debug_timing=False, viewer=None)
            args.update(kw)
            t_variant = time.perf_counter()
            variants[label] = (await get_records(str(ORG), db=session, **args))["partnerships"]
            variant_secs[label] = time.perf_counter() - t_variant
    check("a picked season still narrows the boards",
          variants["season"]["top_partnerships"] != part["top_partnerships"]
          or not part["top_partnerships"])
    check("a picked grade name returns its own boards",
          bool(variants["grade_name"]["top_partnerships"]))
    dump_path = os.environ.get("DUMP")
    if dump_path:
        Path(dump_path).write_text(json.dumps(variants, sort_keys=True, default=str))

    print("\n-- the boards hold the rows and the resolved names --")
    wickets = [k for k in part if k.startswith("wicket_")]
    check("every wicket has a board", len(wickets) == 10, str(sorted(wickets)))
    check("each wicket board holds its ten best", all(len(part[k]) == 10 for k in wickets))
    by_grade = part["by_grade"]
    check("there is a best partnership per wicket for the resolved grade names",
          len(by_grade) >= 8, str(len(by_grade)))
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

    # A picked grade adds a per-row "was it renamed" EXISTS to the same boards, and
    # grades had no index on name: 32s here, 46s on a real long-history club. The
    # index (migration 358) is what keeps it to the same fraction of a second.
    print("\n-- a picked grade, and the index behind the lookup --")
    for label in ("grade_name", "alias_grade_name"):
        secs = variant_secs.get(label, -1)
        print(f"  {label}: {secs:.1f} s")
        check(f"a picked grade ({label}) comes back fast, not rows x grades",
              0 <= secs < (10 ** 9 if os.environ.get("CONTROL") else 5), f"{secs:.1f} s")
    async with Session() as session:
        idx = (await session.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'grades' "
            "AND indexname = 'ix_grades_name_override'"))).scalar()
        check("the index exists and is partial on display_name_override",
              bool(idx) and "display_name_override IS NOT NULL" in idx, str(idx))
        # The shared list is run on every boot, so a second run must change nothing.
        for stmt in GRADE_NAME_INDEX_DDL:
            await session.execute(text(stmt))
        await session.commit()
        check("running the DDL again is a no-op", True)

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
