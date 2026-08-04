"""Public club records — the AFL record book, computed from synced data.

Kept deliberately lean for pass 1: the record set AFL clubs actually talk
about with only games/goals/BOG data available (see the plan doc).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db

router = APIRouter(prefix="/afl-records", tags=["afl-records"])


@router.get("/{org_id}")
async def get_records(org_id: uuid.UUID,
                      grade_id: Optional[uuid.UUID] = None,
                      db: AsyncSession = Depends(get_db)):
    params: dict = {"org": str(org_id)}
    grade_line = ""
    grade_pss = "AND pss.grade_id IS NULL"
    if grade_id:
        params["grade"] = str(grade_id)
        grade_line = "AND gr.id = :grade"
        grade_pss = "AND pss.grade_id = :grade"

    most_goals_game = await db.execute(text(f"""
        SELECT l.player_id, p.name, p.display_name_override, l.goals,
               g.id AS game_id, g.played_at, g.home_team, g.away_team,
               d.round_name, s.name AS season_name
        FROM afl_player_game_lines l
        JOIN players p ON p.id = l.player_id
        JOIN games g ON g.id = l.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org AND l.player_id IS NOT NULL
          AND l.goals > 0 {grade_line}
        ORDER BY l.goals DESC, g.played_at ASC
        LIMIT 10
    """), params)

    most_goals_season = await db.execute(text(f"""
        SELECT pss.player_id, p.name, p.display_name_override, pss.goals,
               s.name AS season_name, s.year
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE pss.organisation_id = :org AND pss.goals > 0 {grade_pss}
        ORDER BY pss.goals DESC, s.year ASC
        LIMIT 10
    """), params)

    most_games_career = await db.execute(text(f"""
        SELECT pss.player_id, p.name, p.display_name_override,
               SUM(pss.games) AS games
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        WHERE pss.organisation_id = :org {grade_pss}
        GROUP BY pss.player_id, p.name, p.display_name_override
        ORDER BY games DESC
        LIMIT 10
    """), params)

    most_goals_career = await db.execute(text(f"""
        SELECT pss.player_id, p.name, p.display_name_override,
               SUM(pss.goals) AS goals
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        WHERE pss.organisation_id = :org {grade_pss}
        GROUP BY pss.player_id, p.name, p.display_name_override
        HAVING SUM(pss.goals) > 0
        ORDER BY goals DESC
        LIMIT 10
    """), params)

    most_bogs_career = await db.execute(text(f"""
        SELECT pss.player_id, p.name, p.display_name_override,
               SUM(pss.bog_count) AS bogs
        FROM afl_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        WHERE pss.organisation_id = :org {grade_pss}
        GROUP BY pss.player_id, p.name, p.display_name_override
        HAVING SUM(pss.bog_count) > 0
        ORDER BY bogs DESC
        LIMIT 10
    """), params)

    biggest_wins = await db.execute(text(f"""
        SELECT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               d.round_name, s.name AS season_name,
               d.home_score, d.away_score, d.our_side,
               ABS(d.home_score - d.away_score) AS margin,
               d.outcome_description
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org AND g.result = 'W'
          AND d.home_score IS NOT NULL AND d.away_score IS NOT NULL
          {grade_line}
        ORDER BY margin DESC, g.played_at ASC
        LIMIT 10
    """), params)

    highest_scores = await db.execute(text(f"""
        SELECT g.id AS game_id, g.played_at, g.home_team, g.away_team,
               d.round_name, s.name AS season_name, d.our_side,
               CASE WHEN d.our_side = 'HOME' THEN d.home_score ELSE d.away_score END AS our_score,
               CASE WHEN d.our_side = 'HOME' THEN d.home_goals ELSE d.away_goals END AS our_goals,
               CASE WHEN d.our_side = 'HOME' THEN d.home_behinds ELSE d.away_behinds END AS our_behinds
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        JOIN afl_game_details d ON d.game_id = g.id
        WHERE s.organisation_id = :org AND d.our_side IS NOT NULL
          AND d.home_score IS NOT NULL AND d.away_score IS NOT NULL
          {grade_line}
        ORDER BY our_score DESC, g.played_at ASC
        LIMIT 10
    """), params)

    def rows(res):
        return [dict(r._mapping) for r in res]

    return {
        "most_goals_in_a_game": rows(most_goals_game),
        "most_goals_in_a_season": rows(most_goals_season),
        "most_games_career": rows(most_games_career),
        "most_goals_career": rows(most_goals_career),
        "most_bogs_career": rows(most_bogs_career),
        "biggest_wins": rows(biggest_wins),
        "highest_scores": rows(highest_scores),
    }
