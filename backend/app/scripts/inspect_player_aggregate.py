"""Where a player's career header actually comes from, branch by branch.

Read-only. No write, no upstream call.

Reported off a live profile: the innings list read 336 innings and 16 hundreds
while the career header above it read 508 and 28 — and NINE seasons sat at
exactly 2.000x on BOTH runs and innings at once. Exact doubling that many times
is the same rows counted twice, not partial scorecard coverage. Nothing
readable from outside says WHICH of the five branches of
`v_effective_player_season_stats` is contributing them, which is what this is
for.

The last line is the one a deploy can get wrong silently: it reads the view
definition back out of `pg_get_viewdef`, so it reports what Postgres actually
holds rather than what the code on disk says it should.

    python -m app.scripts.inspect_player_aggregate <player-uuid> [year]
"""
import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker


async def main(pid: str, year: int) -> None:
    async with async_session_maker() as db:
        print("--- career header, per branch of the effective view")
        for r in (await db.execute(text("""
            SELECT source, COUNT(*) AS n,
                   COALESCE(SUM(matches), 0) AS m,
                   COALESCE(SUM(batting_innings), 0) AS i,
                   COALESCE(SUM(runs), 0) AS r,
                   COALESCE(SUM(hundreds), 0) AS h
              FROM v_effective_player_season_stats
             WHERE player_id = :p
             GROUP BY source ORDER BY source
        """), {"p": pid})).mappings():
            print("  %-18s rows=%-4s matches=%-5s innings=%-5s runs=%-6s 100s=%s"
                  % (r["source"], r["n"], r["m"], r["i"], r["r"], r["h"]))

        print("--- every row the view emits for %s" % year)
        for r in (await db.execute(text("""
            SELECT v.source, s.id AS sid, s.name, v.matches, v.batting_innings,
                   v.runs, v.hundreds
              FROM v_effective_player_season_stats v
              JOIN seasons s ON s.id = v.season_id
             WHERE v.player_id = :p AND s.year = :y
             ORDER BY v.source
        """), {"p": pid, "y": year})).mappings():
            print("  %-16s season=%s %-24s m=%s inn=%s runs=%s 100s=%s"
                  % (r["source"], str(r["sid"])[:8], str(r["name"])[:24],
                     r["matches"], r["batting_innings"], r["runs"], r["hundreds"]))

        print("--- and the raw player_season_stats rows behind them")
        for r in (await db.execute(text("""
            SELECT pss.source, s.id AS sid, s.name, s.grassroots_id AS ca,
                   pss.matches, pss.batting_innings, pss.runs
              FROM player_season_stats pss
              JOIN seasons s ON s.id = pss.season_id
             WHERE pss.player_id = :p AND s.year = :y
        """), {"p": pid, "y": year})).mappings():
            print("  %-10s season=%s ca=%-8s %-24s m=%s inn=%s runs=%s"
                  % (str(r["source"]), str(r["sid"])[:8], str(r["ca"])[:8],
                     str(r["name"])[:24], r["matches"], r["batting_innings"],
                     r["runs"]))

        body = (await db.execute(text(
            "SELECT pg_get_viewdef(to_regclass('v_effective_player_season_stats'))"
        ))).scalar() or ""
        # The reliable needle is `superseded_by_game_id` — the SAME one
        # superseded_ddl.verify() uses. Do NOT grep for `pair_prefers_import`:
        # since v9.70.6 the aggregate branch counts only UNPAIRED imports
        # (`superseded_by_game_id IS NULL`) and never mentions
        # `pair_prefers_import`, so a healthy view reads False on that word and
        # sends you chasing a bug that is not there — that exact red herring
        # cost a round-trip once already.
        print("--- deployed view carries the pairing clause (superseded_by_game_id):",
              "superseded_by_game_id" in body)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2006))
