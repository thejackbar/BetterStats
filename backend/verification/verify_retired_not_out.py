"""Verification for "retired - not out" counting as a not out, not a wicket.

Reported by a club off Lily Thompson's 2025/26: our own profile header and
PlayCricket both read an average of 15.40, while StatLab with a grade picked
read 12.83 for the same 77 runs from the same 8 innings. One innings' worth of
difference, and it was her Retired Not Out on 9 January.

`sync.py` set ``not_out = (dismissalTypeId == 1)``, so every retirement landed
in the database flagged as a wicket and went into the average's denominator.
CA's own season aggregate has always counted it as a not out, and MCC Law
25.4.2 says the same, so the aggregate path was right and the scorecard path
was wrong.

CA's ids, enumerated live from 260 real scorecards and reconciled against CA's
own aggregates: 1 Not Out, 8 Retired Hurt, 14 Retired Not Out are not outs;
13 "Retired" is Law 25.4.3's retired-out, a genuine wicket that CA counts as a
dismissal and as a duck. The suite pins BOTH directions, because a fix written
as ``LIKE 'retired%'`` would pass every check about 14 while quietly handing
every retired-out batter an average they have not earned.

Runs the SHIPPED aggregation, StatLab, records and backfill code over the
effective views pulled straight out of the migrations that define them.

Run:  DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/bstest \
      python verification/verify_retired_not_out.py
"""
from __future__ import annotations

import asyncio
import os
import re
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
from app.services import grade_scope

try:
    from app.services import dismissal
except Exception:  # pragma: no cover - control run against an older commit
    dismissal = None

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


