"""Verification for the doubled-up player season rows, against a real Postgres.

Reported: https://betterat.cricket/players/f0a7c155-… showed "2025/26" twice,
"2022/23" three times and "2020/21" three times, each row holding a slice of
the real season.

Root cause replayed here: a fixture between two synced clubs is ONE `games`
row, and its grade — and therefore its season — belongs to whichever club
synced it first. `_season_by_season_scoped` grouped on that raw season id with
no club scoping at all, so a Gosnells batter's innings in a Gosnells fixture
that Willetton synced first was filed under WILLETTON's "Summer 2025/26" and
drawn as a second, identically-named row.

Runs the SHIPPED `get_season_by_season` (both its scoped and unscoped paths) —
never a re-implementation — over the views pulled straight out of the
migrations that define them.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/bstest?host=/var/tmp&port=5433 \
      python verification/verify_player_season_fold.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services import grade_scope
from app.services.aggregations import get_season_by_season

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


# ── ids ──────────────────────────────────────────────────────────────────────
OURS = uuid.uuid4()      # the club whose page is being read
THEIRS = uuid.uuid4()    # another club in the same competition
THIRD = uuid.uuid4()     # and a third, for the year drawn three times
PLAYER = uuid.uuid4()

# Each club has its own `seasons` row for the same real season.
S_OURS_25 = uuid.uuid4(); S_THEIRS_25 = uuid.uuid4()
S_OURS_22 = uuid.uuid4(); S_THEIRS_22 = uuid.uuid4(); S_THIRD_22 = uuid.uuid4()
# A year only another club holds a row for — nothing to fold onto.
S_THEIRS_10 = uuid.uuid4()
# Two of OUR OWN rows for one year — the split that reaches the unscoped path,
# which reads CA's season aggregates and so never sees another club's row.
S_OURS_19A = uuid.uuid4(); S_OURS_19B = uuid.uuid4()
# CA's pre-migration bundle: a whole career dumped on the earliest season.
S_OURS_99 = uuid.uuid4()

G_OURS_25 = uuid.uuid4(); G_THEIRS_25 = uuid.uuid4()
G_OURS_22 = uuid.uuid4(); G_THEIRS_22 = uuid.uuid4(); G_THIRD_22 = uuid.uuid4()
G_JUNIOR = uuid.uuid4()          # what makes the club's default scope ACTIVE
G_THEIRS_10 = uuid.uuid4()
G_OURS_19A = uuid.uuid4(); G_OURS_19B = uuid.uuid4(); G_OURS_99 = uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Raw-SQL lifespan tables create_all doesn't make.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id    UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active "
            "ON season_aliases(alias_season_id) WHERE undone_at IS NULL"))
        # Raw-SQL tables the effective views read that create_all doesn't make.
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
        # create_all types `raw_payload` as json where the migrations use
        # jsonb, and a UNION cannot coerce between them.
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb '
                f'USING "{col}"::text::jsonb'))
        stmts = view_statements()
        # Applied twice: a DROP … CASCADE can take a dependent view with it,
        # and the second pass puts anything cascaded away back.
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, name in ((OURS, "Our Club"), (THEIRS, "Their Club"), (THIRD, "Third Club")):
        await ex("INSERT INTO organisations (id, name, is_active) "
                 "VALUES (:i, :n, true)", i=oid, n=name)

    seasons = [
        (S_OURS_25, OURS, "Summer 2025/26", 2025),
        (S_THEIRS_25, THEIRS, "Summer 2025/26", 2025),
        (S_OURS_22, OURS, "Summer 2022/23", 2022),
        (S_THEIRS_22, THEIRS, "Summer 2022/23", 2022),
        (S_THIRD_22, THIRD, "Summer 2022/23", 2022),
        (S_THEIRS_10, THEIRS, "Summer 2010/11", 2010),
        (S_OURS_19A, OURS, "Summer 2019/20", 2019),
        (S_OURS_19B, OURS, "Summer 2019/20", 2019),
        (S_OURS_99, OURS, "Summer 1999/00", 1999),
    ]
    for sid, org, nm, yr in seasons:
        await ex(
            "INSERT INTO seasons (id, organisation_id, name, year) "
            "VALUES (:i, :o, :n, :y)", i=sid, o=org, n=nm, y=yr)

    grades = [
        (G_OURS_25, S_OURS_25, "Men's First Grade", "senior"),
        (G_THEIRS_25, S_THEIRS_25, "Men's First Grade", "senior"),
        (G_OURS_22, S_OURS_22, "Men's First Grade", "senior"),
        (G_THEIRS_22, S_THEIRS_22, "Men's First Grade", "senior"),
        (G_THIRD_22, S_THIRD_22, "Men's First Grade", "senior"),
        (G_JUNIOR, S_OURS_25, "Under 14s", "junior"),
        (G_THEIRS_10, S_THEIRS_10, "Men's First Grade", "senior"),
        (G_OURS_19A, S_OURS_19A, "Men's First Grade", "senior"),
        (G_OURS_19B, S_OURS_19B, "Men's First Grade", "senior"),
        (G_OURS_99, S_OURS_99, "Men's First Grade", "senior"),
    ]
    for gid, sid, nm, cat in grades:
        await ex(
            "INSERT INTO grades (id, season_id, name, category) "
            "VALUES (:i, :s, :n, :c)", i=gid, s=sid, n=nm, c=cat)

    await ex(
        "INSERT INTO players (id, organisation_id, name) "
        "VALUES (:i, :o, :n)", i=PLAYER, o=OURS, n="Sawatzky, Cameron")

    # (grade, how many games, runs each) — the club's own season row and the
    # sibling rows another club's sync happened to create.
    plan = [
        (G_OURS_25, 3, 50), (G_THEIRS_25, 1, 24),
        (G_OURS_22, 2, 100), (G_THEIRS_22, 1, 15), (G_THIRD_22, 1, 12),
        (G_THEIRS_10, 1, 7),
    ]
    n = 0
    for gid, count, runs in plan:
        for _ in range(count):
            n += 1
            g = uuid.uuid4()
            await ex(
                "INSERT INTO games (id, grade_id, played_at) "
                "VALUES (:i, :g, :d)",
                i=g, g=gid, d=date(2020, 1, 1))
            await ex(
                "INSERT INTO batting_innings "
                "(game_id, player_id, runs, balls, not_out, fours, sixes, "
                " innings_number, batting_position) "
                "VALUES (:g, :p, :r, 40, false, 2, 0, 1, 3)",
                g=g, p=PLAYER, r=runs)
    # The unscoped path reads CA's own season aggregates, so give it rows to
    # read: our own 2019/20 split across two of our season rows, plus a
    # pre-migration bundle (a whole career on one season row).
    for sid, matches, runs in (
        (S_OURS_19A, 8, 300), (S_OURS_19B, 2, 40),
        (S_OURS_99, 256, 4000),
    ):
        await ex(
            "INSERT INTO player_season_stats "
            "(player_id, season_id, matches, batting_innings, runs, "
            " not_outs, balls_faced, fifties, hundreds, ducks, high_score) "
            "VALUES (:p, :s, :m, :m, :r, 0, 100, 0, 0, 0, 50)",
            p=PLAYER, s=sid, m=matches, r=runs)
    await session.commit()


async def rows_for(session, scope):
    return await get_season_by_season(
        session, str(PLAYER), include_prior=True, scope=scope)


def by_label(rows):
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r.get("season_name")), []).append(r)
    return out


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)

        scope, _ = await grade_scope.resolve_scope_for_player(
            session, OURS, str(PLAYER), None, auto_widen=True)
        print("\n— the club's default scope (this is what the reported page ran) —")
        check("scope is active, so the scoped path is the one under test",
              scope is not None and scope.active)

        scoped = await rows_for(session, scope)
        g = by_label(scoped)

        print("\n— the reported case: one real season, one row —")
        check("2025/26 draws ONE row, not two",
              len(g.get("Summer 2025/26", [])) == 1,
              f"got {len(g.get('Summer 2025/26', []))}")
        check("2022/23 draws ONE row, not three",
              len(g.get("Summer 2022/23", [])) == 1,
              f"got {len(g.get('Summer 2022/23', []))}")

        if len(g.get("Summer 2025/26", [])) == 1:
            r = g["Summer 2025/26"][0]
            check("the folded 2025/26 row is filed under OUR OWN season row",
                  str(r["season_id"]) == str(S_OURS_25), str(r["season_id"]))
            check("2025/26 holds every innings (3 ours + 1 theirs = 4)",
                  r["batting_innings"] == 4, str(r["batting_innings"]))
            check("2025/26 runs are the whole season (3×50 + 24 = 174)",
                  r["total_runs"] == 174, str(r["total_runs"]))
        if len(g.get("Summer 2022/23", [])) == 1:
            r = g["Summer 2022/23"][0]
            check("2022/23 folds all three clubs' rows (2×100 + 15 + 12 = 227)",
                  r["total_runs"] == 227, str(r["total_runs"]))

        print("\n— nothing is dropped —")
        check("a year only ANOTHER club has a season row for still draws",
              len(g.get("Summer 2010/11", [])) == 1)
        total_inn = sum((r.get("batting_innings") or 0) for r in scoped)
        total_runs = sum((r.get("total_runs") or 0) for r in scoped)
        check("innings still add up to the career (9)", total_inn == 9, str(total_inn))
        check("runs still add up to the career (408)", total_runs == 408, str(total_runs))

        print("\n— the same rule on the unscoped path —")
        unscoped = await rows_for(session, None)
        gu = by_label(unscoped)
        check("our own year split across two of our season rows draws ONE row",
              len(gu.get("Summer 2019/20", [])) == 1,
              f"got {len(gu.get('Summer 2019/20', []))}")
        if len(gu.get("Summer 2019/20", [])) == 1:
            r = gu["Summer 2019/20"][0]
            check("that row holds both halves (300 + 40 = 340)",
                  r["total_runs"] == 340, str(r["total_runs"]))
            check("and both halves' matches (8 + 2 = 10)",
                  r["matches"] == 10, str(r["matches"]))
        check("unscoped path draws no duplicate season label at all",
              all(len(v) == 1 for v in gu.values()),
              str({k: len(v) for k, v in gu.items()}))

        print("\n— a historical bundle is still lifted out, not folded in —")
        check("the 256-match bundle draws no dated season row",
              not gu.get("Summer 1999/00"),
              str(len(gu.get("Summer 1999/00", []))))
        prior = gu.get("Prior Seasons & Adjustments", [])
        check("it lands in Prior Seasons & Adjustments instead", len(prior) == 1)
        if prior:
            check("carrying its own figures, whole (4000 runs)",
                  prior[0]["total_runs"] == 4000, str(prior[0]["total_runs"]))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
