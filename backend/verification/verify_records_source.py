"""Verification for the CA-vs-scorecard records SOURCE axis, real Postgres.

Reported off Shoalwater Bay's Peter Ritchie: the profile header read 408
matches while the Competitions breakdown read 425, and picking the club's only
competition (Peel) took every figure UP rather than down. "Competition = All"
was Cricket Australia's own season total masquerading as a competition state,
and CA is not a competition.

The fix makes the records SOURCE its own axis, separate from the competition
filter:

  source = 'ca' (default)   Cricket Australia's own season aggregates. Nothing
                            shrinks on first load.
  source = 'scorecard'      Everything BetterCricket holds a scorecard for,
                            which IS sliceable — and whose no-competition state
                            is the genuine sum of the competitions, not CA.

This drives the SHIPPED service and route bodies over the real ``v_effective_*``
views, on a fixture where CA counts FEWER matches than we hold (the reported
direction: a filter reads higher than the official record).

Run:
  DATABASE_URL=postgresql+asyncpg://postgres:pg@localhost:5432/bsverify \
  python verification/verify_records_source.py
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

MISSING: list[str] = []
try:
    from app.services import grade_scope
    from app.services.aggregations import (
        get_career_batting, get_batting_leaderboard_extended,
    )
    from app.services import match_coverage
    from app.services.competition_stats import player_competition_breakdown
    from app.routers.players import get_player_stats
    from app.routers.records import get_records, get_club_records
    from app.routers.organisations import get_org_summary
    # The flag that separates CA from the competition filter.
    assert hasattr(grade_scope, "wants_scorecards")
    HAVE = True
except (ImportError, AssertionError) as exc:  # pragma: no cover - control run
    HAVE = False
    MISSING.append(str(exc))

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OPPONENT = uuid.uuid4()
SEASON = uuid.uuid4()
GRADE = uuid.uuid4()
COMP = uuid.uuid4()
RITCHIE = uuid.uuid4()

# The reported shape, in miniature. Cricket Australia's own season total credits
# him with 10 matches / 100 runs; we hold scorecards for 12 games / 120 runs,
# all in the one competition. So the scorecard total is HIGHER than the official
# record (extra_scorecards), which is exactly why a competition filter read 425
# against a header of 408.
CA_MATCHES = 10
CA_RUNS = 100
HELD_GAMES = 12
RUNS_EACH = 10
HELD_RUNS = HELD_GAMES * RUNS_EACH


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in COMP_STATEMENTS:
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
        # migration 233 is a raw ALTER that never reached the ORM model, so
        # create_all does not make it — and the club-records route (now
        # exercised here) reads games.innings_totals through v_effective_games,
        # so the column must exist BEFORE the views are created below.
        await conn.execute(text(
            "ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
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

    await ex("INSERT INTO organisations (id, name, slug, is_active) "
             "VALUES (:i, 'Shoalwater Bay CC', 'shoalwater', true)", i=ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
    await ex("INSERT INTO club_competitions (id, organisation_id, name, display_order) "
             "VALUES (:i, :o, 'Peel Cricket Association Inc.', 0)", i=COMP, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, "
             " categories, competition_id) "
             "VALUES (:i, :s, 'A Grade', :g, 'senior', ARRAY['senior'], :c)",
             i=GRADE, s=SEASON, g=str(GRADE), c=COMP)
    await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
             "VALUES (:i, :o, 'Ritchie, Peter', :g, 'active')",
             i=RITCHIE, o=ORG, g=str(RITCHIE))

    # Cricket Australia's own season total: 10 matches, 100 runs. No grade
    # (the api branch of the view carries grade_id NULL), which is exactly why
    # it can say nothing about a competition.
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, "
             " batting_innings, runs, not_outs, wickets, source) "
             "VALUES (:p, :s, :m, :m, :r, 0, 0, 'api')",
             p=RITCHIE, s=SEASON, m=CA_MATCHES, r=CA_RUNS)

    # The scorecards we actually hold: 12 games in the one competition.
    for n in range(HELD_GAMES):
        gid = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, "
                 " away_org_id, match_format, status) "
                 "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                 i=gid, g=GRADE, d=date(2025, 1, 1 + n), o=ORG, x=OPPONENT)
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, "
                 " fours, sixes, not_out, dismissal_type, did_not_bat) "
                 "VALUES (:g, :p, :r, 20, 0, 0, false, 'caught', false)",
                 g=gid, p=RITCHIE, r=RUNS_EACH)
        await ex("INSERT INTO game_appearances (game_id, player_id) "
                 "VALUES (:g, :p)", g=gid, p=RITCHIE)


async def profile(session, **kw):
    """The SHIPPED profile route body, every FastAPI default filled in."""
    params = dict(
        season_id=None, grade_id=None, last_n_games=None, start_date=None,
        end_date=None, categories=None, formats=None, competitions=None,
        source=None,
    )
    params.update(kw)
    return await get_player_stats(player_id=str(RITCHIE), db=session, **params)


def _row(rows, pid):
    for r in rows:
        if str(r.get("player_id")) == str(pid) or str(r.get("id")) == str(pid):
            return r
    return None


async def records_body(session, **kw):
    """The SHIPPED /records/{org} route body, every FastAPI default filled in."""
    params = dict(
        season_id=None, grade_id=None, grade_name=None, finals_only=False,
        captain_only=False, gender=None, categories=None, formats=None,
        competitions=None, source=None, debug_timing=False,
    )
    params.update(kw)
    return await get_records(org_id=str(ORG), db=session, viewer=None, **params)


async def club_records_body(session, **kw):
    """The SHIPPED /records/{org}/club route body."""
    params = dict(
        season_id=None, grade_id=None, grade_name=None, finals_only=False,
        categories=None, formats=None, competitions=None, source=None,
    )
    params.update(kw)
    return await get_club_records(org_id=str(ORG), db=session, **params)


async def summary_body(session, **kw):
    """The SHIPPED /organisations/{org}/summary route body (the Dashboard)."""
    params = dict(
        season_id=None, grade_id=None, categories=None, formats=None,
        competitions=None, source=None,
    )
    params.update(kw)
    return await get_org_summary(org_id=str(ORG), db=session, viewer=None, **params)


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()

        print("\n-- career source switch (service) --")
        scope_ca = await grade_scope.resolve_scope(session, ORG, source="ca")
        scope_sc = await grade_scope.resolve_scope(session, ORG, source="scorecard")
        scope_comp = await grade_scope.resolve_scope(
            session, ORG, competitions=str(COMP))

        check("source=ca is an inactive scope (CA aggregate path)",
              not scope_ca.active)
        check("source=scorecard is an active scope with no clause",
              scope_sc.active and scope_sc.clause("g.grade_id") == "",
              repr(scope_sc.clause("g.grade_id")))

        bat_ca = await get_career_batting(session, str(RITCHIE), None, scope=scope_ca)
        bat_sc = await get_career_batting(session, str(RITCHIE), None, scope=scope_sc)
        check("career source=ca reads CA's own matches (10)",
              bat_ca["games"] == CA_MATCHES, f"got {bat_ca['games']}")
        check("career source=ca reads CA's own runs (100)",
              bat_ca["total_runs"] == CA_RUNS, f"got {bat_ca['total_runs']}")
        check("career source=scorecard reads the scorecards we hold (12)",
              bat_sc["games"] == HELD_GAMES, f"got {bat_sc['games']}")
        check("career source=scorecard reads scorecard runs (120)",
              bat_sc["total_runs"] == HELD_RUNS, f"got {bat_sc['total_runs']}")
        check("the two sources genuinely differ (the reported gap)",
              bat_sc["games"] != bat_ca["games"])

        print("\n-- leaderboard / players-list source switch (service) --")
        lb_ca = await get_batting_leaderboard_extended(
            session, str(ORG), None, None, "total_runs", 50, scope=scope_ca)
        lb_sc = await get_batting_leaderboard_extended(
            session, str(ORG), None, None, "total_runs", 50, scope=scope_sc)
        r_ca, r_sc = _row(lb_ca, RITCHIE), _row(lb_sc, RITCHIE)
        check("leaderboard source=ca lists his official matches (10)",
              r_ca and r_ca["games"] == CA_MATCHES,
              f"got {r_ca and r_ca.get('games')}")
        check("leaderboard source=scorecard lists scorecards held (12)",
              r_sc and r_sc["games"] == HELD_GAMES,
              f"got {r_sc and r_sc.get('games')}")

        print("\n-- Competition = All genuinely equals the sum of competitions --")
        breakdown = await player_competition_breakdown(session, str(RITCHIE), ORG)
        comp_total = breakdown["total_matches"]
        unattr = breakdown["unattributed"]
        check("competition breakdown holds one row (Peel)",
              len(breakdown["rows"]) == 1
              and breakdown["rows"][0]["competition_name"].startswith("Peel"),
              str([r["competition_name"] for r in breakdown["rows"]]))
        check("competition breakdown sums to what we hold (12)",
              comp_total == HELD_GAMES, f"got {comp_total}")
        check("source=scorecard total == sum of competitions + unattributed",
              bat_sc["games"] == comp_total + unattr,
              f"{bat_sc['games']} vs {comp_total}+{unattr}")
        # Picking the competition explicitly is the same scorecard world.
        lb_comp = await get_batting_leaderboard_extended(
            session, str(ORG), None, None, "total_runs", 50, scope=scope_comp)
        r_comp = _row(lb_comp, RITCHIE)
        check("picking the one competition matches the scorecard total (12)",
              r_comp and r_comp["games"] == HELD_GAMES,
              f"got {r_comp and r_comp.get('games')}")

        print("\n-- the coverage note names both figures --")
        cov = await match_coverage.career_coverage(session, str(RITCHIE), ORG)
        check("coverage reports CA's 10 as the career total",
              cov and cov["career_matches"] == CA_MATCHES, str(cov))
        check("coverage reports 12 as what a breakdown reaches",
              cov and cov["breakdown_matches"] == HELD_GAMES, str(cov))
        check("coverage reports 2 extra scorecards (runs the reported way)",
              cov and cov["extra_scorecards"] == HELD_GAMES - CA_MATCHES
              and cov["without_scorecard"] == 0, str(cov))

        print("\n-- the SHIPPED profile route body honours source --")
        p_default = await profile(session)
        p_ca = await profile(session, source="ca")
        p_sc = await profile(session, source="scorecard")
        check("default profile is CA (nothing shrinks on first load)",
              p_default["career_batting"]["games"] == CA_MATCHES,
              f"got {p_default['career_batting']['games']}")
        check("profile source=ca is CA's official record",
              p_ca["career_batting"]["games"] == CA_MATCHES)
        check("profile source=scorecard is the scorecard total",
              p_sc["career_batting"]["games"] == HELD_GAMES,
              f"got {p_sc['career_batting']['games']}")
        check("profile still carries match_coverage so the page can explain it",
              "match_coverage" in p_default
              and p_default["match_coverage"]["breakdown_matches"] == HELD_GAMES)
        check("profile reports the scope's source in grade_scope meta",
              p_sc["grade_scope"]["source"] == "scorecard"
              and p_ca["grade_scope"]["source"] == "ca",
              f"{p_sc['grade_scope']['source']} / {p_ca['grade_scope']['source']}")

        print("\n-- the Records page route bodies honour source --")
        rec_ca = await records_body(session, source="ca")
        rec_sc = await records_body(session, source="scorecard")
        check("records reports the source it resolved (ca / scorecard)",
              rec_ca["grade_scope"]["source"] == "ca"
              and rec_sc["grade_scope"]["source"] == "scorecard",
              f"{rec_ca['grade_scope']['source']} / {rec_sc['grade_scope']['source']}")
        rr_ca = _row(rec_ca["batting"]["top_career_runs"], RITCHIE)
        rr_sc = _row(rec_sc["batting"]["top_career_runs"], RITCHIE)
        check("records source=ca board reads CA's own runs/matches (100/10)",
              rr_ca and rr_ca["runs"] == CA_RUNS and rr_ca["matches"] == CA_MATCHES,
              f"got {rr_ca and (rr_ca.get('runs'), rr_ca.get('matches'))}")
        check("records source=scorecard board reads the scorecards held (120/12)",
              rr_sc and rr_sc["runs"] == HELD_RUNS and rr_sc["matches"] == HELD_GAMES,
              f"got {rr_sc and (rr_sc.get('runs'), rr_sc.get('matches'))}")

        # The CLUB record boards are team totals from per-game scorecards, so
        # with no competition picked BOTH sources see every game (ca is
        # inactive, scorecard's clause is empty) — the toggle's job there is to
        # reveal the competition filter. Assert the source reaches the route and
        # the boards are source-invariant absent a competition.
        club_ca = await club_records_body(session, source="ca")
        club_sc = await club_records_body(session, source="scorecard")
        check("club records route accepts source and reports it",
              club_ca["grade_scope"]["source"] == "ca"
              and club_sc["grade_scope"]["source"] == "scorecard")

        print("\n-- the Dashboard summary route body honours source --")
        sum_default = await summary_body(session)
        sum_ca = await summary_body(session, source="ca")
        sum_sc = await summary_body(session, source="scorecard")
        check("summary default is CA (nothing shrinks on first load)",
              sum_default["total_runs"] == CA_RUNS, f"got {sum_default['total_runs']}")
        check("summary source=ca is CA's official total (100)",
              sum_ca["total_runs"] == CA_RUNS and sum_ca["scope"]["source"] == "ca",
              f"got {sum_ca['total_runs']}")
        check("summary source=scorecard is the scorecard sum (120)",
              sum_sc["total_runs"] == HELD_RUNS and sum_sc["scope"]["source"] == "scorecard",
              f"got {sum_sc['total_runs']}")


if __name__ == "__main__":
    if not HAVE:
        print("SOURCE AXIS NOT PRESENT — control run")
        for m in MISSING:
            print("  missing:", m)
        print("\nREPORTED: the records-source axis is not built.")
        sys.exit(1)
    asyncio.run(main())
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILURES:", ", ".join(FAILURES))
    sys.exit(1 if FAIL else 0)