class guard:
    """Report a section that cannot run at all rather than killing the suite.

    A control run against the previous commit reaches a module that does not
    exist yet. Crashing there would hide every later check, and the count of
    what fails is the whole point of a control run.
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
              f"{exc_type.__name__}: {str(exc)[:200]}")
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
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
SEASON = uuid.uuid4()
GRADE = uuid.uuid4()          # SGCL - Metro U18, the grade the customer filtered to
GRADE_JUNIOR = uuid.uuid4()   # present only so an explicit senior scope is ACTIVE
LILY = uuid.uuid4()           # the reported player
RETIRED_OUT = uuid.uuid4()    # Law 25.4.3 - still a dismissal, still a duck
HURT = uuid.uuid4()           # retired hurt
THEIRS = uuid.uuid4()         # another club, for the backfill's scoping

def writer_flag(dismissal_type: str) -> bool:
    """The flag the app's own writer decides for this dismissal.

    Seeding through the code under test is what lets the read checks below
    FAIL in a control run: with `services/dismissal.py` absent we fall back to
    the rule the old sync applied (``dismissalTypeId == 1``, i.e. a plain not
    out and nothing else), so the fixture is stored exactly as a club's real
    database holds it today and the reported 12.83 comes back out.
    """
    if dismissal is None:
        return dismissal_type == "not out"
    return dismissal.is_not_out(dismissal_type=dismissal_type)


# Lily's real card, in order. (runs, dismissal_type, what the OLD sync stored)
LILY_CARD = [
    (21, "b", False),
    (1, "run out", False),
    (15, "b", False),
    (15, "not out", True),
    (0, "b", False),
    (1, "b", False),
    (15, "retired not out", False),   # <- the innings the whole report is about
    (9, "not out", True),
]
LILY_RUNS = sum(r for r, _, _ in LILY_CARD)          # 77
LILY_INNINGS = len(LILY_CARD)                        # 8
CA_AVERAGE = round(LILY_RUNS / (LILY_INNINGS - 3), 2)   # 15.4  - CA and the Law
OLD_AVERAGE = round(LILY_RUNS / (LILY_INNINGS - 2), 2)  # 12.83 - what we reported


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for name, ddl in (
            ("season_aliases", """
                CREATE TABLE IF NOT EXISTS season_aliases (
                    id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                    org_id UUID NOT NULL,
                    canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                    alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                    undone_at TIMESTAMPTZ)"""),
            ("grade_merge_logs", """
                CREATE TABLE IF NOT EXISTS grade_merge_logs (
                    id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                    org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                    alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""),
            ("org_merge_logs", """
                CREATE TABLE IF NOT EXISTS org_merge_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    source_org_id UUID, source_org_name TEXT NOT NULL,
                    target_org_id UUID NOT NULL,
                    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    undone_at TIMESTAMPTZ)"""),
        ):
            await conn.execute(text(ddl))
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

    await ex("INSERT INTO organisations (id, name, slug, is_active) "
             "VALUES (:i, 'Payneham Cricket Club', 'payneham', true)", i=ORG)
    await ex("INSERT INTO organisations (id, name, slug, is_active) "
             "VALUES (:i, 'Another Club', 'another', true)", i=OTHER_ORG)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, 'SGCL - Metro U18', 'senior')", i=GRADE, s=SEASON)
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, 'NEJCA - U/12', 'junior')", i=GRADE_JUNIOR, s=SEASON)
    for pid, org, nm in ((LILY, ORG, "Thompson, Lily"),
                         (RETIRED_OUT, ORG, "Raux, Nans"),
                         (HURT, ORG, "Shedden, T"),
                         (THEIRS, OTHER_ORG, "Someone, Else")):
        await ex("INSERT INTO players (id, organisation_id, name) VALUES (:i, :o, :n)",
                 i=pid, o=org, n=nm)

    async def game(d, grade=GRADE, venue="Payneham Oval"):
        g = uuid.uuid4()
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format, "
                 "home_team, away_team, home_org_id, opp_club_name) "
                 "VALUES (:i, :g, :d, :v, 'WIN', 'One Day', "
                 "'Payneham Cricket Club', 'Rivals', :o, 'Rivals')",
                 i=g, g=grade, d=d, v=venue, o=ORG)
        return g

    async def bat(g, pid, runs, dt, _old_flag=None, pos=3):
        not_out = writer_flag(dt)
        await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, "
                 "dismissal_type, innings_number, batting_position, did_not_bat) "
                 "VALUES (:g, :p, :r, 20, :n, :d, 1, :pos, false)",
                 g=g, p=pid, r=runs, n=not_out, d=dt, pos=pos)
        await ex("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)",
                 g=g, p=pid)

    # ── the reported card, stored the way the old sync stored it ─────────────
    for n, (runs, dt, no) in enumerate(LILY_CARD):
        g = await game(date(2025, 10, 17 + n))
        await bat(g, LILY, runs, dt, no)

    # ── Law 25.4.3: retired-OUT. A dismissal, and a duck. ────────────────────
    g = await game(date(2025, 10, 18))
    await bat(g, RETIRED_OUT, 0, "retired", False)
    g = await game(date(2025, 11, 29))
    await bat(g, RETIRED_OUT, 3, "not out", True)

    # ── retired hurt, at a second venue so by-venue has something to say ─────
    g = await game(date(2026, 2, 4), venue="Away Reserve")
    await bat(g, HURT, 3, "retired hurt", False)
    g = await game(date(2026, 2, 11), venue="Away Reserve")
    await bat(g, HURT, 20, "c Smith b Jones", False)

    # ── another club's retirement, untouched by a club-scoped backfill ───────
    s2 = uuid.uuid4()
    gr2 = uuid.uuid4()
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=s2, o=OTHER_ORG)
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, 'A Grade', 'senior')", i=gr2, s=s2)
    g2 = uuid.uuid4()
    await ex("INSERT INTO games (id, grade_id, played_at, venue, result, match_format) "
             "VALUES (:i, :g, :d, 'Elsewhere', 'WIN', 'One Day')",
             i=g2, g=gr2, d=date(2025, 11, 1))
    await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, not_out, "
             "dismissal_type, innings_number, batting_position, did_not_bat) "
             "VALUES (:g, :p, 40, 30, :n, 'retired not out', 1, 3, false)",
             g=g2, p=THEIRS, n=writer_flag("retired not out"))
    await session.commit()


