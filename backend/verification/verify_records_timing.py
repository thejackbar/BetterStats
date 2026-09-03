"""Per-query timing on the club record book.

`GET /records/{org}` runs ~40 aggregations in ONE request, each awaited in
turn, and an all-time board scans a club's whole history. Measured against the
live site, an unfiltered load is ~15s for Hamilton Veterans AND ~16s for
Applecross, while the same request narrowed to one competition is ~1.2s — so
the cost is the unfiltered scans, not the competition linkage, and the open
question is WHICH of the forty queries the request is waiting on.

This suite proves the instrumentation that answers it: that every query is
timed and NAMED after the board it builds, that the breakdown is served only
to a viewer who may already see the club's private data, that a slow request
logs its worst offenders, and that a request which asks for none of this is
byte-for-byte the payload it was.

Runs the SHIPPED route body — never a re-implementation — over the
``v_effective_*`` views pulled straight out of the migrations that define them.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_records_timing.py
"""
from __future__ import annotations

import asyncio
import logging
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


# The instrumentation is what this suite exists to check, so its absence is
# reported once rather than as thirty identical import errors — which is what
# a control run against the previous commit produces.
MISSING: list[str] = []
try:
    from app.routers import records as records_router
    from app.routers.records import get_records
    HAVE_TIMING = hasattr(records_router, "_query_label")
    if not HAVE_TIMING:
        MISSING.append("records._query_label is not defined")
except Exception as exc:  # pragma: no cover - control run only
    HAVE_TIMING = False
    MISSING.append(f"import failed: {exc}")

from app.services.competition_ddl import STATEMENTS as COMP_DDL

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
OPPONENT = uuid.UUID("22222222-2222-2222-2222-222222222222")
SEASON = uuid.UUID("33333333-3333-3333-3333-333333333333")
GRADE = uuid.UUID("44444444-4444-4444-4444-444444444444")
PLAYER = uuid.UUID("55555555-5555-5555-5555-555555555555")
MATE = uuid.UUID("66666666-6666-6666-6666-666666666666")
ADMIN = uuid.UUID("77777777-7777-7777-7777-777777777777")
RIVAL_PLAYER = uuid.UUID("88888888-8888-8888-8888-888888888888")
EMPTY_ORG = uuid.UUID("99999999-9999-9999-9999-999999999999")


