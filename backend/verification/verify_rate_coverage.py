"""Verification for strike rate and economy over partially-scored seasons.

Asked for as a RULE to set, not off a live report. A season scored partly on an
iPad and partly in a written book gives CA a runs total covering every innings
and a balls total covering only the ones somebody typed in, and the old
`SUM(runs) / SUM(balls)` divides one population by the other.

The 500 runs / 150 balls / 333.33 seeded below is a WORKED EXAMPLE chosen to
make the arithmetic obvious, not a case anybody hit. Nobody has measured how
far a real club's figures move; what was established before building this is
that the mechanism is real — every rate summed the two halves separately, and
`sync.py` wrote a missing ball count as a zero.

The rule under test: runs and balls must come from the SAME innings. Every rate
is worked out from the innings that carry a ball count, and the figure rides
with a (counted, of) pair so a screen can say which innings answered it.

Runs the SHIPPED aggregation, records, yearbook and player-formats functions —
never a re-implementation — over the effective views pulled straight out of the
migrations that define them.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bstest \
      python verification/verify_rate_coverage.py
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
from app.services import aggregations as agg
from app.services import rate_coverage as rc

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


class guard:
    """Report a section that cannot run at all, rather than killing the suite.

    A control run against the previous commit reaches functions that do not yet
    take these arguments and columns that do not yet exist. Crashing there would
    hide every later check, and the count of what fails is the whole point of a
    control run.
    """

    def __init__(self, session, label: str) -> None:
        self.session = session
        self.label = label

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc is None:
            return False
        check(f"{self.label}: the section runs at all", False,
              f"{exc_type.__name__}: {str(exc)[:160]}")
        # A swallowed database error leaves the transaction aborted, and every
        # later statement on this session then fails with something unrelated.
        # Same rule the app itself keeps around a best-effort read.
        await self.session.rollback()
        return True


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


ORG = uuid.uuid4()
SEASON = uuid.uuid4()      # the reported season: 10 innings, 3 with balls
SEASON_OLD = uuid.uuid4()  # a season with no scorecards at all (CA aggregate)
SEASON_IMP = uuid.uuid4()  # the same, arriving through BetterImport
GRADE = uuid.uuid4()
GRADE_OLD = uuid.uuid4()
GRADE_JUNIOR = uuid.uuid4()   # makes the club's default grade scope ACTIVE
BAT = uuid.uuid4()         # the reported player
BOWL = uuid.uuid4()        # the bowling twin
ZERO = uuid.uuid4()        # the awkward 0(0) cases
RECORD = uuid.uuid4()      # clears the record book's own floor


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active "
            "ON season_aliases(alias_season_id) WHERE undone_at IS NULL"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                undone_at TIMESTAMPTZ)"""))
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
                stumpings int)"""))
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

    await ex("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Our Club', true)", i=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 1998/99', 1998)", i=SEASON_OLD, o=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 1997/98', 1997)", i=SEASON_IMP, o=ORG)
    for gid, sid, nm, cat in (
        (GRADE, SEASON, "1st Grade", "senior"),
        (GRADE_OLD, SEASON_OLD, "1st Grade", "senior"),
        (GRADE_JUNIOR, SEASON, "Under 14s", "junior"),
    ):
        await ex("INSERT INTO grades (id, season_id, name, category) "
                 "VALUES (:i, :s, :n, :c)", i=gid, s=sid, n=nm, c=cat)
    for pid, nm in ((BAT, "Partial, Ballcount"), (BOWL, "Partial, Overs"),
                (ZERO, "Flattened, Zero"), (RECORD, "Covered, Fully")):
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)",
                 i=pid, o=ORG, n=nm)

    async def game(grade=GRADE, d=date(2025, 11, 1)):
        g = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format) "
                 "VALUES (:i, :g, :d, 'Home Oval', 'WIN', 'One Day')", i=g, g=grade, d=d)
        return g

    # ── the reported case ────────────────────────────────────────────────────
    # 10 innings of 50. Three carry a ball count (50 off 50 -> a real SR of 100);
    # seven were scored in the book and carry none.
    for i in range(10):
        g = await game()
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=BAT)
        balls = 50 if i < 3 else None
        await ex("INSERT INTO batting_innings "
                 "(game_id, player_id, runs, balls, not_out, innings_number, batting_position) "
                 "VALUES (:g, :p, 50, :b, false, 1, 3)", g=g, p=BAT, b=balls)
    # CA's own season aggregate for him: every run, only the typed-in balls.
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 10, 10, 500, 0, 150, 50, 10, 0, 0, 0, 0)",
             p=BAT, s=SEASON)

    # ── the flattened-history case ───────────────────────────────────────────
    # sync used to write `balls = ballsFaced or 0`, so a missing count is a ZERO
    # in the database, not a NULL. A 40-run innings off "0 balls" is the source
    # dropping the count, and must not be read as covered.
    g = await game()
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=ZERO)
    await ex("INSERT INTO batting_innings "
             "(game_id, player_id, runs, balls, not_out, innings_number, batting_position) "
             "VALUES (:g, :p, 40, 0, false, 1, 3)", g=g, p=ZERO)
    # A genuine 0 off 0: run out backing up without facing. Consistent, so
    # covered, and it contributes nothing to either half.
    g = await game()
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=ZERO)
    await ex("INSERT INTO batting_innings "
             "(game_id, player_id, runs, balls, not_out, innings_number, batting_position) "
             "VALUES (:g, :p, 0, 0, false, 1, 3)", g=g, p=ZERO)
    # And one real innings so there is a rate to read at all.
    g = await game()
    await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=ZERO)
    await ex("INSERT INTO batting_innings "
             "(game_id, player_id, runs, balls, not_out, innings_number, batting_position) "
             "VALUES (:g, :p, 30, 60, false, 1, 3)", g=g, p=ZERO)
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 3, 3, 70, 0, 60, 40, 0, 0, 0, 0, 0)",
             p=ZERO, s=SEASON)

    # A season that clears the record book's own floors: 12 ball-counted
    # innings at 60 off 40 (SR 150), and 10 spells of 8 overs for 24 (econ 3.00).
    for _ in range(12):
        g = await game()
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=RECORD)
        await ex("INSERT INTO batting_innings "
                 "(game_id, player_id, runs, balls, not_out, innings_number, batting_position) "
                 "VALUES (:g, :p, 60, 40, false, 1, 3)", g=g, p=RECORD)
        await ex("INSERT INTO bowling_spells "
                 "(game_id, player_id, overs, maidens, runs, wickets, innings_number) "
                 "VALUES (:g, :p, 8.0, 0, 24, 2, 1)", g=g, p=RECORD)
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes, "
             " bowling_innings, wickets, overs, bowling_balls, runs_conceded, "
             " maidens, five_wicket_innings) "
             "VALUES (:p, :s, 12, 12, 720, 0, 480, 60, 12, 0, 0, 0, 0, "
             " 12, 24, 96.0, 576, 288, 0, 0)", p=RECORD, s=SEASON)

    # ── bowling ──────────────────────────────────────────────────────────────
    # Four spells. Two carry overs (10 overs, 30 runs each -> economy 3.00),
    # one has no overs recorded, one is the flattened 0-overs-with-runs case.
    for overs, runs, wkts in ((10.0, 30, 2), (10.0, 30, 2), (None, 40, 1), (0.0, 25, 1)):
        g = await game()
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)", g=g, p=BOWL)
        await ex("INSERT INTO bowling_spells "
                 "(game_id, player_id, overs, maidens, runs, wickets, innings_number) "
                 "VALUES (:g, :p, :o, 0, :r, :w, 1)", g=g, p=BOWL, o=overs, r=runs, w=wkts)
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, bowling_innings, wickets, overs, "
             " bowling_balls, runs_conceded, maidens, five_wicket_innings) "
             "VALUES (:p, :s, 4, 4, 6, 30.0, 180, 125, 0, 0)", p=BOWL, s=SEASON)

    # ── a season with no scorecards at all ───────────────────────────────────
    # Pure BetterImport history. Nothing to count innings against, so the
    # aggregate figure stands and says where it came from.
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 8, 8, 240, 1, 400, 66, 1, 0, 0, 0, 0)",
             p=BAT, s=SEASON_OLD)
    # A BetterImport season: aggregate-only, and unlike a CA 'api' row it is a
    # residual, so the SCOPED per-innings path draws it too.
    await ex("INSERT INTO import_effective_deltas "
             "(organisation_id, player_id, season_id, scope, matches, batting_innings, "
             " runs, not_outs, balls_faced, high_score, fifties, hundreds, ducks, "
             " fours, sixes, bowling_innings, wickets, overs, bowling_balls, "
             " runs_conceded, maidens, five_wicket_innings) "
             "VALUES (:o, :p, :s, 'season', 8, 8, 240, 1, 400, 66, 1, 0, 0, 0, 0, "
             " 0, 0, 0, 0, 0, 0, 0)", o=ORG, p=BAT, s=SEASON_IMP)
    await session.commit()


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)

        print("\n— the reported case: 500 runs, 150 balls, 3 of 10 innings —")
        car = await agg.get_career_batting(session, str(BAT), season_id=str(SEASON))
        check("total runs still reads every run scored (500)",
              car["total_runs"] == 500, str(car["total_runs"]))
        check("strike rate is 100, not 333.33",
              float(car["strike_rate"]) == 100.0, str(car["strike_rate"]))
        cov = car.get("strike_rate_coverage") or {}
        check("coverage says 3 of 10 innings",
              (cov.get("counted"), cov.get("of")) == (3, 10), str(cov))
        check("and reports itself as incomplete", cov.get("complete") is False, str(cov))
        check("worked out from the innings, not the season row",
              cov.get("basis") == "innings", str(cov))

        print("\n— a season we hold no scorecards for keeps its own figure —")
        old = await agg.get_career_batting(session, str(BAT), season_id=str(SEASON_OLD))
        check("the aggregate strike rate stands (240 off 400 = 60)",
              float(old["strike_rate"]) == 60.0, str(old["strike_rate"]))
        check("and says it came from the season totals",
              (old.get("strike_rate_coverage") or {}).get("basis") == "aggregate",
              str(old.get("strike_rate_coverage")))

        print("\n— a ball count of zero behind real runs is not a ball count —")
        z = await agg.get_career_batting(session, str(ZERO), season_id=str(SEASON))
        check("the 40 off '0 balls' is excluded, so 30 off 60 gives 50.00",
              float(z["strike_rate"]) == 50.0, str(z["strike_rate"]))
        zc = z.get("strike_rate_coverage") or {}
        check("a genuine 0 off 0 still counts as covered (2 of 3)",
              (zc.get("counted"), zc.get("of")) == (2, 3), str(zc))

        print("\n— bowling —")
        bw = await agg.get_career_bowling(session, str(BOWL), season_id=str(SEASON))
        check("economy is 3.00 from the two spells with overs",
              float(bw["economy"]) == 3.00, str(bw["economy"]))
        bc = bw.get("economy_coverage") or {}
        check("coverage says 2 of 4 spells",
              (bc.get("counted"), bc.get("of")) == (2, 4), str(bc))
        check("balls per wicket reads the same two spells (120/4 = 30)",
              float(bw["bowling_strike_rate"]) == 30.0, str(bw["bowling_strike_rate"]))
        check("wickets still counts every spell (6)",
              bw["total_wickets"] == 6, str(bw["total_wickets"]))

        async with guard(session, "grade scope"):
            print("\n— the same answer with a grade scope applied —")
            from app.services.grade_scope import resolve_scope
            scope = await resolve_scope(session, str(ORG))
            check("the club's default scope is active (it runs a junior grade)",
                  bool(getattr(scope, "active", False)), repr(scope))
            cars = await agg.get_career_batting(
                session, str(BAT), season_id=str(SEASON), scope=scope)
            check("the scoped path agrees: 100",
                  float(cars["strike_rate"]) == 100.0, str(cars["strike_rate"]))
            covs = cars.get("strike_rate_coverage") or {}
            check("and reports the same 3 of 10",
                  (covs.get("counted"), covs.get("of")) == (3, 10), str(covs))
            bws = await agg.get_career_bowling(
                session, str(BOWL), season_id=str(SEASON), scope=scope)
            check("scoped economy agrees: 3.00", float(bws["economy"]) == 3.00, str(bws["economy"]))

        async with guard(session, "season table"):
            print("\n— the season table says the same thing as the header —")
            for label, sc in (("unscoped", None), ("scoped", scope)):
                seasons = await agg.get_season_by_season(session, str(BAT), scope=sc)
                row = next((r for r in seasons if str(r.get("season_id")) == str(SEASON)), None)
                check(f"{label}: the 2025/26 row exists", bool(row), str([r.get("season_name") for r in seasons]))
                if not row:
                    continue
                check(f"{label}: its runs still read 500", row["total_runs"] == 500, str(row["total_runs"]))
                check(f"{label}: its strike rate reads 100, not 333.33",
                      float(row["strike_rate"]) == 100.0, str(row["strike_rate"]))
                cv = row.get("strike_rate_coverage") or {}
                check(f"{label}: its coverage says 3 of 10",
                      (cv.get("counted"), cv.get("of")) == (3, 10), str(cv))
                check(f"{label}: the season row agrees with the career header",
                      float(row["strike_rate"]) == float(car["strike_rate"]),
                      f'{row["strike_rate"]} vs {car["strike_rate"]}')
                # The scoped path is built from per-innings rows and deliberately
                # drops a CA-aggregate season with no scorecards (only a residual
                # source survives it), so each path is asked about the season it
                # actually draws.
                want = SEASON_IMP if sc is not None else SEASON_OLD
                oldrow = next((r for r in seasons if str(r.get("season_id")) == str(want)), None)
                check(f"{label}: the scorecard-less season keeps its aggregate rate (60)",
                      oldrow and float(oldrow["strike_rate"]) == 60.0,
                      str(oldrow and oldrow.get("strike_rate")))
                check(f"{label}: and reports an aggregate basis",
                      ((oldrow or {}).get("strike_rate_coverage") or {}).get("basis") == "aggregate",
                      str((oldrow or {}).get("strike_rate_coverage")))
                bowl_seasons = await agg.get_season_by_season(session, str(BOWL), scope=sc)
                brow = next((r for r in bowl_seasons if str(r.get("season_id")) == str(SEASON)), None)
                check(f"{label}: the season economy reads 3.00",
                      brow and float(brow["economy"]) == 3.00, str(brow and brow.get("economy")))
                bcv = (brow or {}).get("economy_coverage") or {}
                check(f"{label}: bowling coverage says 2 of 4",
                      (bcv.get("counted"), bcv.get("of")) == (2, 4), str(bcv))

        async with guard(session, "leaderboards"):
            print("\n— every leaderboard branch reads the same rate —")
            from app.services import stats_display
            boards = {
                "club default (season aggregates)": dict(),
                "a picked grade by name": dict(grade_name="1st Grade"),
                "a picked grade by id": dict(grade_id=str(GRADE)),
                "finals only": dict(finals_only=True),
                "with the club's grade scope": dict(scope=scope),
            }
            for label, kw in boards.items():
                rows = await agg.get_batting_leaderboard_extended(
                    session, str(ORG), season_id=str(SEASON), sort_by="strike_rate",
                    limit=50, **kw)
                me = next((r for r in rows if str(r["player_id"]) == str(BAT)), None)
                if label == "finals only":
                    # Nothing seeded is a final, so the board is empty by design —
                    # what is being proved here is that the branch RUNS.
                    check(f"{label}: the branch runs", isinstance(rows, list), str(rows)[:80])
                    continue
                check(f"{label}: the player is on the board", bool(me),
                      str([r.get("name") for r in rows]))
                if not me:
                    continue
                check(f"{label}: strike rate reads 100, not 333.33",
                      float(me["strike_rate"]) == 100.0, str(me["strike_rate"]))
                mc = me.get("strike_rate_coverage") or {}
                check(f"{label}: coverage rides with it",
                      mc.get("counted") == 3, str(mc))
                check(f"{label}: the board agrees with the player's own page",
                      float(me["strike_rate"]) == float(car["strike_rate"]),
                      f'{me["strike_rate"]} vs {car["strike_rate"]}')

            for label, kw in boards.items():
                rows = await agg.get_bowling_leaderboard_extended(
                    session, str(ORG), season_id=str(SEASON), sort_by="economy",
                    limit=50, **kw)
                me = next((r for r in rows if str(r["player_id"]) == str(BOWL)), None)
                if label == "finals only":
                    check(f"{label}: the bowling branch runs", isinstance(rows, list), str(rows)[:80])
                    continue
                check(f"{label}: the bowler is on the board", bool(me),
                      str([r.get("name") for r in rows]))
                if me:
                    check(f"{label}: economy reads 3.00", float(me["economy"]) == 3.00,
                          str(me["economy"]))
                    check(f"{label}: economy coverage rides with it",
                          (me.get("economy_coverage") or {}).get("counted") == 2,
                          str(me.get("economy_coverage")))

        async with guard(session, "rate minimums"):
            print("\n— the minimum counts covered innings, not innings played —")
            for label, kw in (("club default", dict()),
                              ("a picked grade", dict(grade_name="1st Grade")),
                              ("with the club's grade scope", dict(scope=scope))):
                rows = await agg.get_batting_leaderboard_extended(
                    session, str(ORG), season_id=str(SEASON), sort_by="strike_rate",
                    limit=50, min_rate_innings=3, **kw)
                check(f"{label}: 3 covered innings clears a bar of 3",
                      any(str(r["player_id"]) == str(BAT) for r in rows),
                      str([r.get("name") for r in rows]))
                rows = await agg.get_batting_leaderboard_extended(
                    session, str(ORG), season_id=str(SEASON), sort_by="strike_rate",
                    limit=50, min_rate_innings=4, **kw)
                check(f"{label}: and does NOT clear a bar of 4, though he played 10",
                      not any(str(r["player_id"]) == str(BAT) for r in rows),
                      str([r.get("name") for r in rows]))
                rows = await agg.get_batting_leaderboard_extended(
                    session, str(ORG), season_id=str(SEASON), sort_by="strike_rate",
                    limit=50, min_rate_innings=0, **kw)
                check(f"{label}: a bar of 0 filters nobody",
                      any(str(r["player_id"]) == str(BAT) for r in rows),
                      str([r.get("name") for r in rows]))
            brows = await agg.get_bowling_leaderboard_extended(
                session, str(ORG), season_id=str(SEASON), sort_by="economy",
                limit=50, min_rate_spells=3)
            check("bowling: 2 covered spells does not clear a bar of 3",
                  not any(str(r["player_id"]) == str(BOWL) for r in brows),
                  str([r.get("name") for r in brows]))

        async with guard(session, "club defaults"):
            print("\n— the club's own default, and a viewer overriding it —")
            mins = await stats_display.club_rate_minimums(session, str(ORG))
            check("a club that has set nothing qualifies nobody (0)",
                  mins == {"min_rate_innings": 0, "min_rate_spells": 0}, str(mins))
            await session.execute(text(
                "UPDATE organisations SET stats_min_rate_innings = 5 WHERE id = :o"), {"o": ORG})
            await session.commit()
            check("the club's own number is read back",
                  (await stats_display.club_rate_minimums(session, str(ORG)))["min_rate_innings"] == 5)
            check("omitting the param uses the club's number",
                  await stats_display.resolve_min_rate_innings(session, str(ORG), None) == 5)
            check("a viewer's explicit 0 beats it, rather than reading as absent",
                  await stats_display.resolve_min_rate_innings(session, str(ORG), 0) == 0)
            check("a viewer's explicit 12 beats it",
                  await stats_display.resolve_min_rate_innings(session, str(ORG), 12) == 12)
            check("junk stores as no qualification rather than refusing",
                  stats_display.clean_minimum("nonsense") == 0)
            check("a negative stores as no qualification",
                  stats_display.clean_minimum(-5) == 0)
            check("null means no club preference, not zero",
                  stats_display.clean_minimum(None) is None)
            await session.execute(text(
                "UPDATE organisations SET stats_min_rate_innings = NULL WHERE id = :o"), {"o": ORG})
            await session.commit()

        async with guard(session, "other surfaces"):
            print("\n— the FORMATS page, StatLab, the Yearbook and the record book —")
            from app.services.player_formats import player_format_splits
            from app.services import statlab
            from app.routers.yearbooks import get_batting_stats, get_bowling_stats
            from app.routers.records import get_records

            fmts = await player_format_splits(session, str(BAT))
            one_day = next((f for f in (fmts.get("formats") or [])
                            if f["format"] == "one_day"), None)
            check("formats: the one-day block exists", bool(one_day),
                  str([f.get("format") for f in (fmts.get("formats") or [])]))
            if one_day:
                check("formats: strike rate reads 100",
                      float(one_day["batting"]["strike_rate"]) == 100.0,
                      str(one_day["batting"]["strike_rate"]))
                check("formats: coverage says 3 of 10",
                      (one_day["batting"]["strike_rate_coverage"]["counted"],
                       one_day["batting"]["strike_rate_coverage"]["of"]) == (3, 10),
                      str(one_day["batting"]["strike_rate_coverage"]))
            bfmt = await player_format_splits(session, str(BOWL))
            bday = next((f for f in (bfmt.get("formats") or [])
                         if f["format"] == "one_day"), None)
            check("formats: economy reads 3.00",
                  bday and float(bday["bowling"]["economy"]) == 3.00,
                  str(bday and bday["bowling"]["economy"]))

            for target, key in (("player_career", "batting_strike_rate"),
                                ("player_season", "batting_strike_rate")):
                out = await statlab.run_query(
                    session, org_id=str(ORG), target=target, sort_by="runs",
                    sort_dir="desc", limit=50, metric_filters=None,
                    filter_tree=None, context={})
                row = next((r for r in out["rows"] if str(r["player_id"]) == str(BAT)), None)
                check(f"statlab {target}: the player is there", bool(row),
                      str([r.get("player_name") for r in out["rows"]]))
                if row:
                    check(f"statlab {target}: strike rate reads 100, not 333.33",
                          float(row[key]) == 100.0, str(row[key]))
            out = await statlab.run_query(
                session, org_id=str(ORG), target="player_career", sort_by="wickets",
                sort_dir="desc", limit=50, metric_filters=None, filter_tree=None,
                context={})
            brow = next((r for r in out["rows"] if str(r["player_id"]) == str(BOWL)), None)
            check("statlab player_career: economy reads 3.00",
                  brow and float(brow["bowling_economy"]) == 3.00,
                  str(brow and brow.get("bowling_economy")))
            # An active match-context filter takes StatLab's live per-innings path,
            # which is a different query family and has to agree with the fast one.
            out = await statlab.run_query(
                session, org_id=str(ORG), target="player_career", sort_by="runs",
                sort_dir="desc", limit=50, metric_filters=None, filter_tree=None,
                context={"result": "drawn"})
            row = next((r for r in out["rows"] if str(r["player_id"]) == str(BAT)), None)
            check("statlab live path: strike rate reads 100 too",
                  row and float(row["batting_strike_rate"]) == 100.0,
                  str(row and row.get("batting_strike_rate")))

            yb = await get_batting_stats(str(ORG), str(SEASON), grade_id=None,
                                         min_innings=1, limit=50, db=session)
            me = next((r for r in yb if str(r["player_id"]) == str(BAT)), None)
            check("yearbook batting: strike rate reads 100", 
                  me and float(me["strike_rate"]) == 100.0, str(me and me.get("strike_rate")))
            check("yearbook batting: coverage rides with it",
                  (me or {}).get("strike_rate_coverage", {}).get("counted") == 3,
                  str((me or {}).get("strike_rate_coverage")))
            ybb = await get_bowling_stats(str(ORG), str(SEASON), grade_id=None,
                                          min_wickets=1, limit=50, db=session)
            mb = next((r for r in ybb if str(r["player_id"]) == str(BOWL)), None)
            check("yearbook bowling: economy reads 3.00",
                  mb and float(mb["economy"]) == 3.00, str(mb and mb.get("economy")))

            recs = await get_records(
                str(ORG), season_id=None, grade_id=None, grade_name=None,
                finals_only=False, captain_only=False, gender=None,
                categories=None, formats=None, db=session, viewer=None)
            srs = (recs.get("batting") or {}).get("best_strike_rate_season") or []
            check("records: a season strike rate record exists", bool(srs), str(srs)[:120])
            top = srs[0] if srs else {}
            check("records: it reads 150 (60 off 40, twelve times)",
                  float(top.get("strike_rate") or 0) == 150.0, str(top))
            check("records: it says which innings answered it",
                  (top.get("strike_rate_coverage") or {}).get("counted") == 12, str(top))
            check("records: the 3-innings season does NOT make the book",
                  not any(str(r.get("player_id")) == str(BAT) for r in srs),
                  str([r.get("name") for r in srs]))
            check("records: it is filed against a season, never all time",
                  bool(top.get("season_name")), str(top))
            check("records: there is no all-time strike rate record",
                  not any("strike_rate" in k and "season" not in k
                          for k in (recs.get("batting") or {})),
                  str(list((recs.get("batting") or {}).keys())))
            econ = (recs.get("bowling") or {}).get("best_economy_season") or []
            check("records: a season economy record exists", bool(econ), str(econ)[:120])

        print("\n— the SQL and the Python agree on every seeded innings —")
        rows = (await session.execute(text(
            "SELECT runs, balls, " + rc.batting_covered_sql("bi") + " AS sql_covered "
            "FROM batting_innings bi"))).mappings().all()
        disagree = [r for r in rows
                    if bool(r["sql_covered"]) != rc.is_batting_covered(r["runs"], r["balls"])]
        check(f"batting: {len(rows)} innings classified identically", not disagree, str(disagree[:3]))
        brows = (await session.execute(text(
            "SELECT runs, overs, " + rc.bowling_covered_sql("bs") + " AS sql_covered "
            "FROM bowling_spells bs"))).mappings().all()
        bdis = [r for r in brows
                if bool(r["sql_covered"]) != rc.is_bowling_covered(r["runs"], r["overs"])]
        check(f"bowling: {len(brows)} spells classified identically", not bdis, str(bdis[:3]))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
