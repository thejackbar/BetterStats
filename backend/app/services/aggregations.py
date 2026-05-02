from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import uuid


async def get_career_batting(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_batting WHERE player_id = :pid"),
        {"pid": player_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_bowling(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_bowling WHERE player_id = :pid"),
        {"pid": player_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_fielding(session: AsyncSession, player_id: str) -> Optional[dict]:
    result = await session.execute(
        text("SELECT * FROM career_fielding WHERE player_id = :pid"),
        {"pid": player_id}
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_batting_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS innings,
            SUM(bi.runs) AS total_runs,
            MAX(bi.runs) AS high_score,
            ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS average,
            ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
            SUM(CASE WHEN bi.runs >= 50 THEN 1 ELSE 0 END) AS fifties,
            SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
        FROM batting_innings bi
        JOIN players p ON p.id = bi.player_id
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_runs DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS games,
            SUM(bs.wickets) AS total_wickets,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
            ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
            MAX(bs.wickets) AS best_figures_wickets,
            SUM(bs.maidens) AS total_maidens
        FROM bowling_spells bs
        JOIN players p ON p.id = bs.player_id
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_wickets DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_fielding_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    base = """
        SELECT
            p.id AS player_id,
            p.name,
            COUNT(*) AS games,
            SUM(fs.catches) AS total_catches,
            SUM(fs.run_outs) AS total_run_outs,
            SUM(fs.stumpings) AS total_stumpings,
            SUM(fs.catches + fs.run_outs + fs.stumpings) AS total_dismissals
        FROM fielding_stats fs
        JOIN players p ON p.id = fs.player_id
        JOIN games g ON g.id = fs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " GROUP BY p.id, p.name ORDER BY total_dismissals DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    base = """
        SELECT
            bi.id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.strike_rate,
            bi.dismissal_type, bi.not_out, bi.batting_position,
            g.id AS game_id, g.played_at, g.home_team, g.away_team, g.result,
            gr.name AS grade_name, s.name AS season_name
        FROM batting_innings bi
        JOIN games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bi.player_id = :pid
    """
    params: dict = {"pid": player_id}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " ORDER BY g.played_at DESC"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_bowling_spells(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    base = """
        SELECT
            bs.id, bs.overs, bs.maidens, bs.runs, bs.wickets, bs.wides,
            bs.no_balls, bs.economy,
            g.id AS game_id, g.played_at, g.home_team, g.away_team, g.result,
            gr.name AS grade_name, s.name AS season_name
        FROM bowling_spells bs
        JOIN games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE bs.player_id = :pid
    """
    params: dict = {"pid": player_id}
    if season_id:
        base += " AND s.id = :season_id"
        params["season_id"] = season_id
    if grade_id:
        base += " AND gr.id = :grade_id"
        params["grade_id"] = grade_id
    base += " ORDER BY g.played_at DESC"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]
