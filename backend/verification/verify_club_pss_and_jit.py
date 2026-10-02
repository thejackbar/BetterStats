"""The record book reads the season totals once, and every connection has JIT off.

Two causes of a slow public stats site, found by timing a real database at the
production's size:

1. **JIT was on for everything but the record book.** The `v_effective_*`
   views plan at a cost of millions, so Postgres compiled a plan before every
   read: one read of `v_effective_player_season_stats` was 7.2s with JIT on and
   0.66s with it off. Milestones, the leaderboard, the dashboard and the player
   page all pay it. The fix is a startup parameter on the app's engine.
2. **`GET /records/{org}` read that view fourteen times.** Each read rebuilds
   the whole view, so the unfiltered record book was a flat ~12s. The club's
   rows are now copied out once into a temp table and the boards read the copy.

This runs the SHIPPED route body over the real view DDL (`superseded_ddl`, which
the lifespan re-applies on every boot), not the older migration definitions, and
asserts on what the database was actually asked.

THE CONTROL RUN is the same file against the previous commit. It must FAIL on
exactly the two reported behaviours (JIT reads `on`; the view is read many times)
and must not crash: every new name is read through a presence-safe accessor.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_pss_and_jit.py [--write-golden F | --golden F]

`--write-golden` is for the CONTROL checkout: it records what that commit's
record book returned, so the commit under test can be compared to it.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import event, text

import verify_records_timing as base
from app.services import superseded_ddl

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


def arg(flag: str):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else None


# Requests that between them reach every board: nothing filtered (the season
# totals path), a format filter (an active scope, the per-innings path), one
# season, a grade picked by name, and finals only.
VARIANTS = {
    "unfiltered": {},
    "format scope": {"formats": "one_day"},
    "one season": {"season_id": str(base.SEASON)},
    "grade by name": {"grade_name": "1st Grade"},
    "finals only": {"finals_only": True},
}

VIEW_READ = re.compile(r"\b(?:FROM|JOIN)\s+v_effective_player_season_stats\b", re.I)
COPY_READ = re.compile(r"\b(?:FROM|JOIN)\s+_club_pss\b", re.I)


async def extra_seed(session) -> None:
    """What the base seed lacks: a hand-entered game, so the view's manual branch
    has something to roll up and the copy has to carry it."""
    mg = uuid.UUID("aaaaaaaa-0000-0000-0000-00000000000a")
    await session.execute(text(
        "INSERT INTO manual_games (id, organisation_id, season_id, grade_id, "
        " played_at, result, match_format) "
        "VALUES (:i, :o, :s, :g, DATE '2025-02-01', 'WIN', 'One Day')"),
        {"i": mg, "o": base.ORG, "s": base.SEASON, "g": base.GRADE})
    await session.execute(text(
        "INSERT INTO manual_batting_innings (manual_game_id, player_id, "
        " innings_number, batting_position, runs, balls, not_out, did_not_bat, "
        " dismissal_type) VALUES (:g, :p, 1, 1, 77, 60, false, false, 'bowled')"),
        {"g": mg, "p": base.PLAYER})
    # One of the seeded games is a final, so the finals-only request has boards.
    await session.execute(text(
        "UPDATE games SET is_final = true WHERE played_at = DATE '2025-01-06'"))
    await session.commit()


def canonical(payload: dict):
    """A payload with every board's row order made irrelevant.

    The copy and the view can break a tie between equal figures differently, and
    this check is about WHICH figures come back, not about how ties are ordered.
    """
    def walk(v):
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items() if k != "_query_timings"}
        if isinstance(v, list):
            return sorted((walk(x) for x in v),
                          key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return v
    return json.dumps(walk(payload), sort_keys=True, default=str)


async def run_variant(**kw):
    """One request on a fresh session, and every statement it sent."""
    sent: list[str] = []

    def grab(conn, cursor, statement, parameters, context, executemany):
        sent.append(statement)

    event.listen(base.engine.sync_engine, "before_cursor_execute", grab)
    try:
        async with base.Session() as session:
            payload = await base.records(session, **kw)
    finally:
        event.remove(base.engine.sync_engine, "before_cursor_execute", grab)
    return payload, sent


async def main() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        # The app's own view definitions, as the lifespan applies them.
        for stmt in superseded_ddl.STATEMENTS:
            await conn.execute(text(stmt))
    async with base.Session() as session:
        await base.seed(session)
        await extra_seed(session)

    print("\n-- every connection the app opens has JIT off --")
    from app.models import db as app_db
    async with app_db.engine.connect() as conn:
        jit = (await conn.execute(text("SHOW jit"))).scalar()
    check("the app's engine opens connections with jit = off", jit == "off",
          f"SHOW jit read {jit!r}")

    print("\n-- the season totals are read once, not once per board --")
    results: dict[str, tuple[dict, list[str]]] = {}
    for name, kw in VARIANTS.items():
        results[name] = await run_variant(**kw)

    _, sent = results["unfiltered"]
    view_reads = sum(1 for s in sent if VIEW_READ.search(s))
    copy_reads = sum(1 for s in sent if COPY_READ.search(s))
    check("an unfiltered request reads the view exactly once", view_reads == 1,
          f"{view_reads} reads of v_effective_player_season_stats")
    check("and the season-total boards read the copy instead", copy_reads >= 10,
          f"{copy_reads} statements read _club_pss")
    # The pairing that makes the two checks above able to fail: the very same
    # statements, counted the same way, on the previous commit.
    check("the count is measuring real boards (a view read or a copy read exists)",
          view_reads + copy_reads >= 10, f"view {view_reads} + copy {copy_reads}")

    _, sent = results["format scope"]
    scoped_view = sum(1 for s in sent if VIEW_READ.search(s))
    check("a filtered request that skips those boards copies nothing it does not read",
          scoped_view <= 1, f"{scoped_view} reads")

    print("\n-- the copy answers exactly what the view answered --")
    golden_out = arg("--write-golden")
    golden_in = arg("--golden")
    got = {name: canonical(payload) for name, (payload, _) in results.items()}
    for name, payload_json in got.items():
        check(f"{name}: the boards are not empty", len(payload_json) > 2000,
              f"{len(payload_json)} bytes")
    if golden_out:
        Path(golden_out).write_text(json.dumps(got, sort_keys=True))
        print(f"  wrote golden for {len(got)} requests to {golden_out}")
    if golden_in:
        want = json.loads(Path(golden_in).read_text())
        for name in VARIANTS:
            check(f"{name}: identical to what the previous commit returned",
                  got.get(name) == want.get(name))
    else:
        print("  (no --golden given: payload comparison skipped)")

    unfiltered = got["unfiltered"]
    check("a rival club's bigger scorer is on no board of ours",
          "Bradman" not in unfiltered and "6996" not in unfiltered)
    check("the hand-entered game is in a season total (the copy carries the manual branch)",
          re.search(r'"runs": 162\b', unfiltered) is not None,
          "PLAYER's 85 api runs plus the 77 hand-entered should read 162 somewhere")

    print("\n-- the copy does not outlive the request --")
    async with base.Session() as session:
        first = await base.records(session)
        left = (await session.execute(
            text("SELECT to_regclass('pg_temp._club_pss')"))).scalar()
        check("the temp table is dropped when the request ends", left is None,
              f"to_regclass returned {left!r}")
        second = await base.records(session)
        check("a second request on the same connection works and agrees",
              canonical(first) == canonical(second))
        await session.execute(text(
            "CREATE TEMP TABLE _club_pss AS SELECT 1 AS stale"))
        third = await base.records(session)
        check("a leftover from a committed request is replaced, not tripped over",
              canonical(third) == canonical(first))

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  FAILED:", f)
    await base.engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
