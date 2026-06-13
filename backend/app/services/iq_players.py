"""BetterIQ — the club's full player roster for the unified Player search.

The Player-trends list is current-season only (it's a form tool), so it can't
back a scouting search where you want to pull up anyone in the club's history.
This returns EVERY player in the org with a light career summary, org-scoped the
same way as the rest of BetterIQ: stats are summed only over the player's own
org seasons (via ``v_effective_player_season_stats`` + a season org filter), so a
player shared with another club doesn't carry their other club's numbers here.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_all_players(session: AsyncSession, org_id: str) -> list[dict]:
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS player_id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   p.player_role,
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS runs,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS wickets,
                   MAX(s.year) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)) AS last_year
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            LEFT JOIN seasons s ON s.id = pss.season_id
            WHERE p.organisation_id = CAST(:org AS UUID)
            GROUP BY p.id, name, p.player_role
            ORDER BY last_year DESC NULLS LAST, runs DESC
            """
        ),
        {"org": org_id},
    )
    return [
        {
            "player_id": r["player_id"],
            "name": r["name"],
            "player_role": r["player_role"],
            "matches": int(r["matches"] or 0),
            "runs": int(r["runs"] or 0),
            "wickets": int(r["wickets"] or 0),
            "last_year": r["last_year"],
        }
        for r in res.mappings()
    ]
