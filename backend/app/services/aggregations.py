from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
import uuid


async def get_career_batting(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                COALESCE(SUM(pss.not_outs), 0) AS not_outs,
                MAX(pss.high_score) AS high_score,
                ROUND(
                    SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0),
                    2
                ) AS average,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.ducks), 0) AS ducks,
                COALESCE(SUM(pss.fifties), 0) AS fifties,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.player_id = :pid {season_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_bowling(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.overs), 0) AS total_overs,
                COALESCE(SUM(pss.maidens), 0) AS total_maidens,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                MAX(pss.best_bowling_wickets) AS best_figures_wickets,
                MAX(pss.best_bowling_figures) AS best_bowling_figures
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.player_id = :pid {season_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_fielding(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_clause = " AND pss.season_id = :sid" if season_id else ""
    params: dict = {"pid": player_id}
    if season_id:
        params["sid"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                COALESCE(SUM(pss.catches), 0) AS total_catches,
                COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(pss.stumpings), 0) AS total_stumpings
            FROM player_season_stats pss
            WHERE pss.player_id = :pid {season_clause}
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    params: dict = {"pid": player_id}
    clauses = ["bi.player_id = :pid"]
    if season_id:
        clauses.append("s.id = :sid")
        params["sid"] = season_id
    if grade_id:
        clauses.append("g.grade_id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bi.id,
                bi.game_id,
                bi.player_id,
                bi.innings_number,
                bi.batting_position,
                bi.runs,
                bi.not_out,
                bi.dismissal_type,
                bi.dismissal_bowler_id,
                bi.dismissal_fielder_id,
                bi.fours,
                bi.sixes,
                bi.balls_faced,
                bi.strike_rate,
                g.played_at,
                gr.name AS grade_name,
                s.name AS season_name
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC NULLS LAST
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_player_bowling_spells(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    params: dict = {"pid": player_id}
    clauses = ["bs.player_id = :pid"]
    if season_id:
        clauses.append("s.id = :sid")
        params["sid"] = season_id
    if grade_id:
        clauses.append("g.grade_id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bs.id,
                bs.game_id,
                bs.player_id,
                bs.innings_number,
                bs.overs,
                bs.maidens,
                bs.runs,
                bs.wickets,
                bs.wides,
                bs.no_balls,
                bs.economy,
                g.played_at,
                gr.name AS grade_name,
                s.name AS season_name
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC NULLS LAST
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(bi.dismissal_type, 'unknown') AS dismissal_type,
                COUNT(*) AS count
            FROM batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.dismissal_type IS NOT NULL
              AND bi.dismissal_type NOT IN ('absent', 'did not bat', 'dnb')
            GROUP BY bi.dismissal_type
            ORDER BY count DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_position(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                bi.batting_position,
                COUNT(*) AS innings,
                SUM(bi.runs) AS runs,
                ROUND(
                    SUM(bi.runs)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL), 0),
                    2
                ) AS average,
                MAX(bi.runs) AS high_score,
                ROUND(AVG(bi.strike_rate), 1) AS avg_strike_rate
            FROM batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.batting_position IS NOT NULL
              AND bi.runs IS NOT NULL
            GROUP BY bi.batting_position
            ORDER BY bi.batting_position
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_grade(session: AsyncSession, player_id: str, org_id: Optional[str] = None) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                COALESCE(am.canonical_name, gr.name) AS grade_name,
                COUNT(*) AS innings,
                SUM(bi.runs) AS runs,
                ROUND(
                    SUM(bi.runs)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL), 0),
                    2
                ) AS average,
                MAX(bi.runs) AS high_score
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
            GROUP BY COALESCE(am.canonical_name, gr.name)
            ORDER BY SUM(bi.runs) DESC
        """),
        {"pid": player_id, "org_id": org_id},
    )
    return [dict(r) for r in result.mappings()]


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
                pss.runs_conceded AS bowling_runs_conceded,
                pss.overs AS total_overs,
                pss.best_bowling_figures,
                pss.best_bowling_wickets AS best_bowling_wickets,
                ROUND(pss.runs_conceded::numeric / NULLIF(pss.bowling_balls, 0) * 6, 2) AS economy,
                pss.bowling_average,
                pss.five_wicket_innings AS five_fors,
                pss.maidens AS total_maidens,
                pss.catches AS total_catches,
                pss.run_outs AS total_run_outs,
                pss.stumpings AS total_stumpings
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.player_id = :pid
            ORDER BY s.year DESC NULLS LAST, s.name DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_milestones(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                pm.id, pm.player_id, pm.milestone_type, pm.milestone_value,
                pm.achieved_at, pm.detail
            FROM player_milestones pm
            WHERE pm.player_id = :pid
            ORDER BY pm.milestone_value DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                CASE
                    WHEN pt.batter1_id = :pid THEN pt.batter2_id
                    ELSE pt.batter1_id
                END AS partner_id,
                CASE
                    WHEN pt.batter1_id = :pid THEN COALESCE(p2.display_name_override, p2.name)
                    ELSE COALESCE(p1.display_name_override, p1.name)
                END AS partner_name,
                COUNT(*) AS partnership_count,
                SUM(pt.runs) AS total_runs,
                MAX(pt.runs) AS best_runs
            FROM partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE (pt.batter1_id = :pid OR pt.batter2_id = :pid)
              AND pt.runs IS NOT NULL
            GROUP BY partner_id, partner_name
            ORDER BY best_runs DESC NULLS LAST
            LIMIT 20
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_activity(session: AsyncSession, player_id: str) -> dict:
    batting_res = await session.execute(
        text("""
            SELECT
                bi.runs,
                bi.not_out,
                bi.dismissal_type,
                g.played_at,
                gr.name AS grade_name
            FROM batting_innings bi
            JOIN games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE bi.player_id = :pid
              AND bi.dismissal_type NOT IN ('absent', 'did not bat', 'dnb')
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT 20
        """),
        {"pid": player_id},
    )
    bowling_res = await session.execute(
        text("""
            SELECT
                bs.wickets,
                bs.runs,
                bs.overs,
                g.played_at,
                gr.name AS grade_name
            FROM bowling_spells bs
            JOIN games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            WHERE bs.player_id = :pid
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT 20
        """),
        {"pid": player_id},
    )
    return {
        "batting": [dict(r) for r in batting_res.mappings()],
        "bowling": [dict(r) for r in bowling_res.mappings()],
    }


async def get_upcoming_milestones_for_org(
    session: AsyncSession,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    RUN_MILESTONES = [50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000]
    WICKET_MILESTONES = [10, 25, 50, 75, 100, 150, 200]
    MATCH_MILESTONES = [10, 25, 50, 100, 150, 200]

    result = await session.execute(
        text("""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.matches), 0) AS total_matches
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """),
        {"org_id": org_id},
    )
    players = [dict(r) for r in result.mappings()]

    upcoming = []
    for player in players:
        total_runs = int(player.get("total_runs") or 0)
        total_wickets = int(player.get("total_wickets") or 0)
        total_matches = int(player.get("total_matches") or 0)
        for m in RUN_MILESTONES:
            if total_runs < m:
                upcoming.append({"player_id": str(player["player_id"]), "name": player["name"], "type": "runs", "current": total_runs, "target": m, "needed": m - total_runs})
                break
        for m in WICKET_MILESTONES:
            if total_wickets < m:
                upcoming.append({"player_id": str(player["player_id"]), "name": player["name"], "type": "wickets", "current": total_wickets, "target": m, "needed": m - total_wickets})
                break
        for m in MATCH_MILESTONES:
            if total_matches < m:
                upcoming.append({"player_id": str(player["player_id"]), "name": player["name"], "type": "matches", "current": total_matches, "target": m, "needed": m - total_matches})
                break

    upcoming.sort(key=lambda x: x["needed"])
    return upcoming[:limit]


async def get_batting_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    where = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        where += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS games,
                SUM(pss.batting_innings) AS innings,
                SUM(pss.runs) AS total_runs,
                MAX(pss.high_score) AS high_score,
                ROUND(
                    SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0),
                    2
                ) AS average
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            {where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY total_runs DESC NULLS LAST LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_runs",
    limit: int = 20,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_runs", "average", "high_score", "fifties", "hundreds",
        "total_sixes", "total_fours", "ducks", "innings",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_runs"

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.batting_innings) AS innings,
            SUM(pss.runs) AS total_runs,
            MAX(pss.high_score) AS high_score,
            ROUND(
                SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0),
                2
            ) AS average,
            SUM(pss.fifties) AS fifties,
            SUM(pss.hundreds) AS hundreds,
            SUM(pss.sixes) AS total_sixes,
            SUM(pss.fours) AS total_fours,
            SUM(pss.ducks) AS ducks
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += f" GROUP BY p.id, COALESCE(p.display_name_override, p.name) ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    return await get_bowling_leaderboard_extended(session, org_id, season_id, grade_id, "total_wickets", limit)


async def get_fielding_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_catches",
    limit: int = 20,
) -> list[dict]:
    ALLOWED_SORTS = {"total_catches", "total_run_outs", "total_stumpings"}
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_catches"

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.catches) AS total_catches,
            SUM(pss.run_outs) AS total_run_outs,
            SUM(pss.stumpings) AS total_stumpings
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    base += f" GROUP BY p.id, COALESCE(p.display_name_override, p.name) ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

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
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.wickets) AS total_wickets,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
            MAX(pss.best_bowling_wickets) AS best_figures_wickets,
            MAX(pss.best_bowling_figures) AS best_bowling_figures,
            SUM(pss.maidens) AS total_maidens,
            SUM(pss.overs) AS total_overs,
            COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    params: dict = {"org_id": org_id, "limit": limit}
    if season_id:
        base += " AND pss.season_id = :season_id"
        params["season_id"] = season_id
    sort_dir = "ASC" if sort_by in ("economy", "average") else "DESC"
    base += f" GROUP BY p.id, COALESCE(p.display_name_override, p.name) ORDER BY {sort_by} {sort_dir} NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_by_grade(session: AsyncSession, player_id: str, org_id: Optional[str] = None) -> list[dict]:
    result = await session.execute(
        text("""
            WITH grade_spells AS (
                SELECT
                    COALESCE(am.canonical_name, gr.name) AS grade_name,
                    bs.wickets,
                    bs.runs,
                    bs.overs,
                    bs.maidens
                FROM bowling_spells bs
                JOIN games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                LEFT JOIN LATERAL (
                    SELECT canonical_name FROM grade_merge_logs gml
                    WHERE gml.org_id = CAST(:org_id AS UUID)
                      AND gml.alias_name = gr.name
                      AND gml.undone_at IS NULL
                    LIMIT 1
                ) am ON TRUE
                WHERE bs.player_id = :pid
                  AND bs.wickets IS NOT NULL
            ),
            best_per_grade AS (
                SELECT DISTINCT ON (grade_name)
                    grade_name,
                    wickets AS best_wickets,
                    runs AS best_runs
                FROM grade_spells
                ORDER BY grade_name, wickets DESC, runs ASC
            )
            SELECT
                gs.grade_name,
                COUNT(*) AS spells,
                COALESCE(SUM(gs.wickets), 0) AS wickets,
                COALESCE(SUM(gs.runs), 0) AS runs_conceded,
                COALESCE(SUM(gs.overs), 0) AS total_overs,
                COALESCE(SUM(gs.maidens), 0) AS maidens,
                ROUND(SUM(gs.runs)::numeric / NULLIF(SUM(gs.wickets), 0), 2) AS average,
                ROUND(SUM(gs.runs)::numeric / NULLIF(SUM(gs.overs), 0), 2) AS economy,
                bp.best_wickets,
                bp.best_runs
            FROM grade_spells gs
            JOIN best_per_grade bp ON bp.grade_name = gs.grade_name
            GROUP BY gs.grade_name, bp.best_wickets, bp.best_runs
            ORDER BY SUM(gs.wickets) DESC
        """),
        {"pid": player_id, "org_id": org_id},
    )
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
        "seasons": int(row.get("seasons") or 0),
        "total_players": int(row.get("total_players") or 0),
        "total_runs": int(row.get("total_runs") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "highest_score": row.get("highest_score"),
    }


async def get_grade_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
) -> list[dict]:
    where = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id}
    if season_id:
        where += " AND pss.season_id = :season_id"
        params["season_id"] = season_id

    result = await session.execute(
        text(f"""
            SELECT
                COALESCE(gml.canonical_name, gr.name) AS grade_name,
                SUM(pss.runs) AS total_runs,
                SUM(pss.wickets) AS total_wickets,
                COUNT(DISTINCT pss.player_id) AS players
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            JOIN grades gr ON gr.season_id = pss.season_id
            LEFT JOIN grade_merge_logs gml
                ON gml.org_id = p.organisation_id
               AND gml.alias_name = gr.name
               AND gml.undone_at IS NULL
            {where}
            GROUP BY COALESCE(gml.canonical_name, gr.name)
            ORDER BY total_runs DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_org_game_ids(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
) -> list[str]:
    params: dict = {"org_id": org_id}
    clause = ""
    if season_id:
        clause = " AND gr.season_id = :season_id"
        params["season_id"] = season_id
    result = await session.execute(
        text(f"""
            SELECT g.id::text
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org_id {clause}
            ORDER BY g.played_at DESC NULLS LAST
        """),
        params,
    )
    return [r[0] for r in result]