# ── the rule itself ──────────────────────────────────────────────────────────
async def section_rule(session) -> None:
    print("\nThe rule: which innings are not outs")
    async with guard(session, "rule"):
        if dismissal is None:
            raise RuntimeError("app.services.dismissal is missing")
        cases = [
            (1, "Not Out", True, "a plain not out"),
            (14, "Retired Not Out", True, "Law 25.4.2 retired - not out"),
            (8, "Retired Hurt", True, "retired hurt"),
            (13, "Retired", False, "Law 25.4.3 retired - out is a dismissal"),
            (2, "Caught", False, "caught"),
            (4, "Bowled", False, "bowled"),
            (6, "Run Out", False, "run out"),
        ]
        for dt_id, name, want, label in cases:
            check(f"by CA id and name: {label}",
                  dismissal.is_not_out(dt_id, name) is want)
        for name, want, label in (
            ("retired not out", True, "retired not out"),
            ("Retired  Not  Out", True, "odd spacing and case"),
            ("retired hurt", True, "retired hurt"),
            ("retired", False, "a bare retired"),
            ("retired out", False, "retired out spelled in full"),
            ("not out", True, "not out"),
            ("b Jones", False, "a bowled dismissal"),
            (None, False, "no dismissal recorded"),
            ("", False, "an empty dismissal"),
        ):
            check(f"by name alone: {label}",
                  dismissal.is_not_out(dismissal_type=name) is want)


async def section_sql_matches_python(session) -> None:
    print("\nThe SQL and the Python agree, row by row")
    async with guard(session, "sql/python"):
        rows = (await session.execute(text(
            f"SELECT dismissal_type, {dismissal.not_out_sql('dismissal_type')} AS sql_says "
            "FROM batting_innings WHERE dismissal_type IS NOT NULL"))).all()
        check("there are rows to compare", len(rows) > 0, f"got {len(rows)}")
        disagreed = [r[0] for r in rows if bool(r[1]) is not dismissal.is_not_out(dismissal_type=r[0])]
        check("every stored dismissal classifies the same both ways",
              not disagreed, f"disagreed on {disagreed}")


# ── the reported case ────────────────────────────────────────────────────────
async def section_reported(session) -> None:
    print("\nThe reported case: Lily Thompson, 77 runs from 8 innings")
    async with guard(session, "reported case"):
        scope = await grade_scope.resolve_scope(session, ORG, categories="senior")
        check("an explicit grade-type filter is an ACTIVE scope, so the "
              "per-innings path is what answers", scope.active)

        row = await agg.get_career_batting(session, str(LILY), scope=scope)
        inn = await agg.get_career_batting_from_innings(session, str(LILY), scope=scope)
        check("the filtered career reads 8 innings", row and row["innings"] == LILY_INNINGS,
              f"got {row and row.get('innings')}")
        check("the filtered career reads 77 runs", row and row["total_runs"] == LILY_RUNS,
              f"got {row and row.get('total_runs')}")
        check("the retirement counts as a not out, so 3 not outs",
              inn and inn["not_outs"] == 3, f"got {inn and inn.get('not_outs')}")
        check(f"the filtered average is {CA_AVERAGE}, matching CA and PlayCricket",
              row and float(row["average"]) == CA_AVERAGE,
              f"got {row and row.get('average')} (the reported bug reads {OLD_AVERAGE})")
        check("and it is NOT the figure the customer was shown",
              row and float(row["average"]) != OLD_AVERAGE,
              f"still reading the reported {OLD_AVERAGE}")

        check("her 0 was a bowled duck, so one duck stands",
              row and row["ducks"] == 1, f"got {row and row.get('ducks')}")


