"""Every stats surface answers a rate from the innings that can answer it.

v9.59.0 made the career header, the season table, the leaderboards, the
yearbook boards, the record book and the formats page work out a strike rate
from the innings that carry a ball count. Several surfaces were never brought
across and kept dividing every run by the balls somebody happened to type in —
reported off a live profile whose radar read a strike rate of 320.19 beside a
career the same page had already worked out correctly.

The surfaces this covers, all through the SHIPPED functions and route bodies:

  * the captain panel's economy (players.get_player_captain_stats)
  * the teammate split (iq_teammates.with_split)
  * the player deep dive's batting style (iq_trends.player_deep_dive)
  * the team analysis attack, discipline and collapse boards (iq_team)
  * the opposition dossier's danger players (iq_opponent)
  * StatLab's three family targets

The fixture is the same worked example the original suite uses, so the
arithmetic stays obvious: ten innings of 50, three of them ball-counted at 50
off 50. The honest strike rate is 100. Dividing 500 by 150 gives 333.33.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/bstest?host=/tmp \
      python verification/verify_rate_coverage_everywhere.py
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
from app.services import rate_coverage as rc

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


class guard:
    """Report a section that cannot run, rather than killing the suite.

    A control run against the previous commit reaches functions that do not yet
    return these keys. Crashing there would hide every later check, and the
    count of what fails is the whole point of a control run.
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
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


def near(a, b, tol=0.01) -> bool:
    return a is not None and abs(float(a) - float(b)) <= tol


ORG = uuid.uuid4()
SEASON = uuid.uuid4()
GRADE = uuid.uuid4()
BAT = uuid.uuid4()      # 10 innings of 50, three ball-counted. SR 100, not 333.33
MATE = uuid.uuid4()     # plays every game with BAT, so the split has both sides
BOWL = uuid.uuid4()     # spells with and without an overs figure
NOTATION = uuid.uuid4()  # two spells of 10.2 overs: 124 balls, not 20.4 "overs"
FAM = uuid.uuid4()

