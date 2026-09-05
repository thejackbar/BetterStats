"""Correct `not_out` on retirements already stored as dismissals.

Until this shipped, `sync.py` set `not_out = (dismissalTypeId == 1)`, so every
Retired Not Out and Retired Hurt landed in the database flagged as a wicket.
Any figure worked out from our own scorecards then counted it against the
batter's average: 77 runs from 8 innings read as 12.83 where Cricket Australia,
PlayCricket and the Laws all say 15.40.

The sync is fixed going forward, but a stored row is only rewritten when the
game is re-synced, and an incremental run never revisits a settled match. This
repairs what is already there, in place, touching ONE column.

No re-fetch and no network at all: the dismissal name is already stored on the
row, so the correction is a plain UPDATE. That makes it quick enough to run
across the whole platform and safe to re-run (idempotent — a second pass
matches nothing).

`services/dismissal.py` decides what qualifies, so this and the sync cannot
disagree. **A bare "retired" is deliberately NOT touched**: that is Law
25.4.3's retired-out, a genuine wicket, and CA counts it as one.

Dry run by default, per the house rule.

Usage from the backend container:
  # one club, dry run:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_retired_not_out <org-id-or-slug>
  # every club, for real:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_retired_not_out all --apply
"""

import asyncio
import sys

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker
from app.services.dismissal import not_out_sql

# The two per-game tables that carry a batting innings. `player_season_stats`
# is deliberately untouched: its rows come from CA's own season aggregate,
# which already had this right, and rewriting them would replace the figure we
# reconcile against with one derived from our own scorecards.
_TABLES = ("batting_innings", "manual_batting_innings")


def _org_filter(table: str) -> tuple[str, str]:
    """(join, where) restricting a batting table to one organisation.

    A synced innings reaches its club through the player; a manual one through
    its own game row. Both are org-scoped, just not by the same column.
    """
    if table == "manual_batting_innings":
        return (
            "JOIN manual_games mg ON mg.id = t.manual_game_id",
            "mg.organisation_id = :org_id",
        )
    return (
        "JOIN players p ON p.id = t.player_id",
        "p.organisation_id = :org_id",
    )


async def _count(session, table: str, org_id) -> int:
    join, where = _org_filter(table) if org_id else ("", "")
    sql = f"""
        SELECT COUNT(*) FROM {table} t
        {join}
        WHERE t.not_out IS NOT TRUE
          AND t.did_not_bat IS NOT TRUE
          AND {not_out_sql('t.dismissal_type')}
          {f'AND {where}' if where else ''}
    """
    params = {"org_id": org_id} if org_id else {}
    return int((await session.execute(sql_text(sql), params)).scalar() or 0)


async def _apply(session, table: str, org_id) -> int:
    join, where = _org_filter(table) if org_id else ("", "")
    # The org restriction needs a subquery rather than a joined UPDATE so the
    # statement reads the same whether or not a club was named.
    scope = ""
    if org_id:
        key = "id" if table == "batting_innings" else "id"
        scope = f"""
          AND {table}.{key} IN (
              SELECT t.{key} FROM {table} t {join} WHERE {where}
          )
        """
    sql = f"""
        UPDATE {table}
        SET not_out = TRUE
        WHERE not_out IS NOT TRUE
          AND did_not_bat IS NOT TRUE
          AND {not_out_sql(f'{table}.dismissal_type')}
          {scope}
    """
    params = {"org_id": org_id} if org_id else {}
    res = await session.execute(sql_text(sql), params)
    return res.rowcount or 0


async def _resolve_org(session, ref: str):
    row = (await session.execute(sql_text(
        "SELECT id, name FROM organisations WHERE id::text = :ref OR slug = :ref"
    ), {"ref": ref})).first()
    if not row:
        raise SystemExit(f"No organisation matching {ref!r}")
    return row[0], row[1]


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    apply = "--apply" in sys.argv[1:]
    ref = args[0] if args else "all"

    async with async_session_maker() as session:
        org_id, label = (None, "every club")
        if ref.lower() != "all":
            org_id, label = await _resolve_org(session, ref)
            label = f"{label} ({org_id})"

        print(f"Retirements stored as dismissals — {label}")
        total = 0
        for table in _TABLES:
            n = await _count(session, table, org_id)
            total += n
            print(f"  {table}: {n} row(s) to correct")

        if not total:
            print("Nothing to do. Every retirement is already recorded as a not out.")
            return

        if not apply:
            print(f"\nDry run. {total} row(s) would be corrected. Re-run with --apply to write.")
            return

        written = 0
        for table in _TABLES:
            written += await _apply(session, table, org_id)
        await session.commit()
        print(f"\nCorrected {written} row(s).")
        print("Averages worked out from scorecards now agree with Cricket Australia's.")
        print("A club whose season totals came from Fix Missing Totals should re-run it,")
        print("since those rows were rolled up from the old flag.")


if __name__ == "__main__":
    asyncio.run(main())
