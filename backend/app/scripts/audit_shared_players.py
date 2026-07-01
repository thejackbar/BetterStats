"""Find players whose CA participant GUID (`grassroots_id`) is shared across
more than one club, and flag any club whose game-level rows for that player
look stale relative to its own aggregate totals.

Background: CA reuses one participant GUID for a person across every club
they've ever played for (see CLAUDE.md "Cross-Club Player Over-Count Fix" /
"per-club player ids"). `_resolve_org_player` in sync.py mints a per-club id
the first time a club syncs a GUID that's already claimed by another club, but
that only takes effect once the club actually re-syncs — a plain "Sync Now"
only re-seeds the aggregate pass, and game-level tables (batting_innings,
bowler_wickets, fielding_stats, game_appearances, ...) only re-attach on a
Full Rebuild (the GR sync skips games it's already inserted). A club that
hasn't had a Full Rebuild since picking up a shared player can sit with
game-level rows undercounting its own `player_season_stats` aggregate
indefinitely — this script surfaces every such case platform-wide instead of
waiting for a support ticket per player.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.audit_shared_players

Read-only — makes no changes. Prints one block per shared GUID, one line per
club, and flags `NEEDS FULL REBUILD` when the club's game-level match/wicket
counts fall short of its own aggregate totals.
"""

import asyncio

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker

# A club is flagged when its game-level count falls short of its own
# aggregate total by more than this many matches/wickets — a small gap can be
# a genuinely in-progress season (games played but not yet scored), not staleness.
STALENESS_THRESHOLD = 2


async def audit() -> None:
    async with async_session_maker() as session:
        shared = await session.execute(
            sql_text(
                "SELECT grassroots_id FROM players "
                "WHERE grassroots_id IS NOT NULL "
                "GROUP BY grassroots_id HAVING COUNT(DISTINCT organisation_id) > 1 "
                "ORDER BY grassroots_id"
            )
        )
        guids = [r[0] for r in shared.all()]

        print(f"Found {len(guids)} CA participant GUIDs shared across multiple clubs.\n")

        flagged = 0
        for guid in guids:
            rows = await session.execute(
                sql_text(
                    """
                    SELECT p.id, p.organisation_id, o.name, p.name
                    FROM players p
                    JOIN organisations o ON o.id = p.organisation_id
                    WHERE p.grassroots_id = :guid
                    ORDER BY o.name
                    """
                ),
                {"guid": guid},
            )
            clubs = rows.all()
            if not clubs:
                continue

            print(f"=== GUID {guid} — {clubs[0][3]} — {len(clubs)} clubs ===")
            for player_id, org_id, org_name, player_name in clubs:
                agg = await session.execute(
                    sql_text(
                        "SELECT COALESCE(SUM(matches), 0), COALESCE(SUM(wickets), 0) "
                        "FROM player_season_stats WHERE player_id = :pid"
                    ),
                    {"pid": player_id},
                )
                agg_matches, agg_wickets = agg.first()

                game_level = await session.execute(
                    sql_text(
                        "SELECT "
                        "  (SELECT COUNT(DISTINCT game_id) FROM game_appearances WHERE player_id = :pid), "
                        "  (SELECT COUNT(*) FROM bowler_wickets WHERE bowler_id = :pid)"
                    ),
                    {"pid": player_id},
                )
                gl_matches, gl_wickets = game_level.first()

                match_gap = agg_matches - gl_matches
                wicket_gap = agg_wickets - gl_wickets
                stale = match_gap > STALENESS_THRESHOLD or wicket_gap > STALENESS_THRESHOLD
                if stale:
                    flagged += 1

                flag = "  <-- NEEDS FULL REBUILD" if stale else ""
                print(
                    f"  {org_name:35s} player_id={player_id}  "
                    f"aggregate: {agg_matches}m/{agg_wickets}w  "
                    f"game-level: {gl_matches}m/{gl_wickets}w  "
                    f"gap: {match_gap}m/{wicket_gap}w{flag}"
                )
            print()

        print(f"Done. {flagged} club/player combinations look stale and would benefit from a Full Rebuild.")


if __name__ == "__main__":
    asyncio.run(audit())
