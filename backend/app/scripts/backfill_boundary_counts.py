"""Take the impossible boundary counts out of what is already stored.

Reported off the record boards: "most sixes in an innings" was topped by a 2006
Under 12 innings of 8 runs with 30 sixes. Verified against Cricket Australia's
own live feed — it sends `sixesScored: 30` for that innings — so this is not a
parsing fault and no re-sync repairs it. `services/boundary_counts.py` is the
rule and the sync applies it going forward; this is the same rule applied to
the history already in the database.

No network at all: the runs are on the row beside the boundary counts, so it is
a plain UPDATE, quick enough to run platform-wide and idempotent. Dry run by
default, per the house rule.

    python -m app.scripts.backfill_boundary_counts <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker

# THE SQL MIRROR OF `boundary_counts.clean`, AND THE SUITE ASSERTS THE TWO
# AGREE ROW BY ROW. Each column is judged on its own first — in the reported
# innings the one four is perfectly possible and only the sixes are not — and
# only when the pair still cannot fit the runs together does the other go too.
_CLEANED = """
    SELECT {key} AS key,
           CASE WHEN COALESCE(f1, 0) * 4 + COALESCE(s1, 0) * 6 > runs
                THEN NULL ELSE f1 END AS new_fours,
           CASE WHEN COALESCE(f1, 0) * 4 + COALESCE(s1, 0) * 6 > runs
                THEN NULL ELSE s1 END AS new_sixes,
           fours, sixes
      FROM (
        SELECT {key} AS {key}, runs, fours, sixes,
               CASE WHEN fours IS NOT NULL AND (fours < 0 OR fours * 4 > runs)
                    THEN NULL ELSE fours END AS f1,
               CASE WHEN sixes IS NOT NULL AND (sixes < 0 OR sixes * 6 > runs)
                    THEN NULL ELSE sixes END AS s1
          FROM {table}
         WHERE runs IS NOT NULL AND runs >= 0
           AND (fours IS NOT NULL OR sixes IS NOT NULL)
      ) judged
"""

# (table, primary key, the runs column) — every table that stores a boundary
# count beside the runs it has to fit inside.
TABLES = (
    ("batting_innings", "id", "runs"),
    ("manual_batting_innings", "id", "runs"),
    ("player_season_stats", "id", "runs"),
)


def _sql(table: str, key: str) -> str:
    return _CLEANED.format(table=table, key=key)


async def repair(org: str, apply: bool) -> dict:
    out: dict[str, int] = {}
    async with async_session_maker() as db:
        org_id = None
        if org != "all":
            org_id = (await db.execute(text(
                "SELECT id FROM organisations WHERE id::text = :o OR slug = :o"),
                {"o": org})).scalar()
            if org_id is None:
                raise SystemExit(f"no club matches {org!r}")

        for table, key, _runs in TABLES:
            scope, params = "", {}
            if org_id is not None:
                if table == "batting_innings":
                    scope = ("AND player_id IN (SELECT id FROM players "
                             "WHERE organisation_id = :org)")
                elif table == "manual_batting_innings":
                    scope = ("AND manual_game_id IN (SELECT id FROM manual_games "
                             "WHERE organisation_id = :org)")
                else:
                    scope = ("AND player_id IN (SELECT id FROM players "
                             "WHERE organisation_id = :org)")
                params["org"] = str(org_id)
            inner = _sql(table, key).replace(
                "AND (fours IS NOT NULL OR sixes IS NOT NULL)",
                f"AND (fours IS NOT NULL OR sixes IS NOT NULL) {scope}")
            found = (await db.execute(text(f"""
                SELECT COUNT(*) FROM ({inner}) c
                 WHERE c.new_fours IS DISTINCT FROM c.fours
                    OR c.new_sixes IS DISTINCT FROM c.sixes
            """), params)).scalar() or 0
            out[table] = int(found)
            if apply and found:
                await db.execute(text(f"""
                    UPDATE {table} t
                       SET fours = c.new_fours, sixes = c.new_sixes
                      FROM ({inner}) c
                     WHERE t.{key} = c.key
                       AND (c.new_fours IS DISTINCT FROM c.fours
                            OR c.new_sixes IS DISTINCT FROM c.sixes)
                """), params)
        if apply:
            await db.commit()
    return out


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    org = args[0] if args else "all"
    found = await repair(org, apply)
    total = sum(found.values())
    for table, n in found.items():
        print(f"  {table}: {n} row(s) with a boundary count that cannot fit the runs")
    if not total:
        print("Nothing to repair.")
    elif apply:
        print(f"Repaired {total} row(s) — those counts now read as not recorded.")
    else:
        print(f"Dry run: {total} row(s) would be repaired. Re-run with --apply.")


if __name__ == "__main__":
    asyncio.run(main())
