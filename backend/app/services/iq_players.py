"""BetterIQ — the club's full player roster for the unified Player search.

The Player-trends list is current-season only (it's a form tool), so it can't
back a scouting search where you want to pull up anyone in the club's history.
This returns EVERY player in the org with a light career summary, org-scoped the
same way as the rest of BetterIQ: stats are summed only over the player's own
org seasons (via ``v_effective_player_season_stats`` + a season org filter), so a
player shared with another club doesn't carry their other club's numbers here.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.aggregations import grid_matches_for_players
from app.services.bowling_style import bowling_class, bowling_label


logger = logging.getLogger(__name__)

# A lookup slower than this is logged at WARNING so it shows up without a search.
SLOW_SEC = 20


def _like_pattern(query: str) -> str:
    """``%query%`` with LIKE's own wildcards escaped, so a name with an underscore
    or a percent sign matches itself and nothing else."""
    return "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def list_all_players(
    session: AsyncSession,
    org_id: str,
    *,
    query: str | None = None,
    grid_for: int | None = None,
) -> list[dict]:
    """The club's players with a light career summary, busiest recent first.

    ``query`` keeps only players whose name contains it (case-insensitive), decided
    in SQL before any stats are read. ``grid_for`` raises only the first N rows to the
    by-grade grid total; the rest keep the scorecard count. The raise is the costly
    part on a club with years of history (it reads the heavy views for every id it is
    given), so a caller that shows a handful of rows says so. Both default to the
    whole roster, which is what the Players page wants.
    """
    t_start = time.monotonic()
    params: dict = {"org": org_id}
    id_clause = ""
    q = (query or "").strip().lower()
    if q:
        ids = (await session.execute(
            text(
                """
                SELECT p.id::text FROM players p
                WHERE p.organisation_id = CAST(:org AS UUID)
                  AND p.is_player IS TRUE
                  AND LOWER(COALESCE(p.display_name_override, p.name)) LIKE :pat ESCAPE '\\'
                """
            ),
            {"org": org_id, "pat": _like_pattern(q)},
        )).scalars().all()
        if not ids:
            return []
        # A bound array of ids, not a subquery: it is pushed into the view.
        id_clause = "AND p.id = ANY(CAST(:ids AS uuid[]))"
        params["ids"] = list(ids)
    res = await session.execute(
        text(
            f"""
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
              {id_clause}
            GROUP BY p.id
            ORDER BY last_year DESC NULLS LAST, runs DESC
            """
        ),
        params,
    )
    rows = list(res.mappings())
    t_stats = time.monotonic()
    # Raised to the by-grade grid like the player's own page (never lower), so a scouting
    # roster and the profile read one number. All grades, no scope: the figure above is CA's
    # all-grades total. A failure leaves the figures as they were.
    raised: dict = {}
    grid_rows = rows if grid_for is None else rows[:max(0, grid_for)]
    try:
        async with session.begin_nested():
            raised = await grid_matches_for_players(
                session, org_id, [r["player_id"] for r in grid_rows], None, None)
    except Exception:
        logger.exception("iq roster games vs profile failed for org %s", org_id)
    t_done = time.monotonic()
    logger.log(
        logging.WARNING if t_done - t_start >= SLOW_SEC else logging.INFO,
        "iq roster: %d players (%d raised to the grid) for org %s, stats %.1fs, grid %.1fs%s",
        len(rows), len(grid_rows), org_id, t_stats - t_start, t_done - t_stats,
        f", name filter {q!r}" if q else "",
    )
    out = []
    for r in rows:
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
            "matches": max(int(r["matches"] or 0), int(raised.get(r["player_id"]) or 0)),
            "runs": int(r["runs"] or 0),
            "wickets": int(r["wickets"] or 0),
            "last_year": r["last_year"],
        })
    return out
