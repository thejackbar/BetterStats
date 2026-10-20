"""A season CA only gave us a summary for must not read as zero under the lens.

Reported at Applecross: Brad Ethell has 4 games, 4 innings, 35 runs and 2 catches
in 2005/06 on Cricket Australia (a 10th Grade season the club holds no
scorecards for). His profile read 0 on every figure, and the Players list showed
dashes. With "all grades" picked it read 4; with the club's default (juniors out)
it read 0.

The default grade-category lens switches the profile and the boards to
scorecards, because CA's season row has no grade to filter by. Import history
and hand-typed adjustments were kept (`_RESIDUAL_SOURCES`); CA's own season
total, for a season with no scorecards behind it, was not. Any club that only
has summary figures, or whose older seasons predate its scorecards, lost them.

Runs the SHIPPED `resolve_scope`, `_career_residuals`, `_season_by_season_scoped`
and `_residual_totals_cte` over the real `v_effective_*` views.

    createdb -h /tmp -p 5599 -U postgres verify_summary_only
    VERIFY_DATABASE_URL=postgresql+asyncpg://postgres@/verify_summary_only?host=/tmp\\&port=5599 \\
      python verification/verify_summary_only_seasons.py
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

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@/verify_summary_only?host=/tmp&port=5599",
)
os.environ["DATABASE_URL"] = DB_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from _view_ddl import view_statements  # noqa: E402
from app.models.db import Base  # noqa: E402
from app.services.grade_scope import resolve_scope  # noqa: E402
from app.services import aggregations as agg  # noqa: E402

engine = create_async_engine(DB_URL, echo=False)
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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG, OTHER = uuid.uuid4(), uuid.uuid4()
S05, S06 = uuid.uuid4(), uuid.uuid4()          # 2005/06 (no scorecards), 2006/07 (scorecards)
S05_OTHER = uuid.uuid4()
G_SEN05, G_JNR05 = uuid.uuid4(), uuid.uuid4()  # 2005/06 grades: 10th Grade, Under 12
G_SEN06 = uuid.uuid4()
BRAD, JUNIOR, MIXED, NOGRADE, COVERED, OTHER_P, BUNDLE = (uuid.uuid4() for _ in range(7))
GAME = uuid.uuid4()


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
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


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        # The club's default hides juniors: the everyday page-load state.
        await ex("INSERT INTO organisations (id, name, slug, is_active, stats_grade_categories) "
                 "VALUES (:i, 'Applecross', 'applecross-v', true, '[\"senior\"]'::jsonb)", i=ORG)
        await ex("INSERT INTO organisations (id, name, slug, is_active, stats_grade_categories) "
                 "VALUES (:i, 'Elsewhere', 'elsewhere-v', true, '[\"senior\"]'::jsonb)", i=OTHER)
        for sid, nm, yr, org in ((S05, "Summer 2005/06", 2005, ORG),
                                 (S06, "Summer 2006/07", 2006, ORG),
                                 (S05_OTHER, "Summer 2005/06", 2005, OTHER)):
            await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:i, :o, :n, :y)",
                     i=sid, o=org, n=nm, y=yr)
        for gid, sid, nm, cat in ((G_SEN05, S05, "10th Grade", "senior"),
                                  (G_JNR05, S05, "Under 12", "junior"),
                                  (G_SEN06, S06, "1st Grade", "senior")):
            await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
                     "VALUES (:i, :s, :n, :g, :c, ARRAY[:c])", i=gid, s=sid, n=nm, g=str(gid), c=cat)
        for pid, org in ((BRAD, ORG), (JUNIOR, ORG), (MIXED, ORG), (NOGRADE, ORG),
                         (COVERED, ORG), (OTHER_P, OTHER), (BUNDLE, ORG)):
            await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                     "VALUES (:i, :o, 'P', :g, 'active')", i=pid, o=org, g=str(pid))

        async def api(pid, sid, matches, innings, runs, catches=0, hs=None, fifties=0):
            await ex("INSERT INTO player_season_stats (player_id, season_id, matches, "
                     " batting_innings, runs, high_score, catches, fifties) "
                     "VALUES (:p, :s, :m, :i, :r, :h, :c, :f)",
                     p=pid, s=sid, m=matches, i=innings, r=runs, h=hs, c=catches, f=fifties)

        async def cell(pid, sid, gid, matches, innings, runs):
            await ex("INSERT INTO player_season_grade_stats (player_id, season_id, grade_id, "
                     " matches, batting_innings, runs) VALUES (:p, :s, :g, :m, :i, :r)",
                     p=pid, s=sid, g=gid, m=matches, i=innings, r=runs)

        # BRAD: the reported player. CA's 2005/06 total, one senior grade, no scorecards.
        await api(BRAD, S05, 4, 4, 35, catches=2, hs=25)
        await cell(BRAD, S05, G_SEN05, 4, 4, 35)
        # JUNIOR: the same shape but his only grade that year was Under 12.
        await api(JUNIOR, S05, 6, 6, 80)
        await cell(JUNIOR, S05, G_JNR05, 6, 6, 80)
        # MIXED: one season split across a senior and a junior grade.
        await api(MIXED, S05, 9, 9, 120)
        await cell(MIXED, S05, G_SEN05, 5, 5, 70)
        await cell(MIXED, S05, G_JNR05, 4, 4, 50)
        # NOGRADE: summary-only club shape, CA total and no per-grade rows at all.
        await api(NOGRADE, S05, 10, 10, 200, fifties=1)
        # COVERED: CA total for 2006/07 AND a scorecard the club holds that year.
        await api(COVERED, S06, 5, 5, 150)
        await ex("INSERT INTO games (id, grade_id, played_at, result, status) "
                 "VALUES (:g, :gr, :d, 'Won', 'COMPLETED')", g=GAME, gr=G_SEN06, d=date(2006, 11, 4))
        await ex("INSERT INTO batting_innings (game_id, player_id, innings_number, runs, balls, "
                 " not_out, did_not_bat) VALUES (:g, :p, 1, 100, 90, false, false)", g=GAME, p=COVERED)
        # BUNDLE: CA's pre-migration career dumped on one season (over 60 matches).
        await api(BUNDLE, S05, 256, 256, 4000)
        # OTHER_P: another club's player with the same shape: must read its own.
        await api(OTHER_P, S05_OTHER, 3, 3, 21)
        await s.commit()


async def career(s, pid, scope):
    r = await agg._career_residuals(s, str(pid), None, scope)
    return int(r.get("games") or 0), int(r.get("total_runs") or 0), int(r.get("total_catches") or 0)


async def season_matches(s, pid, scope):
    rows = await agg._season_by_season_scoped(s, str(pid), scope)
    return sum(int(r.get("matches") or 0) for r in rows)


async def board(s, org, pid, scope):
    params: dict = {"org_id": str(org)}
    try:
        params["club_player_ids"] = await agg._club_player_ids(s, org)
    except AttributeError:      # control run: the helper does not exist yet
        pass
    cte = agg._residual_totals_cte(scope, None, params)
    got = (await s.execute(text(
        f"WITH {cte} SELECT COALESCE(games, 0), COALESCE(total_runs, 0) FROM residual_totals "
        "WHERE player_id = CAST(:pid AS UUID)"), {**params, "pid": str(pid)})).first()
    return (int(got[0]), int(got[1])) if got else (0, 0)


async def main() -> int:
    await build_schema()
    await seed()
    async with Session() as s:
        default = await resolve_scope(s, str(ORG), categories=None)
        allc = await resolve_scope(s, str(ORG), categories="all")
        two_day = await resolve_scope(s, str(ORG), categories=None, formats="two_day")
        check("the club default is an active, junior-excluding scope",
              default.active and default.category_active)

        print("\n── the reported player: a senior season with no scorecards")
        check("Brad reads 4 games, 35 runs, 2 catches under the club default",
              await career(s, BRAD, default) == (4, 35, 2), str(await career(s, BRAD, default)))
        check("the season table reconciles with the header (4 matches)",
              await season_matches(s, BRAD, default) == 4, str(await season_matches(s, BRAD, default)))
        check("the leaderboard residual agrees (4 games, 35 runs)",
              await board(s, ORG, BRAD, default) == (4, 35), str(await board(s, ORG, BRAD, default)))

        print("\n── a club with only summary figures")
        check("a season with no per-grade rows at all is kept (10 games, 200 runs)",
              (await career(s, NOGRADE, default))[:2] == (10, 200), str(await career(s, NOGRADE, default)))

        print("\n── the filter still filters")
        check("a junior-only season stays out of the senior default",
              await career(s, JUNIOR, default) == (0, 0, 0), str(await career(s, JUNIOR, default)))
        check("and the board agrees", await board(s, ORG, JUNIOR, default) == (0, 0))
        check("a season split across a senior and a junior grade stays out (cannot be divided)",
              (await career(s, MIXED, default))[:2] == (0, 0), str(await career(s, MIXED, default)))
        check("a match type pick drops a season total (it has no format)",
              await career(s, BRAD, two_day) == (0, 0, 0), str(await career(s, BRAD, two_day)))
        check("picking all grades is unchanged (the unscoped path)",
              not allc.active)

        print("\n── never counted twice")
        got = await career(s, COVERED, default)
        check("a year the club holds a scorecard for adds nothing from CA's total",
              got == (0, 0, 0), f"{got}")
        scored = await agg.get_career_batting(s, str(COVERED), None, default)
        check("so his scoped career is the scorecard alone (1 game, 100 runs)",
              (scored["games"], scored["total_runs"]) == (1, 100), f"{scored['games']}/{scored['total_runs']}")

        print("\n── the Players page and the milestone scan read the same figure")
        rows = await agg.get_batting_leaderboard_extended(
            s, str(ORG), None, None, "total_runs", 5000, min_rate_innings=0, scope=default)
        row = next((r for r in rows if str(r["player_id"]) == str(BRAD)), None)
        check("Brad is on the batting board with 4 games and 35 runs",
              row is not None and (int(row["games"]), int(row["total_runs"])) == (4, 35), str(row))
        from app.services import milestone_totals
        mt = await milestone_totals.totals_under(s, ORG, [BRAD, COVERED], default)
        check("milestone totals match the profile (4 matches, 35 runs, 2 catches)",
              (mt[str(BRAD)]["matches"], mt[str(BRAD)]["runs"], mt[str(BRAD)]["catches"]) == (4, 35, 2),
              str(mt[str(BRAD)]))
        check("and a season with scorecards is still not counted twice there (1 match, 100 runs)",
              (mt[str(COVERED)]["matches"], mt[str(COVERED)]["runs"]) == (1, 100), str(mt[str(COVERED)]))

        print("\n── CA's pre-migration bundle is not a season")
        check("a 256-match bundle is not added back under the lens",
              await career(s, BUNDLE, default) == (0, 0, 0), str(await career(s, BUNDLE, default)))

        print("\n── another club")
        other = await resolve_scope(s, str(OTHER), categories=None)
        # It has no junior grade, so its scope is inactive and the profile reads
        # CA's season totals directly, exactly as it always did.
        ob = await agg.get_career_batting(s, str(OTHER_P), None, other)
        check("keeps its own player's summary (3 games, 21 runs), scope inactive",
              (not other.active) and (ob["games"], ob["total_runs"]) == (3, 21),
              f"{other.active} {ob['games']}/{ob['total_runs']}")
        check("and the first club's board never sees them",
              await board(s, ORG, OTHER_P, default) == (0, 0))

        print("\n── the finished profile figures")
        brad = await agg.get_career_batting(s, str(BRAD), None, default)
        check("career batting: 4 games, 4 innings, 35 runs, HS 25",
              (brad["games"], brad["innings"], brad["total_runs"], brad["high_score"]) == (4, 4, 35, 25),
              str({k: brad[k] for k in ("games", "innings", "total_runs", "high_score")}))
        field = await agg.get_career_fielding(s, str(BRAD), None, default)
        check("career fielding: 2 catches", field["total_catches"] == 2, str(field.get("total_catches")))

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILURES:", FAILURES)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
