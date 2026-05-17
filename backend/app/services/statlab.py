from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional

# Aggregate field aliases for player-level queries.
# Keys = public API names, values = CTE alias names (identical — safe to reference in outer WHERE).
PLAYER_FIELDS: dict[str, str] = {
    "matches": "matches",
    "seasons_played": "seasons_played",
    "batting_innings": "batting_innings",
    "runs": "runs",
    "not_outs": "not_outs",
    "batting_average": "batting_average",
    "batting_strike_rate": "batting_strike_rate",
    "high_score": "high_score",
    "fifties": "fifties",
    "hundreds": "hundreds",
    "ducks": "ducks",
    "fours": "fours",
    "sixes": "sixes",
    "wickets": "wickets",
    "overs": "overs",
    "bowling_average": "bowling_average",
    "bowling_economy": "bowling_economy",
    "five_wicket_innings": "five_wicket_innings",
    "maidens": "maidens",
    "best_bowling_wickets": "best_bowling_wickets",
    "catches": "catches",
    "run_outs": "run_outs",
    "stumpings": "stumpings",
}

# Field aliases for grade/team-level queries.
GRADE_FIELDS: dict[str, str] = {
    "matches": "matches",
    "unique_players": "unique_players",
    "runs": "runs",
    "hundreds": "hundreds",
    "fifties": "fifties",
    "ducks": "ducks",
    "wickets": "wickets",
    "catches": "catches",
    "run_outs": "run_outs",
    "stumpings": "stumpings",
}

OPERATOR_MAP: dict[str, str] = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}


def _build_filter_clauses(
    filters: list[str],
    allowed_fields: dict[str, str],
) -> tuple[list[str], dict]:
    """
    Parse filter strings of the form 'field:op:value' into parameterised SQL clauses.
    Fields and operators are validated against allowlists. Values are never interpolated.
    """
    clauses: list[str] = []
    params: dict = {}
    for i, f in enumerate(filters or []):
        parts = f.split(":", 2)
        if len(parts) != 3:
            continue
        field, op, value_str = parts
        if field not in allowed_fields or op not in OPERATOR_MAP:
            continue
        try:
            value = float(value_str)
        except ValueError:
            continue
        param_key = f"fv_{i}"
        clauses.append(f"{allowed_fields[field]} {OPERATOR_MAP[op]} :{param_key}")
        params[param_key] = value
    return clauses, params


