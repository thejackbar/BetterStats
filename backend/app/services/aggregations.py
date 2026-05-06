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
    return await get_batting_leaderboard_extended(session, org_id, season_id, grade_id, "total_runs", limit)


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    return await get_bowling_leaderboard_extended(session, org_id, season_id, grade_id, "total_wickets", limit)


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
            SUM(pss.matches) AS games,
            SUM(pss.catches) AS total_catches,
            SUM(pss.run_outs) AS total_run_outs,
            SUM(pss.stumpings) AS total_stumpings,
            SUM(pss.catches + pss.run_outs + pss.stumpings) AS total_dismissals
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += " GROUP BY p.id, p.name ORDER BY total_dismissals DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    return []


async def get_player_bowling_spells(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    return []


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    return []


async def get_batting_by_position(session: AsyncSession, player_id: str) -> list[dict]:
    return []


async def get_batting_by_grade(session: AsyncSession, player_id: str) -> list[dict]:
    return []


async def get_season_by_season(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                pss.matches,
                pss.batting_innings,
                pss.runs AS total_runs,
                pss.high_score,
                pss.batting_average,
                pss.batting_strike_rate AS strike_rate,
                pss.fifties,
                pss.hundreds,
                pss.not_outs,
                pss.ducks,
                pss.fours AS total_fours,
                pss.sixes AS total_sixes,
                pss.wickets AS total_wickets,
                pss.overs AS total_overs,
                pss.bowling_average,
                pss.bowling_economy AS economy,
                pss.best_bowling_wickets,
                pss.maidens AS total_maidens,
                pss.catches AS total_catches,
                pss.run_outs AS total_run_outs,
                pss.stumpings AS total_stumpings
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = :pid
            ORDER BY s.year DESC NULLS LAST, s.name
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_milestones(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                m.id, m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                m.game_id
            FROM milestones m
            WHERE m.player_id = :pid
            ORDER BY m.milestone_type, m.milestone_value
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    return []


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str) -> list[dict]:
    return []


async def get_upcoming_milestones_for_org(
    session: AsyncSession,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                p.id AS player_id,
                p.name,
                COALESCE(SUM(pss.runs), 0) AS career_runs,
                COALESCE(SUM(pss.wickets), 0) AS career_wickets
            FROM players p
            LEFT JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
            GROUP BY p.id, p.name
            HAVING COALESCE(SUM(pss.runs), 0) > 0 OR COALESCE(SUM(pss.wickets), 0) > 0
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in result.mappings()]

    RUN_MILESTONES = [50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]
    WICKET_MILESTONES = [10, 25, 50, 75, 100, 150, 200]

    upcoming = []
    for row in rows:
        runs = int(row["career_runs"] or 0)
        wickets = int(row["career_wickets"] or 0)
        player_id = str(row["player_id"])
        name = row["name"]

        for m in RUN_MILESTONES:
            if runs < m:
                upcoming.append({
                    "player_id": player_id,
                    "name": name,
                    "type": "runs",
                    "current": runs,
                    "target": m,
                    "needed": m - runs,
                })
                break

        for m in WICKET_MILESTONES:
            if wickets < m:
                upcoming.append({
                    "player_id": player_id,
                    "name": name,
                    "type": "wickets",
                    "current": wickets,
                    "target": m,
                    "needed": m - wickets,
                })
                break

    upcoming.sort(key=lambda x: x["needed"])
    return upcoming[:limit]


async def get_player_activity(session: AsyncSession, player_id: str) -> dict:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(pss.matches), 0) AS total_matches,
                COALESCE(SUM(pss.batting_innings), 0) AS total_innings,
                COALESCE(SUM(pss.ducks), 0) AS total_ducks,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                MAX(pss.best_bowling_wickets) AS best_spell_wickets
            FROM player_season_stats pss
            WHERE pss.player_id = :pid
        """),
        {"pid": player_id}
    )
    row = dict(result.mappings().first() or {})
    return {
        "last_game_date": None,
        "last_bat_date": None,
        "last_bowl_date": None,
        "last_wicket_date": None,
        "last_duck_date": None,
        "total_innings": int(row.get("total_innings") or 0),
        "total_ducks": int(row.get("total_ducks") or 0),
        "total_sixes": int(row.get("total_sixes") or 0),
        "total_fours": int(row.get("total_fours") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "best_spell_wickets": int(row.get("best_spell_wickets") or 0),
        "wicketless_spells": 0,
    }


async def get_batting_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_runs",
    limit: int = 20,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_runs", "average", "strike_rate", "total_sixes",
        "total_fours", "ducks", "high_score", "fifties", "hundreds", "innings",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_runs"

    base = """
        SELECT
            p.id AS player_id,
            p.name,
            SUM(pss.batting_innings) AS innings,
            SUM(pss.runs) AS total_runs,
            MAX(pss.high_score) AS high_score,
            ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
            ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
            SUM(pss.fifties) AS fifties,
            SUM(pss.hundreds) AS hundreds,
            COALESCE(SUM(pss.sixes), 0) AS total_sixes,
            COALESCE(SUM(pss.fours), 0) AS total_fours,
            SUM(pss.ducks) AS ducks,
            SUM(pss.matches) AS games
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += f" GROUP BY p.id, p.name ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_wickets",
    limit: int = 20,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_wickets", "average", "economy", "best_figures_wickets",
        "total_maidens", "five_fors",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_wickets"

    base = """
        SELECT
            p.id AS player_id,
            p.name,
            SUM(pss.matches) AS games,
            SUM(pss.wickets) AS total_wickets,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.overs), 0), 2) AS economy,
            MAX(pss.best_bowling_wickets) AS best_figures_wickets,
            SUM(pss.maidens) AS total_maidens,
            SUM(pss.overs) AS total_overs,
            0 AS five_fors
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += f" GROUP BY p.id, p.name ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_club_summary(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> dict:
    where = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id}
    if season_id:
        where += " AND pss.season_id = :season_id"
        params["season_id"] = season_id

    res = await session.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT pss.season_id) AS seasons,
                COUNT(DISTINCT pss.player_id) AS total_players,
                SUM(pss.runs) AS total_runs,
                SUM(pss.wickets) AS total_wickets,
                MAX(pss.high_score) AS highest_score
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            {where}
        """),
        params
    )
    row = dict(res.mappings().first() or {})
    return {
        "total_games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "win_rate": 0,
        "total_runs": int(row.get("total_runs") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "highest_score": int(row.get("highest_score") or 0),
        "total_players": int(row.get("total_players") or 0),
        "seasons": int(row.get("seasons") or 0),
    }


async def get_game_partnerships(session: AsyncSession, game_id: str) -> list[dict]:
    return []