GAMES: list[uuid.UUID] = []


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
            ("import_effective_deltas", """
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
                    stumpings int)"""),
        ):
            await conn.execute(text(ddl))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_season_aliases_alias_active "
            "ON season_aliases(alias_season_id) WHERE undone_at IS NULL"))
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
    await ex("INSERT INTO grades (id, season_id, name, category) "
             "VALUES (:i, :s, '1st Grade', 'senior')", i=GRADE, s=SEASON)
    for pid, nm in ((BAT, "Partial, Ballcount"), (MATE, "Mate, Constant"),
                    (BOWL, "Partial, Overs"), (NOTATION, "Notation, Cricket")):
        await ex("INSERT INTO players (id, organisation_id, name, bowling_type) "
                 "VALUES (:i, :o, :n, 'FAST')", i=pid, o=ORG, n=nm)

    # Ten games. BAT and MATE play every one, so the teammate split has a real
    # "with" side and the captaincy panel has games to read.
    for i in range(10):
        g = uuid.uuid4()
        GAMES.append(g)
        await ex("INSERT INTO games (id, grade_id, played_at, venue, result, "
                 " match_format, home_team, away_team) "
                 "VALUES (:i, :g, :d, 'Home Oval', 'WIN', 'One Day', 'Our Club', 'Them')",
                 i=g, g=GRADE, d=date(2025, 11, 1 + i))
        for pid in (BAT, MATE, BOWL, NOTATION):
            await ex("INSERT INTO game_appearances (game_id, player_id, is_captain) "
                     "VALUES (:g, :p, :c)", g=g, p=pid, c=(pid == BOWL))
        # Three of ten carry a ball count: 50 off 50. The rest were scored in
        # the book, so `sync` wrote the missing count as a zero (the history
        # already stored) for two of them and a NULL for the rest.
        balls = 50 if i < 3 else (0 if i < 5 else None)
        await ex("INSERT INTO batting_innings "
                 "(game_id, player_id, runs, balls, fours, sixes, not_out, "
                 " innings_number, batting_position) "
                 "VALUES (:g, :p, 50, :b, 4, 1, false, 1, 3)", g=g, p=BAT, b=balls)
        await ex("INSERT INTO batting_innings "
                 "(game_id, player_id, runs, balls, fours, sixes, not_out, "
                 " innings_number, batting_position) "
                 "VALUES (:g, :p, 20, 40, 2, 0, false, 1, 4)", g=g, p=MATE)

    # BOWL captains every game. Two spells of 10 overs for 30 (economy 3.00),
    # one with no overs recorded and one flattened to 0 overs with runs on it.
    for i, (overs, runs, wkts) in enumerate(
            ((10.0, 30, 2), (10.0, 30, 2), (None, 40, 1), (0.0, 25, 1))):
        await ex("INSERT INTO bowling_spells "
                 "(game_id, player_id, overs, maidens, runs, wickets, innings_number) "
                 "VALUES (:g, :p, :o, 0, :r, :w, 1)",
                 g=GAMES[i], p=BOWL, o=overs, r=runs, w=wkts)

    # Cricket notation: 10.2 + 10.2 is 20 overs and 4 balls (124), not 20.4.
    # 62 runs off 124 balls is an economy of exactly 3.00.
    for i in range(2):
        await ex("INSERT INTO bowling_spells "
                 "(game_id, player_id, overs, maidens, runs, wickets, innings_number) "
                 "VALUES (:g, :p, 10.2, 0, 31, 1, 1)", g=GAMES[i], p=NOTATION)

    # CA's own season aggregates: every run, only the typed-in balls.
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 10, 10, 500, 0, 150, 50, 10, 0, 0, 40, 10)",
             p=BAT, s=SEASON)
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, batting_innings, runs, not_outs, "
             " balls_faced, high_score, fifties, hundreds, ducks, fours, sixes) "
             "VALUES (:p, :s, 10, 10, 200, 0, 400, 20, 0, 0, 0, 20, 0)",
             p=MATE, s=SEASON)
    await ex("INSERT INTO player_season_stats "
             "(player_id, season_id, matches, bowling_innings, wickets, overs, "
             " bowling_balls, runs_conceded, maidens, five_wicket_innings) "
             "VALUES (:p, :s, 4, 4, 6, 30.0, 180, 125, 0, 0)", p=BOWL, s=SEASON)

    # A family holding the partially-scored batter and the constant mate, so
    # StatLab's family targets have the same 500/150 problem to get right.
    await ex("INSERT INTO families (id, organisation_id, name) "
             "VALUES (:i, :o, 'The Ballcounts')", i=FAM, o=ORG)
    for pid in (BAT, MATE):
        # create_all doesn't carry the gen_random_uuid() server default some
        # raw-SQL migrations set, so the id is supplied here (same trap the
        # self-serve-trial note in CLAUDE.md documents).
        await ex("INSERT INTO family_members (id, family_id, player_id) "
                 "VALUES (:i, :f, :p)", i=uuid.uuid4(), f=FAM, p=pid)
    await session.commit()


