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


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(NULLIF(dismissal_type, ''), 'not out') AS dismissal_type,
                COUNT(*) AS count
            FROM batting_innings
            WHERE player_id = :pid
            GROUP BY dismissal_type
            ORDER BY count DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_position(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                batting_position,
                COUNT(*) AS innings,
                SUM(runs) AS total_runs,
                MAX(runs) AS high_score,
                ROUND(SUM(runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT not_out), 0), 2) AS average,
                ROUND(SUM(runs)::numeric / NULLIF(SUM(balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings
            WHERE player_id = :pid AND batting_position IS NOT NULL
            GROUP BY batting_position
            ORDER BY batting_position
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_grade(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                gr.name AS grade_name,
                COUNT(*) AS innings,
                SUM(bi.runs) AS total_runs,
                MAX(bi.runs) AS high_score,
                ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS average,
                ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE bi.player_id = :pid
            GROUP BY gr.name
            ORDER BY total_runs DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_season_by_season(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                COUNT(DISTINCT bi.game_id) AS batting_innings,
                SUM(bi.runs) AS total_runs,
                MAX(bi.runs) AS high_score,
                ROUND(SUM(bi.runs)::numeric / NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out), 0), 2) AS batting_average,
                ROUND(SUM(bi.runs)::numeric / NULLIF(SUM(bi.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN bi.runs >= 50 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bi.player_id = :pid
            GROUP BY s.id, s.name, s.year
            ORDER BY s.year DESC NULLS LAST, s.name
        """),
        {"pid": player_id}
    )
    batting_rows = {r["season_id"]: dict(r) for r in result.mappings()}

    result2 = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                COUNT(DISTINCT bs.game_id) AS bowling_innings,
                SUM(bs.wickets) AS total_wickets,
                SUM(bs.overs) AS total_overs,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS bowling_average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                MAX(bs.wickets) AS best_figures_wickets
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE bs.player_id = :pid
            GROUP BY s.id
        """),
        {"pid": player_id}
    )
    bowling_rows = {r["season_id"]: dict(r) for r in result2.mappings()}

    all_season_ids = set(batting_rows.keys()) | set(bowling_rows.keys())
    merged = []
    for sid in all_season_ids:
        row = batting_rows.get(sid, {"season_id": sid})
        bowl = bowling_rows.get(sid, {})
        row.update({k: v for k, v in bowl.items() if k != "season_id"})
        merged.append(row)

    merged.sort(key=lambda r: (r.get("year") or 0, r.get("season_name", "")), reverse=True)
    return merged


async def get_player_milestones(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                m.id, m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                m.game_id,
                g.played_at AS game_date,
                g.home_team, g.away_team
            FROM milestones m
            LEFT JOIN games g ON g.id = m.game_id
            WHERE m.player_id = :pid
            ORDER BY m.milestone_type, m.milestone_value
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                p.id,
                p.game_id,
                p.innings_number,
                p.wicket_number,
                p.runs,
                p.balls,
                p.batter1_runs,
                p.batter2_runs,
                p.batter1_id,
                p.batter2_id,
                CASE
                    WHEN p.batter1_id = :pid THEN p2.name
                    ELSE p1.name
                END AS partner_name,
                CASE
                    WHEN p.batter1_id = :pid THEN p.batter1_runs
                    ELSE p.batter2_runs
                END AS player_runs,
                g.played_at, g.home_team, g.away_team,
                gr.name AS grade_name
            FROM partnerships p
            LEFT JOIN players p1 ON p1.id = p.batter1_id
            LEFT JOIN players p2 ON p2.id = p.batter2_id
            JOIN games g ON g.id = p.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE p.batter1_id = :pid OR p.batter2_id = :pid
            ORDER BY g.played_at DESC, p.innings_number, p.wicket_number
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                f.innings_number,
                f.wicket_number,
                f.score_at_fall,
                f.overs_at_fall,
                f.player_id,
                p.name AS player_name
            FROM fall_of_wickets f
            LEFT JOIN players p ON p.id = f.player_id
            WHERE f.game_id = :gid
            ORDER BY f.innings_number, f.wicket_number
        """),
        {"gid": game_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_game_partnerships(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                p.innings_number,
                p.wicket_number,
                p.runs,
                p.balls,
                p.batter1_runs,
                p.batter2_runs,
                p.batter1_id,
                p.batter2_id,
                p1.name AS batter1_name,
                p2.name AS batter2_name
            FROM partnerships p
            LEFT JOIN players p1 ON p1.id = p.batter1_id
            LEFT JOIN players p2 ON p2.id = p.batter2_id
            WHERE p.game_id = :gid
            ORDER BY p.innings_number, p.wicket_number
        """),
        {"gid": game_id}
    )
    return [dict(r) for r in result.mappings()]