class Viewer:
    """Stands in for the authenticated user the route is handed."""

    def __init__(self, user_id):
        self.id = user_id


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in COMP_DDL:
            await conn.execute(text(stmt))
        # Raw-SQL tables the lifespan creates, which `create_all` cannot know
        # about. `audit_logs` is copied column for column: it swallows its own
        # failure, so a wrong name leaves the caller's transaction ABORTED.
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

    for oid, name, slug in ((ORG, "Timing CC", "timing"), (OPPONENT, "Rivals CC", "rivals"),
                            (EMPTY_ORG, "Nobody CC", "nobody")):
        await ex("INSERT INTO organisations (id, name, slug, is_active) "
                 "VALUES (:i, :n, :s, true)", i=oid, n=name, s=slug)
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=SEASON, o=ORG)
    await ex("INSERT INTO grades (id, season_id, name, grassroots_id, category, categories) "
             "VALUES (:i, :s, '1st Grade', :g, 'senior', ARRAY['senior'])",
             i=GRADE, s=SEASON, g=str(GRADE))
    for pid, nm in ((PLAYER, "Barker, Geoffrey"), (MATE, "Baker, Ken")):
        await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
                 "VALUES (:i, :o, :n, :g, 'active')", i=pid, o=ORG, n=nm, g=str(pid))
    # A user who may see the club's private data, which is what gates the
    # breakdown. `user_can_view_org_private` reads the membership, not the user.
    await ex("INSERT INTO users (id, username, password_hash, failed_login_count) "
             "VALUES (:i, 'boss', 'x', 0)", i=ADMIN)
    await ex("INSERT INTO club_memberships (id, user_id, club_id, role) "
             "VALUES (gen_random_uuid(), :u, :o, 'super_admin')", u=ADMIN, o=ORG)

    for n, (result, runs) in enumerate([("WIN", 43), ("WIN", 30), ("LOSS", 12)]):
        gid = uuid.uuid4()
        await ex(
            "INSERT INTO games (id, grade_id, played_at, result, home_org_id, "
            " away_org_id, match_format, status) "
            "VALUES (:i, :g, :d, :r, :o, :x, 'One Day', 'COMPLETED')",
            i=gid, g=GRADE, d=date(2025, 1, 5 + n), r=result, o=ORG, x=OPPONENT)
        for pid, scored in ((PLAYER, runs), (MATE, max(runs - 7, 1))):
            await ex(
                "INSERT INTO batting_innings (game_id, player_id, runs, balls, fours, "
                " sixes, not_out, dismissal_type, did_not_bat, batting_position) "
                "VALUES (:g, :p, :r, :b, 2, 0, false, 'caught', false, 3)",
                g=gid, p=pid, r=scored, b=scored + 10)
            await ex(
                "INSERT INTO bowling_spells (game_id, player_id, overs, maidens, "
                " runs, wickets) VALUES (:g, :p, 5.0, 1, 18, 2)", g=gid, p=pid)
            await ex(
                "INSERT INTO fielding_stats (game_id, player_id, catches, catches_wk, "
                " stumpings, run_outs) VALUES (:g, :p, 1, 0, 0, 0)", g=gid, p=pid)
            await ex("INSERT INTO game_appearances (game_id, player_id) "
                     "VALUES (:g, :p)", g=gid, p=pid)
        await ex(
            "INSERT INTO partnerships (game_id, innings_number, wicket_number, runs, "
            " batter1_id, batter2_id, is_club_innings) "
            "VALUES (:g, 1, 2, :r, :a, :b, true)",
            g=gid, r=runs + 20, a=PLAYER, b=MATE)
    # A rival club's player, outscoring everyone here. The club clause is
    # logically implied by the join and filter already in every board, so it
    # cannot change a row — this is what proves that empirically rather than
    # by reading the SQL.
    rival_season = uuid.uuid4()
    await ex("INSERT INTO seasons (id, organisation_id, name, year) "
             "VALUES (:i, :o, 'Summer 2025/26', 2025)", i=rival_season, o=OPPONENT)
    await ex("INSERT INTO players (id, organisation_id, name, grassroots_id, status) "
             "VALUES (:i, :o, 'Bradman, Don', :g, 'active')",
             i=RIVAL_PLAYER, o=OPPONENT, g=str(RIVAL_PLAYER))
    await ex("INSERT INTO player_season_stats (player_id, season_id, matches, "
             " batting_innings, runs, not_outs, wickets, source) "
             "VALUES (:p, :s, 52, 80, 6996, 10, 2, 'api')",
             p=RIVAL_PLAYER, s=rival_season)

    for pid, runs in ((PLAYER, 85), (MATE, 66)):
        await ex(
            "INSERT INTO player_season_stats (player_id, season_id, matches, "
            " batting_innings, runs, not_outs, wickets, source) "
            "VALUES (:p, :s, 3, 3, :r, 0, 6, 'api')", p=pid, s=SEASON, r=runs)
    await session.commit()


# The route body is called directly, so FastAPI's own `Query(...)` defaults are
# never resolved — every parameter has to be passed. One helper, so a check
# reads as the request it stands for.
async def records(session, **kw):
    args = dict(
        season_id=None, grade_id=None, grade_name=None, finals_only=False,
        captain_only=False, gender=None, categories=None, formats=None,
        competitions=None, debug_timing=False, viewer=None,
    )
    args.update(kw)
    return await get_records(str(ORG), db=session, **args)


BOARD_KEYS = ("batting", "bowling", "partnerships", "team", "allrounders", "grade_scope")


