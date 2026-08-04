"""Public org-scoped reads: results list + the dashboard summary."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl import aggregations

router = APIRouter(prefix="/organisations", tags=["afl-organisations"])


@router.get("/{org_id}/results")
async def get_results(org_id: uuid.UUID,
                      season_id: Optional[uuid.UUID] = None,
                      grade_id: Optional[uuid.UUID] = None,
                      finals_only: bool = False,
                      include_upcoming: bool = False,
                      limit: int = Query(50, le=200),
                      offset: int = 0,
                      db: AsyncSession = Depends(get_db)):
    # Results are played games; upcoming fixtures have their own dashboard
    # section (pass include_upcoming=true to get the whole season list).
    clauses = ["s.organisation_id = :org"]
    if not include_upcoming:
        clauses.append("d.status = 'FINAL'")
    params: dict = {"org": str(org_id), "lim": limit, "off": offset}
    if season_id:
        clauses.append("s.id = :season")
        params["season"] = str(season_id)
    if grade_id:
        clauses.append("gr.id = :grade")
        params["grade"] = str(grade_id)
    if finals_only:
        clauses.append("g.is_final")
    where = " AND ".join(clauses)
    res = await db.execute(text(f"""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.home_club,
               g.away_club, g.result, g.winning_team, g.is_final, g.venue,
               gr.id AS grade_id, gr.name AS grade_name,
               s.id AS season_id, s.name AS season_name, s.year,
               d.round_name, d.round_abbrev, d.status, d.start_time,
               d.our_side, d.home_goals, d.home_behinds, d.home_score,
               d.away_goals, d.away_behinds, d.away_score,
               d.outcome_description, d.home_logo_url, d.away_logo_url
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE {where}
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :lim OFFSET :off
    """), params)
    games = [dict(r._mapping) for r in res]
    summary = await aggregations.club_results_summary(db, org_id, season_id)
    return {"games": games, "summary": summary}


@router.get("/{org_id}/summary")
async def get_summary(org_id: uuid.UUID,
                      season_id: Optional[uuid.UUID] = None,
                      db: AsyncSession = Depends(get_db)):
    """Dashboard payload: headline W/L/D, top goal kickers, most games, most
    BOGs, recent + upcoming games."""
    summary = await aggregations.club_results_summary(db, org_id, season_id)

    season_clause = "AND pss.season_id = :season" if season_id else ""
    params: dict = {"org": str(org_id)}
    if season_id:
        params["season"] = str(season_id)

    _TOP_COLS = {"goals": "goals", "games": "games", "bogs": "bog_count"}

    async def _top(order: str):
        col = _TOP_COLS[order]
        res = await db.execute(text(f"""
            SELECT pss.player_id, p.name, p.display_name_override, p.photo_url,
                   COALESCE(SUM(pss.games),0) AS games,
                   COALESCE(SUM(pss.goals),0) AS goals,
                   COALESCE(SUM(pss.bog_count),0) AS bogs
            FROM afl_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.organisation_id = :org AND pss.grade_id IS NULL {season_clause}
            GROUP BY pss.player_id, p.name, p.display_name_override, p.photo_url
            HAVING COALESCE(SUM(pss.{col}),0) > 0
            ORDER BY COALESCE(SUM(pss.{col}),0) DESC, games DESC
            LIMIT 5
        """), params)
        return [dict(r._mapping) for r in res]

    recent = await db.execute(text("""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.result,
               gr.name AS grade_name, d.round_name,
               d.home_goals, d.home_behinds, d.home_score,
               d.away_goals, d.away_behinds, d.away_score, d.our_side,
               d.outcome_description
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org AND d.status = 'FINAL'
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT 6
    """), {"org": str(org_id)})
    upcoming = await db.execute(text("""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.venue,
               gr.name AS grade_name, d.round_name, d.start_time
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org
          AND (d.status IS DISTINCT FROM 'FINAL')
          AND g.played_at >= CURRENT_DATE
        ORDER BY g.played_at ASC
        LIMIT 6
    """), {"org": str(org_id)})

    return {
        "summary": summary,
        "top_goal_kickers": await _top("goals"),
        "most_games": await _top("games"),
        "most_bogs": await _top("bogs"),
        "recent_games": [dict(r._mapping) for r in recent],
        "upcoming_games": [dict(r._mapping) for r in upcoming],
    }