async def main() -> None:
    await build_schema()
    async with Session() as s:
        await seed(s)

        # ── the captain panel ────────────────────────────────────────────────
        print("\n— the captain panel's economy —")
        async with guard(s, "captain"):
            from app.routers import players as players_router

            class _Club:
                id = ORG
            got = await players_router.get_player_captain_stats.__wrapped__(
                str(BOWL), None, None, None, s
            ) if hasattr(players_router.get_player_captain_stats, "__wrapped__") else \
                await players_router.get_player_captain_stats(str(BOWL), None, None, None, s)
            cap = got["bowling_as_captain"]
            # Covered spells only: 60 runs off 120 balls = 3.00. The old line
            # divided 125 by a summed 20.0 "overs" and read 6.25.
            check("captain: economy reads 3.00 from the two spells that carry overs",
                  near(cap.get("economy"), 3.00), f"got {cap.get('economy')}")
            check("captain: it says two of four spells answered",
                  (cap.get("economy_coverage") or {}).get("counted") == 2
                  and (cap.get("economy_coverage") or {}).get("of") == 4,
                  str(cap.get("economy_coverage")))
            check("captain: and is therefore not marked complete",
                  (cap.get("economy_coverage") or {}).get("complete") is False,
                  str(cap.get("economy_coverage")))
            check("captain: wickets still count every spell",
                  int(cap.get("wickets") or 0) == 6, str(cap.get("wickets")))

        # ── cricket notation ─────────────────────────────────────────────────
        print("\n— overs are converted to balls before anything is divided —")
        async with guard(s, "notation"):
            row = (await s.execute(text(f"""
                SELECT {rc.economy_sql('bs')} AS economy,
                       SUM({rc.overs_to_balls_sql('bs.overs')}) AS balls
                FROM v_effective_bowling_spells bs WHERE bs.player_id = :p
            """), {"p": NOTATION})).mappings().first()
            check("two spells of 10.2 overs are 124 balls, not 20.4",
                  int(row["balls"]) == 124, str(row["balls"]))
            check("62 runs off them is an economy of 3.00",
                  near(row["economy"], 3.00), str(row["economy"]))

        # ── the teammate split ───────────────────────────────────────────────
        print("\n— the teammate split —")
        async with guard(s, "teammates"):
            from app.services import iq_teammates
            split = await iq_teammates.with_split(s, str(ORG), str(BAT), str(MATE))
            bat_with = split["with"]["batting"]
            check("teammates: strike rate reads 100, not 333.33",
                  near(bat_with.get("strike_rate"), 100.0), str(bat_with.get("strike_rate")))
            check("teammates: three of ten innings answered it",
                  (bat_with.get("strike_rate_coverage") or {}).get("counted") == 3
                  and (bat_with.get("strike_rate_coverage") or {}).get("of") == 10,
                  str(bat_with.get("strike_rate_coverage")))
            check("teammates: runs still count every innings",
                  int(bat_with.get("runs") or 0) == 500, str(bat_with.get("runs")))
            mate = split["together"]["teammate"]["batting"]
            check("teammates: the fully-covered mate is not marked short",
                  (mate.get("strike_rate_coverage") or {}).get("complete") is True,
                  str(mate.get("strike_rate_coverage")))
            check("teammates: the mate's own rate is 50.00 (200 off 400)",
                  near(mate.get("strike_rate"), 50.0), str(mate.get("strike_rate")))

        # ── the player deep dive ─────────────────────────────────────────────
        print("\n— the player deep dive's batting style —")
        async with guard(s, "deep dive"):
            from app.services import iq_trends
            deep = await iq_trends.player_deep_dive(s, str(ORG), str(BAT))
            bs = deep.get("batting_style") or {}
            check("deep dive: strike rate reads 100, not 333.33",
                  near(bs.get("strike_rate"), 100.0), str(bs.get("strike_rate")))
            check("deep dive: three of ten innings answered it",
                  (bs.get("strike_rate_coverage") or {}).get("counted") == 3,
                  str(bs.get("strike_rate_coverage")))
            check("deep dive: balls counts only the covered innings (150)",
                  int(bs.get("balls") or 0) == 150, str(bs.get("balls")))
            # 150 balls over 15 boundaries in those three innings.
            check("deep dive: balls per boundary comes from the same innings",
                  near(bs.get("balls_per_boundary"), 10.0), str(bs.get("balls_per_boundary")))

        # ── team analysis ────────────────────────────────────────────────────
        print("\n— the team analysis boards —")
        async with guard(s, "team"):
            from app.services import iq_team
            attack = await iq_team._attack_structure(s, str(ORG), str(SEASON))
            bowlers = {b["name"]: b for b in (attack or {}).get("bowlers", [])}
            cap_row = bowlers.get("Partial, Overs")
            check("attack structure: the captain's economy reads 3.00",
                  cap_row is not None and near(cap_row.get("econ"), 3.00),
                  str(cap_row and cap_row.get("econ")))
            check("attack structure: his flattened 0-over spell adds no runs",
                  cap_row is not None and cap_row.get("overs") == "20.0",
                  str(cap_row and cap_row.get("overs")))

        # ── the opposition dossier ───────────────────────────────────────────
        print("\n— the opposition dossier's danger players —")
        async with guard(s, "dossier"):
            from app.services import iq_opponent
            bat_acc, bowl_acc, field_acc = {}, {}, {}
            card = {"innings": [{
                "batting": [
                    {"participantId": "opp-1", "runsScored": 50, "ballsFaced": 50,
                     "dismissalTypeId": 2, "dismissalType": "Bowled"},
                    {"participantId": "opp-1", "runsScored": 50, "ballsFaced": None,
                     "dismissalTypeId": 2, "dismissalType": "Bowled"},
                    {"participantId": "opp-1", "runsScored": 50, "ballsFaced": 0,
                     "dismissalTypeId": 2, "dismissalType": "Bowled"},
                ],
                "bowling": [
                    {"participantId": "opp-1", "wicketsTaken": 2, "runsConceded": 30,
                     "oversBowled": 10.0, "maidensBowled": 0},
                    {"participantId": "opp-1", "wicketsTaken": 1, "runsConceded": 40,
                     "oversBowled": None, "maidensBowled": 0},
                ],
                "fielding": [],
            }]}
            iq_opponent._accumulate(card, "m1", {"opp-1": "Danger, Man"},
                                    date(2025, 11, 1), bat_acc, bowl_acc, field_acc)
            fb = iq_opponent._finalise_bat("opp-1", bat_acc["opp-1"])
            fw = iq_opponent._finalise_bowl("opp-1", bowl_acc["opp-1"])
            check("dossier: strike rate reads 100, not 300",
                  near(fb.get("strike_rate"), 100.0), str(fb.get("strike_rate")))
            check("dossier: one of three innings answered it",
                  (fb.get("strike_rate_coverage") or {}).get("counted") == 1
                  and (fb.get("strike_rate_coverage") or {}).get("of") == 3,
                  str(fb.get("strike_rate_coverage")))
            check("dossier: his runs are still 150",
                  int(fb.get("runs") or 0) == 150, str(fb.get("runs")))
            check("dossier: economy reads 3.00 from the spell that carries overs",
                  near(fw.get("economy"), 3.00), str(fw.get("economy")))
            check("dossier: his wickets still count both spells",
                  int(fw.get("wickets") or 0) == 3, str(fw.get("wickets")))
            check("dossier: the cache version moved, so built dossiers rebuild",
                  iq_opponent.DOSSIER_VERSION >= 10, str(iq_opponent.DOSSIER_VERSION))

        # ── StatLab's family targets ─────────────────────────────────────────
        print("\n— StatLab's three family targets —")
        async with guard(s, "family"):
            from app.services import statlab
            ctx: dict = {}
            fc = await statlab.query_family_career(
                s, org_id=str(ORG), sort_by="runs", sort_dir="desc", limit=10,
                metric_filters=None, filter_tree=None, context=ctx)
            check("family career: the family is there", len(fc) == 1, str(len(fc)))
            if fc:
                # The family's covered halves: the batter's three counted
                # innings (150 off 150) plus the mate's ten (200 off 400) —
                # 350 / 550. Dividing the family's WHOLE 700 runs by those 550
                # balls would read 127.27, which is the same two-population
                # mixing on a family scale.
                check("family career: strike rate is 63.64, from the counted innings",
                      near(fc[0].get("batting_strike_rate"), 63.64),
                      str(fc[0].get("batting_strike_rate")))
                check("family career: runs still count every innings (700)",
                      int(fc[0].get("runs") or 0) == 700, str(fc[0].get("runs")))
                check("family career: no coverage columns leak into the row",
                      "sr_counted" not in fc[0] and "econ_counted" not in fc[0],
                      str(sorted(k for k in fc[0] if "counted" in k)))
            fs = await statlab.query_family_season(
                s, org_id=str(ORG), sort_by="runs", sort_dir="desc", limit=10,
                metric_filters=None, filter_tree=None, context=ctx)
            check("family season: the season row is there", len(fs) == 1, str(len(fs)))
            if fs:
                check("family season: same figure, per season",
                      near(fs[0].get("batting_strike_rate"), 63.64),
                      str(fs[0].get("batting_strike_rate")))
            fg = await statlab.query_family_grade(
                s, org_id=str(ORG), sort_by="runs", sort_dir="desc", limit=10,
                metric_filters=None, filter_tree=None, context=ctx)
            check("family grade: the grade row is there", len(fg) == 1, str(len(fg)))
            if fg:
                check("family grade: same figure, per grade",
                      near(fg[0].get("batting_strike_rate"), 63.64),
                      str(fg[0].get("batting_strike_rate")))

        # ── the rule itself ──────────────────────────────────────────────────
        print("\n— the SQL and the Python agree on every seeded innings —")
        async with guard(s, "agreement"):
            rows = (await s.execute(text(
                f"SELECT bi.runs, bi.balls, {rc.batting_covered_sql('bi')} AS cov "
                "FROM v_effective_batting_innings bi"))).mappings().all()
            check(f"batting: {len(rows)} innings classified identically",
                  all(bool(r["cov"]) == rc.is_batting_covered(r["runs"], r["balls"])
                      for r in rows))
            rows = (await s.execute(text(
                f"SELECT bs.runs, bs.overs, {rc.bowling_covered_sql('bs')} AS cov "
                "FROM v_effective_bowling_spells bs"))).mappings().all()
            check(f"bowling: {len(rows)} spells classified identically",
                  all(bool(r["cov"]) == rc.is_bowling_covered(r["runs"], r["overs"])
                      for r in rows))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  FAILED: {f}")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
