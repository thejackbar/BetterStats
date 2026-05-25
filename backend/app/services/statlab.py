"""StatLab — Statsguru-style flexible query engine.

The engine supports several QUERY TARGETS, each of which has its own metric set,
identity dimensions, and result shape:

  player_career     — one row per player, sums across all seasons (or filtered subset)
  player_season     — one row per (player, season)
  player_grade      — one row per (player, canonical grade name)
  innings_list      — one row per batting innings (every ball-by-ball-ish row)
  spell_list        — one row per bowling spell
  match_list        — one row per match (from the club's perspective)
  partnership_list  — one row per partnership

All targets accept a common set of CONTEXT FILTERS that operate against the
underlying game (date range, season, grade, opposition, captain/keeper/finals/
result flags). The aggregate targets (player_career, player_season, player_grade)
fall back to per-innings aggregation when any context filter that isn't covered
by `player_season_stats` is in play; otherwise they use the cached aggregate
table for speed.

Derived queries (streak-style metrics like "most consecutive ducks") live in
DERIVED_QUERIES and are handled separately because they need window/sequence
SQL rather than plain aggregation.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from datetime import date

# ─── Operators ─────────────────────────────────────────────────────────────────

OPERATOR_MAP: dict[str, str] = {
    "eq": "=",
    "ne": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}

# ─── Metric registries ─────────────────────────────────────────────────────────
# Per-target dict of {public_name -> SQL alias visible in the outer SELECT}.
# Alias-only references are safe to inline because they come from this allowlist
# and the parameter values are still bound, never interpolated.

PLAYER_AGG_METRICS: dict[str, str] = {
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
    "balls_faced": "balls_faced",
    "wickets": "wickets",
    "overs": "overs",
    "bowling_innings": "bowling_innings",
    "bowling_average": "bowling_average",
    "bowling_economy": "bowling_economy",
    "bowling_strike_rate": "bowling_strike_rate",
    "five_wicket_innings": "five_wicket_innings",
    "maidens": "maidens",
    "runs_conceded": "runs_conceded",
    "best_bowling_wickets": "best_bowling_wickets",
    "catches": "catches",
    "run_outs": "run_outs",
    "stumpings": "stumpings",
    "wides": "wides",
    "no_balls": "no_balls",
}

INNINGS_METRICS: dict[str, str] = {
    "runs": "runs",
    "balls": "balls",
    "fours": "fours",
    "sixes": "sixes",
    "strike_rate": "strike_rate",
    "batting_position": "batting_position",
    "innings_number": "innings_number",
}

SPELL_METRICS: dict[str, str] = {
    "overs": "overs",
    "maidens": "maidens",
    "runs": "runs",
    "wickets": "wickets",
    "wides": "wides",
    "no_balls": "no_balls",
    "economy": "economy",
    "innings_number": "innings_number",
}

MATCH_METRICS: dict[str, str] = {
    "team_runs": "team_runs",
    "team_wickets": "team_wickets",
    "opp_runs": "opp_runs",
    "opp_wickets": "opp_wickets",
    "margin_runs": "margin_runs",
}

PARTNERSHIP_METRICS: dict[str, str] = {
    "runs": "runs",
    "balls": "balls",
    "wicket_number": "wicket_number",
    "batter1_runs": "batter1_runs",
    "batter2_runs": "batter2_runs",
}

TARGETS: dict[str, dict] = {
    "player_career":    {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "player_season":    {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "player_grade":     {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "innings_list":     {"metrics": INNINGS_METRICS,     "default_sort": "runs"},
    "spell_list":       {"metrics": SPELL_METRICS,       "default_sort": "wickets"},
    "match_list":       {"metrics": MATCH_METRICS,       "default_sort": "team_runs"},
    "partnership_list": {"metrics": PARTNERSHIP_METRICS, "default_sort": "runs"},
}

# ─── Context filter spec ───────────────────────────────────────────────────────
# Context filters are top-level (not per-target); they always apply against the
# match/game row of the underlying record. value_kind controls how the value is
# coerced. operator is fixed because each filter has natural semantics.

# Match-level context filters — applied inside the game_universe CTE.
# References inside SQL strings:
#   g, gr, s, am  → table/CTE aliases visible in game_universe's WHERE clause.
#   ga.team_name  → the club's team name for this game (set by a LATERAL
#                   subquery that returns DISTINCT team_names from our org's
#                   appearances; produces 1 row per (game, our_team), not per
#                   appearance row, so downstream joins don't multiply).
MATCH_CONTEXT_FILTERS: dict[str, dict] = {
    "date_from":    {"sql": "g.played_at >= :ctx_date_from",                          "value_kind": "date"},
    "date_to":      {"sql": "g.played_at <= :ctx_date_to",                            "value_kind": "date"},
    "season_id":    {"sql": "(s.id = CAST(:ctx_season_id AS UUID) OR s.id IN (SELECT alias_season_id FROM season_aliases WHERE canonical_season_id = CAST(:ctx_season_id AS UUID) AND undone_at IS NULL))", "value_kind": "uuid"},
    "min_year":     {"sql": "COALESCE(s.year, 0) >= :ctx_min_year",                   "value_kind": "int"},
    "max_year":     {"sql": "COALESCE(s.year, 9999) <= :ctx_max_year",                "value_kind": "int"},
    "grade_id":     {"sql": "gr.id = CAST(:ctx_grade_id AS UUID)",                    "value_kind": "uuid"},
    "grade_name":   {"sql": "COALESCE(am.canonical_name, gr.name) = :ctx_grade_name", "value_kind": "text"},
    "opposition":   {"sql": "LOWER(COALESCE(CASE WHEN ga.team_name = g.home_team THEN g.away_team WHEN ga.team_name = g.away_team THEN g.home_team ELSE NULL END, '')) LIKE LOWER(:ctx_opposition)", "value_kind": "text_like"},
    "finals_only":  {"sql": "g.is_final = TRUE",                                       "value_kind": "flag"},
    "result":       {"sql": "(CASE WHEN g.winning_team IS NULL OR g.winning_team = '' THEN 'drawn' WHEN ga.team_name IS NOT NULL AND g.winning_team = ga.team_name THEN 'won' WHEN ga.team_name IS NOT NULL THEN 'lost' ELSE 'drawn' END) = :ctx_result", "value_kind": "result"},
}

# Per-innings filters — applied to batting_innings (bi) joins only; relevant
# only for innings_list and the live-aggregate paths of player_*.
INNINGS_CONTEXT_FILTERS: dict[str, dict] = {
    "dismissal":    {"sql": "LOWER(COALESCE(bi.dismissal_type, '')) = LOWER(:ctx_dismissal)", "value_kind": "text"},
    "position_min": {"sql": "bi.batting_position >= :ctx_position_min",                       "value_kind": "int"},
    "position_max": {"sql": "bi.batting_position <= :ctx_position_max",                       "value_kind": "int"},
}

# Per-player filters — applied at the (game_universe × player) join because
# captain / keeper status is a property of an individual player's appearance,
# not of the game itself. These are deliberately NOT in game_universe so the
# CTE stays at one row per (game, team) and doesn't fan out across appearances.
PLAYER_CONTEXT_FILTERS: dict[str, dict] = {
    "captain_only": {"sql": "gap.is_captain = TRUE",        "value_kind": "flag"},
    "keeper_only":  {"sql": "gap.is_wicket_keeper = TRUE",  "value_kind": "flag"},
}

# Combined view for schema introspection.
CONTEXT_FILTERS: dict[str, dict] = {**MATCH_CONTEXT_FILTERS, **INNINGS_CONTEXT_FILTERS, **PLAYER_CONTEXT_FILTERS}

# Helper SQL functions emitted once at the top of each query that needs them.
# We define them as inline expressions to avoid creating real DB functions.
HELPER_FN_SQL = """
-- inline helper expressions inlined via column references; see ctx_join below
"""


# ─── Filter parsing ────────────────────────────────────────────────────────────

def _coerce_value(kind: str, value_str: str):
    """Coerce a raw query-string value into a typed param. Returns None if the
    filter should be skipped (invalid value)."""
    if value_str is None or value_str == "":
        return None
    try:
        if kind == "int":
            return int(float(value_str))
        if kind == "float":
            return float(value_str)
        if kind == "date":
            return date.fromisoformat(value_str)
        if kind == "uuid":
            return str(value_str)
        if kind == "text":
            return str(value_str)
        if kind == "text_like":
            return f"%{value_str}%"
        if kind == "flag":
            return str(value_str).lower() in ("1", "true", "yes", "on")
        if kind == "result":
            v = str(value_str).lower()
            return v if v in ("won", "lost", "drawn", "tied") else None
    except (ValueError, TypeError):
        return None
    return value_str


def _build_metric_filters(filters: list[str], allowed: dict[str, str]) -> tuple[list[str], dict]:
    """Parse 'field:op:value' filters against the per-target metric allowlist.
    Produces an AND-joined clause set — flat form, used for back-compat and
    URL-driven simple queries."""
    clauses: list[str] = []
    params: dict = {}
    for i, raw in enumerate(filters or []):
        if not raw:
            continue
        parts = raw.split(":", 2)
        if len(parts) != 3:
            continue
        field, op, value_str = parts
        if field not in allowed or op not in OPERATOR_MAP:
            continue
        try:
            value = float(value_str)
        except (TypeError, ValueError):
            continue
        key = f"mv_{i}"
        clauses.append(f"{allowed[field]} {OPERATOR_MAP[op]} :{key}")
        params[key] = value
    return clauses, params


def _build_filter_tree(tree: dict, allowed: dict[str, str], counter: list[int] | None = None) -> tuple[str | None, dict]:
    """Recursively compile a nested filter tree into a single SQL expression
    plus bound params. Tree shape:
      {"type": "group", "op": "AND"|"OR", "clauses": [tree, ...]}
      {"type": "leaf",  "field": str, "op": str, "value": number}
    Invalid leaves are silently dropped; an empty group returns (None, {}).
    """
    if counter is None:
        counter = [0]
    if not isinstance(tree, dict):
        return None, {}
    kind = tree.get("type")
    if kind == "leaf":
        field = tree.get("field")
        op = tree.get("op")
        value_str = tree.get("value")
        if field not in allowed or op not in OPERATOR_MAP:
            return None, {}
        try:
            value = float(value_str)
        except (TypeError, ValueError):
            return None, {}
        counter[0] += 1
        key = f"ft_{counter[0]}"
        return f"{allowed[field]} {OPERATOR_MAP[op]} :{key}", {key: value}
    if kind == "group":
        op = str(tree.get("op", "AND")).upper()
        if op not in ("AND", "OR"):
            op = "AND"
        parts: list[str] = []
        params: dict = {}
        for child in (tree.get("clauses") or []):
            s, p = _build_filter_tree(child, allowed, counter)
            if s:
                parts.append(s)
                params.update(p)
        if not parts:
            return None, params
        if len(parts) == 1:
            return parts[0], params
        return "(" + (" " + op + " ").join(parts) + ")", params
    return None, {}


def _compile_metric_clause(
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    allowed: dict[str, str],
) -> tuple[str, dict]:
    """Produce a single WHERE-suffix clause (with no leading WHERE) from either
    a flat `metric_filters` list or a nested `filter_tree`. The tree wins when
    both are provided. Empty input returns ("", {}).
    """
    if filter_tree:
        s, p = _build_filter_tree(filter_tree, allowed)
        return (s or "", p)
    clauses, params = _build_metric_filters(metric_filters or [], allowed)
    if not clauses:
        return "", {}
    return " AND ".join(clauses), params


def _build_filter_block(ctx: dict, spec_dict: dict) -> tuple[list[str], dict, bool]:
    """Build filter clauses from a context dict against a specific spec dict
    (MATCH_CONTEXT_FILTERS or INNINGS_CONTEXT_FILTERS).
    Returns (clauses, params, any_used).
    """
    clauses: list[str] = []
    params: dict = {}
    used = False
    for key, spec in spec_dict.items():
        if key not in ctx or ctx[key] in (None, "", []):
            continue
        coerced = _coerce_value(spec["value_kind"], ctx[key])
        if coerced is None or coerced is False:
            continue
        used = True
        if spec["value_kind"] == "flag":
            clauses.append(spec["sql"])
            continue
        clauses.append(spec["sql"])
        params[f"ctx_{key}"] = coerced
    return clauses, params, used


def _build_context_filters(ctx: dict) -> tuple[list[str], dict, list[str], dict, list[str], dict, bool]:
    """Returns (match_clauses, match_params, innings_clauses, innings_params,
    player_clauses, player_params, any_match_used).
    The match block expands inside game_universe; the innings block attaches to
    batting_innings joins; the player block attaches to (game_universe × player)
    via a gap LEFT JOIN that callers must provide.
    """
    mc, mp, mu = _build_filter_block(ctx, MATCH_CONTEXT_FILTERS)
    ic, ip, _iu = _build_filter_block(ctx, INNINGS_CONTEXT_FILTERS)
    pc, pp, _pu = _build_filter_block(ctx, PLAYER_CONTEXT_FILTERS)
    return mc, mp, ic, ip, pc, pp, mu


# ─── Common SQL fragments ──────────────────────────────────────────────────────
# game_universe: builds a CTE of every (game, club_team_name, canonical_grade_name)
# tuple this org cares about, with optional context filters applied. Downstream
# queries join their per-innings/per-spell/etc. tables against this universe.

def _game_universe_sql(ctx_clauses: list[str]) -> str:
    """Build the per-game universe CTE.

    Critical correctness note: `ga.team_name` MUST come from a LATERAL that
    returns at most one row per distinct team_name. A naive LEFT JOIN of
    game_appearances against games multiplies rows by the per-game appearance
    count (typically ~11), and any downstream JOIN to batting_innings /
    bowling_spells / fielding_stats then over-counts by the same factor.
    This bit us once already — manifested as inflated streak lengths in
    derived_consecutive_ducks (4 real ducks reported as 12).
    """
    ctx_where = (" AND " + " AND ".join(ctx_clauses)) if ctx_clauses else ""
    return f"""
        game_universe AS (
            SELECT
                g.id                                          AS game_id,
                ga.team_name                                  AS club_team,
                CASE
                    WHEN ga.team_name = g.home_team THEN g.away_team
                    WHEN ga.team_name = g.away_team THEN g.home_team
                    ELSE NULL
                END                                           AS opposition,
                CASE
                    WHEN g.winning_team IS NULL OR g.winning_team = '' THEN 'drawn'
                    WHEN ga.team_name IS NOT NULL AND g.winning_team = ga.team_name THEN 'won'
                    WHEN ga.team_name IS NOT NULL THEN 'lost'
                    ELSE 'drawn'
                END                                           AS result,
                g.played_at                                   AS played_at,
                gr.id                                         AS grade_id,
                COALESCE(am.canonical_name, gr.name)          AS canonical_grade_name,
                COALESCE(gdn.display_name_override,
                         COALESCE(am.canonical_name, gr.name)) AS display_grade_name,
                s.id                                          AS season_id,
                s.name                                        AS season_name,
                COALESCE(s.year, 0)                           AS season_year,
                g.is_final                                    AS is_final,
                g.home_team                                   AS home_team,
                g.away_team                                   AS away_team,
                g.winning_team                                AS winning_team
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s  ON s.id  = gr.season_id
            LEFT JOIN LATERAL (
                -- One row per distinct team our club fielded in this game.
                -- For a typical game this returns exactly one team_name; if
                -- the org has both home & away sides in an intra-club fixture
                -- it returns two — both legitimate perspectives.
                SELECT DISTINCT ga_inner.team_name
                FROM game_appearances ga_inner
                JOIN players p_inner ON p_inner.id = ga_inner.player_id
                WHERE ga_inner.game_id = g.id
                  AND p_inner.organisation_id = CAST(:org_id AS UUID)
            ) ga ON TRUE
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
            WHERE s.organisation_id = :org_id
              {ctx_where}
        )
    """


# Pseudo-function tokens (`opp_team`, `match_result`) used to live in filter
# specs and were rewritten to inline CASE expressions before query execution.
# The current filter SQL embeds the CASE expressions directly, so this hook is
# a no-op kept for back-compat with any external callers.
def _inline_helpers(sql: str) -> str:
    return sql


def _validated(target: str, sort_by: str, sort_dir: str, limit: int) -> tuple[str, str, int]:
    metrics = TARGETS[target]["metrics"]
    if sort_by not in metrics:
        sort_by = TARGETS[target]["default_sort"]
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"
    limit = min(max(1, int(limit)), 500)
    return sort_by, sort_dir, limit


# ─── Player aggregate queries ──────────────────────────────────────────────────

def _player_agg_innings_cte(
    ctx_clauses: list[str],
    innings_clauses: list[str],
    player_clauses: list[str],
    group_cols: str,
    select_cols: str,
) -> str:
    """Build the per-innings aggregation CTE used when context filters are present.
    group_cols / select_cols control whether we group by player only (career),
    player+season, or player+grade.
    """
    universe = _game_universe_sql(ctx_clauses)
    innings_extra = (" AND " + " AND ".join(innings_clauses)) if innings_clauses else ""
    player_extra = (" AND " + " AND ".join(player_clauses)) if player_clauses else ""
    # gap LEFT JOIN exposes this player's per-game appearance row so the
    # captain_only / keeper_only filters can apply at the right scope.
    return f"""
        WITH {universe},
        bat AS (
            SELECT
                {select_cols}
                COUNT(DISTINCT gu.game_id)                                                  AS matches_bat,
                COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE)                          AS batting_innings,
                COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0)         AS runs,
                COUNT(*) FILTER (WHERE bi.not_out = TRUE AND bi.did_not_bat IS NOT TRUE)    AS not_outs,
                COALESCE(SUM(bi.balls) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0)        AS balls_faced,
                COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100 AND bi.did_not_bat IS NOT TRUE) AS fifties,
                COUNT(*) FILTER (WHERE bi.runs >= 100 AND bi.did_not_bat IS NOT TRUE)       AS hundreds,
                COUNT(*) FILTER (
                    WHERE bi.runs = 0
                      AND bi.not_out = FALSE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                      AND bi.did_not_bat IS NOT TRUE
                ) AS ducks,
                COALESCE(MAX(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0)         AS high_score,
                COALESCE(SUM(bi.fours) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0)        AS fours,
                COALESCE(SUM(bi.sixes) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0)        AS sixes
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {innings_extra} {player_extra}
            GROUP BY {group_cols}
        ),
        bowl AS (
            SELECT
                {select_cols}
                COUNT(*)                                          AS bowling_innings,
                COALESCE(SUM(bs.wickets), 0)                      AS wickets,
                COALESCE(SUM(bs.overs), 0)                        AS overs,
                COALESCE(SUM(bs.runs), 0)                         AS runs_conceded,
                COALESCE(SUM(bs.maidens), 0)                      AS maidens,
                COUNT(*) FILTER (WHERE bs.wickets >= 5)           AS five_wicket_innings,
                MAX(bs.wickets)                                   AS best_bowling_wickets,
                COALESCE(SUM(bs.wides), 0)    AS wides,
                COALESCE(SUM(bs.no_balls), 0) AS no_balls
            FROM game_universe gu
            JOIN bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY {group_cols}
        ),
        field AS (
            SELECT
                {select_cols}
                COALESCE(SUM(fs.catches), 0)   AS catches,
                COALESCE(SUM(fs.run_outs), 0)  AS run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS stumpings
            FROM game_universe gu
            JOIN fielding_stats fs ON fs.game_id = gu.game_id
            JOIN players p ON p.id = fs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY {group_cols}
        ),
        appear AS (
            SELECT
                {select_cols}
                COUNT(DISTINCT gu.game_id) AS matches
            FROM game_universe gu
            JOIN game_appearances gap ON gap.game_id = gu.game_id
            JOIN players p ON p.id = gap.player_id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY {group_cols}
        )
    """


async def query_player_career(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    sort_by, sort_dir, limit = _validated("player_career", sort_by, sort_dir, limit)
    metrics = PLAYER_AGG_METRICS

    mc, mp, ic, ip, pc, pp, used_ctx = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, metrics)
    params = {"org_id": org_id, "limit": limit, **mp, **ip, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")
    needs_live = used_ctx or bool(ic) or bool(pc)

    if needs_live:
        # Live aggregation over per-innings rows so context filters take effect.
        cte = _player_agg_innings_cte(
            mc, ic, pc,
            group_cols="p.id, COALESCE(p.display_name_override, p.name)",
            select_cols="p.id AS player_id, COALESCE(p.display_name_override, p.name) AS player_name,",
        )
        sql = f"""
            {cte},
            agg AS (
                SELECT
                    COALESCE(appear.player_id, bat.player_id, bowl.player_id, field.player_id)::text AS player_id,
                    COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name) AS player_name,
                    COALESCE(appear.matches, 0)                                       AS matches,
                    1                                                                  AS seasons_played,
                    COALESCE(bat.batting_innings, 0)                                  AS batting_innings,
                    COALESCE(bat.runs, 0)                                             AS runs,
                    COALESCE(bat.not_outs, 0)                                         AS not_outs,
                    COALESCE(bat.balls_faced, 0)                                      AS balls_faced,
                    ROUND(bat.runs::numeric / NULLIF(bat.batting_innings - bat.not_outs, 0), 2) AS batting_average,
                    ROUND(bat.runs::numeric / NULLIF(bat.balls_faced, 0) * 100, 2)     AS batting_strike_rate,
                    COALESCE(bat.high_score, 0)                                       AS high_score,
                    COALESCE(bat.fifties, 0)                                          AS fifties,
                    COALESCE(bat.hundreds, 0)                                         AS hundreds,
                    COALESCE(bat.ducks, 0)                                            AS ducks,
                    COALESCE(bat.fours, 0)                                            AS fours,
                    COALESCE(bat.sixes, 0)                                            AS sixes,
                    COALESCE(bowl.bowling_innings, 0)                                 AS bowling_innings,
                    COALESCE(bowl.wickets, 0)                                         AS wickets,
                    COALESCE(bowl.overs, 0)                                           AS overs,
                    COALESCE(bowl.runs_conceded, 0)                                   AS runs_conceded,
                    ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.wickets, 0), 2)   AS bowling_average,
                    ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.overs * 6, 0) * 6, 2) AS bowling_economy,
                    ROUND(bowl.overs::numeric * 6 / NULLIF(bowl.wickets, 0), 2)        AS bowling_strike_rate,
                    COALESCE(bowl.five_wicket_innings, 0)                             AS five_wicket_innings,
                    COALESCE(bowl.maidens, 0)                                         AS maidens,
                    bowl.best_bowling_wickets                                          AS best_bowling_wickets,
                    COALESCE(bowl.wides, 0)    AS wides,
                    COALESCE(bowl.no_balls, 0) AS no_balls,
                    COALESCE(field.catches, 0)                                        AS catches,
                    COALESCE(field.run_outs, 0)                                       AS run_outs,
                    COALESCE(field.stumpings, 0)                                      AS stumpings
                FROM appear
                FULL OUTER JOIN bat  ON bat.player_id  = appear.player_id
                FULL OUTER JOIN bowl ON bowl.player_id = COALESCE(appear.player_id, bat.player_id)
                FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST
            LIMIT :limit
        """
    else:
        # Fast path — use pre-aggregated player_season_stats.
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
                    COALESCE(SUM(pss.balls_faced), 0)                                            AS balls_faced,
                    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS batting_average,
                    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2)     AS batting_strike_rate,
                    MAX(pss.high_score)                                                          AS high_score,
                    COALESCE(SUM(pss.fifties), 0)                                                AS fifties,
                    COALESCE(SUM(pss.hundreds), 0)                                               AS hundreds,
                    COALESCE(SUM(pss.ducks), 0)                                                  AS ducks,
                    COALESCE(SUM(pss.fours), 0)                                                  AS fours,
                    COALESCE(SUM(pss.sixes), 0)                                                  AS sixes,
                    COALESCE(SUM(pss.bowling_innings), 0)                                        AS bowling_innings,
                    COALESCE(SUM(pss.wickets), 0)                                                AS wickets,
                    COALESCE(SUM(pss.overs), 0)                                                  AS overs,
                    COALESCE(SUM(pss.runs_conceded), 0)                                          AS runs_conceded,
                    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2)      AS bowling_average,
                    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS bowling_economy,
                    ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 2)      AS bowling_strike_rate,
                    COALESCE(SUM(pss.five_wicket_innings), 0)                                    AS five_wicket_innings,
                    COALESCE(SUM(pss.maidens), 0)                                                AS maidens,
                    MAX(pss.best_bowling_wickets)                                                AS best_bowling_wickets,
                    COALESCE(SUM(pss.wides), 0)    AS wides,
                    COALESCE(SUM(pss.no_balls), 0) AS no_balls,
                    COALESCE(SUM(pss.catches), 0)                                                AS catches,
                    COALESCE(SUM(pss.run_outs), 0)                                               AS run_outs,
                    COALESCE(SUM(pss.stumpings), 0)                                              AS stumpings
                FROM player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                WHERE p.organisation_id = :org_id
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST
            LIMIT :limit
        """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def query_player_season(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    """One row per (player, season). Uses pss when no context filters require
    per-innings aggregation; otherwise live-aggregates from batting_innings etc.
    """
    sort_by, sort_dir, limit = _validated("player_season", sort_by, sort_dir, limit)
    metrics = PLAYER_AGG_METRICS

    mc, mp, ic, ip, pc, pp, used_ctx = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, metrics)
    params = {"org_id": org_id, "limit": limit, **mp, **ip, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")
    needs_live = used_ctx or bool(ic) or bool(pc)

    if needs_live:
        cte = _player_agg_innings_cte(
            mc, ic, pc,
            group_cols="p.id, COALESCE(p.display_name_override, p.name), gu.season_id, gu.season_name, gu.season_year",
            select_cols=("p.id AS player_id, COALESCE(p.display_name_override, p.name) AS player_name, "
                         "gu.season_id, gu.season_name, gu.season_year,"),
        )
        sql = f"""
            {cte},
            agg AS (
                SELECT
                    COALESCE(appear.player_id, bat.player_id)::text   AS player_id,
                    COALESCE(appear.player_name, bat.player_name)     AS player_name,
                    COALESCE(appear.season_id, bat.season_id)::text   AS season_id,
                    COALESCE(appear.season_name, bat.season_name)     AS season_name,
                    COALESCE(appear.season_year, bat.season_year)     AS season_year,
                    COALESCE(appear.matches, 0)                       AS matches,
                    1                                                  AS seasons_played,
                    COALESCE(bat.batting_innings, 0)                  AS batting_innings,
                    COALESCE(bat.runs, 0)                             AS runs,
                    COALESCE(bat.not_outs, 0)                         AS not_outs,
                    COALESCE(bat.balls_faced, 0)                      AS balls_faced,
                    ROUND(bat.runs::numeric / NULLIF(bat.batting_innings - bat.not_outs, 0), 2) AS batting_average,
                    ROUND(bat.runs::numeric / NULLIF(bat.balls_faced, 0) * 100, 2)             AS batting_strike_rate,
                    COALESCE(bat.high_score, 0)                       AS high_score,
                    COALESCE(bat.fifties, 0)                          AS fifties,
                    COALESCE(bat.hundreds, 0)                         AS hundreds,
                    COALESCE(bat.ducks, 0)                            AS ducks,
                    COALESCE(bat.fours, 0)                            AS fours,
                    COALESCE(bat.sixes, 0)                            AS sixes,
                    COALESCE(bowl.bowling_innings, 0)                 AS bowling_innings,
                    COALESCE(bowl.wickets, 0)                         AS wickets,
                    COALESCE(bowl.overs, 0)                           AS overs,
                    COALESCE(bowl.runs_conceded, 0)                   AS runs_conceded,
                    ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.wickets, 0), 2) AS bowling_average,
                    ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.overs * 6, 0) * 6, 2) AS bowling_economy,
                    ROUND(bowl.overs::numeric * 6 / NULLIF(bowl.wickets, 0), 2) AS bowling_strike_rate,
                    COALESCE(bowl.five_wicket_innings, 0)             AS five_wicket_innings,
                    COALESCE(bowl.maidens, 0)                         AS maidens,
                    bowl.best_bowling_wickets                         AS best_bowling_wickets,
                    COALESCE(bowl.wides, 0)    AS wides,
                    COALESCE(bowl.no_balls, 0) AS no_balls,
                    COALESCE(field.catches, 0)                        AS catches,
                    COALESCE(field.run_outs, 0)                       AS run_outs,
                    COALESCE(field.stumpings, 0)                      AS stumpings
                FROM appear
                FULL OUTER JOIN bat  ON bat.player_id  = appear.player_id AND bat.season_id  = appear.season_id
                FULL OUTER JOIN bowl ON bowl.player_id = COALESCE(appear.player_id, bat.player_id)
                                     AND bowl.season_id = COALESCE(appear.season_id, bat.season_id)
                FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                                     AND field.season_id = COALESCE(appear.season_id, bat.season_id, bowl.season_id)
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST, season_year DESC
            LIMIT :limit
        """
    else:
        season_filter = ""
        if context.get("season_id"):
            season_filter = (
                "AND (s.id = CAST(:ctx_season_id AS UUID) "
                "OR s.id IN (SELECT alias_season_id FROM season_aliases "
                "WHERE canonical_season_id = CAST(:ctx_season_id AS UUID) "
                "AND undone_at IS NULL))"
            )
            params["ctx_season_id"] = context["season_id"]
        sql = f"""
            WITH agg AS (
                SELECT
                    p.id::text                                                                    AS player_id,
                    COALESCE(p.display_name_override, p.name)                                    AS player_name,
                    s.id::text                                                                    AS season_id,
                    s.name                                                                        AS season_name,
                    COALESCE(s.year, 0)                                                           AS season_year,
                    1                                                                             AS seasons_played,
                    COALESCE(pss.matches, 0)                                                      AS matches,
                    COALESCE(pss.batting_innings, 0)                                              AS batting_innings,
                    COALESCE(pss.runs, 0)                                                         AS runs,
                    COALESCE(pss.not_outs, 0)                                                     AS not_outs,
                    COALESCE(pss.balls_faced, 0)                                                  AS balls_faced,
                    pss.batting_average                                                            AS batting_average,
                    pss.batting_strike_rate                                                        AS batting_strike_rate,
                    pss.high_score                                                                 AS high_score,
                    COALESCE(pss.fifties, 0)                                                      AS fifties,
                    COALESCE(pss.hundreds, 0)                                                     AS hundreds,
                    COALESCE(pss.ducks, 0)                                                        AS ducks,
                    COALESCE(pss.fours, 0)                                                        AS fours,
                    COALESCE(pss.sixes, 0)                                                        AS sixes,
                    COALESCE(pss.bowling_innings, 0)                                              AS bowling_innings,
                    COALESCE(pss.wickets, 0)                                                      AS wickets,
                    COALESCE(pss.overs, 0)                                                        AS overs,
                    COALESCE(pss.runs_conceded, 0)                                                AS runs_conceded,
                    pss.bowling_average                                                            AS bowling_average,
                    pss.bowling_economy                                                            AS bowling_economy,
                    pss.bowling_strike_rate                                                        AS bowling_strike_rate,
                    COALESCE(pss.five_wicket_innings, 0)                                          AS five_wicket_innings,
                    COALESCE(pss.maidens, 0)                                                      AS maidens,
                    pss.best_bowling_wickets                                                       AS best_bowling_wickets,
                    COALESCE(pss.wides, 0)    AS wides,
                    COALESCE(pss.no_balls, 0) AS no_balls,
                    COALESCE(pss.catches, 0)                                                      AS catches,
                    COALESCE(pss.run_outs, 0)                                                     AS run_outs,
                    COALESCE(pss.stumpings, 0)                                                    AS stumpings
                FROM player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                JOIN seasons s ON s.id = pss.season_id
                WHERE p.organisation_id = :org_id {season_filter}
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST, season_year DESC
            LIMIT :limit
        """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def query_player_grade(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    """One row per (player, canonical grade name). Always uses per-innings
    aggregation since player_season_stats has no grade dimension."""
    sort_by, sort_dir, limit = _validated("player_grade", sort_by, sort_dir, limit)

    mc, mp, ic, ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, PLAYER_AGG_METRICS)
    params = {"org_id": org_id, "limit": limit, **mp, **ip, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    cte = _player_agg_innings_cte(
        mc, ic, pc,
        group_cols="p.id, COALESCE(p.display_name_override, p.name), gu.canonical_grade_name, gu.display_grade_name",
        select_cols=("p.id AS player_id, COALESCE(p.display_name_override, p.name) AS player_name, "
                     "gu.canonical_grade_name AS grade_name, gu.display_grade_name,"),
    )
    sql = f"""
        {cte},
        agg AS (
            SELECT
                COALESCE(appear.player_id, bat.player_id)::text         AS player_id,
                COALESCE(appear.player_name, bat.player_name)           AS player_name,
                COALESCE(appear.grade_name, bat.grade_name)             AS grade_name,
                COALESCE(appear.display_grade_name, bat.display_grade_name) AS display_grade_name,
                COALESCE(appear.matches, 0)                             AS matches,
                1                                                        AS seasons_played,
                COALESCE(bat.batting_innings, 0)                        AS batting_innings,
                COALESCE(bat.runs, 0)                                   AS runs,
                COALESCE(bat.not_outs, 0)                               AS not_outs,
                COALESCE(bat.balls_faced, 0)                            AS balls_faced,
                ROUND(bat.runs::numeric / NULLIF(bat.batting_innings - bat.not_outs, 0), 2) AS batting_average,
                ROUND(bat.runs::numeric / NULLIF(bat.balls_faced, 0) * 100, 2)             AS batting_strike_rate,
                COALESCE(bat.high_score, 0)                             AS high_score,
                COALESCE(bat.fifties, 0)                                AS fifties,
                COALESCE(bat.hundreds, 0)                               AS hundreds,
                COALESCE(bat.ducks, 0)                                  AS ducks,
                COALESCE(bat.fours, 0)                                  AS fours,
                COALESCE(bat.sixes, 0)                                  AS sixes,
                COALESCE(bowl.bowling_innings, 0)                       AS bowling_innings,
                COALESCE(bowl.wickets, 0)                               AS wickets,
                COALESCE(bowl.overs, 0)                                 AS overs,
                COALESCE(bowl.runs_conceded, 0)                         AS runs_conceded,
                ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.wickets, 0), 2) AS bowling_average,
                ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.overs * 6, 0) * 6, 2) AS bowling_economy,
                ROUND(bowl.overs::numeric * 6 / NULLIF(bowl.wickets, 0), 2) AS bowling_strike_rate,
                COALESCE(bowl.five_wicket_innings, 0)                   AS five_wicket_innings,
                COALESCE(bowl.maidens, 0)                               AS maidens,
                bowl.best_bowling_wickets                                AS best_bowling_wickets,
                COALESCE(bowl.wides, 0)    AS wides,
                COALESCE(bowl.no_balls, 0) AS no_balls,
                COALESCE(field.catches, 0)                              AS catches,
                COALESCE(field.run_outs, 0)                             AS run_outs,
                COALESCE(field.stumpings, 0)                            AS stumpings
            FROM appear
            FULL OUTER JOIN bat   ON bat.player_id   = appear.player_id   AND bat.grade_name   = appear.grade_name
            FULL OUTER JOIN bowl  ON bowl.player_id  = COALESCE(appear.player_id, bat.player_id)
                                 AND bowl.grade_name  = COALESCE(appear.grade_name, bat.grade_name)
            FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                                 AND field.grade_name = COALESCE(appear.grade_name, bat.grade_name, bowl.grade_name)
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST
        LIMIT :limit
    """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


# ─── Flat-list queries ─────────────────────────────────────────────────────────

async def query_innings_list(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    """One row per batting innings."""
    sort_by, sort_dir, limit = _validated("innings_list", sort_by, sort_dir, limit)

    mc, mp, ic, ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, INNINGS_METRICS)
    params = {"org_id": org_id, "limit": limit, **mp, **ip, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")
    innings_extra = (" AND " + " AND ".join(ic)) if ic else ""
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""

    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        rows AS (
            SELECT
                bi.id                                       AS innings_row_id,
                p.id::text                                  AS player_id,
                COALESCE(p.display_name_override, p.name)   AS player_name,
                gu.game_id::text                            AS game_id,
                gu.played_at                                AS played_at,
                gu.display_grade_name                       AS grade_name,
                gu.season_name                              AS season_name,
                gu.season_year                              AS season_year,
                gu.club_team                                AS club_team,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                         AS opposition,
                gu.result                                   AS result,
                bi.runs                                     AS runs,
                bi.balls                                    AS balls,
                bi.fours                                    AS fours,
                bi.sixes                                    AS sixes,
                bi.strike_rate                              AS strike_rate,
                bi.dismissal_type                           AS dismissal_type,
                bi.not_out                                  AS not_out,
                bi.batting_position                         AS batting_position,
                bi.innings_number                           AS innings_number
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {innings_extra}
              {player_extra}
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, played_at DESC
        LIMIT :limit
    """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def query_spell_list(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    sort_by, sort_dir, limit = _validated("spell_list", sort_by, sort_dir, limit)

    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, SPELL_METRICS)
    params = {"org_id": org_id, "limit": limit, **mp, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""

    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        rows AS (
            SELECT
                bs.id                                       AS spell_row_id,
                p.id::text                                  AS player_id,
                COALESCE(p.display_name_override, p.name)   AS player_name,
                gu.game_id::text                            AS game_id,
                gu.played_at                                AS played_at,
                gu.display_grade_name                       AS grade_name,
                gu.season_name                              AS season_name,
                gu.season_year                              AS season_year,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                         AS opposition,
                gu.result                                   AS result,
                bs.overs                                    AS overs,
                bs.maidens                                  AS maidens,
                bs.runs                                     AS runs,
                bs.wickets                                  AS wickets,
                bs.wides                                    AS wides,
                bs.no_balls                                 AS no_balls,
                bs.economy                                  AS economy,
                bs.innings_number                           AS innings_number
            FROM game_universe gu
            JOIN bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, played_at DESC
        LIMIT :limit
    """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def query_match_list(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    """One row per club match. Team / opposition runs are derived from
    batting_innings sums."""
    sort_by, sort_dir, limit = _validated("match_list", sort_by, sort_dir, limit)

    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, MATCH_METRICS)
    params = {"org_id": org_id, "limit": limit, **mp, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        bat_scores AS (
            SELECT
                gu.game_id,
                COALESCE(SUM(bi.runs) FILTER (WHERE p.id IS NOT NULL), 0) AS team_runs,
                COUNT(*) FILTER (
                    WHERE p.id IS NOT NULL
                      AND bi.not_out = FALSE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                      AND bi.did_not_bat IS NOT TRUE
                ) AS team_wickets
            FROM game_universe gu
            LEFT JOIN batting_innings bi ON bi.game_id = gu.game_id
            LEFT JOIN players p ON p.id = bi.player_id AND p.organisation_id = :org_id
            GROUP BY gu.game_id
        ),
        bowl_scores AS (
            SELECT
                gu.game_id,
                COALESCE(SUM(bs.runs)    FILTER (WHERE pb.id IS NOT NULL), 0) AS opp_runs,
                COALESCE(SUM(bs.wickets) FILTER (WHERE pb.id IS NOT NULL), 0) AS opp_wickets
            FROM game_universe gu
            LEFT JOIN bowling_spells bs ON bs.game_id = gu.game_id
            LEFT JOIN players pb ON pb.id = bs.player_id AND pb.organisation_id = :org_id
            GROUP BY gu.game_id
        ),
        rows AS (
            SELECT DISTINCT
                gu.game_id::text                            AS game_id,
                gu.played_at                                AS played_at,
                gu.display_grade_name                       AS grade_name,
                gu.season_name                              AS season_name,
                gu.season_year                              AS season_year,
                gu.club_team                                AS club_team,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                         AS opposition,
                gu.result                                   AS result,
                gu.is_final                                 AS is_final,
                COALESCE(bat_scores.team_runs, 0)           AS team_runs,
                COALESCE(bat_scores.team_wickets, 0)        AS team_wickets,
                COALESCE(bowl_scores.opp_runs, 0)           AS opp_runs,
                COALESCE(bowl_scores.opp_wickets, 0)        AS opp_wickets,
                (COALESCE(bat_scores.team_runs, 0) - COALESCE(bowl_scores.opp_runs, 0)) AS margin_runs
            FROM game_universe gu
            LEFT JOIN bat_scores  ON bat_scores.game_id  = gu.game_id
            LEFT JOIN bowl_scores ON bowl_scores.game_id = gu.game_id
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, played_at DESC
        LIMIT :limit
    """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def query_partnership_list(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    sort_by, sort_dir, limit = _validated("partnership_list", sort_by, sort_dir, limit)

    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, PARTNERSHIP_METRICS)
    params = {"org_id": org_id, "limit": limit, **mp, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        rows AS (
            SELECT
                pt.id                                                 AS partnership_row_id,
                pt.batter1_id::text                                   AS batter1_id,
                COALESCE(p1.display_name_override, p1.name)           AS batter1_name,
                pt.batter2_id::text                                   AS batter2_id,
                COALESCE(p2.display_name_override, p2.name)           AS batter2_name,
                gu.game_id::text                                      AS game_id,
                gu.played_at                                          AS played_at,
                gu.display_grade_name                                 AS grade_name,
                gu.season_name                                        AS season_name,
                gu.season_year                                        AS season_year,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                                   AS opposition,
                pt.runs                                               AS runs,
                pt.balls                                              AS balls,
                pt.wicket_number                                      AS wicket_number,
                pt.batter1_runs                                       AS batter1_runs,
                pt.batter2_runs                                       AS batter2_runs,
                pt.is_club_innings                                    AS is_club_innings
            FROM game_universe gu
            JOIN partnerships pt ON pt.game_id = gu.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND (p1.organisation_id = :org_id OR p2.organisation_id = :org_id)
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, runs DESC
        LIMIT :limit
    """

    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


# ─── Derived / streak queries ──────────────────────────────────────────────────

async def derived_consecutive_ducks(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """For each player, find the longest run of consecutive innings (ordered by
    played_at, then innings_number) that were ducks. A duck = runs=0 AND not_out
    is false AND dismissal_type is a real dismissal (excluding absent / DNB).
    """
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        seq AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.played_at,
                bi.innings_number,
                CASE
                    WHEN bi.runs = 0
                      AND bi.not_out = FALSE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                      AND bi.did_not_bat IS NOT TRUE
                    THEN 1 ELSE 0
                END AS is_duck,
                ROW_NUMBER() OVER (PARTITION BY bi.player_id ORDER BY gu.played_at, bi.innings_number, bi.id) AS rn
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
        ),
        grp AS (
            SELECT player_id, player_name, rn, is_duck,
                   rn - SUM(is_duck) OVER (PARTITION BY player_id ORDER BY rn) AS streak_grp
            FROM seq
        ),
        streaks AS (
            SELECT player_id, player_name, streak_grp,
                   SUM(is_duck) AS streak_len
            FROM grp
            WHERE is_duck = 1
            GROUP BY player_id, player_name, streak_grp
        ),
        best AS (
            SELECT
                player_id::text AS player_id,
                player_name,
                MAX(streak_len)::int AS longest_duck_streak
            FROM streaks
            GROUP BY player_id, player_name
        )
        SELECT * FROM best
        WHERE longest_duck_streak >= 2
        ORDER BY longest_duck_streak DESC, player_name ASC
        LIMIT :limit
    """
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_consecutive_fifties(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """Longest run of consecutive innings scoring 50+."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        seq AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.played_at,
                bi.innings_number,
                CASE WHEN bi.runs >= 50 THEN 1 ELSE 0 END AS is_fifty,
                ROW_NUMBER() OVER (PARTITION BY bi.player_id ORDER BY gu.played_at, bi.innings_number, bi.id) AS rn
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
        ),
        grp AS (
            SELECT player_id, player_name, rn, is_fifty,
                   rn - SUM(is_fifty) OVER (PARTITION BY player_id ORDER BY rn) AS streak_grp
            FROM seq
        ),
        streaks AS (
            SELECT player_id, player_name, streak_grp, SUM(is_fifty) AS streak_len
            FROM grp
            WHERE is_fifty = 1
            GROUP BY player_id, player_name, streak_grp
        ),
        best AS (
            SELECT player_id::text AS player_id, player_name, MAX(streak_len)::int AS longest_fifty_streak
            FROM streaks
            GROUP BY player_id, player_name
        )
        SELECT * FROM best
        WHERE longest_fifty_streak >= 2
        ORDER BY longest_fifty_streak DESC, player_name ASC
        LIMIT :limit
    """
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_best_partnership_pair(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """Best partnership ever for each pair of batters (unordered).

    captain/keeper filters don't apply at the pair level (a partnership has
    two batters, only one of whom might be captain); we ignore pc here.
    """
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        pairs AS (
            SELECT
                LEAST(pt.batter1_id, pt.batter2_id)    AS player_a_id,
                GREATEST(pt.batter1_id, pt.batter2_id) AS player_b_id,
                pt.runs,
                pt.wicket_number,
                gu.game_id,
                gu.played_at,
                gu.display_grade_name AS grade_name,
                gu.season_name
            FROM game_universe gu
            JOIN partnerships pt ON pt.game_id = gu.game_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND pt.batter1_id IS NOT NULL AND pt.batter2_id IS NOT NULL
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY player_a_id, player_b_id ORDER BY runs DESC) AS rk
            FROM pairs
        )
        SELECT
            pa.id::text AS player_a_id,
            COALESCE(pa.display_name_override, pa.name) AS player_a_name,
            pb.id::text AS player_b_id,
            COALESCE(pb.display_name_override, pb.name) AS player_b_name,
            r.runs::int AS best_partnership,
            r.wicket_number::int AS wicket_number,
            r.played_at AS played_at,
            r.grade_name AS grade_name,
            r.season_name AS season_name
        FROM ranked r
        JOIN players pa ON pa.id = r.player_a_id
        JOIN players pb ON pb.id = r.player_b_id
        WHERE r.rk = 1
          AND pa.organisation_id = :org_id
        ORDER BY best_partnership DESC
        LIMIT :limit
    """
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_carried_bat(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """Players who carried the bat — batted at #1 or #2 and were not out when
    their team was bowled out (9+ dismissals in that innings)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        innings_wickets AS (
            SELECT
                bi.game_id,
                bi.innings_number,
                COUNT(*) FILTER (
                    WHERE bi.not_out = FALSE
                      AND bi.did_not_bat IS NOT TRUE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                ) AS wickets_fell
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            WHERE p.organisation_id = :org_id
            GROUP BY bi.game_id, bi.innings_number
        ),
        carried AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                bi.runs,
                bi.batting_position
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            JOIN innings_wickets iw ON iw.game_id = bi.game_id
                                   AND iw.innings_number = bi.innings_number
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id
                                          AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.not_out = TRUE
              AND bi.batting_position IN (1, 2)
              AND bi.did_not_bat IS NOT TRUE
              AND iw.wickets_fell >= 9
              {player_extra}
        ),
        agg AS (
            SELECT
                player_id::text AS player_id,
                player_name,
                COUNT(*)::int   AS carried_bat_count,
                MAX(runs)::int  AS highest_score
            FROM carried
            GROUP BY player_id, player_name
        )
        SELECT * FROM agg
        ORDER BY carried_bat_count DESC, highest_score DESC NULLS LAST
        LIMIT :limit
    """
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_runs_first_n(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """Who scored the most runs in their first N career matches.
    N comes from context['first_n_matches'] (default 50)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    try:
        first_n = max(1, int(float(context.get("first_n_matches") or 50)))
    except (ValueError, TypeError):
        first_n = 50
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), "first_n": first_n, **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        match_nums AS (
            SELECT
                p.id        AS player_id,
                gu.game_id,
                DENSE_RANK() OVER (
                    PARTITION BY p.id ORDER BY gu.played_at, gu.game_id
                ) AS match_rn
            FROM game_universe gu
            JOIN game_appearances gap ON gap.game_id = gu.game_id
            JOIN players p ON p.id = gap.player_id
            WHERE p.organisation_id = :org_id {player_extra}
        ),
        first_n_agg AS (
            SELECT
                mn.player_id,
                COALESCE(p.display_name_override, p.name)             AS player_name,
                COUNT(DISTINCT mn.match_rn)::int                       AS matches_played,
                COALESCE(SUM(bi.runs) FILTER (
                    WHERE bi.did_not_bat IS NOT TRUE
                ), 0)::int                                             AS runs
            FROM match_nums mn
            JOIN players p ON p.id = mn.player_id
            LEFT JOIN batting_innings bi
                   ON bi.game_id = mn.game_id AND bi.player_id = mn.player_id
            WHERE mn.match_rn <= :first_n
            GROUP BY mn.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT
            player_id::text AS player_id,
            player_name,
            runs,
            matches_played
        FROM first_n_agg
        WHERE matches_played >= :first_n
        ORDER BY runs DESC
        LIMIT :limit
    """
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_milestone_runs(
    session: AsyncSession, *, org_id: str, limit: int, context: dict,
) -> list[dict]:
    """Who reached a runs milestone in the fewest career matches.
    Milestone comes from context['milestone_runs'] (default 1000)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    try:
        milestone = max(1, int(float(context.get("milestone_runs") or 1000)))
    except (ValueError, TypeError):
        milestone = 1000
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), "milestone": milestone, **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        player_innings AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.played_at,
                gu.game_id,
                DENSE_RANK() OVER (
                    PARTITION BY bi.player_id ORDER BY gu.played_at, gu.game_id
                ) AS match_rn,
                SUM(COALESCE(bi.runs, 0)) OVER (
                    PARTITION BY bi.player_id
                    ORDER BY gu.played_at, gu.game_id, bi.id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_runs
            FROM game_universe gu
            JOIN batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id
                                          AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              {player_extra}
        ),
        crossings AS (
            SELECT DISTINCT ON (player_id)
                player_id,
                player_name,
                played_at           AS reached_on,
                match_rn::int       AS matches_to_milestone,
                cumulative_runs::int AS runs_at_crossing
            FROM player_innings
            WHERE cumulative_runs >= :milestone
            ORDER BY player_id, played_at, match_rn, cumulative_runs
        )
        SELECT
            player_id::text     AS player_id,
            player_name,
            matches_to_milestone,
            reached_on,
            runs_at_crossing
        FROM crossings
        ORDER BY matches_to_milestone ASC
        LIMIT :limit
    """
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


DERIVED_QUERIES: dict[str, dict] = {
    "consecutive_ducks": {
        "label": "Longest duck streak",
        "description": "Most innings in a row scoring zero (excluding not outs, absent, DNB).",
        "fn": derived_consecutive_ducks,
        "columns": [
            {"key": "player_id", "label": "PLAYER", "kind": "player"},
            {"key": "longest_duck_streak", "label": "DUCKS IN A ROW", "decimal": False},
        ],
    },
    "consecutive_fifties": {
        "label": "Longest 50+ streak",
        "description": "Most innings in a row scoring 50 or more.",
        "fn": derived_consecutive_fifties,
        "columns": [
            {"key": "player_id", "label": "PLAYER", "kind": "player"},
            {"key": "longest_fifty_streak", "label": "50+ IN A ROW", "decimal": False},
        ],
    },
    "best_partnership_pair": {
        "label": "Best partnership by pair",
        "description": "Largest partnership ever shared by each pair of batters.",
        "fn": derived_best_partnership_pair,
        "columns": [
            {"key": "player_a_id", "label": "BATTER A", "kind": "player_a"},
            {"key": "player_b_id", "label": "BATTER B", "kind": "player_b"},
            {"key": "best_partnership", "label": "RUNS", "decimal": False},
            {"key": "wicket_number", "label": "WKT", "decimal": False},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "season_name", "label": "SEASON"},
        ],
    },
    "carried_bat": {
        "label": "Carrying the bat",
        "description": "Openers (pos 1–2) not out when their team was bowled out.",
        "fn": derived_carried_bat,
        "columns": [
            {"key": "player_id", "label": "PLAYER", "kind": "player"},
            {"key": "carried_bat_count", "label": "TIMES", "decimal": False},
            {"key": "highest_score", "label": "TOP SCORE", "decimal": False},
        ],
    },
    "most_runs_first_n": {
        "label": "Most runs after X matches",
        "description": "Who scored the most runs in their first N career matches (set N in Context).",
        "fn": derived_most_runs_first_n,
        "columns": [
            {"key": "player_id", "label": "PLAYER", "kind": "player"},
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "matches_played", "label": "MATCHES", "decimal": False},
        ],
    },
    "milestone_runs": {
        "label": "Fastest to runs milestone",
        "description": "Who reached a career runs milestone in the fewest matches (set milestone in Context).",
        "fn": derived_milestone_runs,
        "columns": [
            {"key": "player_id", "label": "PLAYER", "kind": "player"},
            {"key": "matches_to_milestone", "label": "MATCHES", "decimal": False},
            {"key": "reached_on", "label": "DATE"},
            {"key": "runs_at_crossing", "label": "RUNS AT", "decimal": False},
        ],
    },
}


# ─── Entry point ───────────────────────────────────────────────────────────────

TARGET_DISPATCH = {
    "player_career":    query_player_career,
    "player_season":    query_player_season,
    "player_grade":     query_player_grade,
    "innings_list":     query_innings_list,
    "spell_list":       query_spell_list,
    "match_list":       query_match_list,
    "partnership_list": query_partnership_list,
}


async def run_query(
    session: AsyncSession,
    *,
    org_id: str,
    target: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> list[dict]:
    if target not in TARGET_DISPATCH:
        raise ValueError(f"Unknown query target: {target}")
    fn = TARGET_DISPATCH[target]
    return await fn(
        session,
        org_id=org_id,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        metric_filters=metric_filters,
        filter_tree=filter_tree,
        context=context,
    )


async def run_derived(
    session: AsyncSession, *, name: str, org_id: str, limit: int, context: dict,
) -> list[dict]:
    if name not in DERIVED_QUERIES:
        raise ValueError(f"Unknown derived query: {name}")
    fn = DERIVED_QUERIES[name]["fn"]
    return await fn(session, org_id=org_id, limit=limit, context=context)


METRIC_CATEGORIES: list[dict] = [
    {"key": "participation", "label": "Participation",
     "fields": ["matches", "seasons_played", "batting_innings", "bowling_innings"]},
    {"key": "batting", "label": "Batting",
     "fields": ["runs", "not_outs", "batting_average", "batting_strike_rate", "high_score",
                "fifties", "hundreds", "ducks", "fours", "sixes", "balls_faced", "balls",
                "strike_rate", "batting_position"]},
    {"key": "bowling", "label": "Bowling",
     "fields": ["wickets", "overs", "maidens", "bowling_average", "bowling_economy",
                "bowling_strike_rate", "five_wicket_innings", "best_bowling_wickets",
                "runs_conceded", "wides", "no_balls", "economy"]},
    {"key": "fielding", "label": "Fielding",
     "fields": ["catches", "run_outs", "stumpings"]},
    {"key": "match", "label": "Match",
     "fields": ["team_runs", "team_wickets", "opp_runs", "opp_wickets", "margin_runs",
                "innings_number"]},
    {"key": "partnership", "label": "Partnership",
     "fields": ["wicket_number", "batter1_runs", "batter2_runs"]},
]


def schema() -> dict:
    """Public schema description for the frontend."""
    return {
        "targets": {
            t: {
                "metrics": list(TARGETS[t]["metrics"].keys()),
                "default_sort": TARGETS[t]["default_sort"],
            }
            for t in TARGETS
        },
        "categories": METRIC_CATEGORIES,
        "context_filters": {
            k: {"value_kind": v["value_kind"]} for k, v in CONTEXT_FILTERS.items()
        },
        "operators": list(OPERATOR_MAP.keys()),
        "derived": {
            k: {"label": v["label"], "description": v["description"], "columns": v["columns"]}
            for k, v in DERIVED_QUERIES.items()
        },
    }


# Back-compat aliases preserved for any external callers still on the old API.
PLAYER_FIELDS = PLAYER_AGG_METRICS
GRADE_FIELDS = PLAYER_AGG_METRICS
