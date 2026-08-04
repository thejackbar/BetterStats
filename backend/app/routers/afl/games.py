"""Public match view — everything from our own DB, no live PlayHQ fetch."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db

router = APIRouter(prefix="/games", tags=["afl-games"])


@router.get("/{game_id}")
async def get_game(game_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    game = await db.execute(text("""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.home_club,
               g.away_club, g.result, g.winning_team, g.is_final, g.venue,
               gr.id AS grade_id, gr.name AS grade_name,
               s.id AS season_id, s.name AS season_name, s.year,
               s.organisation_id,
               d.playhq_id, d.round_name, d.round_abbrev, d.status,
               d.start_time, d.our_side,
               d.home_goals, d.home_behinds, d.home_score,
               d.away_goals, d.away_behinds, d.away_score,
               d.outcome_description, d.home_logo_url, d.away_logo_url,
               d.venue_name, d.venue_suburb
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE g.id = :gid
    """), {"gid": str(game_id)})
    row = game.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Game not found")
    payload = dict(row._mapping)

    periods = await db.execute(text("""
        SELECT side, period_number, period_value, goals, behinds, score
        FROM afl_game_periods
        WHERE game_id = :gid
        ORDER BY period_number, side
    """), {"gid": str(game_id)})
    payload["periods"] = [dict(r._mapping) for r in periods]

    lines = await db.execute(text("""
        SELECT side, team_name, name, jumper_number, goals, behinds,
               bog_ranking, player_points, is_captain, player_id
        FROM afl_player_game_lines
        WHERE game_id = :gid
        ORDER BY side,
                 NULLIF(regexp_replace(jumper_number, '\\D', '', 'g'), '')::int
                 NULLS LAST,
                 name
    """), {"gid": str(game_id)})
    payload["player_lines"] = [dict(r._mapping) for r in lines]

    events = await db.execute(text("""
        SELECT sequence, period_value, period_label, clock, side, team_name,
               event_type, scorer_name, scorer_number, player_id,
               progressive_score
        FROM afl_game_events
        WHERE game_id = :gid
        ORDER BY sequence DESC
    """), {"gid": str(game_id)})
    payload["events"] = [dict(r._mapping) for r in events]
    return payload
