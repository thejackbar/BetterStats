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
from app.routers.players import get_player_captain_stats
from app.services import aggregations as agg
from app.services.player_formats import player_format_splits
from app.services.aggregations import (
    get_career_batting_from_innings, get_player_team_breakdown,
    get_season_by_season, _scoped_games_played,
)

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
S_OURS_25 = uuid.uuid4(); S_OURS_25B = uuid.uuid4(); S_THEIRS_25 = uuid.uuid4()
S_OURS_22 = uuid.uuid4(); S_THEIRS_22 = uuid.uuid4(); S_THIRD_22 = uuid.uuid4()
# A year only another club holds a row for — nothing to fold onto.
S_THEIRS_10 = uuid.uuid4()
G_SHARED = uuid.uuid4()   # their grade row, our fixture
# Two of OUR OWN rows for one year — the split that reaches the unscoped path,
# which reads CA's season aggregates and so never sees another club's row.
S_OURS_19A = uuid.uuid4(); S_OURS_19B = uuid.uuid4()
# CA's pre-migration bundle: a whole career dumped on the earliest season.
S_OURS_99 = uuid.uuid4()

G_OURS_25 = uuid.uuid4(); G_OURS_25B = uuid.uuid4(); G_THEIRS_25 = uuid.uuid4()
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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY,
                merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL,
                undone_at TIMESTAMPTZ)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                undone_at TIMESTAMPTZ)
        """))
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
        (S_OURS_25B, OURS, "Summer 2025/26", 2025),
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
        (G_OURS_25B, S_OURS_25B, "Men's First Grade", "senior"),
        (G_THEIRS_25, S_THEIRS_25, "Men's First Grade", "senior"),
        (G_OURS_22, S_OURS_22, "Men's First Grade", "senior"),
        (G_THEIRS_22, S_THEIRS_22, "Men's First Grade", "senior"),
        (G_THIRD_22, S_THIRD_22, "Men's First Grade", "senior"),
        (G_JUNIOR, S_OURS_25, "Under 14s", "junior"),
        (G_THEIRS_10, S_THEIRS_10, "Men's First Grade", "senior"),
        (G_SHARED, S_THEIRS_22, "Men's First Grade", "senior"),
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
        (G_OURS_25, 3, 50), (G_OURS_25B, 1, 30), (G_THEIRS_25, 1, 24),
        (G_OURS_22, 2, 100), (G_THEIRS_22, 1, 15), (G_THIRD_22, 1, 12),
        (G_THEIRS_10, 1, 7),
    ]
    # One shared fixture, sitting on the OTHER club's grade row because they
    # synced it first, with our club as the home side.
    shared = uuid.uuid4()
    await ex(
        "INSERT INTO games "
        "(id, grade_id, played_at, venue, result, match_format, home_org_id) "
        "VALUES (:i, :g, :d, 'Gosnells Oval', 'WIN', 'One Day', :o)",
        i=shared, g=G_SHARED, d=date(2020, 1, 1), o=OURS)
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)",
             g=shared, p=PLAYER)
    await ex(
        "INSERT INTO batting_innings "
        "(game_id, player_id, runs, balls, not_out, fours, sixes, "
        " innings_number, batting_position) "
        "VALUES (:g, :p, 11, 40, false, 2, 0, 1, 3)", g=shared, p=PLAYER)

    n = 0
    for gid, count, runs in plan:
        for _ in range(count):
            n += 1
            g = uuid.uuid4()
            await ex(
                "INSERT INTO games "
                "(id, grade_id, played_at, venue, result, match_format) "
                "VALUES (:i, :g, :d, 'Gosnells Oval', 'WIN', 'One Day')",
                i=g, g=gid, d=date(2020, 1, 1))
            await ex(
                "INSERT INTO game_appearances (game_id, player_id) "
                "VALUES (:g, :p)", g=g, p=PLAYER)
            await ex(
                "INSERT INTO batting_innings "
                "(game_id, player_id, runs, balls, not_out, fours, sixes, "
                " innings_number, batting_position) "
                "VALUES (:g, :p, :r, 40, false, 2, 0, 1, 3)",
                g=g, p=PLAYER, r=runs)
    # CA's own per-grade aggregate (`player_season_grade_stats`), for OUR
    # club's grades only — which is what CA actually reports for this club.
    for gid, sid, m in (
        (G_OURS_25, S_OURS_25, 3), (G_OURS_25B, S_OURS_25B, 1),
        (G_OURS_22, S_OURS_22, 2),
    ):
        await ex(
            "INSERT INTO player_season_grade_stats "
            "(player_id, season_id, grade_id, matches) "
            "VALUES (:p, :s, :g, :m)", p=PLAYER, s=sid, g=gid, m=m)
    # And the other clubs' own rows for the same participant, which must not be
    # added on top of ours.
    for gid, sid, m in (
        (G_THEIRS_25, S_THEIRS_25, 1), (G_THEIRS_22, S_THEIRS_22, 1),
        (G_THIRD_22, S_THIRD_22, 1),
    ):
        await ex(
            "INSERT INTO player_season_grade_stats "
            "(player_id, season_id, grade_id, matches) "
            "VALUES (:p, :s, :g, :m)", p=PLAYER, s=sid, g=gid, m=m)

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


def grade_total(season_rows, label, grade):
    """Sum a grade's cells across EVERY row carrying this season label.

    Summing rather than reading one row is deliberate: with the seasons
    unfolded the label appears several times, and a check that reads whichever
    row lands last in a dict passes against exactly the bug under test.
    """
    return sum((r["grades"].get(grade) or 0)
               for r in season_rows if r["season_name"] == label)


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
            check("the folded 2025/26 row is filed under one of OUR OWN "
                  "season rows, never another club's",
                  str(r["season_id"]) in {str(S_OURS_25), str(S_OURS_25B)},
                  str(r["season_id"]))
            check("2025/26 folds BOTH our own rows for the year (3 + 1 = 4)",
                  r["batting_innings"] == 4, str(r["batting_innings"]))
            check("2025/26 runs are our own two rows (3x50 + 30 = 180), "
                  "with the other club's 24 left out",
                  r["total_runs"] == 180, str(r["total_runs"]))
        if len(g.get("Summer 2022/23", [])) == 1:
            r = g["Summer 2022/23"][0]
            check("2022/23 leaves the other clubs' 15 and 12 out",
                  r["total_runs"] == 211, str(r["total_runs"]))

        print("\n— a shared fixture the other club synced first is still ours —")
        check("2022/23 keeps the shared fixture (200 + 11 = 211)",
              (g.get("Summer 2022/23") or [{}])[0].get("total_runs") == 211,
              str((g.get("Summer 2022/23") or [{}])[0].get("total_runs")))

        print("\n— only the club's own matches are counted —")
        check("a season row belonging to another club is not drawn at all",
              not g.get("Summer 2010/11"),
              str(len(g.get("Summer 2010/11", []))))
        total_inn = sum((r.get("batting_innings") or 0) for r in scoped)
        total_runs = sum((r.get("total_runs") or 0) for r in scoped)
        check("innings are the club's own (4 + 3 = 7), not 11",
              total_inn == 7, str(total_inn))
        check("runs are the club's own (180 + 211 = 391), not 442",
              total_runs == 391, str(total_runs))

        print("\n— and the career header agrees with the table under it —")
        career = await get_career_batting_from_innings(
            session, str(PLAYER), scope=scope)
        check("career innings match the season table's",
              (career or {}).get("innings") == total_inn,
              f"career {(career or {}).get('innings')} vs table {total_inn}")
        check("career runs match the season table's",
              (career or {}).get("total_runs") == total_runs,
              f"career {(career or {}).get('total_runs')} vs table {total_runs}")
        played = await _scoped_games_played(session, str(PLAYER), None, scope)
        check("matches played is the club's own too (7)", played == 7, str(played))

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

        print("\n— the season x grade grid (get_player_team_breakdown) —")
        tb = await get_player_team_breakdown(session, str(PLAYER), str(OURS))
        srows = tb["season_rows"]
        labels = [r["season_name"] for r in srows]
        check("the grid draws 2025/26 once, not twice",
              labels.count("Summer 2025/26") == 1,
              str(labels.count("Summer 2025/26")))
        check("the grid draws 2022/23 once, not three times",
              labels.count("Summer 2022/23") == 1,
              str(labels.count("Summer 2022/23")))
        check("a year only another club has a row for is not drawn as ours",
              "Summer 2010/11" not in labels, str(labels))

        g25 = grade_total(srows, "Summer 2025/26", "Men's First Grade")
        g22 = grade_total(srows, "Summer 2022/23", "Men's First Grade")
        check("2025/26 reads CA's own figure for the club (4), not 4 + 1",
              g25 == 4, str(g25))
        check("2022/23 reads our own games (2 + the shared fixture), not 5",
              g22 == 3, str(g22))

        by_grade = {r["grade_name"]: r for r in tb["rows"]}
        first = by_grade.get("Men's First Grade", {})
        check("the grade's career total is our own games (4 + 3 = 7), not 10",
              first.get("matches") == 7, str(first.get("matches")))
        check("its scorecard count is the club's own games too (7)",
              first.get("scorecard_matches") == 7,
              str(first.get("scorecard_matches")))
        check("the grid's cells still add up to the grade rows",
              sum(sum(r["grades"].values()) for r in srows)
              == sum(r["matches"] for r in tb["rows"]))

        print("\n— a club's own correction reaches the grid (Manual Entries) —")
        await session.execute(text(
            "INSERT INTO manual_season_adjustments "
            "(organisation_id, player_id, season_id, grade_id, games_played) "
            "VALUES (:o, :p, :s, :g, -1)"),
            {"o": OURS, "p": PLAYER, "s": S_OURS_22, "g": G_OURS_22})
        await session.commit()
        tb2 = await get_player_team_breakdown(session, str(PLAYER), str(OURS))
        s2 = tb2["season_rows"]
        after22 = grade_total(s2, "Summer 2022/23", "Men's First Grade")
        check("a -1 correction takes a match off 2022/23 1st Grade",
              after22 == g22 - 1, f"was {g22}, now {after22}")
        by_grade2 = {r["grade_name"]: r for r in tb2["rows"]}
        check("and the grade's career total follows it (7 -> 6)",
              by_grade2.get("Men's First Grade", {}).get("matches") == 6,
              str(by_grade2.get("Men's First Grade", {}).get("matches")))
        check("the correction is not applied twice",
              sum(sum(r["grades"].values()) for r in tb2["season_rows"])
              == sum(r["matches"] for r in tb2["rows"]))
        after25 = grade_total(s2, "Summer 2025/26", "Men's First Grade")
        check("2025/26 is untouched by a 2022/23 correction",
              after25 == g25, f"was {g25}, now {after25}")

        print("\n— every per-game player read runs, and counts ours only —")
        # Each of these interpolates the club clause into its own SQL, so a
        # broken template only shows up by executing it. Both with the club's
        # default scope and with none, since they compose differently.
        per_game = [
            "get_career_batting_from_innings", "get_career_bowling_from_spells",
            "get_career_fielding_from_stats", "get_player_batting_innings",
            "get_player_bowling_spells", "get_dismissal_breakdown",
            "get_bowling_dismissal_breakdown", "get_bowling_by_batter_position",
            "get_batting_by_position", "get_player_partnerships",
            "get_player_by_opposition", "get_player_by_venue",
        ]
        for fname in per_game:
            fn = getattr(agg, fname)
            for label, sc in (("scoped", scope), ("unscoped", None)):
                try:
                    await fn(session, str(PLAYER), scope=sc)
                    ok, why = True, ""
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    ok, why = False, f"{type(exc).__name__}: {exc}"[:150]
                check(f"{fname} ({label})", ok, why)

        for label, coro in (
            ("player_format_splits",
             player_format_splits(session, str(PLAYER))),
            ("get_player_captain_stats",
             get_player_captain_stats(str(PLAYER), db=session)),
        ):
            try:
                await coro
                ok, why = True, ""
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                ok, why = False, f"{type(exc).__name__}: {exc}"[:150]
            check(label, ok, why)

        fmts = await player_format_splits(session, str(PLAYER))
        fmt_matches = sum((row.get("matches") or 0)
                          for row in (fmts.get("formats") or []))
        check("the FORMATS page counts our 7 matches, not all 11",
              fmt_matches == 7, str(fmt_matches))

        innings = await agg.get_player_batting_innings(
            session, str(PLAYER), scope=scope)
        check("get_player_batting_innings returns our 7, not all 11",
              len(innings) == 7, str(len(innings)))
        venues = await agg.get_player_by_venue(session, str(PLAYER), scope=scope)
        vg = sum((v.get("games") or 0) for v in venues)
        check("by-venue counts our 7 games, not all 11", vg == 7, str(vg))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
