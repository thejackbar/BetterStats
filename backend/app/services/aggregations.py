from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from datetime import date as date_cls
import uuid

from app.services.milestone_rules import next_threshold, reach_window
from app.services.season_aliases import (
    resolve_season_filter,
    resolve_season_filter_no_org,
)

# Merge-aware grade match fragment (gr must already be joined).
# Matches grades that are the selected canonical OR are aliases merged into it.
_GRADE_MATCH = (
    "(COALESCE(gr.display_name_override, gr.name) = :grade_name"
    " OR EXISTS (SELECT 1 FROM grade_merge_logs gml"
    " WHERE gml.org_id = CAST(:org_id AS UUID)"
    " AND gml.alias_name = gr.name AND gml.undone_at IS NULL"
    " AND (gml.canonical_name = :grade_name"
    " OR EXISTS (SELECT 1 FROM grades gr2 JOIN seasons s2 ON s2.id = gr2.season_id"
    " WHERE gr2.name = gml.canonical_name AND s2.organisation_id = CAST(:org_id AS UUID)"
    " AND gr2.display_name_override = :grade_name))))"
)


async def get_career_batting(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    season_clause = " AND pss.season_id = ANY(:sids)" if season_ids else ""
    params: dict = {"pid": player_id}
    if season_ids:
        params["sids"] = season_ids
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.organisation_id,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                MAX(pss.high_score) AS high_score,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
                COALESCE(SUM(pss.fifties), 0) AS fifties,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.ducks), 0) AS ducks,
                COALESCE(SUM(pss.matches), 0) AS games
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_bowling(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    season_clause = " AND pss.season_id = ANY(:sids)" if season_ids else ""
    params: dict = {"pid": player_id}
    if season_ids:
        params["sids"] = season_ids
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.organisation_id,
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
                MAX(pss.best_bowling_wickets) AS best_figures_wickets,
                (ARRAY_AGG(pss.best_bowling_figures
                    ORDER BY pss.best_bowling_wickets DESC NULLS LAST,
                             NULLIF(SPLIT_PART(pss.best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
                 ) FILTER (WHERE pss.best_bowling_figures IS NOT NULL AND pss.best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_bowling_figures,
                COALESCE(SUM(pss.maidens), 0) AS total_maidens,
                COALESCE(SUM(pss.overs), 0) AS total_overs,
                COALESCE(SUM(pss.runs_conceded), 0) AS total_runs,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS bowling_strike_rate
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_career_fielding(session: AsyncSession, player_id: str, season_id: Optional[str] = None) -> Optional[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    season_clause = " AND pss.season_id = ANY(:sids)" if season_ids else ""
    params: dict = {"pid": player_id}
    if season_ids:
        params["sids"] = season_ids
    result = await session.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.organisation_id,
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.catches), 0) AS total_catches,
                COALESCE(SUM(pss.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(pss.catches_non_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(pss.assisted_run_outs), 0) AS total_assisted_run_outs,
                COALESCE(SUM(pss.unassisted_run_outs), 0) AS total_unassisted_run_outs,
                COALESCE(SUM(pss.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id{season_clause}
            WHERE p.id = :pid
            GROUP BY p.id, p.name, p.organisation_id
        """),
        params,
    )
    row = result.mappings().first()
    return dict(row) if row else None


def _build_recent_games_cte(player_id_param: str, n_param: str) -> str:
    # UNION (not UNION ALL) already deduplicates game_ids; the JOIN with games
    # is 1:1 on the PK, so no DISTINCT is needed — and PostgreSQL requires
    # ORDER BY columns to appear in the SELECT list when DISTINCT is used.
    return f"""recent_games AS (
        SELECT g.id AS game_id
        FROM (
            SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:{player_id_param} AS UUID)
        ) ap
        JOIN v_effective_games g ON g.id = ap.game_id
        ORDER BY g.played_at DESC NULLS LAST
        LIMIT :{n_param}
    )"""


def _build_date_filtered_games_cte(player_id_param: str, start_date: Optional[str], end_date: Optional[str]) -> str:
    """CTE: the player's games filtered to a date window.

    Uses g.played_at when present; falls back to season-window overlap
    (Oct s.year → Apr s.year+1) for games where played_at is NULL.
    Games whose seasons have no year (s.year IS NULL) are excluded from
    the fallback path — they can only match via played_at.
    """
    date_conds = []
    season_conds = []
    if start_date:
        date_conds.append("g.played_at >= CAST(:start_date AS DATE)")
        season_conds.append("MAKE_DATE(s.year + 1, 4, 30) >= CAST(:start_date AS DATE)")
    if end_date:
        date_conds.append("g.played_at <= CAST(:end_date AS DATE)")
        season_conds.append("MAKE_DATE(s.year, 10, 1) <= CAST(:end_date AS DATE)")

    date_clause = " AND ".join(date_conds) if date_conds else "TRUE"
    season_clause = " AND ".join(season_conds) if season_conds else "TRUE"

    where_clause = f"""WHERE (
            (g.played_at IS NOT NULL AND {date_clause})
            OR (g.played_at IS NULL AND s.year IS NOT NULL AND {season_clause})
        )"""

    return f"""date_filtered_games AS (
        SELECT g.id AS game_id
        FROM (
            SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:{player_id_param} AS UUID)
            UNION
            SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:{player_id_param} AS UUID)
        ) ap
        JOIN v_effective_games g ON g.id = ap.game_id
        LEFT JOIN grades gr ON gr.id = g.grade_id
        LEFT JOIN seasons s ON s.id = gr.season_id
        {where_clause}
    )"""


async def get_career_batting_from_innings(
    session: AsyncSession,
    player_id: str,
    last_n_games: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""

    if last_n_games:
        params["n"] = last_n_games
        ctes.append(_build_recent_games_cte("pid", "n"))
        game_filter = "AND bi.game_id IN (SELECT game_id FROM recent_games)"
    elif start_date or end_date:
        if start_date:
            params["start_date"] = date_cls.fromisoformat(start_date)
        if end_date:
            params["end_date"] = date_cls.fromisoformat(end_date)
        ctes.append(_build_date_filtered_games_cte("pid", start_date, end_date))
        game_filter = "AND bi.game_id IN (SELECT game_id FROM date_filtered_games)"

    ctes.append(f"""qualifying AS (
        SELECT bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out, bi.game_id
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        WHERE bi.player_id = CAST(:pid AS UUID)
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
          {game_filter}
    )""")

    sql = f"""
        WITH {', '.join(ctes)}
        SELECT
            COALESCE(COUNT(*), 0) AS innings,
            COALESCE(SUM(runs), 0) AS total_runs,
            MAX(runs) AS high_score,
            ROUND(SUM(runs)::numeric / NULLIF(COUNT(*) - SUM(not_out::int), 0), 2) AS average,
            ROUND(SUM(runs)::numeric / NULLIF(SUM(balls), 0) * 100, 2) AS strike_rate,
            COALESCE(SUM(CASE WHEN runs >= 50 AND runs < 100 THEN 1 ELSE 0 END), 0) AS fifties,
            COALESCE(SUM(CASE WHEN runs >= 100 THEN 1 ELSE 0 END), 0) AS hundreds,
            COALESCE(SUM(CASE WHEN runs = 0 AND NOT not_out THEN 1 ELSE 0 END), 0) AS ducks,
            COALESCE(SUM(fours), 0) AS total_fours,
            COALESCE(SUM(sixes), 0) AS total_sixes,
            COUNT(DISTINCT game_id) AS games
        FROM qualifying
    """
    result = await session.execute(text(sql), params)
    row = result.mappings().first()
    if not row:
        return None
    d = dict(row)
    d["player_id"] = player_id
    return d


async def get_career_bowling_from_spells(
    session: AsyncSession,
    player_id: str,
    last_n_games: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""

    if last_n_games:
        params["n"] = last_n_games
        ctes.append(_build_recent_games_cte("pid", "n"))
        game_filter = "AND bs.game_id IN (SELECT game_id FROM recent_games)"
    elif start_date or end_date:
        if start_date:
            params["start_date"] = date_cls.fromisoformat(start_date)
        if end_date:
            params["end_date"] = date_cls.fromisoformat(end_date)
        ctes.append(_build_date_filtered_games_cte("pid", start_date, end_date))
        game_filter = "AND bs.game_id IN (SELECT game_id FROM date_filtered_games)"

    ctes.append(f"""qualifying AS (
        SELECT bs.wickets, bs.runs, bs.maidens, bs.overs, bs.game_id
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        WHERE bs.player_id = CAST(:pid AS UUID)
          {game_filter}
    )""")

    sql = f"""
        WITH {', '.join(ctes)}
        SELECT
            COALESCE(SUM(wickets), 0) AS total_wickets,
            ROUND(SUM(runs)::numeric / NULLIF(SUM(wickets), 0), 2) AS average,
            ROUND(SUM(runs)::numeric / NULLIF(SUM(overs), 0), 2) AS economy,
            (SELECT wickets FROM qualifying ORDER BY wickets DESC, runs ASC LIMIT 1) AS best_figures_wickets,
            (SELECT wickets::text || '/' || runs::text FROM qualifying ORDER BY wickets DESC, runs ASC LIMIT 1) AS best_bowling_figures,
            COALESCE(SUM(maidens), 0) AS total_maidens,
            COALESCE(SUM(overs), 0) AS total_overs,
            COALESCE(SUM(CASE WHEN wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors,
            COUNT(DISTINCT game_id) AS games,
            ROUND(SUM(overs)::numeric * 6 / NULLIF(SUM(wickets), 0), 2) AS bowling_strike_rate
        FROM qualifying
    """
    result = await session.execute(text(sql), params)
    row = result.mappings().first()
    if not row:
        return None
    d = dict(row)
    d["player_id"] = player_id
    return d


async def get_career_fielding_from_stats(
    session: AsyncSession,
    player_id: str,
    last_n_games: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""

    if last_n_games:
        params["n"] = last_n_games
        ctes.append(_build_recent_games_cte("pid", "n"))
        game_filter = "AND fs.game_id IN (SELECT game_id FROM recent_games)"
    elif start_date or end_date:
        if start_date:
            params["start_date"] = date_cls.fromisoformat(start_date)
        if end_date:
            params["end_date"] = date_cls.fromisoformat(end_date)
        ctes.append(_build_date_filtered_games_cte("pid", start_date, end_date))
        game_filter = "AND fs.game_id IN (SELECT game_id FROM date_filtered_games)"

    ctes.append(f"""qualifying AS (
        SELECT fs.catches, fs.catches_wk, fs.run_outs, fs.stumpings, fs.game_id
        FROM v_effective_fielding_stats fs
        JOIN v_effective_games g ON g.id = fs.game_id
        WHERE fs.player_id = CAST(:pid AS UUID)
          {game_filter}
    )""")

    sql = f"""
        WITH {', '.join(ctes)}
        SELECT
            COALESCE(SUM(catches), 0) AS total_catches,
            COALESCE(SUM(catches_wk), 0) AS total_catches_wk,
            COALESCE(SUM(catches - catches_wk), 0) AS total_catches_non_wk,
            COALESCE(SUM(run_outs), 0) AS total_run_outs,
            COALESCE(SUM(stumpings), 0) AS total_stumpings,
            COALESCE(SUM(catches + run_outs + stumpings), 0) AS total_dismissals,
            COUNT(DISTINCT game_id) AS games
        FROM qualifying
    """
    result = await session.execute(text(sql), params)
    row = result.mappings().first()
    if not row:
        return None
    d = dict(row)
    d["player_id"] = player_id
    return d


async def get_batting_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
    finals_only: Optional[bool] = None,
) -> list[dict]:
    return await get_batting_leaderboard_extended(session, org_id, season_id, grade_id, "total_runs", limit, finals_only=finals_only)


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
    finals_only: Optional[bool] = None,
) -> list[dict]:
    return await get_bowling_leaderboard_extended(session, org_id, season_id, grade_id, "total_wickets", limit, finals_only=finals_only)


async def get_fielding_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_dismissals",
    limit: int = 20,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    ALLOWED_SORTS = {"total_catches", "total_catches_non_wk", "total_catches_wk", "total_run_outs", "total_stumpings", "total_dismissals", "games"}
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_dismissals"

    season_ids = await resolve_season_filter(session, org_id, season_id)

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = fs.game_id AND gap.player_id = fs.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if gender:
        params["gender"] = gender
    if season_ids:
        params["season_ids"] = season_ids

    if grade_id:
        params["grade_id"] = grade_id
        base = f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT fs.game_id) AS games,
                COALESCE(SUM(fs.catches), 0) AS total_catches,
                COALESCE(SUM(fs.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(fs.catches - fs.catches_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(fs.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0) AS total_dismissals
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id{captain_join}
            JOIN players p ON p.id = fs.player_id
            WHERE g.grade_id = :grade_id AND p.organisation_id = :org_id{finals_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT fs.game_id) AS games,
                COALESCE(SUM(fs.catches), 0) AS total_catches,
                COALESCE(SUM(fs.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(fs.catches - fs.catches_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(fs.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0) AS total_dismissals
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN grades gr ON gr.id = g.grade_id{captain_join}
            JOIN players p ON p.id = fs.player_id
            WHERE {_GRADE_MATCH}{season_clause}
              AND p.organisation_id = :org_id{finals_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if finals_only:
        # When finals_only=True with no grade filter, switch to per-game query
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT fs.game_id) AS games,
                COALESCE(SUM(fs.catches), 0) AS total_catches,
                COALESCE(SUM(fs.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(fs.catches - fs.catches_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(fs.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0) AS total_dismissals
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id{captain_join}
            JOIN players p ON p.id = fs.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND g.is_final = TRUE{season_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    elif captain_only:
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT fs.game_id) AS games,
                COALESCE(SUM(fs.catches), 0) AS total_catches,
                COALESCE(SUM(fs.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(fs.catches - fs.catches_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(fs.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS total_stumpings,
                COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0) AS total_dismissals
            FROM v_effective_fielding_stats fs
            JOIN v_effective_games g ON g.id = fs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN game_appearances gap ON gap.game_id = fs.game_id AND gap.player_id = fs.player_id AND gap.is_captain = TRUE
            JOIN players p ON p.id = fs.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.catches) AS total_catches,
            SUM(pss.catches_wk) AS total_catches_wk,
            SUM(pss.catches_non_wk) AS total_catches_non_wk,
            SUM(pss.run_outs) AS total_run_outs,
            SUM(pss.stumpings) AS total_stumpings,
            SUM(pss.catches + pss.run_outs + pss.stumpings) AS total_dismissals
        FROM v_effective_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    if season_ids:
        base += " AND pss.season_id = ANY(:season_ids)"
    if gender:
        base += " AND p.gender = :gender"
    if overseas == "only":
        base += " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        base += " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    base += f" GROUP BY p.id, COALESCE(p.display_name_override, p.name) ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_player_batting_innings(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
) -> list[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    clauses = ["bi.player_id = :pid"]
    params: dict = {"pid": player_id}
    if season_ids:
        clauses.append("s.id = ANY(:sids)")
        params["sids"] = season_ids
    if grade_id:
        clauses.append("gr.id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bi.runs,
                bi.balls,
                bi.fours,
                bi.sixes,
                bi.strike_rate,
                bi.dismissal_type,
                bi.not_out,
                bi.batting_position,
                bi.innings_number,
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.played_at::text,
                g.result,
                COALESCE(gr.display_name_override, gr.name) AS grade_name,
                s.name AS season_name,
                s.year AS season_year
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
              AND (bi.did_not_bat IS NOT TRUE)
            ORDER BY g.played_at DESC
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
    season_ids = await resolve_season_filter_no_org(session, season_id)
    clauses = ["bs.player_id = :pid"]
    params: dict = {"pid": player_id}
    if season_ids:
        clauses.append("s.id = ANY(:sids)")
        params["sids"] = season_ids
    if grade_id:
        clauses.append("gr.id = :gid")
        params["gid"] = grade_id
    where = " AND ".join(clauses)
    result = await session.execute(
        text(f"""
            SELECT
                bs.overs,
                bs.maidens,
                bs.runs,
                bs.wickets,
                bs.wides,
                bs.no_balls,
                bs.economy,
                bs.innings_number,
                g.id::text AS game_id,
                g.home_team,
                g.away_team,
                g.played_at::text,
                g.result,
                COALESCE(gr.display_name_override, gr.name) AS grade_name,
                s.name AS season_name,
                s.year AS season_year
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE {where}
            ORDER BY g.played_at DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                CASE
                    WHEN bi.not_out THEN 'not out'
                    WHEN bi.dismissal_type IS NULL THEN 'unknown'
                    WHEN bi.dismissal_type = 'b' OR bi.dismissal_type LIKE 'b %' THEN 'bowled'
                    WHEN bi.dismissal_type = 'c' OR bi.dismissal_type LIKE 'c %' THEN 'caught'
                    WHEN bi.dismissal_type = 'lbw' OR bi.dismissal_type LIKE 'lbw %'
                         OR bi.dismissal_type = 'leg before wicket'
                         OR bi.dismissal_type LIKE 'leg before wicket%' THEN 'lbw'
                    WHEN bi.dismissal_type = 'st' OR bi.dismissal_type LIKE 'st %' THEN 'stumped'
                    WHEN bi.dismissal_type LIKE 'run out%' THEN 'run out'
                    WHEN bi.dismissal_type = 'hit wicket' OR bi.dismissal_type LIKE 'hit wicket%' THEN 'hit wicket'
                    WHEN bi.dismissal_type LIKE 'ret%' THEN 'retired'
                    ELSE bi.dismissal_type
                END AS dismissal_type,
                COUNT(*) AS count
            FROM v_effective_batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
              AND (bi.did_not_bat IS NOT TRUE)
            GROUP BY 1
            ORDER BY COUNT(*) DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_bowling_dismissal_breakdown(session: AsyncSession, player_id: str) -> list[dict]:
    """Breakdown of HOW this bowler dismisses batters (bowled/caught/lbw/etc).

    Counts bowler_wickets rows where bowler_id = player. caught-and-bowled is
    its own slice. Excludes non-credit dismissal types (run-outs etc.) — they
    aren't recorded in bowler_wickets in the first place.
    """
    result = await session.execute(
        text("""
            SELECT
                COALESCE(bw.dismissal_type, 'unknown') AS dismissal_type,
                COUNT(*) AS count
            FROM bowler_wickets bw
            WHERE bw.bowler_id = :pid
            GROUP BY 1
            ORDER BY COUNT(*) DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_bowling_by_batter_position(session: AsyncSession, player_id: str) -> list[dict]:
    """How many batters at each batting position (1-13) this bowler has dismissed.

    Returns one row per position with a wicket count. Positions with zero
    wickets are still returned so the chart shows the full spread. 12-13
    cover the rare cases of substitutes / forfeits where CA assigns a higher
    batting order than the standard 1-11.
    """
    result = await session.execute(
        text("""
            WITH positions AS (
                SELECT generate_series(1, 13) AS batting_position
            )
            SELECT
                p.batting_position,
                COALESCE(COUNT(bw.id), 0) AS wickets
            FROM positions p
            LEFT JOIN bowler_wickets bw
              ON bw.batter_position = p.batting_position
             AND bw.bowler_id = :pid
            GROUP BY p.batting_position
            ORDER BY p.batting_position
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
            FROM v_effective_batting_innings bi
            WHERE bi.player_id = :pid
              AND bi.batting_position IS NOT NULL
              AND bi.runs IS NOT NULL
              AND (bi.did_not_bat IS NOT TRUE)
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
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(*) AS innings,
                SUM(bi.runs) AS runs,
                ROUND(
                    SUM(bi.runs)::numeric /
                    NULLIF(COUNT(*) FILTER (WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL), 0),
                    2
                ) AS average,
                MAX(bi.runs) AS high_score
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
              AND (bi.did_not_bat IS NOT TRUE)
            GROUP BY COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
            ORDER BY SUM(bi.runs) DESC
        """),
        {"pid": player_id, "org_id": org_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_team_breakdown(
    session: AsyncSession,
    player_id: str,
    org_id: Optional[str] = None,
    season_id: Optional[str] = None,
) -> dict:
    """Per-grade match breakdown for a single player.

    Returns ``{rows, unattributed, total_aggregate_matches}``. Each row is a
    canonical (merge-aware) grade with matches, seasons, won/lost/drawn,
    win_pct, and a ``scorecard_matches`` count for the per-game source.

    ``player_season_stats.matches`` is the CA aggregate count and is the source
    of truth for "how many games did this player play". Per-game scorecard
    coverage can be incomplete, so we attribute any per-season gap to a grade
    when only one grade has per-game appearances that season (the unambiguous
    case). Truly ambiguous seasons accumulate into ``unattributed``.
    """
    season_clause_gr = ""
    season_clause_pss = ""
    params: dict = {"pid": player_id, "org_id": org_id}
    season_ids = await resolve_season_filter(session, org_id, season_id) if season_id else None
    if season_ids:
        season_clause_gr = " AND gr.season_id = ANY(:sids)"
        season_clause_pss = " AND pss.season_id = ANY(:sids)"
        params["sids"] = season_ids

    # Per-grade summary: roll up appearances to the canonical grade name.
    summary = await session.execute(
        text(f"""
            WITH appearances AS (
                SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
                WHERE bi.player_id = CAST(:pid AS UUID)
                UNION
                SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
                WHERE bs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
                WHERE fs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT ga.player_id, ga.game_id FROM game_appearances ga
                WHERE ga.player_id = CAST(:pid AS UUID)
            )
            SELECT
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ap.game_id) AS matches,
                COUNT(DISTINCT gr.season_id) AS seasons,
                COUNT(*) FILTER (WHERE g.result = 'WIN')  AS won,
                COUNT(*) FILTER (WHERE g.result = 'LOSS') AS lost,
                COUNT(*) FILTER (WHERE g.result IN ('DRAW', 'TIE')) AS drawn
            FROM appearances ap
            JOIN v_effective_games g  ON g.id = ap.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE TRUE {season_clause_gr}
            GROUP BY COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
            ORDER BY matches DESC, grade_name
        """),
        params,
    )
    rows: list[dict] = []
    rows_by_name: dict[str, dict] = {}
    for r in summary.mappings():
        d = dict(r)
        matches = int(d.get("matches") or 0)
        won = int(d.get("won") or 0)
        lost = int(d.get("lost") or 0)
        drawn = int(d.get("drawn") or 0)
        row = {
            "grade_name": d.get("grade_name"),
            "scorecard_matches": matches,
            "matches": matches,
            "seasons": int(d.get("seasons") or 0),
            "won": won,
            "lost": lost,
            "drawn": drawn,
            "win_pct": None,
            "attributed_unknown": 0,
        }
        rows.append(row)
        rows_by_name[row["grade_name"]] = row

    # Per-(season, grade) per-game counts — needed for the heuristic fallback
    # used when player_season_grade_stats hasn't been populated yet.
    per_season_grade = await session.execute(
        text(f"""
            WITH appearances AS (
                SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:pid AS UUID)
                UNION
                SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:pid AS UUID)
                UNION
                SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:pid AS UUID)
            )
            SELECT
                gr.season_id AS season_id,
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COUNT(DISTINCT ap.game_id) AS games
            FROM appearances ap
            JOIN v_effective_games g  ON g.id = ap.game_id
            JOIN grades gr ON gr.id = g.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE TRUE {season_clause_gr}
            GROUP BY gr.season_id, COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
        """),
        params,
    )
    season_grade_games: dict = {}  # season_id -> {grade_name: count}
    for r in per_season_grade.mappings():
        sid = str(r["season_id"])
        season_grade_games.setdefault(sid, {})[r["grade_name"]] = int(r["games"] or 0)

    # Per-season CA aggregate match counts (kept as a sanity reference and
    # for the heuristic fallback below).
    season_totals = await session.execute(
        text(f"""
            SELECT pss.season_id, COALESCE(pss.matches, 0) AS matches
            FROM v_effective_player_season_stats pss
            WHERE pss.player_id = CAST(:pid AS UUID)
              {season_clause_pss}
        """),
        params,
    )
    season_aggregate = {str(r["season_id"]): int(r["matches"] or 0) for r in season_totals.mappings()}

    # Exact per-(season,grade) aggregate from CA (when synced). Source of truth.
    per_grade_agg = await session.execute(
        text(f"""
            SELECT
                psgs.season_id,
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                COALESCE(psgs.matches, 0) AS matches
            FROM player_season_grade_stats psgs
            JOIN grades gr ON gr.id = psgs.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = gr.name
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, gr.name)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE psgs.player_id = CAST(:pid AS UUID)
              {(" AND psgs.season_id = ANY(:sids)") if season_ids else ""}
        """),
        params,
    )
    # Roll up per-(season, canonical-grade-name): sum because merged grades
    # could resolve to the same canonical name within a season.
    exact_per_season_grade: dict = {}  # season_id -> {grade_name: matches}
    exact_per_grade: dict = {}         # grade_name -> total matches
    for r in per_grade_agg.mappings():
        sid = str(r["season_id"])
        gn = r["grade_name"]
        m = int(r["matches"] or 0)
        exact_per_season_grade.setdefault(sid, {})[gn] = exact_per_season_grade.get(sid, {}).get(gn, 0) + m
        exact_per_grade[gn] = exact_per_grade.get(gn, 0) + m

    # Track which seasons have exact per-grade data so we don't double-count
    # them with the legacy heuristic.
    seasons_with_exact = set(exact_per_season_grade.keys())

    unattributed = 0

    # 1) Apply exact per-grade matches where available.
    for grade_name, agg_matches in exact_per_grade.items():
        row = rows_by_name.get(grade_name)
        if row is None:
            row = {
                "grade_name": grade_name,
                "scorecard_matches": 0,
                "matches": 0,
                "seasons": 0,
                "won": 0,
                "lost": 0,
                "drawn": 0,
                "win_pct": None,
                "attributed_unknown": 0,
            }
            rows.append(row)
            rows_by_name[grade_name] = row
        extra = max(0, agg_matches - (row.get("scorecard_matches") or 0))
        if extra > 0:
            row["matches"] = (row.get("scorecard_matches") or 0) + extra
            row["attributed_unknown"] = extra
        # Update seasons count if exact data covers seasons the per-game data missed
        seasons_seen = {sid for sid, gn_map in exact_per_season_grade.items() if grade_name in gn_map}
        row["seasons"] = max(row.get("seasons") or 0, len(seasons_seen))

    # 2) Heuristic fallback for seasons WITHOUT per-grade aggregate yet.
    grade_attributed_fallback: dict = {}
    for sid, agg in season_aggregate.items():
        if sid in seasons_with_exact:
            continue
        per_game = sum(season_grade_games.get(sid, {}).values())
        gap = agg - per_game
        if gap <= 0:
            continue
        grades_with_data = list(season_grade_games.get(sid, {}).keys())
        if len(grades_with_data) == 1:
            grade_attributed_fallback[grades_with_data[0]] = grade_attributed_fallback.get(grades_with_data[0], 0) + gap
        else:
            unattributed += gap

    for grade_name, extra in grade_attributed_fallback.items():
        row = rows_by_name.get(grade_name)
        if row is None:
            row = {
                "grade_name": grade_name,
                "scorecard_matches": 0,
                "matches": extra,
                "attributed_unknown": extra,
                "seasons": 0,
                "won": 0,
                "lost": 0,
                "drawn": 0,
                "win_pct": None,
            }
            rows.append(row)
            rows_by_name[grade_name] = row
        else:
            row["matches"] = (row.get("matches") or 0) + extra
            row["attributed_unknown"] = (row.get("attributed_unknown") or 0) + extra

    rows.sort(key=lambda r: (-(r.get("matches") or 0), r.get("grade_name") or ""))
    for row in rows:
        decided = row["won"] + row["lost"] + row["drawn"]
        row["win_pct"] = round(row["won"] / decided * 100, 1) if decided > 0 else None

    total_aggregate = sum(season_aggregate.values())
    return {
        "rows": rows,
        "unattributed": unattributed,
        "total_aggregate_matches": total_aggregate,
    }


async def get_season_by_season(session: AsyncSession, player_id: str) -> list[dict]:
    # Merge-aware: if Summer 25/26 + Winter 25/26 are aliased into one canonical
    # season, sum their stats into a single row keyed on the canonical season.
    # Non-aliased seasons map to themselves so the GROUP BY collapses to one
    # row per season either way.
    result = await session.execute(
        text("""
            WITH per_pss AS (
                SELECT
                    pss.*,
                    COALESCE(sa.canonical_season_id, pss.season_id) AS canonical_season_id
                FROM v_effective_player_season_stats pss
                LEFT JOIN season_aliases sa
                  ON sa.alias_season_id = pss.season_id
                 AND sa.undone_at IS NULL
                WHERE pss.player_id = :pid
            )
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                SUM(p.matches) AS matches,
                SUM(p.batting_innings) AS batting_innings,
                SUM(p.runs) AS total_runs,
                MAX(p.high_score) AS high_score,
                ROUND(SUM(p.runs)::numeric / NULLIF(SUM(p.batting_innings) - SUM(p.not_outs), 0), 2) AS batting_average,
                ROUND(SUM(p.runs)::numeric / NULLIF(SUM(p.balls_faced), 0) * 100, 2) AS strike_rate,
                SUM(p.fifties) AS fifties,
                SUM(p.hundreds) AS hundreds,
                SUM(p.not_outs) AS not_outs,
                SUM(p.ducks) AS ducks,
                SUM(p.fours) AS total_fours,
                SUM(p.sixes) AS total_sixes,
                SUM(p.wickets) AS total_wickets,
                SUM(p.runs_conceded) AS bowling_runs_conceded,
                SUM(p.overs) AS total_overs,
                ROUND(SUM(p.runs_conceded)::numeric / NULLIF(SUM(p.wickets), 0), 2) AS bowling_average,
                ROUND(SUM(p.runs_conceded)::numeric / NULLIF(SUM(p.bowling_balls), 0) * 6, 2) AS economy,
                MAX(p.best_bowling_wickets) AS best_bowling_wickets,
                (ARRAY_AGG(p.best_bowling_figures
                    ORDER BY p.best_bowling_wickets DESC NULLS LAST,
                             NULLIF(SPLIT_PART(p.best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
                 ) FILTER (WHERE p.best_bowling_figures IS NOT NULL AND p.best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_bowling_figures,
                SUM(p.five_wicket_innings) AS five_fors,
                SUM(p.maidens) AS total_maidens,
                SUM(p.catches) AS total_catches,
                SUM(p.catches_wk) AS total_catches_wk,
                SUM(p.catches_non_wk) AS total_catches_non_wk,
                SUM(p.run_outs) AS total_run_outs,
                SUM(p.stumpings) AS total_stumpings
            FROM per_pss p
            JOIN seasons s ON s.id = p.canonical_season_id
            GROUP BY s.id, s.name, s.year
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
            ORDER BY
                CASE m.milestone_type
                    WHEN 'runs' THEN 1
                    WHEN 'wickets' THEN 2
                    WHEN 'matches' THEN 3
                    WHEN 'catches' THEN 4
                    ELSE 5
                END,
                m.milestone_value DESC
        """),
        {"pid": player_id}
    )
    return [dict(r) for r in result.mappings()]


async def get_player_partnerships(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                CASE WHEN pt.batter1_id = :pid THEN pt.batter2_id::text ELSE pt.batter1_id::text END AS partner_id,
                CASE WHEN pt.batter1_id = :pid
                     THEN COALESCE(p2.display_name_override, p2.name)
                     ELSE COALESCE(p1.display_name_override, p1.name)
                END AS partner_name,
                COUNT(*) AS partnership_count,
                COALESCE(SUM(pt.runs), 0) AS total_runs,
                MAX(pt.runs) AS best_runs,
                MAX(g.played_at)::text AS last_played
            FROM partnerships pt
            JOIN v_effective_games g ON g.id = pt.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE (pt.batter1_id = :pid OR pt.batter2_id = :pid)
              AND pt.runs IS NOT NULL AND pt.runs > 0
            GROUP BY
                CASE WHEN pt.batter1_id = :pid THEN pt.batter2_id::text ELSE pt.batter1_id::text END,
                CASE WHEN pt.batter1_id = :pid
                     THEN COALESCE(p2.display_name_override, p2.name)
                     ELSE COALESCE(p1.display_name_override, p1.name)
                END
            ORDER BY total_runs DESC
            LIMIT 20
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            SELECT
                fow.wicket_number,
                fow.innings_number,
                fow.score_at_fall,
                fow.overs_at_fall,
                COALESCE(p.display_name_override, p.name) AS player_name,
                fow.player_id::text
            FROM fall_of_wickets fow
            LEFT JOIN players p ON p.id = fow.player_id
            WHERE fow.game_id = :gid
            ORDER BY fow.innings_number, fow.wicket_number
        """),
        {"gid": game_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_upcoming_milestones_for_org(
    session: AsyncSession,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    result = await session.execute(
        text("""
            WITH recent_seasons AS (
                SELECT s.id
                FROM seasons s
                JOIN v_effective_player_season_stats pss ON pss.season_id = s.id
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id
                GROUP BY s.id, s.year, s.name
                ORDER BY s.year DESC NULLS LAST, s.name DESC
                LIMIT 3
            ),
            active_players AS (
                SELECT DISTINCT pss.player_id
                FROM v_effective_player_season_stats pss
                WHERE pss.season_id IN (SELECT id FROM recent_seasons)
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.runs), 0) AS career_runs,
                COALESCE(SUM(pss.wickets), 0) AS career_wickets,
                COALESCE(SUM(pss.matches), 0) AS career_matches,
                COALESCE(SUM(pss.catches), 0) AS career_catches
            FROM players p
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND p.id IN (SELECT player_id FROM active_players)
            GROUP BY p.id, p.name, p.display_name_override
            HAVING COALESCE(SUM(pss.runs), 0) > 0 OR COALESCE(SUM(pss.wickets), 0) > 0
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in result.mappings()]

    # Score formula: milestone_value² / needed.
    # Heavily weights milestone size so 500-from-9000 beats 1-from-100.
    def importance_score(target, needed):
        return (target ** 2) / (needed + 1)

    CATEGORY_MAP = {
        "runs": "batting",
        "wickets": "bowling",
        "matches": "matches",
        "catches": "fielding",
    }

    upcoming = []
    for row in rows:
        player_id = str(row["player_id"])
        name = row["name"]
        totals = {
            "runs":    int(row["career_runs"]    or 0),
            "wickets": int(row["career_wickets"] or 0),
            "matches": int(row["career_matches"] or 0),
            "catches": int(row["career_catches"] or 0),
        }

        for stat, current in totals.items():
            target = next_threshold(stat, current)
            if target is None:
                continue
            needed = target - current
            # Same in-reach window as the player profile — dashboard only
            # surfaces milestones that are genuinely imminent.
            if needed > reach_window(stat, target):
                continue
            upcoming.append({
                "player_id": player_id,
                "name": name,
                "type": stat,
                "category": CATEGORY_MAP[stat],
                "current": current,
                "target": target,
                "needed": needed,
                "score": importance_score(target, needed),
            })

    upcoming.sort(key=lambda x: x["score"], reverse=True)

    # Return top 50 per category — frontend handles pagination
    per_cat = 50
    counts: dict = {}
    result = []
    for item in upcoming:
        cat = item["category"]
        if counts.get(cat, 0) < per_cat:
            result.append(item)
            counts[cat] = counts.get(cat, 0) + 1
    return result


async def get_recently_achieved_milestones_for_org(
    session: AsyncSession,
    org_id: str,
) -> list[dict]:
    # Fetch the 3 most recent non-Winter seasons, returned oldest-first so we can
    # simulate cumulative totals season-by-season to pinpoint when each milestone crossed.
    seasons_result = await session.execute(
        text("""
            SELECT sub.id, sub.year, sub.name
            FROM (
                SELECT s.id, s.year, s.name
                FROM seasons s
                JOIN v_effective_player_season_stats pss ON pss.season_id = s.id
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id
                  AND s.name NOT ILIKE '%winter%'
                GROUP BY s.id, s.year, s.name
                ORDER BY s.year DESC NULLS LAST, s.name DESC
                LIMIT 3
            ) sub
            ORDER BY sub.year ASC NULLS LAST, sub.name ASC
        """),
        {"org_id": org_id}
    )
    recent_seasons = [dict(r) for r in seasons_result.mappings()]
    if not recent_seasons:
        return []

    # Safe to interpolate — IDs are UUIDs from our own DB query
    sid_list = ", ".join(f"'{s['id']}'" for s in recent_seasons)

    # Fetch recorded milestone dates for active players (set by sync when first detected)
    dates_result = await session.execute(
        text(f"""
            SELECT player_id, milestone_type, milestone_value, achieved_at
            FROM milestones
            WHERE player_id IN (
                SELECT DISTINCT pss.player_id FROM v_effective_player_season_stats pss
                WHERE pss.season_id IN ({sid_list})
            ) AND achieved_at IS NOT NULL
        """)
    )
    milestone_date_map = {
        (str(r["player_id"]), r["milestone_type"], int(r["milestone_value"])): r["achieved_at"]
        for r in dates_result.mappings()
    }

    data_result = await session.execute(
        text(f"""
            WITH active_players AS (
                SELECT DISTINCT pss.player_id
                FROM v_effective_player_season_stats pss
                WHERE pss.season_id IN ({sid_list})
            ),
            prior_totals AS (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COALESCE(SUM(pss.runs), 0) AS prior_runs,
                    COALESCE(SUM(pss.wickets), 0) AS prior_wickets,
                    COALESCE(SUM(pss.matches), 0) AS prior_matches,
                    COALESCE(SUM(pss.catches), 0) AS prior_catches
                FROM players p
                LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
                    AND pss.season_id NOT IN ({sid_list})
                WHERE p.organisation_id = :org_id
                  AND p.id IN (SELECT player_id FROM active_players)
                GROUP BY p.id, p.name, p.display_name_override
            )
            SELECT
                pt.player_id,
                pt.name,
                pt.prior_runs, pt.prior_wickets, pt.prior_matches, pt.prior_catches,
                pss.season_id,
                COALESCE(pss.runs, 0) AS season_runs,
                COALESCE(pss.wickets, 0) AS season_wickets,
                COALESCE(pss.matches, 0) AS season_matches,
                COALESCE(pss.catches, 0) AS season_catches
            FROM prior_totals pt
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = pt.player_id
                AND pss.season_id IN ({sid_list})
        """),
        {"org_id": org_id}
    )
    rows = [dict(r) for r in data_result.mappings()]

    # Group per-season stats by player
    player_data: dict = {}
    for row in rows:
        pid = str(row["player_id"])
        if pid not in player_data:
            player_data[pid] = {
                "name": row["name"],
                "prior": {
                    "runs": int(row["prior_runs"] or 0),
                    "wickets": int(row["prior_wickets"] or 0),
                    "matches": int(row["prior_matches"] or 0),
                    "catches": int(row["prior_catches"] or 0),
                },
                "seasons": {},
            }
        if row["season_id"]:
            player_data[pid]["seasons"][str(row["season_id"])] = {
                "runs": int(row["season_runs"] or 0),
                "wickets": int(row["season_wickets"] or 0),
                "matches": int(row["season_matches"] or 0),
                "catches": int(row["season_catches"] or 0),
            }

    RUN_MILESTONES = [
        50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 4000, 5000,
        6000, 7000, 8000, 9000, 10000, 12500, 15000, 17500, 20000,
        25000, 30000, 35000, 40000, 45000, 50000,
    ]
    WICKET_MILESTONES = [
        10, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500,
        600, 700, 800, 900, 1000, 1500, 2000, 2500, 3000, 4000, 5000,
    ]
    MATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000]
    CATCH_MILESTONES = [10, 25, 50, 100, 150, 200, 300, 400, 500, 750, 1000, 1500, 2000]

    CATEGORY_MAP = {
        "runs": "batting",
        "wickets": "bowling",
        "matches": "matches",
        "catches": "fielding",
    }
    MILESTONE_LISTS = {
        "runs": RUN_MILESTONES,
        "wickets": WICKET_MILESTONES,
        "matches": MATCH_MILESTONES,
        "catches": CATCH_MILESTONES,
    }

    achieved = []
    for pid, pdata in player_data.items():
        # Pre-compute all-time career total for display
        career_total = dict(pdata["prior"])
        for s in recent_seasons:
            ss = pdata["seasons"].get(str(s["id"]), {})
            for stat in career_total:
                career_total[stat] += ss.get(stat, 0)

        # Simulate cumulative totals oldest→newest to find which season each milestone crossed
        running = dict(pdata["prior"])
        for season in recent_seasons:
            ss = pdata["seasons"].get(str(season["id"]), {})
            for stat, milestones in MILESTONE_LISTS.items():
                before = running[stat]
                after = before + ss.get(stat, 0)
                for m in milestones:
                    if before < m <= after:
                        achieved_at = milestone_date_map.get((pid, stat, m))
                        achieved.append({
                            "player_id": pid,
                            "name": pdata["name"],
                            "type": stat,
                            "category": CATEGORY_MAP[stat],
                            "milestone": m,
                            "current": career_total[stat],
                            "season_year": season["year"] or 0,
                            "season_name": season["name"],
                            "achieved_at": achieved_at.isoformat() if achieved_at else None,
                        })
            for stat in running:
                running[stat] += ss.get(stat, 0)

    # Dated entries first (most recent date first), then undated by season year desc
    achieved.sort(key=lambda x: (
        0 if x["achieved_at"] else 1,
        -(int(x["achieved_at"].replace("-", "")) if x["achieved_at"] else 0),
        -x["season_year"],
        -x["milestone"],
    ))
    return achieved


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
                MAX(pss.best_bowling_wickets) AS best_spell_wickets,
                (ARRAY_AGG(pss.best_bowling_figures
                    ORDER BY pss.best_bowling_wickets DESC NULLS LAST,
                             NULLIF(SPLIT_PART(pss.best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
                 ) FILTER (WHERE pss.best_bowling_figures IS NOT NULL AND pss.best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_bowling_figures
            FROM v_effective_player_season_stats pss
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
        "best_bowling_figures": row.get("best_bowling_figures"),
        "wicketless_spells": 0,
    }


async def get_batting_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_runs",
    limit: int = 20,
    min_runs: int = 0,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_runs", "average", "strike_rate", "total_sixes",
        "total_fours", "ducks", "high_score", "fifties", "hundreds", "innings",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_runs"

    season_ids = await resolve_season_filter(session, org_id, season_id)

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = bi.game_id AND gap.player_id = bi.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if gender:
        params["gender"] = gender
    if season_ids:
        params["season_ids"] = season_ids

    if grade_id:
        params["grade_id"] = grade_id
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id{captain_join}
                WHERE g.grade_id = :grade_id
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb'){finals_clause}
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(*) AS innings,
                COALESCE(SUM(q.runs), 0) AS total_runs,
                MAX(q.runs) AS high_score,
                ROUND(SUM(q.runs)::numeric / NULLIF(COUNT(*) - SUM(q.not_out::int), 0), 2) AS average,
                ROUND(SUM(q.runs)::numeric / NULLIF(SUM(q.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) AS ducks,
                COUNT(DISTINCT q.game_id) AS games,
                COALESCE(SUM(q.fours), 0) AS total_fours,
                COALESCE(SUM(q.sixes), 0) AS total_sixes
            FROM qualifying q
            JOIN players p ON p.id = q.player_id
            WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """
        if min_runs > 0:
            base += " HAVING SUM(q.runs) >= :min_runs"
            params["min_runs"] = min_runs
        base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id{captain_join}
                WHERE {_GRADE_MATCH}{season_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb'){finals_clause}
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(*) AS innings,
                COALESCE(SUM(q.runs), 0) AS total_runs,
                MAX(q.runs) AS high_score,
                ROUND(SUM(q.runs)::numeric / NULLIF(COUNT(*) - SUM(q.not_out::int), 0), 2) AS average,
                ROUND(SUM(q.runs)::numeric / NULLIF(SUM(q.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) AS ducks,
                COUNT(DISTINCT q.game_id) AS games,
                COALESCE(SUM(q.fours), 0) AS total_fours,
                COALESCE(SUM(q.sixes), 0) AS total_sixes
            FROM qualifying q
            JOIN players p ON p.id = q.player_id
            WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """
        if min_runs > 0:
            base += " HAVING SUM(q.runs) >= :min_runs"
            params["min_runs"] = min_runs
        base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if finals_only:
        # When finals_only=True with no grade filter, switch to per-game query
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id{captain_join}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND g.is_final = TRUE{season_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(*) AS innings,
                COALESCE(SUM(q.runs), 0) AS total_runs,
                MAX(q.runs) AS high_score,
                ROUND(SUM(q.runs)::numeric / NULLIF(COUNT(*) - SUM(q.not_out::int), 0), 2) AS average,
                ROUND(SUM(q.runs)::numeric / NULLIF(SUM(q.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) AS ducks,
                COUNT(DISTINCT q.game_id) AS games,
                COALESCE(SUM(q.fours), 0) AS total_fours,
                COALESCE(SUM(q.sixes), 0) AS total_sixes
            FROM qualifying q
            JOIN players p ON p.id = q.player_id
            WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """
        if min_runs > 0:
            base += " HAVING SUM(q.runs) >= :min_runs"
            params["min_runs"] = min_runs
        base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    elif captain_only:
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                JOIN game_appearances gap ON gap.game_id = bi.game_id AND gap.player_id = bi.player_id AND gap.is_captain = TRUE
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(*) AS innings,
                COALESCE(SUM(q.runs), 0) AS total_runs,
                MAX(q.runs) AS high_score,
                ROUND(SUM(q.runs)::numeric / NULLIF(COUNT(*) - SUM(q.not_out::int), 0), 2) AS average,
                ROUND(SUM(q.runs)::numeric / NULLIF(SUM(q.balls), 0) * 100, 2) AS strike_rate,
                SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) AS ducks,
                COUNT(DISTINCT q.game_id) AS games,
                COALESCE(SUM(q.fours), 0) AS total_fours,
                COALESCE(SUM(q.sixes), 0) AS total_sixes
            FROM qualifying q
            JOIN players p ON p.id = q.player_id
            WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        """
        if min_runs > 0:
            base += " HAVING SUM(q.runs) >= :min_runs"
            params["min_runs"] = min_runs
        base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
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
        FROM v_effective_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    if season_ids:
        base += " AND pss.season_id = ANY(:season_ids)"
    if gender:
        base += " AND p.gender = :gender"
    if overseas == "only":
        base += " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        base += " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    base += " GROUP BY p.id, COALESCE(p.display_name_override, p.name)"
    if min_runs > 0:
        base += " HAVING SUM(pss.runs) >= :min_runs"
        params["min_runs"] = min_runs
    base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_leaderboard_extended(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    sort_by: str = "total_wickets",
    limit: int = 20,
    min_overs: int = 0,
    min_wickets: int = 0,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_wickets", "average", "economy", "best_figures_wickets",
        "total_maidens", "five_fors",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_wickets"

    season_ids = await resolve_season_filter(session, org_id, season_id)

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = bs.game_id AND gap.player_id = bs.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if gender:
        params["gender"] = gender
    if season_ids:
        params["season_ids"] = season_ids
    sort_dir = "ASC" if sort_by in ("economy", "average") else "DESC"
    # When sorting by best figures (wickets DESC), break ties on runs ASC —
    # 9/21 ranks above 9/28 because fewer runs conceded is better.
    if sort_by == "best_figures_wickets":
        order_clause = f"ORDER BY best_figures_wickets {sort_dir} NULLS LAST, best_figures_runs ASC NULLS LAST"
    else:
        order_clause = f"ORDER BY {sort_by} {sort_dir} NULLS LAST"

    if grade_id:
        params["grade_id"] = grade_id
        base = f"""
            WITH best_spell AS (
                SELECT DISTINCT ON (bs.player_id)
                    bs.player_id,
                    bs.wickets AS best_figures_wickets,
                    bs.runs AS best_figures_runs,
                    bs.wickets::text || '/' || bs.runs::text AS best_bowling_figures
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id{captain_join}
                WHERE g.grade_id = :grade_id{finals_clause}
                ORDER BY bs.player_id, bs.wickets DESC, bs.runs ASC
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT bs.game_id) AS games,
                COALESCE(SUM(bs.wickets), 0) AS total_wickets,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                bsf.best_figures_wickets,
                bsf.best_figures_runs,
                bsf.best_bowling_figures,
                COALESCE(SUM(bs.maidens), 0) AS total_maidens,
                COALESCE(SUM(bs.overs), 0) AS total_overs,
                COALESCE(SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id{captain_join}
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN best_spell bsf ON bsf.player_id = p.id
            WHERE g.grade_id = :grade_id AND p.organisation_id = :org_id{finals_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), bsf.best_figures_wickets, bsf.best_figures_runs, bsf.best_bowling_figures
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("COALESCE(SUM(bs.overs), 0) >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("COALESCE(SUM(bs.wickets), 0) >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " HAVING " + " AND ".join(having_clauses)
        base += f" {order_clause} LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH best_spell AS (
                SELECT DISTINCT ON (bs.player_id)
                    bs.player_id,
                    bs.wickets AS best_figures_wickets,
                    bs.runs AS best_figures_runs,
                    bs.wickets::text || '/' || bs.runs::text AS best_bowling_figures
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id{captain_join}
                WHERE {_GRADE_MATCH}{season_clause}{finals_clause}
                ORDER BY bs.player_id, bs.wickets DESC, bs.runs ASC
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT bs.game_id) AS games,
                COALESCE(SUM(bs.wickets), 0) AS total_wickets,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                bsf.best_figures_wickets,
                bsf.best_figures_runs,
                bsf.best_bowling_figures,
                COALESCE(SUM(bs.maidens), 0) AS total_maidens,
                COALESCE(SUM(bs.overs), 0) AS total_overs,
                COALESCE(SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id{captain_join}
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN best_spell bsf ON bsf.player_id = p.id
            WHERE {_GRADE_MATCH}{season_clause}{finals_clause}
              AND p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), bsf.best_figures_wickets, bsf.best_figures_runs, bsf.best_bowling_figures
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("COALESCE(SUM(bs.overs), 0) >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("COALESCE(SUM(bs.wickets), 0) >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " HAVING " + " AND ".join(having_clauses)
        base += f" {order_clause} LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if finals_only:
        # When finals_only=True with no grade filter, switch to per-game query
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH best_spell AS (
                SELECT DISTINCT ON (bs.player_id)
                    bs.player_id,
                    bs.wickets AS best_figures_wickets,
                    bs.runs AS best_figures_runs,
                    bs.wickets::text || '/' || bs.runs::text AS best_bowling_figures
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id{captain_join}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND g.is_final = TRUE{season_clause}
                ORDER BY bs.player_id, bs.wickets DESC, bs.runs ASC
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT bs.game_id) AS games,
                COALESCE(SUM(bs.wickets), 0) AS total_wickets,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                bsf.best_figures_wickets,
                bsf.best_figures_runs,
                bsf.best_bowling_figures,
                COALESCE(SUM(bs.maidens), 0) AS total_maidens,
                COALESCE(SUM(bs.overs), 0) AS total_overs,
                COALESCE(SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id{captain_join}
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN best_spell bsf ON bsf.player_id = p.id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND g.is_final = TRUE{season_clause}
              AND p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), bsf.best_figures_wickets, bsf.best_figures_runs, bsf.best_bowling_figures
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("COALESCE(SUM(bs.overs), 0) >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("COALESCE(SUM(bs.wickets), 0) >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " HAVING " + " AND ".join(having_clauses)
        base += f" {order_clause} LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    elif captain_only:
        season_clause = " AND s.id = ANY(:season_ids)" if season_ids else ""
        base = f"""
            WITH best_spell AS (
                SELECT DISTINCT ON (bs.player_id)
                    bs.player_id,
                    bs.wickets AS best_figures_wickets,
                    bs.runs AS best_figures_runs,
                    bs.wickets::text || '/' || bs.runs::text AS best_bowling_figures
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                JOIN game_appearances gap ON gap.game_id = bs.game_id AND gap.player_id = bs.player_id AND gap.is_captain = TRUE
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}
                ORDER BY bs.player_id, bs.wickets DESC, bs.runs ASC
            )
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                COUNT(DISTINCT bs.game_id) AS games,
                COALESCE(SUM(bs.wickets), 0) AS total_wickets,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.wickets), 0), 2) AS average,
                ROUND(SUM(bs.runs)::numeric / NULLIF(SUM(bs.overs), 0), 2) AS economy,
                bsf.best_figures_wickets,
                bsf.best_figures_runs,
                bsf.best_bowling_figures,
                COALESCE(SUM(bs.maidens), 0) AS total_maidens,
                COALESCE(SUM(bs.overs), 0) AS total_overs,
                COALESCE(SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN game_appearances gap ON gap.game_id = bs.game_id AND gap.player_id = bs.player_id AND gap.is_captain = TRUE
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN best_spell bsf ON bsf.player_id = p.id
            WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}
              AND p.organisation_id = :org_id{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), bsf.best_figures_wickets, bsf.best_figures_runs, bsf.best_bowling_figures
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("COALESCE(SUM(bs.overs), 0) >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("COALESCE(SUM(bs.wickets), 0) >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " HAVING " + " AND ".join(having_clauses)
        base += f" {order_clause} LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    base = """
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            SUM(pss.matches) AS games,
            SUM(pss.wickets) AS total_wickets,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
            ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
            MAX(pss.best_bowling_wickets) AS best_figures_wickets,
            (ARRAY_AGG(pss.best_bowling_figures
                ORDER BY pss.best_bowling_wickets DESC NULLS LAST,
                         NULLIF(SPLIT_PART(pss.best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
             ) FILTER (WHERE pss.best_bowling_figures IS NOT NULL AND pss.best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_bowling_figures,
            (ARRAY_AGG(NULLIF(SPLIT_PART(pss.best_bowling_figures, '-', 2), '')::integer
                ORDER BY pss.best_bowling_wickets DESC NULLS LAST,
                         NULLIF(SPLIT_PART(pss.best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
             ) FILTER (WHERE pss.best_bowling_figures IS NOT NULL AND pss.best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_figures_runs,
            SUM(pss.maidens) AS total_maidens,
            SUM(pss.overs) AS total_overs,
            COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
        FROM v_effective_player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
    """
    if season_ids:
        base += " AND pss.season_id = ANY(:season_ids)"
    if gender:
        base += " AND p.gender = :gender"
    if overseas == "only":
        base += " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        base += " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    base += " GROUP BY p.id, COALESCE(p.display_name_override, p.name)"
    having_clauses = []
    if min_overs > 0:
        having_clauses.append("COALESCE(SUM(pss.bowling_balls), 0) / 6.0 >= :min_overs")
        params["min_overs"] = min_overs
    if min_wickets > 0:
        having_clauses.append("SUM(pss.wickets) >= :min_wickets")
        params["min_wickets"] = min_wickets
    if having_clauses:
        base += " HAVING " + " AND ".join(having_clauses)
    base += f" {order_clause} LIMIT :limit"

    result = await session.execute(text(base), params)
    return [dict(r) for r in result.mappings()]


async def get_bowling_by_grade(session: AsyncSession, player_id: str, org_id: Optional[str] = None) -> list[dict]:
    result = await session.execute(
        text("""
            WITH grade_spells AS (
                SELECT
                    COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                    bs.wickets,
                    bs.runs,
                    bs.overs,
                    bs.maidens
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                LEFT JOIN LATERAL (
                    SELECT canonical_name FROM grade_merge_logs gml
                    WHERE gml.org_id = CAST(:org_id AS UUID)
                      AND gml.alias_name = gr.name
                      AND gml.undone_at IS NULL
                    LIMIT 1
                ) am ON TRUE
                LEFT JOIN LATERAL (
                    SELECT gr2.display_name_override FROM grades gr2
                    JOIN seasons s2 ON s2.id = gr2.season_id
                    WHERE s2.organisation_id = CAST(:org_id AS UUID)
                      AND gr2.name = COALESCE(am.canonical_name, gr.name)
                      AND gr2.display_name_override IS NOT NULL
                    LIMIT 1
                ) gdn ON TRUE
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


async def get_player_by_opposition(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            WITH player_game_ids AS (
                -- Synced games: player has a roster entry
                SELECT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID)
                UNION
                -- Manual games: player appears in any batting/bowling/fielding row
                SELECT manual_game_id AS game_id FROM manual_batting_innings WHERE player_id = CAST(:pid AS UUID)
                UNION
                SELECT manual_game_id AS game_id FROM manual_bowling_spells WHERE player_id = CAST(:pid AS UUID)
                UNION
                SELECT manual_game_id AS game_id FROM manual_fielding_stats WHERE player_id = CAST(:pid AS UUID)
            ),
            player_games AS (
                -- opp_key: stable org UUID when available (populated by sync),
                -- falls back to home/away team-name match for synced rows,
                -- and to the manual_games.opposition text for manual rows.
                SELECT
                    pgi.game_id,
                    g.played_at,
                    COALESCE(
                        g.opp_org_id,
                        CASE
                            WHEN ga.team_name = g.home_team THEN g.away_club
                            WHEN ga.team_name = g.away_team THEN g.home_club
                            ELSE g.opp_club_name
                        END
                    ) AS opp_key,
                    COALESCE(
                        g.opp_club_name,
                        CASE
                            WHEN ga.team_name = g.home_team THEN g.away_club
                            WHEN ga.team_name = g.away_team THEN g.home_club
                            ELSE NULL
                        END
                    ) AS opp_name,
                    g.result
                FROM player_game_ids pgi
                JOIN v_effective_games g ON g.id = pgi.game_id
                LEFT JOIN game_appearances ga ON ga.game_id = pgi.game_id AND ga.player_id = CAST(:pid AS UUID)
            ),
            opp_display AS (
                -- Most recently seen display name for each opp_key.
                SELECT DISTINCT ON (opp_key)
                    opp_key,
                    opp_name AS opposition
                FROM player_games
                WHERE opp_key IS NOT NULL AND opp_name IS NOT NULL
                ORDER BY opp_key, played_at DESC NULLS LAST
            ),
            games_by_opposition AS (
                -- Exclude result=NULL games (abandoned / washed-out / mid-day-one
                -- forfeits where no winner was determined). CA's aggregate
                -- player_season_stats.matches counter excludes these too, so
                -- filtering here keeps the opposition sum aligned with the
                -- career total shown on the profile.
                SELECT
                    opp_key,
                    COUNT(*) AS games,
                    COUNT(*) FILTER (WHERE result = 'WIN') AS wins,
                    COUNT(*) FILTER (WHERE result = 'LOSS') AS losses
                FROM player_games
                WHERE opp_key IS NOT NULL
                  AND result IS NOT NULL
                GROUP BY opp_key
            ),
            batting_by_opposition AS (
                SELECT
                    pg.opp_key,
                    COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL) AS innings,
                    COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS total_runs,
                    MAX(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS high_score,
                    COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS dismissals
                FROM v_effective_batting_innings bi
                JOIN player_games pg ON pg.game_id = bi.game_id
                WHERE bi.player_id = CAST(:pid AS UUID)
                  AND pg.opp_key IS NOT NULL
                GROUP BY pg.opp_key
            ),
            bowling_by_opposition AS (
                SELECT
                    pg.opp_key,
                    COALESCE(SUM(bs.wickets), 0) AS wickets,
                    COALESCE(SUM(bs.runs), 0) AS bowling_runs,
                    COALESCE(SUM(bs.overs), 0) AS bowling_overs
                FROM v_effective_bowling_spells bs
                JOIN player_games pg ON pg.game_id = bs.game_id
                WHERE bs.player_id = CAST(:pid AS UUID)
                  AND pg.opp_key IS NOT NULL
                GROUP BY pg.opp_key
            ),
            fielding_by_opposition AS (
                SELECT
                    pg.opp_key,
                    COALESCE(SUM(fs.catches), 0) AS catches,
                    COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
                    COALESCE(SUM(fs.stumpings), 0) AS stumpings
                FROM v_effective_fielding_stats fs
                JOIN player_games pg ON pg.game_id = fs.game_id
                WHERE fs.player_id = CAST(:pid AS UUID)
                  AND pg.opp_key IS NOT NULL
                GROUP BY pg.opp_key
            )
            SELECT
                COALESCE(od.opposition, gbo.opp_key) AS opposition,
                gbo.games,
                gbo.wins,
                gbo.losses,
                COALESCE(bao.innings, 0) AS innings,
                COALESCE(bao.total_runs, 0) AS total_runs,
                ROUND(bao.total_runs::numeric / NULLIF(bao.dismissals, 0), 2) AS batting_average,
                bao.high_score,
                COALESCE(boo.wickets, 0) AS wickets,
                ROUND(boo.bowling_runs::numeric / NULLIF(boo.wickets, 0), 2) AS bowling_average,
                ROUND(boo.bowling_runs::numeric / NULLIF(boo.bowling_overs, 0), 2) AS economy,
                COALESCE(fo.catches, 0) AS total_catches,
                COALESCE(fo.catches_wk, 0) AS catches_wk,
                COALESCE(fo.catches - fo.catches_wk, 0) AS catches_non_wk,
                COALESCE(fo.stumpings, 0) AS stumpings
            FROM games_by_opposition gbo
            LEFT JOIN opp_display od ON od.opp_key = gbo.opp_key
            LEFT JOIN batting_by_opposition bao ON bao.opp_key = gbo.opp_key
            LEFT JOIN bowling_by_opposition boo ON boo.opp_key = gbo.opp_key
            LEFT JOIN fielding_by_opposition fo ON fo.opp_key = gbo.opp_key
            ORDER BY gbo.games DESC
        """),
        {"pid": player_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_by_venue(session: AsyncSession, player_id: str) -> list[dict]:
    result = await session.execute(
        text("""
            WITH player_game_ids AS (
                -- Same union as per-opposition: synced via appearances + manual via per-innings tables.
                SELECT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID)
                UNION
                SELECT manual_game_id AS game_id FROM manual_batting_innings WHERE player_id = CAST(:pid AS UUID)
                UNION
                SELECT manual_game_id AS game_id FROM manual_bowling_spells WHERE player_id = CAST(:pid AS UUID)
                UNION
                SELECT manual_game_id AS game_id FROM manual_fielding_stats WHERE player_id = CAST(:pid AS UUID)
            ),
            games_by_venue AS (
                -- Same NULL-result exclusion as games_by_opposition: keeps the
                -- venue sum aligned with the career total. Abandoned games are
                -- still recorded but don't show up in venue/opposition counts.
                SELECT
                    g.venue,
                    COUNT(*) AS games,
                    COUNT(*) FILTER (WHERE g.result = 'WIN') AS wins,
                    COUNT(*) FILTER (WHERE g.result = 'LOSS') AS losses
                FROM player_game_ids pgi
                JOIN v_effective_games g ON g.id = pgi.game_id
                WHERE g.venue IS NOT NULL
                  AND g.result IS NOT NULL
                GROUP BY g.venue
            ),
            batting_by_venue AS (
                SELECT
                    g.venue,
                    COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL) AS innings,
                    COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS total_runs,
                    MAX(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS high_score,
                    COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL) AS dismissals
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                WHERE bi.player_id = CAST(:pid AS UUID)
                  AND g.venue IS NOT NULL
                GROUP BY g.venue
            ),
            bowling_by_venue AS (
                SELECT
                    g.venue,
                    COALESCE(SUM(bs.wickets), 0) AS wickets,
                    COALESCE(SUM(bs.runs), 0) AS bowling_runs,
                    COALESCE(SUM(bs.overs), 0) AS bowling_overs
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                WHERE bs.player_id = CAST(:pid AS UUID)
                  AND g.venue IS NOT NULL
                GROUP BY g.venue
            ),
            fielding_by_venue AS (
                SELECT
                    g.venue,
                    COALESCE(SUM(fs.catches), 0) AS catches,
                    COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
                    COALESCE(SUM(fs.stumpings), 0) AS stumpings
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                WHERE fs.player_id = CAST(:pid AS UUID)
                  AND g.venue IS NOT NULL
                GROUP BY g.venue
            )
            SELECT
                gv.venue,
                gv.games,
                gv.wins,
                gv.losses,
                COALESCE(bav.innings, 0) AS innings,
                COALESCE(bav.total_runs, 0) AS total_runs,
                ROUND(bav.total_runs::numeric / NULLIF(bav.dismissals, 0), 2) AS batting_average,
                bav.high_score,
                COALESCE(bov.wickets, 0) AS wickets,
                ROUND(bov.bowling_runs::numeric / NULLIF(bov.wickets, 0), 2) AS bowling_average,
                ROUND(bov.bowling_runs::numeric / NULLIF(bov.bowling_overs, 0), 2) AS economy,
                COALESCE(fv.catches, 0) AS total_catches,
                COALESCE(fv.catches_wk, 0) AS catches_wk,
                COALESCE(fv.catches - fv.catches_wk, 0) AS catches_non_wk,
                COALESCE(fv.stumpings, 0) AS stumpings
            FROM games_by_venue gv
            LEFT JOIN batting_by_venue bav ON bav.venue = gv.venue
            LEFT JOIN bowling_by_venue bov ON bov.venue = gv.venue
            LEFT JOIN fielding_by_venue fv ON fv.venue = gv.venue
            ORDER BY gv.games DESC
        """),
        {"pid": player_id},
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
    season_ids = await resolve_season_filter(session, org_id, season_id)
    if season_ids:
        where += " AND pss.season_id = ANY(:season_ids)"
        params["season_ids"] = season_ids

    res = await session.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT pss.season_id) AS seasons,
                COUNT(DISTINCT pss.player_id) AS total_players,
                SUM(pss.runs) AS total_runs,
                SUM(pss.wickets) AS total_wickets,
                MAX(pss.high_score) AS highest_score
            FROM v_effective_player_season_stats pss
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
    result = await session.execute(
        text("""
            SELECT
                pt.wicket_number,
                pt.innings_number,
                pt.runs,
                pt.balls,
                pt.batter1_runs,
                pt.batter2_runs,
                pt.batter1_id::text,
                pt.batter2_id::text,
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name
            FROM partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.game_id = :gid
            ORDER BY pt.innings_number, pt.wicket_number
        """),
        {"gid": game_id},
    )
    return [dict(r) for r in result.mappings()]


async def get_player_rankings(
    session: AsyncSession,
    player_id: str,
    org_id: str,
    season_id: Optional[str] = None,
) -> dict:
    """Return the player's rank for runs, wickets, and catches within their org.
    Returns None for each category if the player is outside the top 100."""
    season_ids = await resolve_season_filter(session, org_id, season_id)
    season_clause = " AND pss.season_id = ANY(:season_ids)" if season_ids else ""
    params: dict = {"org_id": org_id, "player_id": player_id}
    if season_ids:
        params["season_ids"] = season_ids

    result = await session.execute(
        text(f"""
            WITH batting_agg AS (
                SELECT pss.player_id, SUM(pss.runs) AS total_runs
                FROM v_effective_player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            batting_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_runs DESC NULLS LAST) AS runs_rank
                FROM batting_agg
            ),
            bowling_agg AS (
                SELECT pss.player_id, SUM(pss.wickets) AS total_wickets
                FROM v_effective_player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            bowling_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_wickets DESC NULLS LAST) AS wickets_rank
                FROM bowling_agg
            ),
            fielding_agg AS (
                SELECT pss.player_id, SUM(pss.catches) AS total_catches
                FROM v_effective_player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id{season_clause}
                GROUP BY pss.player_id
            ),
            fielding_ranked AS (
                SELECT player_id,
                       RANK() OVER (ORDER BY total_catches DESC NULLS LAST) AS catches_rank
                FROM fielding_agg
            )
            SELECT
                (SELECT CASE WHEN runs_rank <= 100 THEN runs_rank ELSE NULL END
                 FROM batting_ranked WHERE player_id = :player_id) AS runs_rank,
                (SELECT CASE WHEN wickets_rank <= 100 THEN wickets_rank ELSE NULL END
                 FROM bowling_ranked WHERE player_id = :player_id) AS wickets_rank,
                (SELECT CASE WHEN catches_rank <= 100 THEN catches_rank ELSE NULL END
                 FROM fielding_ranked WHERE player_id = :player_id) AS catches_rank
        """),
        params,
    )
    row = result.mappings().first()
    if not row:
        return {"runs_rank": None, "wickets_rank": None, "catches_rank": None}
    return {
        "runs_rank": row["runs_rank"],
        "wickets_rank": row["wickets_rank"],
        "catches_rank": row["catches_rank"],
    }


async def _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=False, stat_alias='bi'):
    """Return (season_clause, finals_clause, grade_clause, captain_join) strings and mutate params."""
    season_clause = ""
    season_ids = await resolve_season_filter(session, org_id, season_id) if season_id else None
    if season_ids:
        params["season_ids"] = season_ids
        season_clause = " AND s.id = ANY(:season_ids)"
    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    grade_clause = ""
    if grade_name:
        params["grade_name"] = grade_name
        grade_clause = f" AND {_GRADE_MATCH}"
    captain_join = (f" JOIN game_appearances gap ON gap.game_id = {stat_alias}.game_id AND gap.player_id = {stat_alias}.player_id AND gap.is_captain = TRUE" if captain_only else "")
    return season_clause, finals_clause, grade_clause, captain_join


def _sirs_stringify(rows):
    out = []
    for r in rows:
        d = dict(r)
        d["player_id"] = str(d["player_id"])
        if d.get("performances") is None:
            d["performances"] = []
        out.append(d)
    return out


async def get_sirs_batting(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    limit: int = 200,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bi')
    gender_clause = f" AND p.gender = :gender" if gender else ""
    overseas_clause = " AND p.is_overseas = TRUE" if overseas == "only" else (" AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)" if overseas == "exclude" else "")
    if gender:
        params["gender"] = gender
    result = await session.execute(text(f"""
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            COUNT(*) AS century_count,
            json_agg(json_build_object(
                'runs', bi.runs,
                'not_out', bi.not_out,
                'game_id', g.id,
                'grade', COALESCE(gr.display_name_override, gr.name),
                'season', s.name,
                'date', g.played_at
            ) ORDER BY bi.runs DESC) AS performances
        FROM v_effective_batting_innings bi
        JOIN v_effective_games g ON g.id = bi.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        JOIN players p ON p.id = bi.player_id{captain_join}
        WHERE p.organisation_id = CAST(:org_id AS UUID)
          AND s.organisation_id = CAST(:org_id AS UUID)
          AND bi.runs >= 100
          AND NOT COALESCE(bi.did_not_bat, FALSE)
          AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb'){season_clause}{finals_clause}{grade_clause}{gender_clause}{overseas_clause}
        GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        ORDER BY century_count DESC NULLS LAST
        LIMIT :limit
    """), params)
    return _sirs_stringify(result.mappings())


async def get_sirs_bowling_innings(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    limit: int = 200,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bs')
    gender_clause = f" AND p.gender = :gender" if gender else ""
    overseas_clause = " AND p.is_overseas = TRUE" if overseas == "only" else (" AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)" if overseas == "exclude" else "")
    if gender:
        params["gender"] = gender
    result = await session.execute(text(f"""
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            COUNT(*) AS haul_count,
            json_agg(json_build_object(
                'wickets', bs.wickets,
                'runs', bs.runs,
                'overs', bs.overs,
                'game_id', g.id,
                'grade', COALESCE(gr.display_name_override, gr.name),
                'season', s.name,
                'date', g.played_at
            ) ORDER BY bs.wickets DESC, bs.runs ASC) AS performances
        FROM v_effective_bowling_spells bs
        JOIN v_effective_games g ON g.id = bs.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        JOIN players p ON p.id = bs.player_id{captain_join}
        WHERE p.organisation_id = CAST(:org_id AS UUID)
          AND s.organisation_id = CAST(:org_id AS UUID)
          AND bs.wickets >= 7{season_clause}{finals_clause}{grade_clause}{gender_clause}{overseas_clause}
        GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        ORDER BY haul_count DESC NULLS LAST
        LIMIT :limit
    """), params)
    return _sirs_stringify(result.mappings())


async def get_sirs_bowling_match(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_name: Optional[str] = None,
    finals_only: Optional[bool] = None,
    limit: int = 200,
    captain_only: Optional[bool] = None,
    gender: Optional[str] = None,
    overseas: Optional[str] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bs')
    gender_clause = f" AND p.gender = :gender" if gender else ""
    overseas_clause = " AND p.is_overseas = TRUE" if overseas == "only" else (" AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)" if overseas == "exclude" else "")
    if gender:
        params["gender"] = gender
    result = await session.execute(text(f"""
        WITH match_totals AS (
            SELECT
                bs.player_id,
                bs.game_id,
                SUM(bs.wickets) AS total_wickets,
                SUM(bs.runs)    AS total_runs
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN players p ON p.id = bs.player_id{captain_join}
            WHERE p.organisation_id = CAST(:org_id AS UUID)
              AND s.organisation_id = CAST(:org_id AS UUID){season_clause}{finals_clause}{grade_clause}{gender_clause}{overseas_clause}
            GROUP BY bs.player_id, bs.game_id
            HAVING SUM(bs.wickets) >= 10
        )
        SELECT
            p.id AS player_id,
            COALESCE(p.display_name_override, p.name) AS name,
            COUNT(*) AS haul_count,
            json_agg(json_build_object(
                'wickets', mt.total_wickets,
                'runs', mt.total_runs,
                'game_id', g.id,
                'grade', COALESCE(gr.display_name_override, gr.name),
                'season', s.name,
                'date', g.played_at
            ) ORDER BY mt.total_wickets DESC, mt.total_runs ASC) AS performances
        FROM match_totals mt
        JOIN players p ON p.id = mt.player_id
        JOIN v_effective_games g ON g.id = mt.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        ORDER BY haul_count DESC NULLS LAST
        LIMIT :limit
    """), params)
    return _sirs_stringify(result.mappings())