async def section_one_formula(session) -> None:
    print("\nOne formula: every surface agrees on her average")
    async with guard(session, "one formula"):
        scope = await grade_scope.resolve_scope(session, ORG, categories="senior")

        by_opp = await agg.get_player_by_opposition(session, str(LILY), scope=scope)
        opp = next((r for r in by_opp if (r.get("innings") or 0) > 0), None)
        check("by-opposition reports the same average",
              opp and float(opp["batting_average"]) == CA_AVERAGE,
              f"got {opp and opp.get('batting_average')}")

        by_venue = await agg.get_player_by_venue(session, str(LILY), scope=scope)
        ven = next((r for r in by_venue if (r.get("innings") or 0) > 0), None)
        check("by-venue reports the same average",
              ven and float(ven["batting_average"]) == CA_AVERAGE,
              f"got {ven and ven.get('batting_average')}")

        by_grade = await agg.get_batting_by_grade(session, str(LILY), scope=scope)
        gr = next((r for r in by_grade if (r.get("innings") or 0) > 0), None)
        check("by-grade reports the same average",
              gr and float(gr["average"]) == CA_AVERAGE,
              f"got {gr and gr.get('average')}")

        from app.services import competition_stats, iq, iq_selection

        comp = await competition_stats.player_competition_breakdown(session, str(LILY), ORG)
        crow = next((r for r in comp["rows"] if (r["batting"] or {}).get("innings")), None)
        check("the competitions panel reports the same average",
              crow and float(crow["batting"]["average"]) == CA_AVERAGE,
              f"got {crow and (crow.get('batting') or {}).get('average')}")
        check("and counts 3 not outs",
              crow and crow["batting"]["not_outs"] == 3,
              f"got {crow and (crow.get('batting') or {}).get('not_outs')}")

        perf = await iq._our_performers_vs(session, str(ORG), "Rivals")
        me = next((r for r in perf["batting"] if str(r["player_id"]) == str(LILY)), None)
        check("BetterIQ's record-against-this-opponent reports the same average",
              me and float(me["average"]) == CA_AVERAGE, f"got {me and me.get('average')}")

        vs = await iq_selection._vs_opponent(session, str(ORG), "Rivals")
        mine = (vs.get(str(LILY)) or {}).get("bat") or {}
        check("the selection board's form average agrees too",
              mine.get("avg") == round(CA_AVERAGE, 1), f"got {mine.get('avg')}")

        board = await agg.get_batting_leaderboard_extended(
            session, str(ORG), season_id=str(SEASON), limit=50, scope=scope)
        rows = board["rows"] if isinstance(board, dict) else board
        me = next((r for r in rows if str(r.get("player_id")) == str(LILY)), None)
        check("the leaderboard reports the same average",
              me and float(me["average"]) == CA_AVERAGE,
              f"got {me and me.get('average')}")


async def section_retired_out(session) -> None:
    print("\nLaw 25.4.3: a retired-OUT is still a wicket")
    async with guard(session, "retired out"):
        scope = await grade_scope.resolve_scope(session, ORG, categories="senior")
        row = await agg.get_career_batting(session, str(RETIRED_OUT), scope=scope)
        inn = await agg.get_career_batting_from_innings(session, str(RETIRED_OUT), scope=scope)
        check("2 innings", row and row["innings"] == 2, f"got {row and row.get('innings')}")
        check("only the genuine not out counts as one",
              inn and inn["not_outs"] == 1, f"got {inn and inn.get('not_outs')}")
        check("the retirement counts against the average: 3 runs / 1 dismissal = 3.0",
              row and float(row["average"]) == 3.0, f"got {row and row.get('average')}")
        check("and retiring for 0 is still a duck",
              row and row["ducks"] == 1, f"got {row and row.get('ducks')}")

        hurt = await agg.get_career_batting(session, str(HURT), scope=scope)
        hurt_inn = await agg.get_career_batting_from_innings(session, str(HURT), scope=scope)
        check("retired hurt, by contrast, is a not out",
              hurt_inn and hurt_inn["not_outs"] == 1, f"got {hurt_inn and hurt_inn.get('not_outs')}")
        check("so 23 runs from 2 innings averages 23.0, not 11.5",
              hurt and float(hurt["average"]) == 23.0, f"got {hurt and hurt.get('average')}")


async def section_breakdown(session) -> None:
    print("\nHow I get out: a retirement is not a way of getting out")
    async with guard(session, "dismissal breakdown"):
        rows = await agg.get_dismissal_breakdown(session, str(LILY))
        by_kind = {r["dismissal_type"]: r["count"] for r in rows}
        check("her retired not out is filed under 'not out', not as a dismissal",
              by_kind.get("not out") == 3, f"got {by_kind}")
        check("nothing of hers is filed as 'retired'",
              "retired" not in by_kind, f"got {by_kind}")

        rows = await agg.get_dismissal_breakdown(session, str(RETIRED_OUT))
        by_kind = {r["dismissal_type"]: r["count"] for r in rows}
        check("a retired-OUT is still listed as a dismissal",
              by_kind.get("retired") == 1, f"got {by_kind}")


