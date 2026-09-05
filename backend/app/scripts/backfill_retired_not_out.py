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

It also repairs the synthetic season rows a club's "Fix Missing Totals" run
wrote from the old flag (``player_season_stats.source = 'backfill'``). Those
have to be fixed HERE rather than by pressing that button again: its INSERT ends
``ON CONFLICT (player_id, season_id) DO NOTHING``, so a second run writes
nothing at all to a row that already exists. Rows CA itself supplied
(``source = 'api'``) are never touched, since CA already had this right and
those are the figures we reconcile against.

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

# The two per-game tables that carry a batting innings.
_TABLES = ("batting_innings", "manual_batting_innings")

# Repair for the synthetic season rows only. `source = 'backfill'` marks a row
# "Fix Missing Totals" computed FROM our own per-game data, for a (player,
# season) CA omitted — so it inherited the old flag and has to move with it.
# `not_outs` and `ducks` are the two figures that flip: a retirement was
# counted as a wicket, and a retirement on 0 was counted as a duck.
_SEASON_ROW_SQL = """
    WITH innings AS (
        SELECT bi.player_id, gr.season_id,
               COUNT(*) FILTER (WHERE bi.not_out)                       AS not_outs,
               COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT bi.not_out)   AS ducks
        FROM batting_innings bi
        JOIN games g    ON g.id = bi.game_id
        JOIN grades gr  ON gr.id = g.grade_id
        JOIN seasons s  ON s.id = gr.season_id
        WHERE COALESCE(LOWER(bi.dismissal_type), '')
              NOT IN ('absent', 'did not bat', 'dnb')
          {org}
        GROUP BY bi.player_id, gr.season_id
    )
    UPDATE player_season_stats pss
       SET not_outs = i.not_outs, ducks = i.ducks
      FROM innings i
     WHERE pss.player_id = i.player_id
       AND pss.season_id = i.season_id
       AND pss.source = 'backfill'
       AND (pss.not_outs IS DISTINCT FROM i.not_outs
            OR pss.ducks IS DISTINCT FROM i.ducks)
"""


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


async def _season_rows(session, org_id, *, apply: bool) -> int:
    """Bring `source='backfill'` season rows back in line with the corrected
    per-game rows. Counts by running the same UPDATE and rolling it back, so a
    dry run reports the real figure rather than an estimate of one."""
    sql = _SEASON_ROW_SQL.format(org="AND s.organisation_id = :org_id" if org_id else "")
    params = {"org_id": org_id} if org_id else {}
    if apply:
        res = await session.execute(sql_text(sql), params)
        return res.rowcount or 0
    sp = await session.begin_nested()
    try:
        res = await session.execute(sql_text(sql), params)
        return res.rowcount or 0
    finally:
        await sp.rollback()


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

        if not apply:
            # The season-row repair is counted against the CURRENT per-game
            # rows, so on a dry run it reports what is already out of step and
            # not what the correction above will additionally move. A real run
            # fixes the innings first, then re-derives, so it catches both.
            stale = await _season_rows(session, org_id, apply=False)
            print(f"  player_season_stats (Fix Missing Totals rows): "
                  f"at least {stale} row(s) to re-derive")
            if not total and not stale:
                print("\nNothing to do. Every retirement is already recorded as a not out.")
                return
            print(f"\nDry run. Nothing written. Re-run with --apply.")
            return

        written = 0
        for table in _TABLES:
            written += await _apply(session, table, org_id)
        # Only after the per-game rows are right, or this re-derives from the
        # very flag it is meant to correct.
        rederived = await _season_rows(session, org_id, apply=True)
        await session.commit()
        print(f"\nCorrected {written} innings.")
        print(f"Re-derived {rederived} Fix Missing Totals season row(s).")
        print("Averages worked out from scorecards now agree with Cricket Australia's.")
        print("Nothing else to run: pressing Fix Missing Totals again would write")
        print("nothing, since its INSERT ends ON CONFLICT DO NOTHING.")


if __name__ == "__main__":
    asyncio.run(main())
