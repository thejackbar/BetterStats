"""Public org-scoped reads: results list + the dashboard summary."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services.afl import aggregations
from app.services.afl.manual_stats import manual_branch
from app.services.afl.aggregations import matching_grade_ids

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
    """One page of a club's results, plus the summary + per-team split for the
    WHOLE filtered set (not just this page).

    ``total`` is what makes the page after this one reachable: the results
    screen used to ask for 100 rows and stop, which for a club with 3,000
    games meant its history silently ended in the mid-1970s with nothing on
    screen saying so. The count is the same filters as the list, so "showing
    100 of 3,021" is always true.
    """
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
        clauses.append("gr.id = ANY(:grade)")
        params["grade"] = await matching_grade_ids(db, org_id, grade_id)
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

    # How many games match these filters in total — the same WHERE, without
    # the page window, so the screen can say what it isn't showing and offer
    # the rest.
    count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
    total_res = await db.execute(text(f"""
        SELECT COUNT(*)
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        LEFT JOIN afl_game_details d ON d.game_id = g.id
        WHERE {where}
    """), count_params)
    total = int(total_res.scalar() or 0)

    # The same filters the list above was built with, so the headline cards
    # and the per-team split both describe what's actually on screen.
    grade_ids = params.get("grade")
    summary = await aggregations.club_results_summary(
        db, org_id, season_id, grade_ids=grade_ids, finals_only=finals_only)
    by_team = await aggregations.team_results_breakdown(
        db, org_id, season_id, grade_ids=grade_ids, finals_only=finals_only)
    return {"games": games, "summary": summary, "by_team": by_team,
            "total": total, "limit": limit, "offset": offset}


@router.get("/{org_id}/summary")
async def get_summary(org_id: uuid.UUID,
                      season_id: Optional[uuid.UUID] = None,
                      db: AsyncSession = Depends(get_db)):
    """Dashboard payload: headline W/L/D, top goal kickers, most games,
    recent + upcoming games."""
    summary = await aggregations.club_results_summary(db, org_id, season_id)

    # Whole-org flag (not scoped to the selected season) — the frontend uses
    # this to decide whether the club's Games/Wins/Losses/Draws card is safe
    # to show for "All seasons": a club with ANY imported history has a
    # summary that only ever reflects its synced fraction of a much longer
    # real history, which reads as a complete total when it isn't. A season-
    # scoped view doesn't need this — summary.played for that one season is
    # either real or it isn't.
    # A manual adjustment carrying games counts here for the same reason an
    # import does: those matches are in the club's totals and in nobody's
    # games table, so the W/L/D card is describing a fraction of the history
    # the rest of the page shows. An adjustment with no games (a goals-only
    # correction) says nothing about match coverage and is left out.
    has_imported = await db.execute(text("""
        SELECT EXISTS(SELECT 1 FROM afl_imported_stats WHERE organisation_id = :org)
            OR EXISTS(SELECT 1 FROM afl_manual_adjustments
                      WHERE organisation_id = :org AND games_played > 0)
    """), {"org": str(org_id)})
    has_imported_history = bool(has_imported.scalar())

    params: dict = {"org": str(org_id)}
    season_clause_s = ""
    season_clause_i = ""
    season_clause_m = ""
    if season_id:
        params["season"] = str(season_id)
        season_clause_s = "AND s.season_id = :season"
        season_clause_i = "AND i.season_id = :season"
        season_clause_m = "AND m.season_id = :season"
    manual = manual_branch(
        ["player_id", "season_id", "games", "goals", "bog_count"],
        where=season_clause_m,
    )

    _TOP_COLS = {"goals": "goals", "games": "games"}

    # Combines synced (afl_player_season_stats) with imported (Import Stats
    # upload) the same way the leaderboard/admin Players list do — without
    # this, a club whose whole history came from an upload had real numbers
    # nowhere on the public dashboard's "leading players" panels.
    # first_year/last_year (debut/final season, joined off the same combined
    # season_id) mirror where BetterStats (Core)'s equivalent board shows
    # each player's AVG/HS sub-line — AFL has no batting average, so a
    # career span reads better here than a rate stat would.
    #
    # Ten rows, which is what the dashboard's "Top 10s" panels show. The full
    # ordered list lives on the Leaderboard page, so this is a headline, not a
    # register — 10 is as far as it goes deliberately.
    async def _top(order: str):
        col = _TOP_COLS[order]
        res = await db.execute(text(f"""
            WITH combined AS (
                SELECT s.player_id, s.season_id, s.games, s.goals, s.bog_count
                FROM afl_player_season_stats s
                WHERE s.organisation_id = :org AND s.grade_id IS NULL {season_clause_s}
                UNION ALL
                SELECT i.player_id, i.season_id, i.games_played AS games, i.goals, i.bog_count
                FROM afl_imported_stats i
                WHERE i.organisation_id = :org {season_clause_i}
                  AND NOT EXISTS (
                    SELECT 1 FROM afl_player_season_stats s2
                    WHERE s2.player_id = i.player_id AND s2.season_id = i.season_id
                      AND s2.grade_id IS NULL AND s2.games > 0
                  )
                UNION ALL
                {manual}
            )
            SELECT c.player_id, p.name, p.display_name_override, p.photo_url,
                   COALESCE(SUM(c.games),0) AS games,
                   COALESCE(SUM(c.goals),0) AS goals,
                   COALESCE(SUM(c.bog_count),0) AS bogs,
                   MIN(sn.year) AS first_year,
                   MAX(sn.year) AS last_year
            FROM combined c
            JOIN players p ON p.id = c.player_id
            LEFT JOIN seasons sn ON sn.id = c.season_id
            GROUP BY c.player_id, p.name, p.display_name_override, p.photo_url
            HAVING COALESCE(SUM(c.{col}),0) > 0
            ORDER BY COALESCE(SUM(c.{col}),0) DESC, games DESC
            LIMIT 10
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
        "has_imported_history": has_imported_history,
        "top_goal_kickers": await _top("goals"),
        "most_games": await _top("games"),
        "recent_games": [dict(r._mapping) for r in recent],
        "upcoming_games": [dict(r._mapping) for r in upcoming],
        # Career-wide (never season-scoped — a milestone is a lifetime tally,
        # so it's computed once regardless of the dashboard's season filter).
        "milestones_in_reach": await aggregations.upcoming_milestones(db, org_id),
    }
