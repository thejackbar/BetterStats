"""Verification for the career-vs-breakdown match note, against a real Postgres.

Reported off Rob Wilton's profile: **333 matches with Competition set to All,
337 with one competition picked**. A filter that INCREASES a total is
incoherent however it is explained, and the reader's next move is to add the
competitions up and conclude the site is broken.

Neither figure is wrong. A career carries TWO match counts and any filter
switches between them:

  no filter  -> ``SUM(player_season_stats.matches)``, Cricket Australia's own
                season totals, which carry no grade at all
  any filter -> the matches we hold a game row for, because a grade — and so a
                competition, a grade type or a format — is only recorded on a
                match

This predates competitions entirely: ``?categories=senior`` reproduces it, and
that axis shipped with migration 228. Measured across the platform (95,151
players) the two sources agree for 41%, we hold MORE than CA counts for 20%
(worst +221) and CA counts more than we hold for 39% (worst -484). Adopting the
higher figure would renumber 19,439 careers, so the figures stay as they are
and the page says why they differ — BEFORE anyone has to notice.

Runs the SHIPPED service and route bodies — never a re-implementation — over
the ``v_effective_*`` views pulled straight out of the migrations that define
them.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_match_coverage.py
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
from app.routers.players import get_player_stats

try:
    from app.routers.players import get_player_team_breakdown_endpoint
    HAVE_GRID_SCOPE = True
except ImportError:  # pragma: no cover
    HAVE_GRID_SCOPE = False

# Behind a guard so a CONTROL RUN against the previous commit reports the
# feature missing as one failed check rather than dying on an ImportError
# before a single one runs.
MISSING: list[str] = []
try:
    from app.services import match_coverage
    HAVE = True
except ImportError as exc:  # pragma: no cover - control run only
    HAVE = False
    MISSING.append(str(exc))
    match_coverage = None

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

try:
    from app.routers.players import get_player_competitions
    HAVE_COMPS = True
except ImportError:  # pragma: no cover
    HAVE_COMPS = False

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
OTHER = uuid.uuid4()
OPPONENT = uuid.uuid4()   # deliberately NOT `OTHER` — a club recorded as one
                          # of the two sides IS a participant by the app's own
                          # home_org_id/away_org_id rule, so using the control
                          # club here would make every fixture genuinely its
                          # own and the cross-club check would measure nothing.

S_NEW = uuid.uuid4()      # 2025/26
S_OLD = uuid.uuid4()      # 2024/25
S_OTHER = uuid.uuid4()

G_1ST = uuid.uuid4()
G_2ND = uuid.uuid4()
G_OLD = uuid.uuid4()
G_JNR = uuid.uuid4()      # a junior grade, so a Men's filter has work to do
G_OTHER = uuid.uuid4()

# The reported shape: CA counts FEWER than we hold, so a filter reads HIGHER
# than the career total.
WILTON = uuid.uuid4()
# The other direction, which is the more common one platform-wide: CA counts
# more than we hold, so a filter reads lower.
SHORT = uuid.uuid4()
# The two sources agree — no note at all.
EVEN = uuid.uuid4()
# Nothing recorded either way.
EMPTY = uuid.uuid4()
# A career that arrived as season totals with no scorecards behind it.
IMPORTED = uuid.uuid4()
STRANGER = uuid.uuid4()


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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS org_merge_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_org_id UUID, source_org_name TEXT NOT NULL,
                target_org_id UUID NOT NULL,
                performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                undone_at TIMESTAMPTZ)
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


# How many games each player holds a scorecard for, per grade, and what CA's
# own season totals claim. Declared once here because every assertion below is
# written against these numbers.
HELD = {
    WILTON: {G_1ST: 5, G_2ND: 2, G_OLD: 2, G_JNR: 3},  # 12 graded, 3 of them junior
    SHORT:  {G_1ST: 3},                        # 3 held
    EVEN:   {G_1ST: 5},                        # 5 held
    IMPORTED: {},                              # nothing held at all
    EMPTY:  {},
}
CLAIMED = {
    WILTON: {S_NEW: 5, S_OLD: 2},   # 7, plus 1 the manual game contributes
    SHORT:  {S_NEW: 9},             # 9 claimed against 3 held -> 6 with no scorecard
    EVEN:   {S_NEW: 5},             # agrees exactly -> no note
    IMPORTED: {S_OLD: 40},          # a whole career of season totals, no games
}
# A grade-less manual game, on top of WILTON's 9 graded ones. It belongs to no
# competition and MUST still count as held: we have the match, there is nothing
# to file. It ALSO adds 1 to the aggregate, through the `manual_game` branch of
# `v_effective_player_season_stats` — so both sides see it, which is what makes
# this a fair test of the boundary rather than a free +1 on one side.
WILTON_MANUAL = 1
WILTON_HELD = 5 + 2 + 2 + 3 + WILTON_MANUAL   # 13
WILTON_CLAIMED = 5 + 2 + WILTON_MANUAL    # 8


async def seed(session) -> None:
    async def ex(sql, **kw):
        await session.execute(text(sql), kw)

    for oid, nm, slug in ((ORG, "Reported Club", "reported"),
                          (OTHER, "Somebody Else CC", "other")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=nm, s=slug)
    for sid, org, nm, yr in ((S_NEW, ORG, "Summer 2025/26", 2025),
                             (S_OLD, ORG, "Summer 2024/25", 2024),
                             (S_OTHER, OTHER, "Summer 2025/26", 2025)):
        await ex("INSERT INTO seasons (id, organisation_id, name, year) "
                 "VALUES (:i, :o, :n, :y)", i=sid, o=org, n=nm, y=yr)
    for gid, sid, nm in ((G_1ST, S_NEW, "1st Grade"), (G_2ND, S_NEW, "2nd Grade"),
                         (G_OLD, S_OLD, "1st Grade"), (G_OTHER, S_OTHER, "1st Grade")):
        await ex("INSERT INTO grades (id, season_id, name, grassroots_id, "
                 " category, categories) "
                 "VALUES (:i, :s, :n, :g, 'senior', ARRAY['senior'])",
                 i=gid, s=sid, n=nm, g=str(gid))
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, "
             " category, categories) "
             "VALUES (:i, :s, 'Under 16s', :g, 'junior', ARRAY['junior'])",
             i=G_JNR, s=S_NEW, g=str(G_JNR))
    for pid, org, nm in ((WILTON, ORG, "Wilton, Rob"), (SHORT, ORG, "Short, Sam"),
                         (EVEN, ORG, "Even, Ed"), (EMPTY, ORG, "Empty, Eve"),
                         (IMPORTED, ORG, "Ancient, Arthur"),
                         (STRANGER, OTHER, "Nobody, Ivan")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, "
                 " status) VALUES (:i, :o, :n, :g, 'active')",
                 i=pid, o=org, n=nm, g=str(pid))

    day = 1
    for player, by_grade in HELD.items():
        for grade_id, count in by_grade.items():
            for _ in range(count):
                gid = uuid.uuid4()
                await ex(
                    "INSERT INTO games (id, grade_id, played_at, result, "
                    " home_org_id, away_org_id, match_format, status) "
                    "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
                    i=gid, g=grade_id, d=date(2025, 1, 1 + (day % 27)),
                    o=ORG, x=OPPONENT)
                day += 1
                await ex(
                    "INSERT INTO batting_innings (game_id, player_id, runs, balls, "
                    " fours, sixes, not_out, dismissal_type, did_not_bat) "
                    "VALUES (:g, :p, 30, 40, 2, 0, false, 'caught', false)",
                    g=gid, p=player)
                await ex("INSERT INTO game_appearances (game_id, player_id) "
                         "VALUES (:g, :p)", g=gid, p=player)

    # The control club's own game, to prove nothing leaks across.
    stranger_game = uuid.uuid4()
    await ex("INSERT INTO games (id, grade_id, played_at, result, home_org_id, "
             " away_org_id, match_format, status) "
             "VALUES (:i, :g, :d, 'WIN', :o, :x, 'One Day', 'COMPLETED')",
             i=stranger_game, g=G_OTHER, d=date(2025, 2, 2), o=OTHER, x=OPPONENT)
    await ex("INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, "
             " sixes, not_out, dismissal_type, did_not_bat) "
             "VALUES (:g, :p, 5, 9, 0, 0, false, 'caught', false)",
             g=stranger_game, p=STRANGER)

    for player, seasons in CLAIMED.items():
        for sid, matches in seasons.items():
            await ex(
                "INSERT INTO player_season_stats (player_id, season_id, matches, "
                " batting_innings, runs, not_outs, wickets, source) "
                "VALUES (:p, :s, :m, :m, :r, 0, 0, 'api')",
                p=player, s=sid, m=matches, r=matches * 30)

    # A grade-less manual game for WILTON, in the current season. There is no
    # `game_appearances` row: that table FKs to `games`, and a manual game is
    # not one — the appearance union picks it up through the effective
    # batting-innings view, which is how the app itself sees it.
    manual = uuid.uuid4()
    await ex("INSERT INTO manual_games (id, organisation_id, season_id, played_at, "
             " result, home_team, away_team) "
             "VALUES (:i, :o, :s, :d, 'WIN', 'Us', 'Them')",
             i=manual, o=ORG, s=S_NEW, d=date(2025, 3, 1))
    await ex("INSERT INTO manual_batting_innings (manual_game_id, player_id, runs, "
             " not_out, did_not_bat) VALUES (:g, :p, 55, false, false)",
             g=manual, p=WILTON)


async def stats(session, player, **kw):
    """The SHIPPED route body, with every FastAPI default filled in."""
    params = dict(
        season_id=None, grade_id=None, last_n_games=None, start_date=None,
        end_date=None, categories=None, formats=None, competitions=None,
    )
    params.update(kw)
    return await get_player_stats(player_id=str(player), db=session, **params)


async def grid(session, player, **kw):
    """The SHIPPED grid route body, with every FastAPI default filled in."""
    params = dict(season_id=None, categories=None, formats=None, competitions=None)
    params.update(kw)
    return await get_player_team_breakdown_endpoint(
        player_id=str(player), db=session, **params)


async def main() -> None:
    if not HAVE:
        check("the match-coverage note is built at all", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        await engine.dispose()
        sys.exit(1)

    await build_schema()
    async with Session() as session:
        await seed(session)
        await session.commit()

    async with Session() as session:
        print("\n-- the two sources, counted independently --")
        claimed = await match_coverage.aggregate_matches(session, str(WILTON))
        held = await match_coverage.scorecard_matches(session, str(WILTON), ORG)
        check("CA's season totals for the reported player read 8",
              claimed == WILTON_CLAIMED, f"got {claimed}")
        check("the scorecards we hold read 13 (12 graded + 1 grade-less)",
              held == WILTON_HELD, f"got {held}")
        check("A GRADE-LESS MANUAL GAME COUNTS AS HELD — we have the match, so "
              "it must not be reported as one we have no scorecard for",
              held == sum(HELD[WILTON].values()) + WILTON_MANUAL,
              f"got {held}")

        print("\n-- the reported case: a filter reads HIGHER than the career --")
        cov = await match_coverage.career_coverage(session, str(WILTON), ORG)
        check("a note is drawn", bool(cov))
        check("career total is CA's own figure",
              cov and cov["career_matches"] == WILTON_CLAIMED, str(cov))
        check("the breakdown figure is what a filter counts from",
              cov and cov["breakdown_matches"] == WILTON_HELD, str(cov))
        check("nothing is reported as missing a scorecard",
              cov and cov["without_scorecard"] == 0, str(cov))
        check("THE SURPLUS IS ITS OWN FIGURE, never a negative 'missing' one — "
              "'13 of 8 matches' is the shape of a bug, not an explanation",
              cov and cov["extra_scorecards"] == WILTON_HELD - WILTON_CLAIMED,
              str(cov))

        print("\n-- the other direction: CA counts more than we hold --")
        cov = await match_coverage.career_coverage(session, str(SHORT), ORG)
        check("a note is drawn", bool(cov))
        check("career total 9, breakdown 3",
              cov and cov["career_matches"] == 9 and cov["breakdown_matches"] == 3,
              str(cov))
        check("six matches are reported as having no scorecard",
              cov and cov["without_scorecard"] == 6, str(cov))
        check("and no surplus is invented", cov and cov["extra_scorecards"] == 0,
              str(cov))

        print("\n-- silence where there is nothing to say --")
        check("the two agreeing draws NO note",
              await match_coverage.career_coverage(session, str(EVEN), ORG) is None)
        check("a player with nothing recorded either way draws NO note",
              await match_coverage.career_coverage(session, str(EMPTY), ORG) is None)

        print("\n-- a career of season totals with no scorecards behind it --")
        cov = await match_coverage.career_coverage(session, str(IMPORTED), ORG)
        check("all 40 matches are reported as having no scorecard",
              cov and cov["career_matches"] == 40 and cov["breakdown_matches"] == 0
              and cov["without_scorecard"] == 40, str(cov))

        print("\n-- cross-club --")
        check("another club's player, read through our org, holds nothing of ours",
              await match_coverage.scorecard_matches(session, str(STRANGER), ORG) == 0)
        check("and our player holds nothing under their org",
              await match_coverage.scorecard_matches(session, str(WILTON), OTHER) == 0)

        print("\n-- season scope --")
        held_new = await match_coverage.scorecard_matches(
            session, str(WILTON), ORG, str(S_NEW))
        check("this season's held matches are the 10 graded plus the manual one",
              held_new == 11, f"got {held_new}")
        claimed_new = await match_coverage.aggregate_matches(
            session, str(WILTON), str(S_NEW))
        check("and CA's figure narrows to the same season", claimed_new == 6,
              f"got {claimed_new}")
        cov = await match_coverage.career_coverage(
            session, str(WILTON), ORG, str(S_NEW))
        check("the season note reports both narrowed figures",
              cov and cov["career_matches"] == 6 and cov["breakdown_matches"] == 11,
              str(cov))

    print("\n-- through the shipped route body --")
    async with Session() as session:
        res = await stats(session, WILTON)
        # `or {}` throughout, so a CONTROL RUN with the route left unwired
        # reports each check rather than dying on the first None — otherwise
        # the other checks say nothing.
        cov = res.get("match_coverage") or {}
        check("the profile payload carries the note", bool(cov))
        # A CLUB WITH JUNIOR GRADES HAS A DEFAULT SCOPE ACTIVE WITH NOBODY
        # HAVING TOUCHED A CONTROL, so `res` above is already a filtered view
        # and its headline is neither career figure. Ask for every category
        # explicitly to get a genuinely unscoped read.
        unscoped = await stats(session, WILTON, categories="senior,junior")
        check("asking for every category really is an inactive scope",
              not (unscoped.get("grade_scope") or {}).get("active"),
              str(unscoped.get("grade_scope")))
        headline = (unscoped.get("career_batting") or {}).get("games")
        check("with no scope at all the headline IS Cricket Australia's figure, "
              "which is what the note quotes",
              bool(cov) and cov.get("career_matches") == headline,
              f"note {cov} vs headline {headline}")
        default_headline = (res.get("career_batting") or {}).get("games")
        check("but the CLUB DEFAULT already moves it, so the note must never "
              "claim its figures are the headline",
              default_headline != cov.get("career_matches")
              and default_headline != cov.get("breakdown_matches"),
              f"default headline {default_headline} vs {cov}")

        even = await stats(session, EVEN)
        check("a player the two sources agree on carries NO key at all — the "
              "payload keeps its exact shape, the presence-aware rule",
              "match_coverage" not in even)

        print("\n-- THE NOTE MUST NOT VANISH THE MOMENT A FILTER IS ON --")
        # This is the whole point. With a scope active the career figure has
        # already switched to the scorecards, so a note derived from the
        # caller's own figure would compare them against themselves and draw
        # nothing at exactly the moment somebody is looking at a moved number.
        fmt = await stats(session, WILTON, formats="one_day")
        # Asserted, not assumed. `categories="senior"` on a club whose grades
        # are all senior excludes nothing and resolves to NO scope at all, so a
        # check written against it would pass while measuring the unfiltered
        # path — a check that cannot fail is not a check.
        check("the scope really is active, so this is genuinely a filtered view",
              bool((fmt.get("grade_scope") or {}).get("active")),
              str(fmt.get("grade_scope")))
        fmt_headline = (fmt.get("career_batting") or {}).get("games")
        check("the filter moves the headline off the career total — this IS the "
              "reported symptom, a filter reading HIGHER than All",
              fmt_headline == 9 and fmt_headline > (cov.get("career_matches") or 0),
              f"headline {fmt_headline} vs career {cov.get('career_matches')}")
        fcov = fmt.get("match_coverage") or {}
        check("a filtered view still carries the note rather than dropping it "
              "at exactly the moment somebody is looking at a moved number",
              bool(fcov))
        check("and it reports the SAME two figures as the unfiltered view — "
              "the difference is a fact about the career, not about the view",
              bool(cov) and fcov == cov, f"{fcov} vs {cov}")

        print("\n-- a slice of a career is not a career --")
        windowed = await stats(session, WILTON, last_n_games=3)
        check("a last-N-games window draws no note: the headline is a slice, "
              "so comparing it against a career total would mean nothing",
              "match_coverage" not in windowed)

        print("\n-- season-scoped, through the route --")
        season = await stats(session, WILTON, season_id=str(S_NEW))
        scov = season.get("match_coverage") or {}
        check("the season view carries its own narrowed note",
              scov.get("career_matches") == 6 and scov.get("breakdown_matches") == 11,
              str(scov))

    if HAVE_COMPS:
        print("\n-- the panel where the figures visibly fail to add up --")
        async with Session() as session:
            comps = await get_player_competitions(
                player_id=str(WILTON), season_id=None, db=session)
            rows = comps.get("rows") or []
            total = sum(r.get("matches") or 0 for r in rows)
            unatt = comps.get("unattributed") or 0
            check("the competition rows sum to the graded matches we hold",
                  total == sum(HELD[WILTON].values()), f"rows {total}")
            check("the grade-less game is reported on its own as unattributed",
                  unatt == WILTON_MANUAL, f"got {unatt}")
            check("ROWS + UNATTRIBUTED == THE BREAKDOWN FIGURE, so the panel's "
                  "own arithmetic closes and only the career total is left to "
                  "explain", total + unatt == WILTON_HELD, f"{total} + {unatt}")
            check("and the career total sits below it, which is exactly the "
                  "gap the note has to account for",
                  WILTON_CLAIMED - (total + unatt) == -5, f"{total + unatt}")
    else:  # pragma: no cover - control run only
        check("the competitions panel is available to cross-check against", False)

    if HAVE_GRID_SCOPE:
        print("\n-- THE GRID ANSWERS TO THE FILTER BAR ABOVE IT --")
        async with Session() as session:
            # The filter bar is page-level, so a grid that ignored it put the
            # junior grades back one click after the Batting tab dropped them.
            everything = await grid(session, WILTON, categories="senior,junior")
            names = {r["grade_name"] for r in everything["rows"]}
            check("asking for every category lists the junior grade too",
                  "Under 16s" in names, str(sorted(names)))
            check("and reports no scope, so the payload keeps its old shape",
                  "scope" not in everything, str(everything.get("scope")))

            default = await grid(session, WILTON)
            dnames = {r["grade_name"] for r in default["rows"]}
            check("THE CLUB DEFAULT ALREADY EXCLUDES JUNIOR, and the grid now "
                  "follows it rather than showing what the header just dropped",
                  "Under 16s" not in dnames, str(sorted(dnames)))
            check("the senior grades are all still there",
                  {"1st Grade", "2nd Grade"} <= dnames, str(sorted(dnames)))
            check("and it says a filter is in play",
                  (default.get("scope") or {}).get("active") is True,
                  str(default.get("scope")))

            jnr = await grid(session, WILTON, categories="junior")
            jnames = {r["grade_name"] for r in jnr["rows"]}
            check("picking Juniors returns the junior grade and nothing else",
                  jnames == {"Under 16s"}, str(sorted(jnames)))
            check("with its own three matches",
                  sum(r["matches"] for r in jnr["rows"]) == 3,
                  str([(r["grade_name"], r["matches"]) for r in jnr["rows"]]))

            print("\n-- a match type cannot be asked of a per-grade aggregate --")
            fmt = await grid(session, WILTON, formats="one_day")
            check("it says so on the payload rather than leaving a shorter grid "
                  "to read as data going missing",
                  (fmt.get("scope") or {}).get("aggregate_excluded") is True,
                  str(fmt.get("scope")))
            check("and a category filter alone does NOT drop the aggregate — a "
                  "grade has one category, so that half is answerable",
                  (default.get("scope") or {}).get("aggregate_excluded") is False,
                  str(default.get("scope")))
            fmt_total = sum(r["matches"] for r in fmt["rows"]) + fmt["unattributed"]
            check("under a match type the grid is what we hold a scorecard for, "
                  "and nothing is invented on top",
                  fmt_total == sum(r["scorecard_matches"] for r in fmt["rows"]),
                  f"total {fmt_total}")
            check("the grade-less manual game is still out of every grid — it "
                  "has no grade to sit under",
                  all(r["grade_name"] for r in everything["rows"]))
    else:  # pragma: no cover - control run only
        check("the grid takes the filter bar's scope", False)

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
