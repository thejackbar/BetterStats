"""EXPLAIN (ANALYZE, BUFFERS) the club dashboard's leaderboard queries.

WHY THIS EXISTS
    The public club home page loads a top-5 batting and bowling board with no
    season and no category picked. For a club with many seasons that opening
    call took about 28 seconds. This runs the SAME service function the route
    runs, through the same scope resolution, and for every large statement it
    sends it prints the Postgres plan (with the real bound parameters) and then
    runs it once more plain, so the wall-clock figure is the control number to
    compare a fix against.

READ ONLY
    Every statement is a SELECT or an EXPLAIN of one. The session is rolled back
    at the end. Nothing is written, so there is no --apply.

USAGE (inside the backend container)
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board bowling
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --season <season uuid>
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --no-explain   # timing only

    The org argument is a slug or an organisation id.
"""
from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import select, text
from sqlalchemy.sql.elements import TextClause

from app.models.db import Organisation, async_session_maker, engine
from app.routers.auth import public_junior_hiding
from app.services import grade_scope, stats_display
from app.services.aggregations import (
    get_batting_leaderboard_extended,
    get_bowling_leaderboard_extended,
)

# Statements shorter than this are lookups (season ids, minimums, grade names).
# The board query is several kilobytes of SQL.
BIG_STATEMENT_CHARS = 1500


class ExplainingSession:
    """Delegates to a real session, EXPLAINing each big raw-SQL statement first."""

    def __init__(self, session, explain: bool):
        self._session = session
        self._explain = explain
        self.timings: list[tuple[str, float]] = []

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def execute(self, statement, params=None, *args, **kwargs):
        sql = statement.text if isinstance(statement, TextClause) else None
        big = sql is not None and len(sql) >= BIG_STATEMENT_CHARS
        label = " ".join(sql.split())[:90] if sql else str(type(statement).__name__)
        if big and self._explain:
            print(f"\n=== EXPLAIN (ANALYZE, BUFFERS): {label}...\n", flush=True)
            started = time.perf_counter()
            plan = await self._session.execute(
                text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params)
            for (line,) in plan.all():
                print(line)
            print(f"\n--- explain run took {time.perf_counter() - started:.2f}s", flush=True)
        started = time.perf_counter()
        result = await self._session.execute(statement, params, *args, **kwargs)
        elapsed = time.perf_counter() - started
        if big:
            self.timings.append((label, elapsed))
            print(f"--- plain run of that statement: {elapsed:.2f}s", flush=True)
        return result


async def _org_id(session, org: str) -> str:
    row = (await session.execute(
        select(Organisation.id, Organisation.slug, Organisation.name)
        .where((Organisation.slug == org) | (Organisation.id == _as_uuid(org))))
    ).first()
    if not row:
        raise SystemExit(f"No organisation with slug or id {org!r}")
    print(f"Club: {row.name} ({row.slug}) {row.id}")
    return str(row.id)


def _as_uuid(value: str):
    import uuid
    try:
        return uuid.UUID(value)
    except ValueError:
        return uuid.UUID(int=0)


async def main(args) -> None:
    async with async_session_maker() as real:
        org_id = await _org_id(real, args.org)
        db = ExplainingSession(real, explain=not args.no_explain)

        # Exactly the route's own scope: the club default, public viewer, no
        # season, no grade, 5 rows. That is the dashboard's opening request.
        hiding = await public_junior_hiding(real, None, org_id, with_players=False)
        scope = await grade_scope.resolve_scope(
            db, org_id, args.categories, formats=None, competitions=None,
            hidden_grade_ids=hiding.grade_ids)

        started = time.perf_counter()
        if args.board == "batting":
            rows = await get_batting_leaderboard_extended(
                db, org_id, args.season, None, "total_runs", 5,
                min_runs=0,
                min_rate_innings=await stats_display.resolve_min_rate_innings(real, org_id, None),
                scope=scope)
        else:
            rows = await get_bowling_leaderboard_extended(
                db, org_id, args.season, None, "total_wickets", 5,
                min_overs=0, min_wickets=0,
                min_rate_spells=await stats_display.resolve_min_rate_spells(real, org_id, None),
                scope=scope)
        total = time.perf_counter() - started

        print(f"\n=== {args.board} board: {len(rows)} rows, "
              f"{total:.2f}s including {'EXPLAIN runs and ' if not args.no_explain else ''}plain runs")
        for label, elapsed in db.timings:
            print(f"  plain run {elapsed:6.2f}s  {label}")
        await real.rollback()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("org", help="club slug or organisation id")
    parser.add_argument("--board", choices=["batting", "bowling"], default="batting")
    parser.add_argument("--season", default=None, help="season id; omitted means every season")
    parser.add_argument("--categories", default=None,
                        help="comma-separated grade categories; omitted is the club default")
    parser.add_argument("--no-explain", action="store_true", help="time the plain run only")
    asyncio.run(main(parser.parse_args()))