async def main() -> None:
    if not HAVE_TIMING:
        check("records query timing is built at all", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        await engine.dispose()
        sys.exit(1)

    await build_schema()
    async with Session() as session:
        await seed(session)

    print("\n-- the ordinary payload is unchanged --")
    async with Session() as session:
        plain = await records(session)
    check("every board still comes back", all(k in plain for k in BOARD_KEYS),
          str(sorted(plain)))
    check("and still holds rows", bool(plain["batting"]["top_career_runs"]))
    check("a request that asked for no timings carries none",
          "_query_timings" not in plain, str(sorted(plain)))

    print("\n-- the breakdown is gated on who may see the club's private data --")
    async with Session() as session:
        anon = await records(session, debug_timing=True)
    check("a signed-out visitor asking for timings gets none",
          "_query_timings" not in anon)
    async with Session() as session:
        stranger = await records(session, debug_timing=True, viewer=Viewer(uuid.uuid4()))
    check("nor does a user with no membership at this club",
          "_query_timings" not in stranger)
    async with Session() as session:
        timed = await records(session, debug_timing=True, viewer=Viewer(ADMIN))
    check("an admin of the club gets one", "_query_timings" in timed)

    print("\n-- what the breakdown says --")
    t = timed.get("_query_timings") or {}
    queries = t.get("queries") or []
    check("it names every query the request ran", len(queries) >= 25, str(len(queries)))
    check("the count agrees with the list", t.get("query_count") == len(queries))
    labels = [q["label"] for q in queries]
    check("no query is left unnamed",
          not [l for l in labels if l == "unknown" or l.startswith("line:")],
          str([l for l in labels if l == "unknown" or l.startswith("line:")][:5]))
    for expected in ("top_career_runs", "top_high_scores", "top_career_wickets",
                     "top_partnerships", "most_matches", "top_allrounders"):
        check(f"the board `{expected}` is timed under its own name",
              expected in labels, str(labels[:6]))
    for expected in ("resolve_scope", "user_can_view_org_private",
                     "org_available_categories"):
        check(f"the non-board read `{expected}` is timed too", expected in labels)

    print("\n-- the JIT compiler is switched off for this transaction --")
    # Measured on production: a board reading v_effective_player_season_stats
    # plans at ~5.3M, so Postgres compiles 177 functions at 505ms to run a
    # query that then takes ~580ms — half the cost of every one of the
    # fourteen boards that read it.
    check("the request switches JIT off before running a board",
          "SET LOCAL jit = off" in labels)
    first = min(queries, key=lambda x: x["n"])
    check("and does it FIRST, so every board that follows is covered",
          first["label"] == "SET LOCAL jit = off", f"first was {first['label']}")
    check("every entry says where in the request it ran",
          sorted(q["n"] for q in queries) == list(range(len(queries))))
    check("the setting itself costs almost nothing",
          next(q["ms"] for q in queries if q["label"] == "SET LOCAL jit = off") < 25,
          str(next(q["ms"] for q in queries if q["label"] == "SET LOCAL jit = off")))
    async with Session() as session:
        jit_state = (await session.execute(text("SHOW jit"))).scalar()
    check("and it is transaction-scoped, so a pooled connection never keeps it",
          jit_state == "on", f"a fresh session reports jit={jit_state}")
    check("slowest first", labels == [q["label"] for q in
                                      sorted(queries, key=lambda x: x["ms"], reverse=True)])
    check("every query reports a duration",
          all(isinstance(q["ms"], float) and q["ms"] >= 0 for q in queries))
    check("a board query reports how many rows it returned",
          any(q["rows"] is not None for q in queries))
    check("the total is at least what the queries cost",
          t.get("total_ms", 0) >= t.get("query_ms", 0),
          f"total={t.get('total_ms')} query={t.get('query_ms')}")
    check("and the remainder is reported separately",
          abs((t.get("query_ms", 0) + t.get("other_ms", 0)) - t.get("total_ms", 0)) < 0.5)
    check("the timings do not disturb the boards",
          all(k in timed for k in BOARD_KEYS)
          and timed["batting"]["top_career_runs"] == plain["batting"]["top_career_runs"])

    print("\n-- naming the club's players narrows the view without moving a row --")
    check("the club's players are resolved once, up front",
          "club_player_ids" in labels)
    runs_board = timed["batting"]["top_career_runs"]
    check("the club's own top scorer leads its board",
          runs_board and runs_board[0]["player_id"] == str(PLAYER),
          str(runs_board[:1]))
    everyone = str(timed)
    check("a rival club's bigger scorer appears on no board of ours",
          str(RIVAL_PLAYER) not in everyone and "Bradman" not in everyone)
    check("and both of this club's scorers are still on it",
          {r["player_id"] for r in runs_board} == {str(PLAYER), str(MATE)},
          str([r["player_id"] for r in runs_board]))
    # Structural, so a board added later cannot quietly skip the narrowing and
    # put the platform-wide scan back. Every board that reads the view carries
    # the gender clause too, so the two must appear together, always.
    src = (Path(__file__).resolve().parent.parent
           / "app" / "routers" / "records.py").read_text()
    with_club = src.count("+ pss_club_clause + pss_gender_clause + ")
    total = src.count("+ pss_gender_clause + ")
    check("every board that reads the view carries the club clause",
          with_club == total and total >= 14, f"{with_club} of {total}")
    async with Session() as session:
        empty = await get_records(
            str(EMPTY_ORG), season_id=None, grade_id=None, grade_name=None,
            finals_only=False, captain_only=False, gender=None, categories=None,
            formats=None, competitions=None, debug_timing=False, db=session, viewer=None)
    # A club with no players binds an EMPTY array, which asyncpg cannot type
    # without the CAST. Empty correctly matches nothing.
    check("a club with no players answers rather than raising",
          all(k in empty for k in BOARD_KEYS))
    check("and its boards are empty",
          not empty["batting"]["top_career_runs"] and not empty["bowling"]["top_career_wickets"])

    print("\n-- a slow request says so in the log, an ordinary one stays quiet --")
    records_logger = logging.getLogger("app.routers.records")

    class Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.lines: list[str] = []

        def emit(self, record):
            self.lines.append(record.getMessage())

    cap = Capture()
    records_logger.addHandler(cap)
    original = records_router.SLOW_RECORDS_LOG_MS
    try:
        async with Session() as session:
            await records(session)
        check("a fast request logs nothing", not cap.lines, str(cap.lines[:1]))
        records_router.SLOW_RECORDS_LOG_MS = 0.0
        async with Session() as session:
            await records(session)
        check("a slow one logs exactly one line", len(cap.lines) == 1, str(len(cap.lines)))
        line = cap.lines[0] if cap.lines else ""
        check("the line names the club", str(ORG) in line)
        check("it says how long the whole request took", "total=" in line)
        check("how many queries ran", "queries=" in line)
        check("and names the worst offenders", "slowest=[" in line and "ms" in line)
        check("the worst offenders are named boards, not line numbers",
              "top_" in line or "most_" in line or "resolve_scope" in line, line[:200])
        # The log fires for a signed-out visitor, who never sees the payload
        # breakdown — which is the whole point of logging as well as returning.
        # They also pay for one query the admin does not: working out which
        # players the club has hidden, which an admin is allowed to see anyway.
        check("an admin's request skips the hidden-players read",
              "hidden_player_ids" not in labels)
        check("a signed-out visitor pays for that one read and nothing else",
              f"queries={t['query_count'] + 1}" in line,
              f"expected queries={t['query_count'] + 1} in {line[:160]}")
    finally:
        records_router.SLOW_RECORDS_LOG_MS = original
        records_logger.removeHandler(cap)

    print("\n-- a filtered request is timed the same way --")
    async with Session() as session:
        scoped = await records(
            session, season_id=str(SEASON), debug_timing=True, viewer=Viewer(ADMIN))
    st = scoped.get("_query_timings") or {}
    check("a season-filtered request reports its own breakdown", bool(st.get("queries")))
    check("including the season resolution itself",
          "resolve_season_filter" in [q["label"] for q in st.get("queries", [])])

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