async def get_game_scorecard(session: AsyncSession, game_id: str) -> Optional[dict]:
    result = await session.execute(
        text("""
            SELECT
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.result,
                g.played_at,
                gr.name AS grade_name,
                s.name AS season_name
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE g.id = :gid
        """),
        {"gid": game_id},
    )
    game_row = result.mappings().first()
    if not game_row:
        return None
    game = dict(game_row)

    batting_res = await session.execute(
        text("""
            SELECT
                bi.innings_number,
                bi.batting_position,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.id::text AS player_id,
                bi.runs,
                bi.not_out,
                bi.dismissal_type,
                bi.fours,
                bi.sixes,
                bi.balls_faced
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            WHERE bi.game_id = :gid
            ORDER BY bi.innings_number, bi.batting_position
        """),
        {"gid": game_id},
    )
    batting = [dict(r) for r in batting_res.mappings()]

    bowling_res = await session.execute(
        text("""
            SELECT
                bs.innings_number,
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.id::text AS player_id,
                bs.overs,
                bs.maidens,
                bs.runs,
                bs.wickets,
                bs.economy
            FROM bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            WHERE bs.game_id = :gid
            ORDER BY bs.innings_number, bs.wickets DESC NULLS LAST
        """),
        {"gid": game_id},
    )
    bowling = [dict(r) for r in bowling_res.mappings()]

    fielding_res = await session.execute(
        text("""
            SELECT
                COALESCE(p.display_name_override, p.name) AS player_name,
                p.id::text AS player_id,
                fs.catches,
                fs.run_outs,
                fs.stumpings
            FROM fielding_stats fs
            JOIN players p ON p.id = fs.player_id
            WHERE fs.game_id = :gid
        """),
        {"gid": game_id},
    )
    fielding = [dict(r) for r in fielding_res.mappings()]

    partnerships_res = await session.execute(
        text("""
            SELECT
                pt.innings_number,
                pt.wicket_number,
                pt.runs,
                pt.batter1_id::text,
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                pt.batter2_id::text,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name
            FROM partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.game_id = :gid
            ORDER BY pt.innings_number, pt.wicket_number
        """),
        {"gid": game_id},
    )
    partnerships = [dict(r) for r in partnerships_res.mappings()]

    return {
        **game,
        "batting": batting,
        "bowling": bowling,
        "fielding": fielding,
        "partnerships": partnerships,
    }


async def get_game_by_playhq_id(session: AsyncSession, playhq_game_id: str) -> Optional[dict]:
    result = await session.execute(
        text("""
            SELECT g.id::text, g.home_team, g.away_team, g.result, g.played_at,
                   gr.name AS grade_name, s.name AS season_name
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE g.playhq_game_id = :gid
        """),
        {"gid": playhq_game_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_recent_games(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    clauses = ["s.organisation_id = :org_id"]
    if season_id:
        clauses.append("s.id = :season_id")
        params["season_id"] = season_id
    if grade_id:
        clauses.append("g.grade_id = :grade_id")
        params["grade_id"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.result,
                g.played_at,
                gr.name AS grade_name,
                s.name AS season_name
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_game_partnerships(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                pt.wicket_number,
                pt.runs,
                pt.innings_number,
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                p1.id::text AS batter1_id,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name,
                p2.id::text AS batter2_id
            FROM partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.game_id = :gid
            ORDER BY pt.innings_number, pt.wicket_number
        """),
        {"gid": game_id},
    )
    return [dict(r) for r in result.mappings()]