async def query_players(
    session: AsyncSession,
    org_id: str,
    mode: str = "career",
    season_id: Optional[str] = None,
    sort_by: str = "runs",
    sort_dir: str = "desc",
    limit: int = 100,
    filters: Optional[list[str]] = None,
) -> list[dict]:
    """
    Aggregate player_season_stats per player (career or single-season) and return rows
    matching all provided filter expressions.
    """
    if sort_by not in PLAYER_FIELDS:
        sort_by = "runs"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    limit = min(max(1, limit), 500)

    params: dict = {"org_id": org_id, "limit": limit}
    season_clause = ""
    if mode == "season" and season_id:
        season_clause = "AND pss.season_id = :season_id"
        params["season_id"] = season_id

    filter_clauses, filter_params = _build_filter_clauses(filters or [], PLAYER_FIELDS)
    params.update(filter_params)
    where_sql = ("WHERE " + " AND ".join(filter_clauses)) if filter_clauses else ""
    nulls = "LAST"

    sql = f"""
        WITH agg AS (
            SELECT
                p.id::text                                                                    AS player_id,
                COALESCE(p.display_name_override, p.name)                                    AS player_name,
                COUNT(DISTINCT pss.season_id)                                                AS seasons_played,
                COALESCE(SUM(pss.matches), 0)                                                AS matches,
                COALESCE(SUM(pss.batting_innings), 0)                                        AS batting_innings,
                COALESCE(SUM(pss.runs), 0)                                                   AS runs,
                COALESCE(SUM(pss.not_outs), 0)                                               AS not_outs,
                ROUND(
                    SUM(pss.runs)::numeric /
                    NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2)              AS batting_average,
                ROUND(
                    SUM(pss.runs)::numeric /
                    NULLIF(SUM(pss.balls_faced), 0) * 100, 2)                                AS batting_strike_rate,
                MAX(pss.high_score)                                                          AS high_score,
                COALESCE(SUM(pss.fifties), 0)                                                AS fifties,
                COALESCE(SUM(pss.hundreds), 0)                                               AS hundreds,
                COALESCE(SUM(pss.ducks), 0)                                                  AS ducks,
                COALESCE(SUM(pss.fours), 0)                                                  AS fours,
                COALESCE(SUM(pss.sixes), 0)                                                  AS sixes,
                COALESCE(SUM(pss.wickets), 0)                                                AS wickets,
                COALESCE(SUM(pss.overs), 0)                                                  AS overs,
                ROUND(
                    SUM(pss.runs_conceded)::numeric /
                    NULLIF(SUM(pss.wickets), 0), 2)                                          AS bowling_average,
                ROUND(
                    SUM(pss.runs_conceded)::numeric /
                    NULLIF(SUM(pss.bowling_balls), 0) * 6, 2)                               AS bowling_economy,
                COALESCE(SUM(pss.five_wicket_innings), 0)                                   AS five_wicket_innings,
                COALESCE(SUM(pss.maidens), 0)                                                AS maidens,
                MAX(pss.best_bowling_wickets)                                                AS best_bowling_wickets,
                COALESCE(SUM(pss.catches), 0)                                                AS catches,
                COALESCE(SUM(pss.run_outs), 0)                                               AS run_outs,
                COALESCE(SUM(pss.stumpings), 0)                                              AS stumpings
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE p.organisation_id = :org_id {season_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS {nulls}
        LIMIT :limit
    """

    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def query_grades(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    group_by_season: bool = False,
    sort_by: str = "runs",
    sort_dir: str = "desc",
    limit: int = 100,
    filters: Optional[list[str]] = None,
) -> list[dict]:
    """
    Aggregate game-level data per canonical grade name (and optionally per season).
    Batting, bowling, and fielding tables are aggregated independently to avoid row explosion.
    """
    if sort_by not in GRADE_FIELDS:
        sort_by = "runs"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    limit = min(max(1, limit), 500)

    params: dict = {"org_id": org_id, "limit": limit}
    season_clause = ""
    if season_id:
        season_clause = "AND s.id = :season_id"
        params["season_id"] = season_id

    filter_clauses, filter_params = _build_filter_clauses(filters or [], GRADE_FIELDS)
    params.update(filter_params)
    where_sql = ("WHERE " + " AND ".join(filter_clauses)) if filter_clauses else ""
    nulls = "LAST"

    if group_by_season:
        group_cols = "og.grade_name, og.season_name, og.season_year"
        select_id_cols = "og.grade_name, og.season_name, og.season_year,"
        final_group = "bat.grade_name, bat.season_name, bat.season_year"
        final_select_extra = "bat.season_name, bat.season_year,"
    else:
        group_cols = "og.grade_name"
        select_id_cols = "og.grade_name,"
        final_group = "bat.grade_name"
        final_select_extra = ""

    sql = f"""
        WITH org_games AS (
            SELECT
                g.id                                       AS game_id,
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                s.name                                     AS season_name,
                COALESCE(s.year, 0)                        AS season_year
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s  ON s.id  = gr.season_id
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
            WHERE s.organisation_id = :org_id {season_clause}
        ),
        bat AS (
            SELECT
                {select_id_cols}
                COUNT(DISTINCT og.game_id)                                                       AS matches,
                COUNT(DISTINCT bi.player_id)                                                     AS unique_players,
                COALESCE(SUM(bi.runs), 0)                                                        AS runs,
                COUNT(*) FILTER (WHERE bi.runs >= 100)                                           AS hundreds,
                COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100)                          AS fifties,
                COUNT(*) FILTER (
                    WHERE bi.runs = 0
                      AND bi.not_out = FALSE
                      AND bi.dismissal_type IS NOT NULL
                )                                                                                AS ducks
            FROM org_games og
            LEFT JOIN batting_innings bi ON bi.game_id = og.game_id AND (bi.did_not_bat IS NOT TRUE)
            GROUP BY {group_cols}
        ),
        bowl AS (
            SELECT
                {select_id_cols}
                COALESCE(SUM(bs.wickets), 0) AS wickets
            FROM org_games og
            LEFT JOIN bowling_spells bs ON bs.game_id = og.game_id
            GROUP BY {group_cols}
        ),
        field AS (
            SELECT
                {select_id_cols}
                COALESCE(SUM(fs.catches), 0)   AS catches,
                COALESCE(SUM(fs.run_outs), 0)  AS run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS stumpings
            FROM org_games og
            LEFT JOIN fielding_stats fs ON fs.game_id = og.game_id
            GROUP BY {group_cols}
        ),
        agg AS (
            SELECT
                bat.grade_name,
                {final_select_extra}
                bat.matches,
                bat.unique_players,
                bat.runs,
                bat.hundreds,
                bat.fifties,
                bat.ducks,
                COALESCE(bowl.wickets, 0)   AS wickets,
                COALESCE(field.catches, 0)  AS catches,
                COALESCE(field.run_outs, 0) AS run_outs,
                COALESCE(field.stumpings, 0) AS stumpings
            FROM bat
            LEFT JOIN bowl  ON bowl.grade_name  = bat.grade_name  {"AND bowl.season_name = bat.season_name" if group_by_season else ""}
            LEFT JOIN field ON field.grade_name = bat.grade_name  {"AND field.season_name = bat.season_name" if group_by_season else ""}
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS {nulls}
        LIMIT :limit
    """

    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]
