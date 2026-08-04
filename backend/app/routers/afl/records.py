"""Public club records — the AFL record book.

Two different shapes of record here, and only one of them can use imported
(Import Stats upload) data:

- Season/career records (most goals in a season, most games/goals/BOGs in a
  career) are built from afl_player_season_stats combined with
  afl_imported_stats — same "sync wins per season, imported fills the gap"
  rule the leaderboard/dashboard use, since a season-total upload genuinely
  has this data.
- Single-game records (most goals in a game, biggest win, highest score) stay
  synced-only — a season-total spreadsheet has no per-game breakdown to draw
  a single-game record from, so there's nothing to combine.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl.aggregations import matching_grade_ids

router = APIRouter(prefix="/afl-records", tags=["afl-records"])


@router.get("/{org_id}")
async def get_records(org_id: uuid.UUID,
                      grade_id: Optional[uuid.UUID] = None,
                      db: AsyncSession = Depends(get_db)):
    params: dict = {"org": str(org_id)}
    grade_line = ""
    grade_pss = "AND pss.grade_id IS NULL"
    grade_i = ""
    if grade_id:
        # Every grade_id (any season) merged into/with this one — so a
        # merged grade's games count under whichever name you filter by.
        params["grade"] = await matching_grade_ids(db, org_id, grade_id)
        grade_line = "AND gr.id = ANY(:grade)"
        grade_pss = "AND pss.grade_id = ANY(:grade)"
        grade_i = "AND i.grade_id = ANY(:grade)"

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
        WITH combined AS (
            SELECT pss.player_id, pss.goals, pss.season_id
            FROM afl_player_season_stats pss
            WHERE pss.organisation_id = :org {grade_pss}
            UNION ALL
            SELECT i.player_id, i.goals, i.season_id
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {grade_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id, p.name, p.display_name_override, c.goals,
               s.name AS season_name, s.year
        FROM combined c
        JOIN players p ON p.id = c.player_id
        JOIN seasons s ON s.id = c.season_id
        WHERE c.goals > 0
        ORDER BY c.goals DESC, s.year ASC
        LIMIT 10
    """), params)

    most_games_career = await db.execute(text(f"""
        WITH combined AS (
            SELECT pss.player_id, pss.season_id, pss.games
            FROM afl_player_season_stats pss
            WHERE pss.organisation_id = :org {grade_pss}
            UNION ALL
            SELECT i.player_id, i.season_id, i.games_played AS games
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {grade_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id, p.name, p.display_name_override,
               SUM(c.games) AS games
        FROM combined c
        JOIN players p ON p.id = c.player_id
        GROUP BY c.player_id, p.name, p.display_name_override
        ORDER BY games DESC
        LIMIT 10
    """), params)

    most_goals_career = await db.execute(text(f"""
        WITH combined AS (
            SELECT pss.player_id, pss.season_id, pss.goals
            FROM afl_player_season_stats pss
            WHERE pss.organisation_id = :org {grade_pss}
            UNION ALL
            SELECT i.player_id, i.season_id, i.goals
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {grade_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id, p.name, p.display_name_override,
               SUM(c.goals) AS goals
        FROM combined c
        JOIN players p ON p.id = c.player_id
        GROUP BY c.player_id, p.name, p.display_name_override
        HAVING SUM(c.goals) > 0
        ORDER BY goals DESC
        LIMIT 10
    """), params)

    most_bogs_career = await db.execute(text(f"""
        WITH combined AS (
            SELECT pss.player_id, pss.season_id, pss.bog_count
            FROM afl_player_season_stats pss
            WHERE pss.organisation_id = :org {grade_pss}
            UNION ALL
            SELECT i.player_id, i.season_id, i.bog_count
            FROM afl_imported_stats i
            WHERE i.organisation_id = :org {grade_i}
              AND NOT EXISTS (
                SELECT 1 FROM afl_player_season_stats s2
                WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                  AND s2.grade_id IS NULL AND s2.games > 0
              )
        )
        SELECT c.player_id, p.name, p.display_name_override,
               SUM(c.bog_count) AS bogs
        FROM combined c
        JOIN players p ON p.id = c.player_id
        GROUP BY c.player_id, p.name, p.display_name_override
        HAVING SUM(c.bog_count) > 0
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