async def section_statlab(session) -> None:
    print("\nStatLab reads the same figure as the profile")
    async with guard(session, "statlab"):
        from app.services import statlab

        ctx = {"season_id": str(SEASON), "grade_name": "SGCL - Metro U18"}
        rows = await statlab.query_player_season(
            session, org_id=str(ORG), sort_by="runs", sort_dir="desc", limit=50,
            metric_filters=None, filter_tree=None, context=ctx)
        me = next((r for r in rows if str(r.get("player_id")) == str(LILY)), None)
        check("StatLab lists her", me is not None)
        check(f"StatLab's player-season average is {CA_AVERAGE}",
              me and float(me["batting_average"]) == CA_AVERAGE,
              f"got {me and me.get('batting_average')} "
              f"(the customer's screenshot read {OLD_AVERAGE})")
        check("StatLab counts 3 not outs",
              me and me["not_outs"] == 3, f"got {me and me.get('not_outs')}")

        unusual = await statlab.derived_unusual_dismissals(
            session, org_id=str(ORG), limit=50, context={})
        kinds = {(r["dismissal_type"] or "").lower() for r in unusual}
        check("a retired-OUT is listed among the unusual dismissals",
              "retired" in kinds, f"got {kinds}")
        check("a retired NOT out is not, because it is not a dismissal",
              "retired not out" not in kinds, f"got {kinds}")
        check("neither is a retired hurt", "retired hurt" not in kinds, f"got {kinds}")


# ── the backfill ─────────────────────────────────────────────────────────────
async def _reset_flags(session) -> None:
    """Put every retirement back the way the OLD sync stored it, so the
    backfill has the damage it exists to repair."""
    await session.execute(text(
        "UPDATE batting_innings SET not_out = false "
        "WHERE LOWER(dismissal_type) IN ('retired not out', 'retired hurt')"))
    await session.commit()


async def backfill(session) -> int:
    from app.scripts import backfill_retired_not_out as bf
    n = 0
    for table in bf._TABLES:
        n += await bf._apply(session, table, None)
    await session.commit()
    return n


async def section_backfill(session) -> None:
    print("\nThe backfill repairs history already stored")
    async with guard(session, "backfill"):
        from app.scripts import backfill_retired_not_out as bf

        await _reset_flags(session)
        # The ORM caches the rows this raw UPDATE just changed.
        session.expire_all()

        counted = sum([await bf._count(session, t, None) for t in bf._TABLES])
        check("the dry run counts every retirement stored as a wicket",
              counted == 3, f"got {counted}")

        ours = await bf._count(session, "batting_innings", ORG)
        check("scoped to one club it counts only that club's", ours == 2, f"got {ours}")

        before = (await session.execute(text(
            "SELECT COUNT(*) FROM batting_innings WHERE not_out"))).scalar()
        written = await backfill(session)
        session.expire_all()
        after = (await session.execute(text(
            "SELECT COUNT(*) FROM batting_innings WHERE not_out"))).scalar()
        check("applying corrects exactly what it counted",
              written == counted and after - before == counted,
              f"wrote {written}, moved {after - before}")

        again = sum([await bf._count(session, t, None) for t in bf._TABLES])
        check("a second run finds nothing to do", again == 0, f"got {again}")

        still_out = (await session.execute(text(
            "SELECT not_out FROM batting_innings WHERE dismissal_type = 'retired'"))).scalar()
        check("a retired-OUT is never touched", still_out is False, f"got {still_out}")

        bowled = (await session.execute(text(
            "SELECT COUNT(*) FROM batting_innings WHERE dismissal_type = 'b' AND not_out"))).scalar()
        check("no ordinary dismissal is touched", bowled == 0, f"got {bowled}")


async def section_backfill_scoping(session) -> None:
    print("\nThe backfill respects club scoping")
    async with guard(session, "backfill scoping"):
        from app.scripts import backfill_retired_not_out as bf

        await _reset_flags(session)
        session.expire_all()
        await bf._apply(session, "batting_innings", ORG)
        await session.commit()
        session.expire_all()

        theirs = (await session.execute(text(
            "SELECT not_out FROM batting_innings WHERE player_id = :p"), {"p": THEIRS})).scalar()
        check("another club's retirement is left for their own run",
              theirs is False, f"got {theirs}")
        mine = (await session.execute(text(
            "SELECT COUNT(*) FROM batting_innings bi JOIN players p ON p.id = bi.player_id "
            "WHERE p.organisation_id = :o AND bi.not_out "
            "AND LOWER(bi.dismissal_type) LIKE 'retired%'"), {"o": ORG})).scalar()
        check("ours are corrected", mine == 2, f"got {mine}")
        await backfill(session)   # leave the fixture correct for later sections
        session.expire_all()


