"""EXPLAIN (ANALYZE, BUFFERS) the club dashboard's queries.

WHY THIS EXISTS
    The public club home page loads a top-5 batting and bowling board, the
    upcoming and recently achieved milestones and the club summary, with no
    season and no category picked. For a club with many seasons the opening
    leaderboard call took about 28 seconds. This runs the SAME service function
    the route runs, through the same scope resolution, times every statement it
    sends, and for each large raw-SQL SELECT prints the Postgres plan (with the
    real bound parameters) and then runs it once more plain, so the wall-clock
    figure is the control number to compare a fix against.

READ ONLY
    Every statement is a SELECT or an EXPLAIN of one. A statement that mentions
    INSERT, UPDATE, DELETE or similar is never EXPLAINed (ANALYZE would run it),
    and the session is rolled back at the end. Nothing is written, so there is
    no --apply.

USAGE (inside the backend container)
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board bowling
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board upcoming-milestones
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board recent-milestones
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board summary
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --season <season uuid>
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --no-explain   # timing only
    python -m app.scripts.explain_leaderboard summer-hill-cricket-club --board recent-milestones --explain-min-chars 300

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
    get_club_summary,
    get_recently_achieved_milestones_for_org,
    get_upcoming_milestones_for_org,
)

# Statements shorter than this are lookups (season ids, minimums, grade names).
# A board query is several kilobytes of SQL. --explain-min-chars lowers it for
# the milestone and summary calls, whose statements are shorter.
BIG_STATEMENT_CHARS = 1500
# Every statement slower than this is listed in the closing summary.
REPORT_SECONDS = 0.25
_WRITES = ("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "ALTER", "DROP", "CREATE")


class ExplainingSession:
    """Delegates to a real session, EXPLAINing each big raw-SQL SELECT first."""

    def __init__(self, session, explain: bool, min_chars: int = BIG_STATEMENT_CHARS):
        self._session = session
        self._explain = explain
        self._min_chars = min_chars
        self.timings: list[tuple[str, float]] = []

    def __getattr__(self, name):
        return getattr(self._session, name)

    def _explainable(self, sql) -> bool:
        if not self._explain or sql is None or len(sql) < self._min_chars:
            return False
        head = sql.lstrip().upper()
        if not head.startswith(("WITH", "SELECT")):
            return False
        words = set(head.replace("(", " ").replace(")", " ").replace(",", " ").split())
        return not any(w in words for w in _WRITES)

    async def execute(self, statement, params=None, *args, **kwargs):
        sql = statement.text if isinstance(statement, TextClause) else None
        label = " ".join(sql.split())[:90] if sql else type(statement).__name__
        if self._explainable(sql):
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
        if elapsed >= REPORT_SECONDS:
            self.timings.append((label, elapsed))
            print(f"--- plain run: {elapsed:.2f}s  {label}", flush=True)
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
        db = ExplainingSession(real, explain=not args.no_explain,
                               min_chars=args.explain_min_chars)

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
        elif args.board == "bowling":
            rows = await get_bowling_leaderboard_extended(
                db, org_id, args.season, None, "total_wickets", 5,
                min_overs=0, min_wickets=0,
                min_rate_spells=await stats_display.resolve_min_rate_spells(real, org_id, None),
                scope=scope)
        elif args.board == "upcoming-milestones":
            rows = await get_upcoming_milestones_for_org(db, org_id, 200)
        elif args.board == "recent-milestones":
            rows = await get_recently_achieved_milestones_for_org(db, org_id)
        else:
            rows = [await get_club_summary(db, org_id, args.season, None, scope=scope)]
        total = time.perf_counter() - started

        print(f"\n=== {args.board}: {len(rows)} rows, "
              f"{total:.2f}s including {'EXPLAIN runs and ' if not args.no_explain else ''}plain runs")
        for label, elapsed in sorted(db.timings, key=lambda t: -t[1]):
            print(f"  plain run {elapsed:6.2f}s  {label}")
        await real.rollback()
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("org", help="club slug or organisation id")
    parser.add_argument("--board", default="batting",
                        choices=["batting", "bowling", "upcoming-milestones",
                                 "recent-milestones", "summary"])
    parser.add_argument("--season", default=None, help="season id; omitted means every season")
    parser.add_argument("--categories", default=None,
                        help="comma-separated grade categories; omitted is the club default")
    parser.add_argument("--no-explain", action="store_true", help="time the plain run only")
    parser.add_argument("--explain-min-chars", type=int, default=BIG_STATEMENT_CHARS,
                        help="EXPLAIN raw-SQL SELECTs at least this long (default %(default)s); "
                             "lower it for the milestone and summary calls")
    asyncio.run(main(parser.parse_args()))
