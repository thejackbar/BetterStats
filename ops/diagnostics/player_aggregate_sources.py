"""Where a player's career header actually comes from, row by row.

Reported off a live profile: the innings list read 336 innings and 16 hundreds
while the career header above it read 508 and 28, with nine seasons at EXACTLY
2.000x on both runs and innings. Exact doubling across that many seasons is the
same rows counted twice, not partial scorecard coverage — and nothing readable
from outside says WHICH of the five branches of
`v_effective_player_season_stats` is contributing them.

Read-only. Run it against a club that holds both a CricketStatz import and a
Cricket Australia sync:

    docker compose exec -T betterstats-backend \
        python ops/diagnostics/player_aggregate_sources.py <player-uuid> [year]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.models.db import async_session_maker  # noqa: E402


async def main(pid: str, year: int) -> None:
    async with async_session_maker() as db:
        print("--- career header, per branch of the effective view")
        for r in (await db.execute(text("""
            SELECT source, COUNT(*) AS n,
                   COALESCE(SUM(matches), 0) m,
                   COALESCE(SUM(batting_innings), 0) i,
                   COALESCE(SUM(runs), 0) r,
                   COALESCE(SUM(hundreds), 0) h
              FROM v_effective_player_season_stats
             WHERE player_id = :p
             GROUP BY source ORDER BY source
        """), {"p": pid})).mappings():
            print(f"  {r['source']:18} rows={r['n']:<4} matches={r['m']:<5} "
                  f"innings={r['i']:<5} runs={r['r']:<6} 100s={r['h']}")

        print(f"--- every row the view emits for {year}")
        for r in (await db.execute(text("""
            SELECT v.source, s.id AS sid, s.name, s.organisation_id AS org,
                   v.matches, v.batting_innings, v.runs, v.hundreds
              FROM v_effective_player_season_stats v
              JOIN seasons s ON s.id = v.season_id
             WHERE v.player_id = :p AND s.year = :y
             ORDER BY v.source
        """), {"p": pid, "y": year})).mappings():
            print(f"  {r['source']:16} season={str(r['sid'])[:8]} "
                  f"{str(r['name'])[:24]:24} m={r['matches']} "
                  f"inn={r['batting_innings']} runs={r['runs']} 100s={r['hundreds']}")

        print(f"--- and the raw player_season_stats rows behind them for {year}")
        for r in (await db.execute(text("""
            SELECT pss.source, s.id AS sid, s.name, s.grassroots_id,
                   pss.matches, pss.batting_innings, pss.runs
              FROM player_season_stats pss JOIN seasons s ON s.id = pss.season_id
             WHERE pss.player_id = :p AND s.year = :y
        """), {"p": pid, "y": year})).mappings():
            print(f"  {str(r['source']):10} season={str(r['sid'])[:8]} "
                  f"ca={str(r['grassroots_id'])[:8]:8} {str(r['name'])[:24]:24} "
                  f"m={r['matches']} inn={r['batting_innings']} runs={r['runs']}")

        # THE ONE THING A DEPLOY CAN GET WRONG SILENTLY. If this reads True the
        # view in the database is the pre-v9.70.6 definition, whatever the code
        # on disk says.
        body = (await db.execute(text(
            "SELECT pg_get_viewdef(to_regclass('v_effective_player_season_stats'))"
        ))).scalar() or ""
        seg = body.split("player_games", 1)[1][:4000] if "player_games" in body else ""
        print("--- aggregate branch still carries pair_prefers_import:",
              "pair_prefers_import" in seg)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2006))