# ── the writers ──────────────────────────────────────────────────────────────
async def section_writers(session) -> None:
    print("\nEvery writer stores the flag the same way")
    async with guard(session, "writers"):
        from app.routers.manual_entries import ManualBattingIn

        pid = str(uuid.uuid4())
        for dt, want, label in (
            ("retired not out", True, "a hand-typed retired not out"),
            ("retired hurt", True, "a hand-typed retired hurt"),
            ("not out", True, "a plain not out"),
            ("retired", False, "a retired-out"),
            ("b Jones", False, "a bowled dismissal"),
        ):
            row = ManualBattingIn(player_id=pid, runs=10, dismissal_type=dt, not_out=False)
            check(f"the manual writer raises the flag for {label}: {want}",
                  row.not_out is want, f"got {row.not_out}")

        row = ManualBattingIn(player_id=pid, runs=10, dismissal_type=None, not_out=True)
        check("a card that says not out with no dismissal text keeps its flag",
              row.not_out is True)

        src = (Path(__file__).resolve().parent.parent / "app/services/sync.py").read_text()
        check("the sync no longer decides this with `dt_id == 1`",
              "not_out = dt_id == 1" not in src)
        check("the sync routes through the shared rule",
              "dismissal.is_not_out(dt_id, dt_long)" in src)

        games_src = (Path(__file__).resolve().parent.parent / "app/routers/games.py").read_text()
        check("the live scorecard merge routes through it too, so the card's "
              "asterisk agrees with the average",
              games_src.count("dismissal.is_not_out(dt_id, dt_long)") == 2,
              f"found {games_src.count('dismissal.is_not_out(dt_id, dt_long)')}")

        ocr_src = (Path(__file__).resolve().parent.parent / "app/services/scorecard_ocr.py").read_text()
        check("the scorecard reader stops counting a retirement against the "
              "card's own fall of wickets",
              "dismissal.NOT_OUT_DISMISSAL_NAMES" in ocr_src)

        # One formula, asserted rather than claimed. The two averages that had
        # drifted both excluded an innings whose dismissal was never read, so a
        # denominator that still tests dismissal_type is the shape of the drift.
        root = Path(__file__).resolve().parent.parent
        # Matched on the ALIAS, so this covers the denominators an average is
        # divided by (dismissals / outs) and deliberately leaves the wicket
        # counters beside them alone (wkts_lost, our_wkts_lost, fantasy's out):
        # how many wickets a side lost is a different question from how many
        # times a batter was dismissed, and nobody asked for those to move.
        denom = re.compile(
            r"NOT (\w+)\.not_out AND \1\.dismissal_type IS NOT NULL[\s\S]{0,60}?AS (dismissals|outs)\b")
        offenders = []
        for f in sorted((root / "app").rglob("*.py")):
            if "/afl/" in str(f):
                continue
            for m in denom.finditer(f.read_text()):
                offenders.append(f"{f.name}: AS {m.group(2)}")
        check("every batting average divides by innings - not outs, with no "
              "extra filter of its own", not offenders, f"found {offenders}")

        js = (Path(__file__).resolve().parent.parent.parent
              / "frontend/src/lib/dismissal.js").read_text()
        names = set(re.findall(r"'([a-z ]+)'", js.split("NOT_OUT_DISMISSALS")[1].split("]")[0]))
        check("the browser's copy of the rule names the same three innings",
              names == set(dismissal.NOT_OUT_DISMISSAL_NAMES), f"got {names}")


async def main() -> None:
    await build_schema()
    async with Session() as session:
        await seed(session)
        await section_rule(session)
        await section_sql_matches_python(session)
        await section_reported(session)
        await section_one_formula(session)
        await section_retired_out(session)
        await section_breakdown(session)
        await section_statlab(session)
        await section_backfill(session)
        await section_backfill_scoping(session)
        await section_writers(session)
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed:")
        for f in FAILURES:
            print(f"  - {f}")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
