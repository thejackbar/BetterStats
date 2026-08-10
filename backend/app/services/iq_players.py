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

from app.services.bowling_style import bowling_class, bowling_label


async def list_all_players(session: AsyncSession, org_id: str) -> list[dict]:
    res = await session.execute(
        text(
            """
            SELECT p.id::text AS player_id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   p.player_role, p.skill_positions,
                   p.bowling_action, p.bowling_type,
                   MAX(t.name) AS squad,
                   COALESCE(SUM(pss.matches) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS matches,
                   COALESCE(SUM(pss.runs) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS runs,
                   COALESCE(SUM(pss.wickets) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)), 0) AS wickets,
                   MAX(s.year) FILTER (WHERE s.organisation_id = CAST(:org AS UUID)) AS last_year
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            LEFT JOIN seasons s ON s.id = pss.season_id
            LEFT JOIN teams t ON t.id = p.squad_team_id
            -- is_player IS TRUE: coaches/officials (is_player = FALSE) have no
            -- business in a scouting roster or the Ask IQ player pickers. The
            -- column was added with server_default 'true' (migration 023), so
            -- every real player reads TRUE.
            WHERE p.organisation_id = CAST(:org AS UUID)
              AND p.is_player IS TRUE
            GROUP BY p.id
            ORDER BY last_year DESC NULLS LAST, runs DESC
            """
        ),
        {"org": org_id},
    )
    out = []
    for r in res.mappings():
        sp = r["skill_positions"] or []
        keeper = ("WKT" in sp) or bool(r["player_role"] and "KEEP" in (r["player_role"] or "").upper())
        out.append({
            "player_id": r["player_id"],
            "name": r["name"],
            "player_role": r["player_role"],
            "is_keeper": keeper,
            "bowling_style": bowling_label(r["bowling_action"], r["bowling_type"]),
            "bowling_class": bowling_class(r["bowling_type"]),
            "squad": r["squad"],
            "matches": int(r["matches"] or 0),
            "runs": int(r["runs"] or 0),
            "wickets": int(r["wickets"] or 0),
            "last_year": r["last_year"],
        })
    return out
