"""BetterFootball — team lists, public.

The side PlayHQ returns with each game, read straight out of what the sync
already stored (see ``services/afl/lineups.py`` for why nothing is fetched
live here). Public and unauthenticated, matching the cricket lineups endpoints
and every other public club page.

Post-game only, per direct instruction: a game reaches us once PlayHQ marks it
FINAL, so a scheduled match reads as "not played yet" rather than as a side
nobody named.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl import lineups as lineup_svc

router = APIRouter(prefix="/afl-lineups", tags=["afl-lineups"])

MAX_LIMIT = 60


@router.get("/organisations/{org_id}/games")
async def list_lineup_games(
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """The club's played games, newest first, each saying whether a team list
    came through — so the page can list "no team list" honestly rather than
    rendering an empty card."""
    try:
        oid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organisation")

    res = await db.execute(
        text(
            """
            SELECT g.id, g.played_at, g.home_team, g.away_team, g.result,
                   d.round_name, d.our_side, d.publish_lineup, d.venue_name,
                   gr.id AS grade_id, gr.name AS grade_name,
                   s.id AS season_id, s.name AS season_name,
                   (SELECT COUNT(*) FROM afl_player_game_lines l
                     WHERE l.game_id = g.id) AS named
            FROM games g
            JOIN afl_game_details d ON d.game_id = g.id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org
              AND g.played_at IS NOT NULL
              AND COALESCE(d.is_bye, false) = false
              AND (CAST(:season AS uuid) IS NULL OR s.id = CAST(:season AS uuid))
              AND (CAST(:grade AS uuid) IS NULL OR gr.id = CAST(:grade AS uuid))
            ORDER BY g.played_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"org": oid, "season": season_id, "grade": grade_id,
         "limit": limit + 1, "offset": offset},
    )
    rows = [dict(r) for r in res.mappings().all()]
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "has_more": has_more,
        "games": [
            {
                "id": str(r["id"]),
                "date": r["played_at"].isoformat() if r["played_at"] else None,
                "round": r["round_name"],
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "result": r["result"],
                "venue": r["venue_name"],
                "grade": r["grade_name"],
                "grade_id": str(r["grade_id"]) if r["grade_id"] else None,
                "season": r["season_name"],
                "our_side": r["our_side"],
                "published": r["publish_lineup"],
                "named": int(r["named"] or 0),
            }
            for r in rows
        ],
    }


@router.get("/games/{game_id}")
async def game_lineups(
    game_id: str,
    org_id: str = Query(..., description="The club whose page this is"),
    db: AsyncSession = Depends(get_db),
):
    """Both teams' named sides for one game.

    ``org_id`` is required rather than derived: a game between two clubs that
    both use BetterFootball is one row, and which club is "ours" depends on who
    is asking. Scoping the read to the caller's club is also what stops a game
    id resolving against a competition the club has nothing to do with.
    """
    try:
        gid, oid = uuid.UUID(game_id), uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid id")
    out = await lineup_svc.game_lineups(db, oid, gid)
    if not out:
        raise HTTPException(status_code=404, detail="Game not found")
    return out
