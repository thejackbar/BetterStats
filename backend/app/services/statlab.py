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
import uuid

# The one list of "aggregate-only, no per-game rows behind it" sources
# (an imported season, a manual season/career adjustment) — see its own
# docstring in aggregations.py. Shared so the two modules can't drift on
# what counts as a residual.
from app.services.aggregations import _RESIDUAL_SOURCES
from app.services.game_status import appearance_counts_as_match


# ─── Grade type / match type scope ─────────────────────────────────────────────
# The two platform-wide grade filters (migration 259): Grade Type (men's /
# juniors / women's / masters) and Match Type (two day / one day / T20). Every
# other stats surface resolves them into one `GradeScope` and StatLab was the
# last one that didn't, so a club whose default leaves juniors out saw them
# counted here and nowhere else.
#
# The resolved scope rides in the context dict under `_scope`. That key can
# never arrive from a URL — `_ctx_from_request` only ever writes keys from its
# own whitelists, and none of them start with an underscore — so a browser
# can't hand us a scope of its own choosing.
_SCOPE_KEY = "_scope"


def _ctx_scope(ctx: dict):
    """The resolved GradeScope for this query, or None."""
    scope = (ctx or {}).get(_SCOPE_KEY)
    return scope if scope is not None and getattr(scope, "active", False) else None


def _scope_clause_for_join(scope, column: str, params: dict) -> str:
    """An aggregate-kind scope condition (leading AND), bound into `params`.

    For the two family targets, which sum `player_season_stats` directly and so
    have no game to read a format from. Returns "" when there is no scope.
    """
    if not scope:
        return ""
    clause = scope.clause(column, "aggregate")
    if clause:
        scope.bind(params)
    return clause


def _scope_fragment(clause: str) -> str:
    """`GradeScope.clause()` output as a bare condition, ready to AND-join.

    It hands back a fragment with a leading " AND " because most callers paste
    it straight into a WHERE. StatLab keeps its conditions in a list and joins
    them itself, so the leading AND has to come off. Each condition inside is
    already bracketed, so what's left composes safely.
    """
    frag = (clause or "").strip()
    if frag.startswith("AND "):
        frag = frag[4:]
    return frag.strip()


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
    "catches_wk": "catches_wk",
    "catches_non_wk": "catches_non_wk",
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
    "played_at": "played_at",
}

PARTNERSHIP_METRICS: dict[str, str] = {
    "runs": "runs",
    "balls": "balls",
    "wicket_number": "wicket_number",
    "batter1_runs": "batter1_runs",
    "batter2_runs": "batter2_runs",
}

# Family targets reuse every PLAYER_AGG_METRICS dimension (sums across all
# family members) and add a family-specific member_count column.
FAMILY_AGG_METRICS: dict[str, str] = {
    "member_count": "member_count",
    **PLAYER_AGG_METRICS,
}

TARGETS: dict[str, dict] = {
    "player_career":    {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "player_season":    {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "player_grade":     {"metrics": PLAYER_AGG_METRICS,  "default_sort": "runs"},
    "family_career":    {"metrics": FAMILY_AGG_METRICS,  "default_sort": "runs"},
    "family_season":    {"metrics": FAMILY_AGG_METRICS,  "default_sort": "runs"},
    "family_grade":     {"metrics": FAMILY_AGG_METRICS,  "default_sort": "runs"},
    "innings_list":     {"metrics": INNINGS_METRICS,     "default_sort": "runs"},
    "spell_list":       {"metrics": SPELL_METRICS,       "default_sort": "wickets"},
    "match_list":       {"metrics": MATCH_METRICS,       "default_sort": "team_runs"},
    "partnership_list": {"metrics": PARTNERSHIP_METRICS, "default_sort": "runs"},
}

# ─── Context filter spec ───────────────────────────────────────────────────────
# Context filters are top-level (not per-target); they always apply against the
# match/game row of the underlying record. value_kind controls how the value is
# coerced. operator is fixed because each filter has natural semantics.

# The result of a game from OUR side, as SQL. Extracted so the single-value
# `result` filter and the multi-select `results` one compare the same
# expression — two copies of a CASE this size drift the first time one is
# edited. Note it only ever emits won/lost/drawn: `games` has a winning team
# or it doesn't, so a tie is indistinguishable from a draw here.
_RESULT_CASE_SQL = (
    "(CASE WHEN g.winning_team IS NULL OR g.winning_team = '' THEN 'drawn'"
    " WHEN ga.team_name IS NOT NULL AND g.winning_team = ga.team_name THEN 'won'"
    " WHEN ga.team_name IS NOT NULL THEN 'lost' ELSE 'drawn' END)"
)


def _dismissal_match_sql(param: str) -> str:
    """Match one friendly dismissal label against what sync actually stores
    (bare short codes 'c'/'b'/'st', long forms for the rest), plus the
    caught_behind flag for "caught behind". ELSE keeps the exact-match
    fallback (e.g. 'not out').

    Takes its bind param by name so the single-value `dismissal` filter and
    each value of the multi-select `dismissals` one share this one definition.
    """
    return (
        "(CASE "
        f"WHEN LOWER(:{param}) = 'caught behind' THEN bi.caught_behind IS TRUE "
        f"WHEN LOWER(:{param}) = 'caught'  THEN (bi.dismissal_type = 'c' OR bi.dismissal_type LIKE 'c %' OR LOWER(bi.dismissal_type) LIKE 'ct%' OR LOWER(bi.dismissal_type) LIKE 'caught%') "
        f"WHEN LOWER(:{param}) = 'bowled'  THEN (bi.dismissal_type = 'b' OR bi.dismissal_type LIKE 'b %' OR LOWER(bi.dismissal_type) LIKE 'bowled%') "
        f"WHEN LOWER(:{param}) = 'stumped' THEN (bi.dismissal_type = 'st' OR bi.dismissal_type LIKE 'st %' OR LOWER(bi.dismissal_type) LIKE 'stumped%') "
        f"WHEN LOWER(:{param}) = 'lbw'     THEN (LOWER(bi.dismissal_type) LIKE 'lbw%' OR LOWER(bi.dismissal_type) LIKE 'leg before%') "
        f"WHEN LOWER(:{param}) = 'run out' THEN LOWER(bi.dismissal_type) LIKE 'run out%' "
        f"WHEN LOWER(:{param}) = 'hit wicket' THEN LOWER(bi.dismissal_type) LIKE 'hit wicket%' "
        f"ELSE LOWER(COALESCE(bi.dismissal_type, '')) = LOWER(:{param}) END)"
    )


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
    "result":       {"sql": f"{_RESULT_CASE_SQL} = :ctx_result",                       "value_kind": "result"},
    "on_this_day":  {"sql": "EXTRACT(MONTH FROM g.played_at) = EXTRACT(MONTH FROM CURRENT_DATE) AND EXTRACT(DAY FROM g.played_at) = EXTRACT(DAY FROM CURRENT_DATE)", "value_kind": "flag"},
}

# Per-innings filters — applied to batting_innings (bi) joins only; relevant
# only for innings_list and the live-aggregate paths of player_*.
INNINGS_CONTEXT_FILTERS: dict[str, dict] = {
    # See _dismissal_match_sql — the same CASE serves the multi-select
    # `dismissals` filter, one bound value at a time.
    "dismissal":    {"sql": _dismissal_match_sql("ctx_dismissal"), "value_kind": "text"},
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
    "gender":       {"sql": "LOWER(COALESCE(p.gender, '')) = LOWER(:ctx_gender)",            "value_kind": "text"},
    "player_role":  {"sql": "LOWER(COALESCE(p.player_role, '')) = LOWER(:ctx_player_role)",  "value_kind": "text"},
    "overseas":     {"sql": "("
                             "(:ctx_overseas = 'only' AND p.is_overseas = TRUE)"
                             " OR "
                             "(:ctx_overseas = 'exclude' AND (p.is_overseas IS NULL OR p.is_overseas = FALSE))"
                             ")",
                     "value_kind": "text"},
    # Achievement-driven filters — restrict results to players who have a
    # recorded entry in player_achievements matching the criterion. Subselect
    # is keyed by org_id, which is already bound at the outer query level.
    "award_category": {
        "sql": "p.id IN (SELECT player_id FROM player_achievements WHERE org_id = CAST(:org_id AS UUID) AND LOWER(COALESCE(category, '')) = LOWER(:ctx_award_category) AND player_id IS NOT NULL)",
        "value_kind": "text",
    },
    "award_subcategory": {
        "sql": "p.id IN (SELECT player_id FROM player_achievements WHERE org_id = CAST(:org_id AS UUID) AND LOWER(COALESCE(subcategory, '')) = LOWER(:ctx_award_subcategory) AND player_id IS NOT NULL)",
        "value_kind": "text",
    },
    "award_name": {
        "sql": "p.id IN (SELECT player_id FROM player_achievements WHERE org_id = CAST(:org_id AS UUID) AND LOWER(COALESCE(achievement, '')) = LOWER(:ctx_award_name) AND player_id IS NOT NULL)",
        "value_kind": "text",
    },
    "office_bearer": {
        "sql": "p.id IN (SELECT player_id FROM player_achievements WHERE org_id = CAST(:org_id AS UUID) AND LOWER(COALESCE(category, '')) = 'office bearer' AND LOWER(COALESCE(achievement, '')) = LOWER(:ctx_office_bearer) AND player_id IS NOT NULL)",
        "value_kind": "text",
    },
    # Family filter — restrict to players in the chosen family. The family
    # must belong to the same org; the org_id bind is already in scope.
    "family_id": {
        "sql": "p.id IN (SELECT fm.player_id FROM family_members fm JOIN families f ON f.id = fm.family_id WHERE f.id = CAST(:ctx_family_id AS UUID) AND f.organisation_id = CAST(:org_id AS UUID))",
        "value_kind": "uuid",
    },
}

# Combined view for schema introspection.
CONTEXT_FILTERS: dict[str, dict] = {**MATCH_CONTEXT_FILTERS, **INNINGS_CONTEXT_FILTERS, **PLAYER_CONTEXT_FILTERS}

# A residual row (an imported season, a manual season/career adjustment — see
# import_reconcile.py) has no per-game rows behind it at all: no date, no
# opposition, no result, no dismissal, no batting position, no per-appearance
# captain/keeper flag. So the moment ANY of these are in play, "live"
# per-innings aggregation is the only honest answer and a residual simply
# can't be evaluated against the filter — same reasoning as _RESIDUAL_SOURCES
# in aggregations.py, applied to whichever filters make it unanswerable.
# What a residual DOES carry: its own season_id, grade_id (when the upload
# named one, or grade_label when it's a career-scope import spanning many
# seasons' worth of same-named grades — see _RESIDUAL_GRADE_MATCH) and the
# player it belongs to — so season/grade/year filters and player-attribute
# filters (gender, role, overseas, family, awards) can be answered and are
# deliberately NOT in this disqualifying set. `grade_name` used to be listed
# here (a straight bug, contradicting this very comment) — see the "records
# before 2008/09 disappear once a merged grade is filtered" report, fixed by
# _RESIDUAL_GRADE_MATCH below instead of disqualifying the residual outright.
_RESIDUAL_DISQUALIFYING_MATCH_KEYS = (
    "date_from", "date_to", "opposition", "finals_only", "result", "on_this_day",
)
# The multi-select forms of the same unanswerable questions, mapped to the
# value_kind their single-value twin declares. Held separately because they
# have no MATCH_CONTEXT_FILTERS spec entry of their own — the clause grows
# with the selection, so it's built in _build_match_list_filters instead.
# (`season_ids` and `grade_ids`/`grade_names` are deliberately absent: a
# residual carries its own season and grade. `dismissals` is absent too — it
# lands in the innings block, which disqualifies on its own.)
_RESIDUAL_DISQUALIFYING_LIST_KEYS = {"results": "result"}
_RESIDUAL_DISQUALIFYING_PLAYER_KEYS = ("captain_only", "keeper_only")

# The player-level filters a residual row CAN be tested against — everything
# except captain_only/keeper_only, which are per-appearance (game_appearances)
# facts a residual has no row to carry.
_RESIDUAL_PLAYER_FILTERS = {
    k: v for k, v in PLAYER_CONTEXT_FILTERS.items() if k not in _RESIDUAL_DISQUALIFYING_PLAYER_KEYS
}


def _residual_disqualified(context: dict, ic: list[str]) -> bool:
    """True when a filter is active that a residual (no-per-game-data) row
    simply cannot be tested against — see the block comment above."""
    if ic:  # any INNINGS_CONTEXT_FILTERS (dismissal, batting position) in play
        return True
    for key in _RESIDUAL_DISQUALIFYING_MATCH_KEYS:
        if key in context and context[key] not in (None, "", []):
            coerced = _coerce_value(MATCH_CONTEXT_FILTERS[key]["value_kind"], context[key])
            if coerced not in (None, False):
                return True
    for key in _RESIDUAL_DISQUALIFYING_PLAYER_KEYS:
        if key in context and context[key] not in (None, "", []):
            coerced = _coerce_value(PLAYER_CONTEXT_FILTERS[key]["value_kind"], context[key])
            if coerced not in (None, False):
                return True
    for key, kind in _RESIDUAL_DISQUALIFYING_LIST_KEYS.items():
        # Coerce first: a selection that's entirely junk filters nothing, so it
        # must not knock residuals out either.
        if any(_coerce_value(kind, v) for v in _text_list(context.get(key))):
            return True
    return False


def _text_list(value) -> list[str]:
    """Normalise a multi-select TEXT context value into a list of strings.

    Accepts the canonical list form, or a single string (a saved report or an
    old URL that carried one value). Deliberately does NOT split on commas the
    way the UUID list filters do — a grade name is free text and can contain
    one ("1st Grade (Smith, Jones & Co)"), so splitting would quietly turn one
    real grade into two that match nothing.
    """
    if value in (None, "", []):
        return []
    raw = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[str] = []
    for v in raw:
        if v in (None, ""):
            continue
        text = str(v).strip()
        if text and text not in out:
            out.append(text)
    return out


def _residual_grade_match(prefix: str, suffix: str = "") -> str:
    """Merge-aware grade-name match for a residual row.

    `suffix` distinguishes one bound value from the next when several grades
    are selected at once (grade_names) — each gets its own
    `:{prefix}grade_name{suffix}` param and the caller ORs the clauses.

    Mirrors aggregations.py's `_GRADE_MATCH` / `_IMPORT_GRADE_MATCH` — the
    identical fix (migration 154) applied there for grade-filtered
    leaderboards, ported to StatLab's residual CTEs (`_residual_career_cte` /
    `_residual_season_cte` / `_residual_grade_cte`), which read the view
    instead of `import_effective_deltas` directly and so need their own copy.

    A season-scope import delta or a `manual_aggregate` row carries a real
    `grade_id` — one actual `grades` row for that season — resolved via `rg`
    (every caller LEFT JOINs `grades rg ON rg.id = pss.grade_id`). A
    career-scope import residual spans many seasons' worth of same-named
    grades and so has no `grade_id` at all (see migration 154's note); it's
    tagged by grade *name* instead, via `pss.grade_label`
    (migration 252 — surfaced onto the view; `manual_career`/`manual_game`
    rows always carry NULL here, since they were never grade-scoped at
    upload time and self-exclude by never matching).
    """
    p = f"{prefix}grade_name{suffix}"
    return (
        f"(COALESCE(rg.name, pss.grade_label) = :{p}"
        " OR EXISTS (SELECT 1 FROM grade_merge_logs gml"
        " WHERE gml.org_id = CAST(:org_id AS UUID)"
        " AND gml.alias_name = COALESCE(rg.name, pss.grade_label) AND gml.undone_at IS NULL"
        f" AND (gml.canonical_name = :{p}"
        " OR EXISTS (SELECT 1 FROM grades gr2 JOIN seasons s2 ON s2.id = gr2.season_id"
        " WHERE gr2.name = gml.canonical_name AND s2.organisation_id = CAST(:org_id AS UUID)"
        f" AND gr2.display_name_override = :{p}))))"
    )


def _residual_scope_clause(context: dict, params: dict, prefix: str) -> str:
    """Season/year/grade clauses for a residual query, using the `pss`/`s`/
    `rg` aliases a residual CTE joins (not `g`/`gr`/`gu` — a residual has no
    game row; `rg` is `LEFT JOIN grades rg ON rg.id = pss.grade_id`, added by
    every caller for _residual_grade_match). Covers the same dimensions
    MATCH_CONTEXT_FILTERS' season_id/season_ids/min_year/max_year/grade_id/
    grade_ids/grade_name already validate; reusing those functions isn't
    possible since the SQL text differs by alias.
    """
    clauses: list[str] = []

    season_id = context.get("season_id")
    if season_id:
        coerced = _coerce_value("uuid", season_id)
        if coerced:
            clauses.append(
                f"(s.id = CAST(:{prefix}season_id AS UUID) OR s.id IN "
                f"(SELECT alias_season_id FROM season_aliases "
                f"WHERE canonical_season_id = CAST(:{prefix}season_id AS UUID) AND undone_at IS NULL))"
            )
            params[f"{prefix}season_id"] = coerced

    season_ids_raw = context.get("season_ids")
    if isinstance(season_ids_raw, str):
        season_ids_raw = [x.strip() for x in season_ids_raw.split(",") if x.strip()]
    season_ids = [v for v in (_coerce_value("uuid", x) for x in (season_ids_raw or [])) if v]
    if season_ids:
        ph = ", ".join(f"CAST(:{prefix}season_ids_{i} AS UUID)" for i in range(len(season_ids)))
        clauses.append(
            f"(s.id IN ({ph}) OR s.id IN (SELECT alias_season_id FROM season_aliases "
            f"WHERE canonical_season_id IN ({ph}) AND undone_at IS NULL))"
        )
        for i, v in enumerate(season_ids):
            params[f"{prefix}season_ids_{i}"] = v

    min_year = context.get("min_year")
    if min_year not in (None, ""):
        coerced = _coerce_value("int", min_year)
        if coerced is not None:
            clauses.append(f"COALESCE(s.year, 0) >= :{prefix}min_year")
            params[f"{prefix}min_year"] = coerced

    max_year = context.get("max_year")
    if max_year not in (None, ""):
        coerced = _coerce_value("int", max_year)
        if coerced is not None:
            clauses.append(f"COALESCE(s.year, 9999) <= :{prefix}max_year")
            params[f"{prefix}max_year"] = coerced

    grade_id = context.get("grade_id")
    if grade_id:
        coerced = _coerce_value("uuid", grade_id)
        if coerced:
            clauses.append(f"pss.grade_id = CAST(:{prefix}grade_id AS UUID)")
            params[f"{prefix}grade_id"] = coerced

    grade_ids_raw = context.get("grade_ids")
    if isinstance(grade_ids_raw, str):
        grade_ids_raw = [x.strip() for x in grade_ids_raw.split(",") if x.strip()]
    grade_ids = [v for v in (_coerce_value("uuid", x) for x in (grade_ids_raw or [])) if v]
    if grade_ids:
        ph = ", ".join(f"CAST(:{prefix}grade_ids_{i} AS UUID)" for i in range(len(grade_ids)))
        clauses.append(f"pss.grade_id IN ({ph})")
        for i, v in enumerate(grade_ids):
            params[f"{prefix}grade_ids_{i}"] = v

    # The filter StatLab's own Grade dropdown actually sends (ctx.grade_name
    # in StatLab.jsx) — see _residual_grade_match for the merge-aware match
    # this resolves through.
    grade_name = context.get("grade_name")
    if grade_name:
        coerced = _coerce_value("text", grade_name)
        if coerced:
            clauses.append(_residual_grade_match(prefix))
            params[f"{prefix}grade_name"] = coerced

    # Several grades ticked at once (ctx.grade_names — what StatLab's Grade
    # picker sends). ORed together, so "1st Grade or 3rd Grade" is one clause;
    # the single-value grade_name above still ANDs, which is what a saved
    # report written before the picker went multi-select expects.
    grade_names = _text_list(context.get("grade_names"))
    if grade_names:
        ors = []
        for i, v in enumerate(grade_names):
            suffix = f"s_{i}"  # → :{prefix}grade_names_0, _1, …
            ors.append(_residual_grade_match(prefix, suffix))
            params[f"{prefix}grade_name{suffix}"] = v
        clauses.append("(" + " OR ".join(ors) + ")")

    # Grade type / match type against an aggregate row. `kind='aggregate'` is
    # what makes this honest: a residual has a grade (sometimes) but never a
    # game, so under a MATCH TYPE filter it emits AND FALSE rather than counting
    # an imported season towards a T20 record it can say nothing about. A
    # category-only scope still keeps residuals, per _RESIDUAL_SOURCES.
    scope = _ctx_scope(context)
    if scope:
        frag = _scope_fragment(scope.clause("pss.grade_id", "aggregate"))
        if frag:
            clauses.append(frag)
            scope.bind(params)

    return (" AND " + " AND ".join(clauses)) if clauses else ""


# Column list a residual CTE sums, shared by the career- and season-grouped
# builders below — every column the live per-game bat/bowl/field CTEs also
# produce, so the two sides COALESCE together cleanly.
_RESIDUAL_AGG_COLS_SQL = """
    COALESCE(SUM(pss.matches), 0)         AS matches,
    COALESCE(SUM(pss.batting_innings), 0) AS batting_innings,
    COALESCE(SUM(pss.runs), 0)            AS runs,
    COALESCE(SUM(pss.not_outs), 0)        AS not_outs,
    COALESCE(SUM(pss.balls_faced), 0)     AS balls_faced,
    MAX(pss.high_score)                   AS high_score,
    COALESCE(SUM(pss.fifties), 0)         AS fifties,
    COALESCE(SUM(pss.hundreds), 0)        AS hundreds,
    COALESCE(SUM(pss.ducks), 0)           AS ducks,
    COALESCE(SUM(pss.fours), 0)           AS fours,
    COALESCE(SUM(pss.sixes), 0)           AS sixes,
    COALESCE(SUM(pss.bowling_innings), 0) AS bowling_innings,
    COALESCE(SUM(pss.wickets), 0)         AS wickets,
    COALESCE(SUM(pss.overs), 0)           AS overs,
    COALESCE(SUM(pss.runs_conceded), 0)   AS runs_conceded,
    COALESCE(SUM(pss.maidens), 0)         AS maidens,
    MAX(pss.best_bowling_wickets)         AS best_bowling_wickets,
    COALESCE(SUM(pss.five_wicket_innings), 0) AS five_wicket_innings,
    COALESCE(SUM(pss.wides), 0)           AS wides,
    COALESCE(SUM(pss.no_balls), 0)        AS no_balls,
    COALESCE(SUM(pss.catches), 0)         AS catches,
    COALESCE(SUM(pss.catches_wk), 0)      AS catches_wk,
    COALESCE(SUM(pss.catches_non_wk), 0)  AS catches_non_wk,
    COALESCE(SUM(pss.run_outs), 0)        AS run_outs,
    COALESCE(SUM(pss.stumpings), 0)       AS stumpings
"""


def _residual_career_cte(context: dict, params: dict) -> str:
    """A `resid` CTE (one row per player) for query_player_career's live
    branch — the residual-sources union of v_effective_player_season_stats,
    scoped to whatever season/grade/year/player filters a residual row can
    actually answer (see _residual_scope_clause / _RESIDUAL_PLAYER_FILTERS).
    Career-level rows (season_id NULL — a manual career adjustment, an
    import career residual) are kept via the LEFT JOIN, same as the fast
    path above.
    """
    params["residual_sources"] = list(_RESIDUAL_SOURCES)
    scope_clause = _residual_scope_clause(context, params, "rc_")
    player_clauses, player_params, _ = _build_filter_block(context, _RESIDUAL_PLAYER_FILTERS)
    params.update(player_params)
    player_clause = (" AND " + " AND ".join(player_clauses)) if player_clauses else ""
    return f"""
        resid AS (
            SELECT
                -- Native UUID (not ::text) to match bat/bowl/field/appear's
                -- player_id — they COALESCE and join together in
                -- query_player_career, and mixing UUID/text there is a type
                -- error, not a silent cast. Cast happens once, in the
                -- caller's outer SELECT.
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                {_RESIDUAL_AGG_COLS_SQL}
            FROM v_effective_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            LEFT JOIN seasons s ON s.id = pss.season_id
            -- To-one (grades.id is a PK): resolves a grade filter for the
            -- rows that carry a real grade_id (manual_aggregate, a
            -- season-scope import delta) — see _residual_grade_match.
            LEFT JOIN grades rg ON rg.id = pss.grade_id
            WHERE p.organisation_id = :org_id
              AND pss.source = ANY(:residual_sources)
              {scope_clause}
              {player_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
        )
    """


def _residual_season_cte(context: dict, params: dict) -> str:
    """The season-grouped mirror of `_residual_career_cte`, for
    query_player_season's live branch. A career-level row (season_id NULL)
    has no season to sit in and is naturally dropped by the INNER JOIN —
    matching how the live per-game side has no career-level row either.
    Grouped on the residual's OWN season_id (not canonicalised through
    season_aliases) to match `gu.season_id`, which the live per-game side
    also leaves un-canonicalised — a pre-existing StatLab limitation, not
    something introduced here.
    """
    params["residual_sources"] = list(_RESIDUAL_SOURCES)
    scope_clause = _residual_scope_clause(context, params, "rs_")
    player_clauses, player_params, _ = _build_filter_block(context, _RESIDUAL_PLAYER_FILTERS)
    params.update(player_params)
    player_clause = (" AND " + " AND ".join(player_clauses)) if player_clauses else ""
    return f"""
        resid AS (
            SELECT
                -- Native UUID (not ::text) on both id columns to match
                -- bat/bowl/field/appear's player_id and gu.season_id's
                -- types — they COALESCE and join together in
                -- query_player_season, and mixing UUID/text there is a type
                -- error, not a silent cast. Casts happen once, in the
                -- caller's outer SELECT.
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                pss.season_id AS season_id,
                s.name AS season_name,
                COALESCE(s.year, 0) AS season_year,
                {_RESIDUAL_AGG_COLS_SQL}
            FROM v_effective_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            JOIN seasons s ON s.id = pss.season_id
            -- To-one (grades.id is a PK) — see _residual_career_cte's own note.
            LEFT JOIN grades rg ON rg.id = pss.grade_id
            WHERE p.organisation_id = :org_id
              AND pss.source = ANY(:residual_sources)
              AND pss.season_id IS NOT NULL
              {scope_clause}
              {player_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), pss.season_id, s.name, s.year
        )
    """


def _residual_grade_cte(context: dict, params: dict) -> str:
    """The grade-grouped mirror of `_residual_career_cte`, for
    query_player_grade — previously the one target with NO residual branch
    at all, filtered or not, so an imported/manual-aggregate history never
    appeared under any grade. This is the direct fix for the reported bug: a
    club merges many old grade names into one canonical grade and StatLab's
    GRADE filter shows nothing before the season real per-game scorecards
    begin, because everything before that is exactly this kind of residual
    row.

    Resolves the canonical grade name the same way `game_universe` does for
    real per-game rows (`am`/`gdn` LATERALs against `grade_merge_logs` /
    `grades.display_name_override`), just fed from `rg`/`pss.grade_label`
    instead of a real games→grades join. A row with neither `grade_id` nor
    `grade_label` (`manual_career`, always ungraded at upload time) has
    nothing to group under here and is dropped by the WHERE clause — it's
    still visible career-wide via query_player_career, just not per grade.
    """
    params["residual_sources"] = list(_RESIDUAL_SOURCES)
    scope_clause = _residual_scope_clause(context, params, "rg_")
    player_clauses, player_params, _ = _build_filter_block(context, _RESIDUAL_PLAYER_FILTERS)
    params.update(player_params)
    player_clause = (" AND " + " AND ".join(player_clauses)) if player_clauses else ""
    return f"""
        resid AS (
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COALESCE(am.canonical_name, rg.name, pss.grade_label) AS grade_name,
                COALESCE(gdn.display_name_override,
                         COALESCE(am.canonical_name, rg.name, pss.grade_label)) AS display_grade_name,
                {_RESIDUAL_AGG_COLS_SQL}
            FROM v_effective_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            LEFT JOIN seasons s ON s.id = pss.season_id
            -- To-one (grades.id is a PK) — see _residual_career_cte's own note.
            LEFT JOIN grades rg ON rg.id = pss.grade_id
            LEFT JOIN LATERAL (
                SELECT canonical_name FROM grade_merge_logs gml
                WHERE gml.org_id = CAST(:org_id AS UUID)
                  AND gml.alias_name = COALESCE(rg.name, pss.grade_label)
                  AND gml.undone_at IS NULL
                LIMIT 1
            ) am ON TRUE
            LEFT JOIN LATERAL (
                SELECT gr2.display_name_override FROM grades gr2
                JOIN seasons s2 ON s2.id = gr2.season_id
                WHERE s2.organisation_id = CAST(:org_id AS UUID)
                  AND gr2.name = COALESCE(am.canonical_name, rg.name, pss.grade_label)
                  AND gr2.display_name_override IS NOT NULL
                LIMIT 1
            ) gdn ON TRUE
            WHERE p.organisation_id = :org_id
              AND pss.source = ANY(:residual_sources)
              AND (pss.grade_id IS NOT NULL OR pss.grade_label IS NOT NULL)
              {scope_clause}
              {player_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name),
                     COALESCE(am.canonical_name, rg.name, pss.grade_label),
                     COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, rg.name, pss.grade_label))
        )
    """


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
            uuid.UUID(str(value_str))
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


def _build_match_list_filters(ctx: dict) -> tuple[list[str], dict]:
    """Multi-select MATCH-scope filters (season_ids, grade_ids, grade_names).
    These don't fit the per-value spec dict because their SQL clause grows
    with the number of selected values. Expanded inline as
    ``IN (:p_0, :p_1, …)`` with one bound param per value.

    The two id filters accept either a list (canonical) or a comma-separated
    string (back-compat when the API receives a single repeated query param).
    `grade_names` is free text and so is never comma-split — see _text_list."""

    def _normalise(v):
        if v is None or v == "":
            return []
        if isinstance(v, (list, tuple, set)):
            raw = [str(x) for x in v if x not in (None, "")]
        else:
            raw = [s.strip() for s in str(v).split(",") if s.strip()]
        valid = []
        for s in raw:
            try:
                uuid.UUID(s)
            except (ValueError, TypeError, AttributeError):
                continue
            valid.append(s)
        return valid

    clauses: list[str] = []
    params: dict = {}

    season_ids = _normalise(ctx.get("season_ids"))
    if season_ids:
        ph = ", ".join(f"CAST(:ctx_season_ids_{i} AS UUID)" for i in range(len(season_ids)))
        # Match canonical seasons OR any alias mapped to one of them so a
        # user who selects a canonical season still sees alias-tagged stats.
        clauses.append(
            f"(s.id IN ({ph}) OR s.id IN (SELECT alias_season_id FROM season_aliases "
            f"WHERE canonical_season_id IN ({ph}) AND undone_at IS NULL))"
        )
        for i, v in enumerate(season_ids):
            params[f"ctx_season_ids_{i}"] = v

    grade_ids = _normalise(ctx.get("grade_ids"))
    if grade_ids:
        ph = ", ".join(f"CAST(:ctx_grade_ids_{i} AS UUID)" for i in range(len(grade_ids)))
        clauses.append(f"gr.id IN ({ph})")
        for i, v in enumerate(grade_ids):
            params[f"ctx_grade_ids_{i}"] = v

    # Results ticked (won / lost / drawn). Same expression the single-value
    # `result` filter compares, so the two can't disagree about what a draw is.
    results = [v for v in (_coerce_value("result", x) for x in _text_list(ctx.get("results"))) if v]
    if results:
        ph = ", ".join(f":ctx_results_{i}" for i in range(len(results)))
        clauses.append(f"{_RESULT_CASE_SQL} IN ({ph})")
        for i, v in enumerate(results):
            params[f"ctx_results_{i}"] = v

    # Grades ticked by name — what StatLab's own Grade picker sends. Compared
    # against the same COALESCE(am.canonical_name, gr.name) the single-value
    # grade_name filter uses, so a merged grade still resolves through its
    # canonical name and a season's worth of alias spellings all match.
    grade_names = _text_list(ctx.get("grade_names"))
    if grade_names:
        ph = ", ".join(f":ctx_grade_names_{i}" for i in range(len(grade_names)))
        clauses.append(f"COALESCE(am.canonical_name, gr.name) IN ({ph})")
        for i, v in enumerate(grade_names):
            params[f"ctx_grade_names_{i}"] = v

    return clauses, params


def _pss_season_filter(context: dict, params: dict, prefix: str) -> str:
    """`AND (…)` restricting a player_season_stats-based query to the chosen
    season(s), alias-aware, or "" when no season is chosen.

    Three queries aggregate straight off pss rather than through
    game_universe (player_season's aggregate path, family_season, and the
    batting-minutes derived query), so MATCH_CONTEXT_FILTERS never reaches
    them and each needs this clause of its own. They had three near-copies of
    it, one of which only ever honoured the single `season_id` — which is how
    a multi-season pick would have been silently ignored on one screen and
    obeyed on the others. `prefix` keeps the bind names distinct per query.

    The multi-select `season_ids` wins outright over the legacy single
    `season_id`, rather than ANDing: the picker writes one and clears the
    other, and a saved report carrying both means the newer key.
    """
    season_ids = context.get("season_ids")
    if isinstance(season_ids, str):
        season_ids = [x.strip() for x in season_ids.split(",") if x.strip()]
    season_ids = [v for v in (_coerce_value("uuid", x) for x in (season_ids or [])) if v]
    if season_ids:
        ph = ", ".join(f"CAST(:{prefix}season_ids_{i} AS UUID)" for i in range(len(season_ids)))
        for i, v in enumerate(season_ids):
            params[f"{prefix}season_ids_{i}"] = v
        return (
            f"AND (s.id IN ({ph}) "
            f"OR s.id IN (SELECT alias_season_id FROM season_aliases "
            f"WHERE canonical_season_id IN ({ph}) AND undone_at IS NULL))"
        )
    season_id = _coerce_value("uuid", context.get("season_id"))
    if season_id:
        params[f"{prefix}season_id"] = season_id
        return (
            f"AND (s.id = CAST(:{prefix}season_id AS UUID) "
            f"OR s.id IN (SELECT alias_season_id FROM season_aliases "
            f"WHERE canonical_season_id = CAST(:{prefix}season_id AS UUID) "
            f"AND undone_at IS NULL))"
        )
    return ""


def _build_innings_list_filters(ctx: dict) -> tuple[list[str], dict]:
    """Multi-select INNINGS-scope filters (dismissals). ORed inside one
    bracket — "caught or caught behind" is one question about one innings,
    whereas ANDing would ask for an innings that ended two ways at once."""
    values = _text_list(ctx.get("dismissals"))
    if not values:
        return [], {}
    ors, params = [], {}
    for i, v in enumerate(values):
        param = f"ctx_dismissals_{i}"
        ors.append(_dismissal_match_sql(param))
        params[param] = v
    return ["(" + " OR ".join(ors) + ")"], params


def _build_context_filters(ctx: dict) -> tuple[list[str], dict, list[str], dict, list[str], dict, bool]:
    """Returns (match_clauses, match_params, innings_clauses, innings_params,
    player_clauses, player_params, any_match_used).
    The match block expands inside game_universe; the innings block attaches to
    batting_innings joins; the player block attaches to (game_universe × player)
    via a gap LEFT JOIN that callers must provide.
    """
    mc, mp, mu = _build_filter_block(ctx, MATCH_CONTEXT_FILTERS)
    # Merge in multi-select MATCH filters (season_ids, grade_ids, grade_names).
    list_clauses, list_params = _build_match_list_filters(ctx)
    if list_clauses:
        mc = mc + list_clauses
        mp = {**mp, **list_params}
        mu = True
    # Grade type / match type. `kind='game'` (the default) is right for
    # game_universe: it reads the CATEGORY exclusion off the game's grade_id and
    # the FORMAT off each fixture's own match_format, which is what stops a
    # grade that plays both formats filing all of its games under one.
    scope = _ctx_scope(ctx)
    if scope:
        frag = _scope_fragment(scope.clause("g.grade_id"))
        if frag:
            mc = mc + [frag]
            scope.bind(mp)
            # An active scope is only answerable from per-game rows, so it also
            # switches the aggregate-path targets to live aggregation — the same
            # trade records.py makes with its own `scope_active`.
            mu = True
    ic, ip, _iu = _build_filter_block(ctx, INNINGS_CONTEXT_FILTERS)
    # Merge in the multi-select INNINGS filter (dismissals). Landing in `ic` is
    # what keeps residuals disqualified from a dismissal-scoped query — see
    # _residual_disqualified, which treats any innings clause as unanswerable.
    inn_clauses, inn_params = _build_innings_list_filters(ctx)
    if inn_clauses:
        ic = ic + inn_clauses
        ip = {**ip, **inn_params}
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
            FROM v_effective_games g
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
    # The alias is `gap` in the appear CTE below, which is the row this tests.
    played_clause = appearance_counts_as_match("gap")
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY {group_cols}
        ),
        field AS (
            SELECT
                {select_cols}
                COALESCE(SUM(fs.catches), 0)   AS catches,
                COALESCE(SUM(fs.catches_wk), 0) AS catches_wk,
                COALESCE(SUM(GREATEST(fs.catches - fs.catches_wk, 0)), 0) AS catches_non_wk,
                COALESCE(SUM(fs.run_outs), 0)  AS run_outs,
                COALESCE(SUM(fs.stumpings), 0) AS stumpings
            FROM game_universe gu
            JOIN v_effective_fielding_stats fs ON fs.game_id = gu.game_id
            JOIN players p ON p.id = fs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY {group_cols}
        ),
        appear AS (
            -- This CTE is the ONLY source of StatLab's `matches`, so the
            -- called-off rule has to live here as well as in
            -- v_effective_player_season_stats. Without it a washout a player
            -- was named in counts here while the same player's season row on
            -- every other screen has it netted off, and StatLab reads as
            -- broken. See services/game_status.py.
            SELECT
                {select_cols}
                COUNT(DISTINCT gu.game_id) AS matches
            FROM game_universe gu
            JOIN game_appearances gap ON gap.game_id = gu.game_id
            JOIN players p ON p.id = gap.player_id
            WHERE p.organisation_id = :org_id {player_extra}
              AND {played_clause}
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
    offset: int = 0,
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
        # A residual (imported/manual-aggregate) row has no per-game data, so
        # it can only join in when every active filter is one it can actually
        # answer — see _residual_disqualified. Without this, the moment ANY
        # context filter was set (a season, a year range, even just a grade),
        # an imported season vanished from StatLab even though the unfiltered
        # fast path above shows it fine (the reported 1970/71 case).
        residual_ok = not _residual_disqualified(context, ic)
        resid_with = (",\n" + _residual_career_cte(context, params)) if residual_ok else ""
        # The join condition's RHS must NOT include resid.player_id — a FULL
        # OUTER JOIN condition can't reference the table it's joining on both
        # sides (Postgres rejects it outright: "only supported with
        # merge-joinable or hash-joinable join conditions"). The outer
        # SELECT's id, below, is a separate expression that DOES add resid
        # as the final fallback, for a player whose only row is residual.
        live_id = "COALESCE(appear.player_id, bat.player_id, bowl.player_id, field.player_id)"
        resid_id = f"COALESCE({live_id}, resid.player_id)" if residual_ok else live_id
        resid_name = "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name, resid.player_name)" if residual_ok \
            else "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name)"
        resid_join = f"FULL OUTER JOIN resid ON resid.player_id = {live_id}" if residual_ok else ""

        def _r(col: str) -> str:
            """A live column plus its residual counterpart, or just the live
            column when a disqualifying filter ruled the residual out."""
            return f"(COALESCE({col}, 0) + COALESCE(resid.{col.split('.')[-1]}, 0))" if residual_ok else f"COALESCE({col}, 0)"

        sql = f"""
            {cte}{resid_with},
            agg AS (
                SELECT
                    {resid_id}::text AS player_id,
                    {resid_name} AS player_name,
                    {_r('appear.matches')}                                            AS matches,
                    1                                                                  AS seasons_played,
                    {_r('bat.batting_innings')}                                       AS batting_innings,
                    {_r('bat.runs')}                                                  AS runs,
                    {_r('bat.not_outs')}                                              AS not_outs,
                    {_r('bat.balls_faced')}                                           AS balls_faced,
                    ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.batting_innings')} - {_r('bat.not_outs')}, 0), 2) AS batting_average,
                    ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.balls_faced')}, 0) * 100, 2)     AS batting_strike_rate,
                    GREATEST(COALESCE(bat.high_score, 0){', COALESCE(resid.high_score, 0)' if residual_ok else ''}) AS high_score,
                    {_r('bat.fifties')}                                               AS fifties,
                    {_r('bat.hundreds')}                                              AS hundreds,
                    {_r('bat.ducks')}                                                 AS ducks,
                    {_r('bat.fours')}                                                 AS fours,
                    {_r('bat.sixes')}                                                 AS sixes,
                    {_r('bowl.bowling_innings')}                                      AS bowling_innings,
                    {_r('bowl.wickets')}                                              AS wickets,
                    {_r('bowl.overs')}                                                AS overs,
                    {_r('bowl.runs_conceded')}                                        AS runs_conceded,
                    ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.wickets')}, 0), 2)   AS bowling_average,
                    ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.overs')} * 6, 0) * 6, 2) AS bowling_economy,
                    ROUND({_r('bowl.overs')}::numeric * 6 / NULLIF({_r('bowl.wickets')}, 0), 2)        AS bowling_strike_rate,
                    {_r('bowl.five_wicket_innings')}                                  AS five_wicket_innings,
                    {_r('bowl.maidens')}                                              AS maidens,
                    GREATEST(bowl.best_bowling_wickets{', resid.best_bowling_wickets' if residual_ok else ''}) AS best_bowling_wickets,
                    {_r('bowl.wides')}    AS wides,
                    {_r('bowl.no_balls')} AS no_balls,
                    {_r('field.catches')}                                             AS catches,
                    {_r('field.catches_wk')}                                          AS catches_wk,
                    {_r('field.catches_non_wk')}                                      AS catches_non_wk,
                    {_r('field.run_outs')}                                            AS run_outs,
                    {_r('field.stumpings')}                                           AS stumpings
                FROM appear
                FULL OUTER JOIN bat  ON bat.player_id  = appear.player_id
                FULL OUTER JOIN bowl ON bowl.player_id = COALESCE(appear.player_id, bat.player_id)
                FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                {resid_join}
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST
            LIMIT :limit OFFSET :offset
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
                    COALESCE(SUM(pss.catches_wk), 0)                                             AS catches_wk,
                    COALESCE(SUM(pss.catches_non_wk), 0)                                         AS catches_non_wk,
                    COALESCE(SUM(pss.run_outs), 0)                                               AS run_outs,
                    COALESCE(SUM(pss.stumpings), 0)                                              AS stumpings
                -- The effective view, not the base table: imported history
                -- (BetterImport deltas) and manual season/career adjustments
                -- only exist as view branches, and reading the base table
                -- left every one of them out of StatLab (the reported
                -- 1970/71-import case). The view's api branch already carries
                -- the migration-060 cross-club guard.
                FROM v_effective_player_season_stats pss
                JOIN players p ON p.id = pss.player_id
                -- LEFT: career-level rows (a manual career adjustment, an
                -- import career residual) have no season and must still count
                -- toward career totals, exactly as the player profile counts
                -- them. Season-keyed rows stay scoped to this org's seasons.
                LEFT JOIN seasons s ON s.id = pss.season_id
                WHERE p.organisation_id = :org_id
                  AND (pss.season_id IS NULL OR s.organisation_id = :org_id)
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST
            LIMIT :limit OFFSET :offset
        """

    params["offset"] = offset
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
    offset: int = 0,
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
        # See query_player_career's own note: a residual row (an imported
        # season, a manual adjustment) has no per-game data, so it only joins
        # in when every active filter is one it can actually answer.
        residual_ok = not _residual_disqualified(context, ic)
        resid_with = (",\n" + _residual_season_cte(context, params)) if residual_ok else ""
        # The join condition's RHS must NOT reference resid.* itself — see
        # query_player_career's own note (Postgres rejects a FULL OUTER JOIN
        # condition that's circular through the table being joined). The
        # outer SELECT's id/season columns, below, are separate expressions
        # that DO add resid as the final fallback.
        live_pid = "COALESCE(appear.player_id, bat.player_id, bowl.player_id, field.player_id)"
        live_sid = "COALESCE(appear.season_id, bat.season_id, bowl.season_id, field.season_id)"
        resid_pid = f"COALESCE({live_pid}, resid.player_id)" if residual_ok else live_pid
        resid_pname = "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name, resid.player_name)" if residual_ok \
            else "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name)"
        resid_sid = f"COALESCE({live_sid}, resid.season_id)" if residual_ok else live_sid
        resid_sname = "COALESCE(appear.season_name, bat.season_name, bowl.season_name, field.season_name, resid.season_name)" if residual_ok \
            else "COALESCE(appear.season_name, bat.season_name, bowl.season_name, field.season_name)"
        resid_syear = "COALESCE(appear.season_year, bat.season_year, bowl.season_year, field.season_year, resid.season_year)" if residual_ok \
            else "COALESCE(appear.season_year, bat.season_year, bowl.season_year, field.season_year)"
        resid_join = (
            f"FULL OUTER JOIN resid ON resid.player_id = {live_pid} AND resid.season_id = {live_sid}"
        ) if residual_ok else ""

        def _r(col: str) -> str:
            """A live column plus its residual counterpart, or just the live
            column when a disqualifying filter ruled the residual out."""
            return f"(COALESCE({col}, 0) + COALESCE(resid.{col.split('.')[-1]}, 0))" if residual_ok else f"COALESCE({col}, 0)"

        sql = f"""
            {cte}{resid_with},
            agg AS (
                SELECT
                    {resid_pid}::text   AS player_id,
                    {resid_pname}       AS player_name,
                    {resid_sid}::text   AS season_id,
                    {resid_sname}       AS season_name,
                    {resid_syear}       AS season_year,
                    {_r('appear.matches')}                            AS matches,
                    1                                                  AS seasons_played,
                    {_r('bat.batting_innings')}                       AS batting_innings,
                    {_r('bat.runs')}                                  AS runs,
                    {_r('bat.not_outs')}                              AS not_outs,
                    {_r('bat.balls_faced')}                           AS balls_faced,
                    ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.batting_innings')} - {_r('bat.not_outs')}, 0), 2) AS batting_average,
                    ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.balls_faced')}, 0) * 100, 2)             AS batting_strike_rate,
                    GREATEST(COALESCE(bat.high_score, 0){', COALESCE(resid.high_score, 0)' if residual_ok else ''}) AS high_score,
                    {_r('bat.fifties')}                               AS fifties,
                    {_r('bat.hundreds')}                              AS hundreds,
                    {_r('bat.ducks')}                                 AS ducks,
                    {_r('bat.fours')}                                 AS fours,
                    {_r('bat.sixes')}                                 AS sixes,
                    {_r('bowl.bowling_innings')}                      AS bowling_innings,
                    {_r('bowl.wickets')}                              AS wickets,
                    {_r('bowl.overs')}                                AS overs,
                    {_r('bowl.runs_conceded')}                        AS runs_conceded,
                    ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.wickets')}, 0), 2) AS bowling_average,
                    ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.overs')} * 6, 0) * 6, 2) AS bowling_economy,
                    ROUND({_r('bowl.overs')}::numeric * 6 / NULLIF({_r('bowl.wickets')}, 0), 2) AS bowling_strike_rate,
                    {_r('bowl.five_wicket_innings')}                  AS five_wicket_innings,
                    {_r('bowl.maidens')}                              AS maidens,
                    GREATEST(bowl.best_bowling_wickets{', resid.best_bowling_wickets' if residual_ok else ''}) AS best_bowling_wickets,
                    {_r('bowl.wides')}    AS wides,
                    {_r('bowl.no_balls')} AS no_balls,
                    {_r('field.catches')}                             AS catches,
                    {_r('field.catches_wk')}                          AS catches_wk,
                    {_r('field.catches_non_wk')}                      AS catches_non_wk,
                    {_r('field.run_outs')}                            AS run_outs,
                    {_r('field.stumpings')}                           AS stumpings
                FROM appear
                FULL OUTER JOIN bat  ON bat.player_id  = appear.player_id AND bat.season_id  = appear.season_id
                FULL OUTER JOIN bowl ON bowl.player_id = COALESCE(appear.player_id, bat.player_id)
                                     AND bowl.season_id = COALESCE(appear.season_id, bat.season_id)
                FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                                     AND field.season_id = COALESCE(appear.season_id, bat.season_id, bowl.season_id)
                {resid_join}
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST, season_year DESC
            LIMIT :limit OFFSET :offset
        """
    else:
        season_filter = _pss_season_filter(context, params, "ctx_pss_")
        sql = f"""
            WITH per_pss AS (
                -- The effective view, not the base table: an imported season
                -- delta or manual season adjustment only exists as a view
                -- branch (see query_player_career's own note above). Season
                -- aliasing is applied here too, so a merged season sums every
                -- source under its one canonical row, matching
                -- get_season_by_season's own merge-aware behaviour.
                SELECT
                    pss.*,
                    COALESCE(sa.canonical_season_id, pss.season_id) AS canonical_season_id
                FROM v_effective_player_season_stats pss
                LEFT JOIN season_aliases sa
                  ON sa.alias_season_id = pss.season_id
                 AND sa.undone_at IS NULL
                WHERE pss.season_id IS NOT NULL
            ),
            agg AS (
                SELECT
                    p.id::text                                                                    AS player_id,
                    COALESCE(p.display_name_override, p.name)                                    AS player_name,
                    s.id::text                                                                    AS season_id,
                    s.name                                                                        AS season_name,
                    COALESCE(s.year, 0)                                                           AS season_year,
                    1                                                                             AS seasons_played,
                    COALESCE(SUM(pss.matches), 0)                                                 AS matches,
                    COALESCE(SUM(pss.batting_innings), 0)                                         AS batting_innings,
                    COALESCE(SUM(pss.runs), 0)                                                    AS runs,
                    COALESCE(SUM(pss.not_outs), 0)                                                AS not_outs,
                    COALESCE(SUM(pss.balls_faced), 0)                                             AS balls_faced,
                    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS batting_average,
                    ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2)     AS batting_strike_rate,
                    MAX(pss.high_score)                                                            AS high_score,
                    COALESCE(SUM(pss.fifties), 0)                                                 AS fifties,
                    COALESCE(SUM(pss.hundreds), 0)                                                AS hundreds,
                    COALESCE(SUM(pss.ducks), 0)                                                   AS ducks,
                    COALESCE(SUM(pss.fours), 0)                                                   AS fours,
                    COALESCE(SUM(pss.sixes), 0)                                                   AS sixes,
                    COALESCE(SUM(pss.bowling_innings), 0)                                         AS bowling_innings,
                    COALESCE(SUM(pss.wickets), 0)                                                 AS wickets,
                    COALESCE(SUM(pss.overs), 0)                                                   AS overs,
                    COALESCE(SUM(pss.runs_conceded), 0)                                           AS runs_conceded,
                    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2)       AS bowling_average,
                    ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS bowling_economy,
                    ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 2)       AS bowling_strike_rate,
                    COALESCE(SUM(pss.five_wicket_innings), 0)                                     AS five_wicket_innings,
                    COALESCE(SUM(pss.maidens), 0)                                                 AS maidens,
                    MAX(pss.best_bowling_wickets)                                                  AS best_bowling_wickets,
                    COALESCE(SUM(pss.wides), 0)    AS wides,
                    COALESCE(SUM(pss.no_balls), 0) AS no_balls,
                    COALESCE(SUM(pss.catches), 0)                                                 AS catches,
                    COALESCE(SUM(pss.catches_wk), 0)                                               AS catches_wk,
                    COALESCE(SUM(pss.catches_non_wk), 0)                                           AS catches_non_wk,
                    COALESCE(SUM(pss.run_outs), 0)                                                AS run_outs,
                    COALESCE(SUM(pss.stumpings), 0)                                               AS stumpings
                FROM per_pss pss
                JOIN players p ON p.id = pss.player_id
                JOIN seasons s ON s.id = pss.canonical_season_id
                WHERE p.organisation_id = :org_id AND s.organisation_id = :org_id {season_filter}
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), s.id, s.name, s.year
            )
            SELECT * FROM agg
            {where_sql}
            ORDER BY {sort_by} {sort_dir} NULLS LAST, season_year DESC
            LIMIT :limit OFFSET :offset
        """

    params["offset"] = offset
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
    offset: int = 0,
    context: dict,
) -> list[dict]:
    """One row per (player, canonical grade name). Always uses per-innings
    aggregation since player_season_stats has no grade dimension. Blends in
    the residual (imported/manual-aggregate) history under its own resolved
    grade — see _residual_grade_cte for why this target needed one at all."""
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
    # Same rule as query_player_career/query_player_season: a residual row can
    # only join in when every active filter is one it can actually answer.
    residual_ok = not _residual_disqualified(context, ic)
    resid_with = (",\n" + _residual_grade_cte(context, params)) if residual_ok else ""
    # See query_player_career's own note: a FULL OUTER JOIN condition can't
    # reference the table it's joining on both sides, so the join uses the
    # live-only columns and the outer SELECT below adds resid as a separate
    # final fallback.
    live_pid = "COALESCE(appear.player_id, bat.player_id, bowl.player_id, field.player_id)"
    live_gname = "COALESCE(appear.grade_name, bat.grade_name, bowl.grade_name, field.grade_name)"
    resid_pid = f"COALESCE({live_pid}, resid.player_id)" if residual_ok else live_pid
    resid_pname = "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name, resid.player_name)" if residual_ok \
        else "COALESCE(appear.player_name, bat.player_name, bowl.player_name, field.player_name)"
    resid_gname = f"COALESCE({live_gname}, resid.grade_name)" if residual_ok else live_gname
    resid_dispname = "COALESCE(appear.display_grade_name, bat.display_grade_name, bowl.display_grade_name, field.display_grade_name, resid.display_grade_name)" if residual_ok \
        else "COALESCE(appear.display_grade_name, bat.display_grade_name, bowl.display_grade_name, field.display_grade_name)"
    resid_join = f"FULL OUTER JOIN resid ON resid.player_id = {live_pid} AND resid.grade_name = {live_gname}" if residual_ok else ""

    def _r(col: str) -> str:
        """A live column plus its residual counterpart, or just the live
        column when a disqualifying filter ruled the residual out."""
        return f"(COALESCE({col}, 0) + COALESCE(resid.{col.split('.')[-1]}, 0))" if residual_ok else f"COALESCE({col}, 0)"

    sql = f"""
        {cte}{resid_with},
        agg AS (
            SELECT
                {resid_pid}::text  AS player_id,
                {resid_pname}      AS player_name,
                {resid_gname}      AS grade_name,
                {resid_dispname}   AS display_grade_name,
                {_r('appear.matches')}                                   AS matches,
                1                                                        AS seasons_played,
                {_r('bat.batting_innings')}                              AS batting_innings,
                {_r('bat.runs')}                                         AS runs,
                {_r('bat.not_outs')}                                     AS not_outs,
                {_r('bat.balls_faced')}                                  AS balls_faced,
                ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.batting_innings')} - {_r('bat.not_outs')}, 0), 2) AS batting_average,
                ROUND({_r('bat.runs')}::numeric / NULLIF({_r('bat.balls_faced')}, 0) * 100, 2)                     AS batting_strike_rate,
                GREATEST(COALESCE(bat.high_score, 0){', COALESCE(resid.high_score, 0)' if residual_ok else ''}) AS high_score,
                {_r('bat.fifties')}                                      AS fifties,
                {_r('bat.hundreds')}                                     AS hundreds,
                {_r('bat.ducks')}                                        AS ducks,
                {_r('bat.fours')}                                        AS fours,
                {_r('bat.sixes')}                                        AS sixes,
                {_r('bowl.bowling_innings')}                             AS bowling_innings,
                {_r('bowl.wickets')}                                     AS wickets,
                {_r('bowl.overs')}                                       AS overs,
                {_r('bowl.runs_conceded')}                               AS runs_conceded,
                ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.wickets')}, 0), 2)   AS bowling_average,
                ROUND({_r('bowl.runs_conceded')}::numeric / NULLIF({_r('bowl.overs')} * 6, 0) * 6, 2) AS bowling_economy,
                ROUND({_r('bowl.overs')}::numeric * 6 / NULLIF({_r('bowl.wickets')}, 0), 2)        AS bowling_strike_rate,
                {_r('bowl.five_wicket_innings')}                         AS five_wicket_innings,
                {_r('bowl.maidens')}                                     AS maidens,
                GREATEST(bowl.best_bowling_wickets{', resid.best_bowling_wickets' if residual_ok else ''}) AS best_bowling_wickets,
                {_r('bowl.wides')}    AS wides,
                {_r('bowl.no_balls')} AS no_balls,
                {_r('field.catches')}                                    AS catches,
                {_r('field.catches_wk')}                                 AS catches_wk,
                {_r('field.catches_non_wk')}                             AS catches_non_wk,
                {_r('field.run_outs')}                                   AS run_outs,
                {_r('field.stumpings')}                                  AS stumpings
            FROM appear
            FULL OUTER JOIN bat   ON bat.player_id   = appear.player_id   AND bat.grade_name   = appear.grade_name
            FULL OUTER JOIN bowl  ON bowl.player_id  = COALESCE(appear.player_id, bat.player_id)
                                 AND bowl.grade_name  = COALESCE(appear.grade_name, bat.grade_name)
            FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                                 AND field.grade_name = COALESCE(appear.grade_name, bat.grade_name, bowl.grade_name)
            {resid_join}
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
    """

    params["offset"] = offset
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


# ─── Family-aggregate queries ──────────────────────────────────────────────────
# One row per family (or per family+season / family+grade). Stats are summed
# across every member of the family; averages and rate stats are re-derived
# from the family-level sums so e.g. "Family batting average" treats the whole
# family as one combined career, which is what users intuitively expect.
#
# Players that aren't in any family don't appear in these reports (the JOIN is
# inner). The family_id context filter is ignored here — every row is a
# different family by construction, so filtering to one family would just
# return that one row, which the existing player_career + family_id filter
# already covers.
#
# member_count and members are family-shaped columns that aren't in
# PLAYER_AGG_METRICS; they always come through regardless of metric filters.

# Family-aggregate SUM/derivation SQL shared by all three targets. Takes the
# group_cols / select_extra / join_extra / order_extra placeholders that
# differentiate career / season / grade.
def _family_agg_select_cols() -> str:
    return """
        f.id::text                                                                              AS family_id,
        f.name                                                                                  AS family_name,
        COUNT(DISTINCT p.id)                                                                    AS member_count,
        STRING_AGG(DISTINCT COALESCE(p.display_name_override, p.name), ', '
                   ORDER BY COALESCE(p.display_name_override, p.name))                          AS members,
        COUNT(DISTINCT pss.season_id)                                                           AS seasons_played,
        COALESCE(SUM(pss.matches), 0)                                                           AS matches,
        COALESCE(SUM(pss.batting_innings), 0)                                                   AS batting_innings,
        COALESCE(SUM(pss.runs), 0)                                                              AS runs,
        COALESCE(SUM(pss.not_outs), 0)                                                          AS not_outs,
        COALESCE(SUM(pss.balls_faced), 0)                                                       AS balls_faced,
        ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS batting_average,
        ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2)                AS batting_strike_rate,
        MAX(pss.high_score)                                                                     AS high_score,
        COALESCE(SUM(pss.fifties), 0)                                                           AS fifties,
        COALESCE(SUM(pss.hundreds), 0)                                                          AS hundreds,
        COALESCE(SUM(pss.ducks), 0)                                                             AS ducks,
        COALESCE(SUM(pss.fours), 0)                                                             AS fours,
        COALESCE(SUM(pss.sixes), 0)                                                             AS sixes,
        COALESCE(SUM(pss.bowling_innings), 0)                                                   AS bowling_innings,
        COALESCE(SUM(pss.wickets), 0)                                                           AS wickets,
        COALESCE(SUM(pss.overs), 0)                                                             AS overs,
        COALESCE(SUM(pss.runs_conceded), 0)                                                     AS runs_conceded,
        ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2)                 AS bowling_average,
        ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2)       AS bowling_economy,
        ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 2)                 AS bowling_strike_rate,
        COALESCE(SUM(pss.five_wicket_innings), 0)                                               AS five_wicket_innings,
        COALESCE(SUM(pss.maidens), 0)                                                           AS maidens,
        MAX(pss.best_bowling_wickets)                                                           AS best_bowling_wickets,
        COALESCE(SUM(pss.wides), 0)                                                             AS wides,
        COALESCE(SUM(pss.no_balls), 0)                                                          AS no_balls,
        COALESCE(SUM(pss.catches), 0)                                                           AS catches,
        COALESCE(SUM(pss.catches_wk), 0)                                                         AS catches_wk,
        COALESCE(SUM(pss.catches_non_wk), 0)                                                     AS catches_non_wk,
        COALESCE(SUM(pss.run_outs), 0)                                                          AS run_outs,
        COALESCE(SUM(pss.stumpings), 0)                                                         AS stumpings
    """


async def query_family_career(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    offset: int = 0,
    context: dict,
) -> list[dict]:
    """One row per family — sums of every member's career stats."""
    sort_by, sort_dir, limit = _validated("family_career", sort_by, sort_dir, limit)

    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, FAMILY_AGG_METRICS)
    params = {"org_id": org_id, "limit": limit, "offset": offset, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    select_cols = _family_agg_select_cols()
    # This target sums player_season_stats directly and has no per-game path, so
    # the only scope it can answer is the aggregate one: a category exclusion
    # lands on the rows that carry a grade, and a MATCH TYPE filter empties it
    # (kind='aggregate' emits AND FALSE) rather than inventing a format for a
    # season total. In the join condition, not the WHERE — a family whose every
    # row is out of scope should still list, at zero, rather than disappear.
    scope = _ctx_scope(context)
    scope_clause = _scope_clause_for_join(scope, "pss.grade_id", params)
    sql = f"""
        WITH agg AS (
            SELECT {select_cols}
            FROM families f
            JOIN family_members fm ON fm.family_id = f.id
            JOIN players p ON p.id = fm.player_id
            -- The effective view, not the base table: an imported career/
            -- season delta or manual adjustment only exists as a view branch
            -- (see query_player_career's own note). A career-level residual
            -- has no season_id at all and must still be kept.
            LEFT JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
                -- Only this org's seasons (shared cross-club GUID guard, migration 060)
                AND (pss.season_id IS NULL OR EXISTS (
                    SELECT 1 FROM seasons s
                    WHERE s.id = pss.season_id AND s.organisation_id = :org_id
                )){scope_clause}
            WHERE f.organisation_id = :org_id
            GROUP BY f.id, f.name
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
    """

    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def query_family_season(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    offset: int = 0,
    context: dict,
) -> list[dict]:
    """One row per (family, season). INNER JOIN to pss so a season the family
    didn't play doesn't appear (member_count would be 0 anyway)."""
    sort_by, sort_dir, limit = _validated("family_season", sort_by, sort_dir, limit)

    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, FAMILY_AGG_METRICS)
    params = {"org_id": org_id, "limit": limit, "offset": offset, **metric_params}

    season_filter = _pss_season_filter(context, params, "ctx_fs_")
    # Same aggregate-only scope as family_career above — see its note.
    scope_clause = _scope_clause_for_join(_ctx_scope(context), "pss.grade_id", params)
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    select_cols = _family_agg_select_cols()
    sql = f"""
        WITH agg AS (
            SELECT {select_cols},
                   s.id::text                AS season_id,
                   s.name                    AS season_name,
                   COALESCE(s.year, 0)       AS season_year
            FROM families f
            JOIN family_members fm ON fm.family_id = f.id
            JOIN players p ON p.id = fm.player_id
            -- The effective view: see query_family_career's own note. A
            -- career-level residual has no season_id and is naturally
            -- excluded by the INNER JOIN to seasons below, same as before.
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            JOIN seasons s ON s.id = pss.season_id
            WHERE f.organisation_id = :org_id AND s.organisation_id = :org_id {season_filter}{scope_clause}
            GROUP BY f.id, f.name, s.id, s.name, s.year
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, season_year DESC
        LIMIT :limit OFFSET :offset
    """

    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def query_family_grade(
    session: AsyncSession,
    *,
    org_id: str,
    sort_by: str,
    sort_dir: str,
    limit: int,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    offset: int = 0,
    context: dict,
) -> list[dict]:
    """One row per (family, canonical grade). Lives off the same per-innings
    CTEs as player_grade — pss has no grade dimension. Heavier than the other
    two family queries; that's intrinsic to the per-grade breakdown."""
    sort_by, sort_dir, limit = _validated("family_grade", sort_by, sort_dir, limit)

    mc, mp, ic, ip, pc, pp, _ = _build_context_filters(context)
    metric_clause_sql, metric_params = _compile_metric_clause(metric_filters, filter_tree, FAMILY_AGG_METRICS)
    params = {"org_id": org_id, "limit": limit, "offset": offset, **mp, **ip, **pp, **metric_params}
    where_sql = (f"WHERE {metric_clause_sql}" if metric_clause_sql else "")

    # Reuse the per-player innings CTEs and aggregate them up to family level
    # in an outer GROUP BY. The CTE groups by (player_id, grade_name); we then
    # join to family_members and re-group by (family_id, grade_name).
    cte = _player_agg_innings_cte(
        mc, ic, pc,
        group_cols="p.id, gu.canonical_grade_name, gu.display_grade_name",
        select_cols="p.id AS player_id, gu.canonical_grade_name AS grade_name, gu.display_grade_name,",
    )
    sql = f"""
        {cte},
        per_player AS (
            SELECT
                COALESCE(appear.player_id, bat.player_id, bowl.player_id, field.player_id) AS player_id,
                COALESCE(appear.grade_name, bat.grade_name, bowl.grade_name, field.grade_name) AS grade_name,
                COALESCE(appear.display_grade_name, bat.display_grade_name, bowl.display_grade_name, field.display_grade_name) AS display_grade_name,
                COALESCE(appear.matches, 0)             AS matches,
                COALESCE(bat.batting_innings, 0)        AS batting_innings,
                COALESCE(bat.runs, 0)                   AS runs,
                COALESCE(bat.not_outs, 0)               AS not_outs,
                COALESCE(bat.balls_faced, 0)            AS balls_faced,
                COALESCE(bat.high_score, 0)             AS high_score,
                COALESCE(bat.fifties, 0)                AS fifties,
                COALESCE(bat.hundreds, 0)               AS hundreds,
                COALESCE(bat.ducks, 0)                  AS ducks,
                COALESCE(bat.fours, 0)                  AS fours,
                COALESCE(bat.sixes, 0)                  AS sixes,
                COALESCE(bowl.bowling_innings, 0)       AS bowling_innings,
                COALESCE(bowl.wickets, 0)               AS wickets,
                COALESCE(bowl.overs, 0)                 AS overs,
                COALESCE(bowl.runs_conceded, 0)         AS runs_conceded,
                COALESCE(bowl.five_wicket_innings, 0)   AS five_wicket_innings,
                COALESCE(bowl.maidens, 0)               AS maidens,
                COALESCE(bowl.best_bowling_wickets, 0)  AS best_bowling_wickets,
                COALESCE(bowl.wides, 0)                 AS wides,
                COALESCE(bowl.no_balls, 0)              AS no_balls,
                COALESCE(field.catches, 0)              AS catches,
                COALESCE(field.catches_wk, 0)           AS catches_wk,
                COALESCE(field.catches_non_wk, 0)       AS catches_non_wk,
                COALESCE(field.run_outs, 0)             AS run_outs,
                COALESCE(field.stumpings, 0)            AS stumpings
            FROM appear
            FULL OUTER JOIN bat   ON bat.player_id   = appear.player_id   AND bat.grade_name   = appear.grade_name
            FULL OUTER JOIN bowl  ON bowl.player_id  = COALESCE(appear.player_id, bat.player_id)
                                 AND bowl.grade_name  = COALESCE(appear.grade_name, bat.grade_name)
            FULL OUTER JOIN field ON field.player_id = COALESCE(appear.player_id, bat.player_id, bowl.player_id)
                                 AND field.grade_name = COALESCE(appear.grade_name, bat.grade_name, bowl.grade_name)
        ),
        agg AS (
            SELECT
                f.id::text                                                                      AS family_id,
                f.name                                                                          AS family_name,
                pp.grade_name,
                pp.display_grade_name,
                COUNT(DISTINCT p.id)                                                            AS member_count,
                STRING_AGG(DISTINCT COALESCE(p.display_name_override, p.name), ', '
                           ORDER BY COALESCE(p.display_name_override, p.name))                  AS members,
                1                                                                               AS seasons_played,
                COALESCE(SUM(pp.matches), 0)                                                    AS matches,
                COALESCE(SUM(pp.batting_innings), 0)                                            AS batting_innings,
                COALESCE(SUM(pp.runs), 0)                                                       AS runs,
                COALESCE(SUM(pp.not_outs), 0)                                                   AS not_outs,
                COALESCE(SUM(pp.balls_faced), 0)                                                AS balls_faced,
                ROUND(SUM(pp.runs)::numeric / NULLIF(SUM(pp.batting_innings) - SUM(pp.not_outs), 0), 2) AS batting_average,
                ROUND(SUM(pp.runs)::numeric / NULLIF(SUM(pp.balls_faced), 0) * 100, 2)          AS batting_strike_rate,
                MAX(pp.high_score)                                                              AS high_score,
                COALESCE(SUM(pp.fifties), 0)                                                    AS fifties,
                COALESCE(SUM(pp.hundreds), 0)                                                   AS hundreds,
                COALESCE(SUM(pp.ducks), 0)                                                      AS ducks,
                COALESCE(SUM(pp.fours), 0)                                                      AS fours,
                COALESCE(SUM(pp.sixes), 0)                                                      AS sixes,
                COALESCE(SUM(pp.bowling_innings), 0)                                            AS bowling_innings,
                COALESCE(SUM(pp.wickets), 0)                                                    AS wickets,
                COALESCE(SUM(pp.overs), 0)                                                      AS overs,
                COALESCE(SUM(pp.runs_conceded), 0)                                              AS runs_conceded,
                ROUND(SUM(pp.runs_conceded)::numeric / NULLIF(SUM(pp.wickets), 0), 2)           AS bowling_average,
                ROUND(SUM(pp.runs_conceded)::numeric / NULLIF(SUM(pp.overs * 6), 0) * 6, 2)     AS bowling_economy,
                ROUND(SUM(pp.overs)::numeric * 6 / NULLIF(SUM(pp.wickets), 0), 2)               AS bowling_strike_rate,
                COALESCE(SUM(pp.five_wicket_innings), 0)                                        AS five_wicket_innings,
                COALESCE(SUM(pp.maidens), 0)                                                    AS maidens,
                MAX(pp.best_bowling_wickets)                                                    AS best_bowling_wickets,
                COALESCE(SUM(pp.wides), 0)                                                      AS wides,
                COALESCE(SUM(pp.no_balls), 0)                                                   AS no_balls,
                COALESCE(SUM(pp.catches), 0)                                                    AS catches,
                COALESCE(SUM(pp.catches_wk), 0)                                                  AS catches_wk,
                COALESCE(SUM(pp.catches_non_wk), 0)                                              AS catches_non_wk,
                COALESCE(SUM(pp.run_outs), 0)                                                   AS run_outs,
                COALESCE(SUM(pp.stumpings), 0)                                                  AS stumpings
            FROM per_player pp
            JOIN players p ON p.id = pp.player_id
            JOIN family_members fm ON fm.player_id = p.id
            JOIN families f ON f.id = fm.family_id AND f.organisation_id = :org_id
            GROUP BY f.id, f.name, pp.grade_name, pp.display_grade_name
        )
        SELECT * FROM agg
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST
        LIMIT :limit OFFSET :offset
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
    offset: int = 0,
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """

    params["offset"] = offset
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
    offset: int = 0,
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
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, played_at DESC
        LIMIT :limit OFFSET :offset
    """

    params["offset"] = offset
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
    offset: int = 0,
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
            LEFT JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            LEFT JOIN players p ON p.id = bi.player_id AND p.organisation_id = :org_id
            GROUP BY gu.game_id
        ),
        bowl_scores AS (
            SELECT
                gu.game_id,
                COALESCE(SUM(bs.runs)    FILTER (WHERE pb.id IS NOT NULL), 0) AS opp_runs,
                COALESCE(SUM(bs.wickets) FILTER (WHERE pb.id IS NOT NULL), 0) AS opp_wickets
            FROM game_universe gu
            LEFT JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """

    params["offset"] = offset
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
    offset: int = 0,
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
            JOIN v_effective_partnerships pt ON pt.game_id = gu.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND (p1.organisation_id = :org_id OR p2.organisation_id = :org_id)
        )
        SELECT * FROM rows
        {where_sql}
        ORDER BY {sort_by} {sort_dir} NULLS LAST, runs DESC
        LIMIT :limit OFFSET :offset
    """

    params["offset"] = offset
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


# ─── Derived / streak queries ──────────────────────────────────────────────────

async def derived_consecutive_ducks(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_consecutive_fifties(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_best_partnership_pair(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            JOIN v_effective_partnerships pt ON pt.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(_inline_helpers(sql)), params)
    return [dict(r) for r in result.mappings()]


async def derived_carried_bat(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_runs_first_n(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            LEFT JOIN v_effective_batting_innings bi
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_milestone_runs(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
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
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
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
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Per-match aggregates ──────────────────────────────────────────────────────
# Most X in a single match — sum across both innings of a game and rank.
# Each function follows the same pattern: build game_universe, group by
# (player, game), order by the target metric desc.

async def derived_most_runs_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Highest (player, match) batting aggregates — sums across both innings."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                SUM(COALESCE(bi.runs, 0))::int            AS runs,
                SUM(COALESCE(bi.balls, 0))::int           AS balls,
                COUNT(*)                                  AS innings_count
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY runs DESC, balls ASC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_sixes_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most sixes by one player in a single match (across both innings)."""
    return await _per_match_batting_metric(session, org_id=org_id, limit=limit, offset=offset, context=context, metric_col="sixes")


async def derived_most_fours_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most fours by one player in a single match."""
    return await _per_match_batting_metric(session, org_id=org_id, limit=limit, offset=offset, context=context, metric_col="fours")


async def derived_most_boundaries_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most boundaries (4s + 6s) by one player in a single match."""
    return await _per_match_batting_metric(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                            metric_col="(COALESCE(bi.fours,0)+COALESCE(bi.sixes,0))", metric_label="boundaries")


async def _per_match_batting_metric(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, metric_col: str, metric_label: str | None = None,
) -> list[dict]:
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    label = metric_label or metric_col
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                SUM({metric_col})::int                    AS {label}
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
            HAVING SUM({metric_col}) > 0
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY {label} DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_best_bowling_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Best bowling figures in a single match — combined wickets, total runs conceded."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bs.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                SUM(COALESCE(bs.wickets, 0))::int         AS wickets,
                SUM(COALESCE(bs.runs, 0))::int            AS runs,
                SUM(COALESCE(bs.overs, 0))::numeric       AS overs
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY bs.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
            HAVING SUM(COALESCE(bs.wickets, 0)) > 0
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY wickets DESC, runs ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_wickets_in_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Same data as best_bowling_in_match but sorted by wickets only."""
    return await derived_best_bowling_in_match(session, org_id=org_id, limit=limit, offset=offset, context=context)


async def derived_most_balls_bowled_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most balls bowled by one player in a single match."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bs.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                SUM(COALESCE(bs.overs, 0))::numeric       AS overs,
                ROUND(SUM(COALESCE(bs.overs, 0) * 6))::int AS balls_bowled
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY bs.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
        )
        SELECT player_id::text AS player_id, * FROM per_match
        WHERE balls_bowled > 0
        ORDER BY balls_bowled DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def _per_match_fielding_metric(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, col: str, label: str,
) -> list[dict]:
    """Highest single-match values of catches / run_outs / stumpings."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                fs.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                COALESCE(fs.{col}, 0)::int                AS {label}
            FROM game_universe gu
            JOIN v_effective_fielding_stats fs ON fs.game_id = gu.game_id
            JOIN players p ON p.id = fs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND COALESCE(fs.{col}, 0) > 0
              {player_extra}
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY {label} DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_catches_in_match(session, *, org_id, limit, offset=0, context):
    return await _per_match_fielding_metric(session, org_id=org_id, limit=limit, offset=offset, context=context, col="catches", label="catches")


async def derived_most_stumpings_in_match(session, *, org_id, limit, offset=0, context):
    return await _per_match_fielding_metric(session, org_id=org_id, limit=limit, offset=offset, context=context, col="stumpings", label="stumpings")


async def derived_most_run_outs_in_match(session, *, org_id, limit, offset=0, context):
    return await _per_match_fielding_metric(session, org_id=org_id, limit=limit, offset=offset, context=context, col="run_outs", label="run_outs")


# ─── Duck variants ─────────────────────────────────────────────────────────────

async def derived_golden_ducks(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Out for 0 off the first ball (golden duck) — count per player.
    Requires balls = 1; balls = 0 is the API's 'not tracked' default."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        ducks AS (
            SELECT bi.player_id, COALESCE(p.display_name_override, p.name) AS player_name
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.runs = 0
              AND bi.not_out = FALSE
              AND bi.did_not_bat IS NOT TRUE
              AND bi.balls = 1
              AND bi.dismissal_type IS NOT NULL
              AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
        )
        SELECT
            player_id::text AS player_id,
            player_name,
            COUNT(*)::int AS golden_ducks
        FROM ducks
        GROUP BY player_id, player_name
        ORDER BY golden_ducks DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_duck_pairs(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players who scored a duck in BOTH innings of the same match — count per player."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match_ducks AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id,
                COUNT(*) FILTER (
                    WHERE bi.runs = 0
                      AND bi.not_out = FALSE
                      AND bi.did_not_bat IS NOT TRUE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                ) AS ducks_in_match
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name), gu.game_id
            HAVING COUNT(*) FILTER (
                WHERE bi.runs = 0
                  AND bi.not_out = FALSE
                  AND bi.did_not_bat IS NOT TRUE
                  AND bi.dismissal_type IS NOT NULL
                  AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
            ) >= 2
        )
        SELECT
            player_id::text AS player_id,
            player_name,
            COUNT(*)::int AS duck_pairs
        FROM per_match_ducks
        GROUP BY player_id, player_name
        ORDER BY duck_pairs DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_consecutive_no_duck(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Longest run of consecutive innings without being dismissed for a duck."""
    return await _longest_streak(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                  is_match_expr=(
                                      "(bi.runs > 0 OR bi.not_out = TRUE OR "
                                      "bi.dismissal_type IS NULL OR "
                                      "LOWER(bi.dismissal_type) IN ('absent', 'did not bat', 'dnb'))"
                                  ),
                                  result_col="longest_no_duck_streak")


# ─── Streak helpers ────────────────────────────────────────────────────────────

async def _longest_streak(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, is_match_expr: str, result_col: str,
) -> list[dict]:
    """Generic longest-streak-of-innings helper. is_match_expr is a SQL bool
    expression evaluated per batting_innings row inside the streak CTE."""
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
                CASE WHEN {is_match_expr} THEN 1 ELSE 0 END AS is_match,
                ROW_NUMBER() OVER (PARTITION BY bi.player_id ORDER BY gu.played_at, bi.innings_number, bi.id) AS rn
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
        ),
        grp AS (
            SELECT player_id, player_name, rn, is_match,
                   rn - SUM(is_match) OVER (PARTITION BY player_id ORDER BY rn) AS streak_grp
            FROM seq
        ),
        streaks AS (
            SELECT player_id, player_name, streak_grp, SUM(is_match) AS streak_len
            FROM grp
            WHERE is_match = 1
            GROUP BY player_id, player_name, streak_grp
        ),
        best AS (
            SELECT player_id::text AS player_id, player_name, MAX(streak_len)::int AS {result_col}
            FROM streaks
            GROUP BY player_id, player_name
        )
        SELECT * FROM best
        WHERE {result_col} >= 2
        ORDER BY {result_col} DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_consecutive_no_century(
    session, *, org_id, limit, offset=0, context,
) -> list[dict]:
    """Longest streak of innings scoring under 100."""
    return await _longest_streak(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                  is_match_expr="bi.runs < 100", result_col="longest_no_century_streak")


async def derived_consecutive_hundreds(
    session, *, org_id, limit, offset=0, context,
) -> list[dict]:
    """Longest streak of innings scoring 100+."""
    return await _longest_streak(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                  is_match_expr="bi.runs >= 100", result_col="longest_hundred_streak")


# ─── Bowling streaks ───────────────────────────────────────────────────────────

async def _longest_bowling_streak(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, is_match_expr: str, result_col: str,
) -> list[dict]:
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 200), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        seq AS (
            SELECT
                bs.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                CASE WHEN {is_match_expr} THEN 1 ELSE 0 END AS is_match,
                ROW_NUMBER() OVER (PARTITION BY bs.player_id ORDER BY gu.played_at, bs.innings_number, bs.id) AS rn
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
        ),
        grp AS (
            SELECT player_id, player_name, rn, is_match,
                   rn - SUM(is_match) OVER (PARTITION BY player_id ORDER BY rn) AS streak_grp
            FROM seq
        ),
        streaks AS (
            SELECT player_id, player_name, streak_grp, SUM(is_match) AS streak_len
            FROM grp
            WHERE is_match = 1
            GROUP BY player_id, player_name, streak_grp
        ),
        best AS (
            SELECT player_id::text AS player_id, player_name, MAX(streak_len)::int AS {result_col}
            FROM streaks
            GROUP BY player_id, player_name
        )
        SELECT * FROM best
        WHERE {result_col} >= 2
        ORDER BY {result_col} DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_consecutive_innings_with_wicket(session, *, org_id, limit, offset=0, context):
    """Longest streak of bowling innings (spells) where player took 1+ wicket."""
    return await _longest_bowling_streak(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                          is_match_expr="COALESCE(bs.wickets, 0) >= 1",
                                          result_col="longest_wicket_streak")


async def derived_consecutive_5wi(session, *, org_id, limit, offset=0, context):
    """Longest streak of bowling innings with 5+ wickets."""
    return await _longest_bowling_streak(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                          is_match_expr="COALESCE(bs.wickets, 0) >= 5",
                                          result_col="longest_5wi_streak")


# ─── Debut performances ────────────────────────────────────────────────────────

async def derived_batting_on_debut(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Best score in a player's debut match (sum across both innings of that match)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        debut_match AS (
            SELECT DISTINCT ON (gap.player_id)
                gap.player_id,
                gu.game_id,
                gu.played_at,
                gu.display_grade_name AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END AS opposition
            FROM game_universe gu
            JOIN game_appearances gap ON gap.game_id = gu.game_id
            JOIN players p ON p.id = gap.player_id
            WHERE p.organisation_id = :org_id {player_extra}
            ORDER BY gap.player_id, gu.played_at, gu.game_id
        ),
        debut_runs AS (
            SELECT
                dm.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                dm.game_id::text                          AS game_id,
                dm.played_at,
                dm.grade_name,
                dm.opposition,
                COALESCE(SUM(bi.runs), 0)::int            AS runs,
                COALESCE(SUM(bi.balls), 0)::int           AS balls
            FROM debut_match dm
            JOIN players p ON p.id = dm.player_id
            LEFT JOIN v_effective_batting_innings bi
                   ON bi.game_id = dm.game_id AND bi.player_id = dm.player_id
                  AND bi.did_not_bat IS NOT TRUE
            GROUP BY dm.player_id, COALESCE(p.display_name_override, p.name),
                     dm.game_id, dm.played_at, dm.grade_name, dm.opposition
        )
        SELECT player_id::text AS player_id, * FROM debut_runs
        ORDER BY runs DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_ducks_on_debut(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players whose debut batting innings was a duck."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        first_inn AS (
            SELECT DISTINCT ON (bi.player_id)
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                bi.runs,
                bi.balls,
                bi.not_out,
                bi.dismissal_type
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
            ORDER BY bi.player_id, gu.played_at, bi.innings_number, bi.id
        )
        SELECT player_id::text AS player_id, * FROM first_inn
        WHERE runs = 0 AND not_out = FALSE
        ORDER BY played_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_bowling_on_debut_innings(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Best bowling figures in a player's debut spell."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        first_spell AS (
            SELECT DISTINCT ON (bs.player_id)
                bs.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                COALESCE(bs.wickets, 0)::int              AS wickets,
                COALESCE(bs.runs, 0)::int                 AS runs,
                COALESCE(bs.overs, 0)::numeric            AS overs
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            ORDER BY bs.player_id, gu.played_at, bs.innings_number, bs.id
        )
        SELECT player_id::text AS player_id, * FROM first_spell
        ORDER BY wickets DESC, runs ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Dismissal-type counts ─────────────────────────────────────────────────────

async def _dismissal_count(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, like_patterns: list[str], result_col: str,
) -> list[dict]:
    """Generic dismissal-type counter — counts batting_innings rows where
    LOWER(dismissal_type) matches any of the LIKE patterns."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    pattern_clause = " OR ".join([f"LOWER(bi.dismissal_type) LIKE :dp_{i}" for i in range(len(like_patterns))])
    for i, p in enumerate(like_patterns):
        params[f"dp_{i}"] = p
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        counts AS (
            SELECT
                bi.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*)::int AS {result_col}
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND ({pattern_clause})
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM counts
        WHERE {result_col} > 0
        ORDER BY {result_col} DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# Dismissal-type patterns must match what's actually stored. Grassroots sync
# canonicalises dismissal_type to bare short forms ('b', 'c', 'st', 'lbw',
# 'run out', etc.) via _GR_DISMISSAL_SHORT in sync.py — so each pattern set
# includes both the bare short form and the long form for resilience against
# any older / non-GR rows. See aggregations.py:_dismissal_breakdown for the
# canonical matcher used elsewhere.

async def derived_dismissal_bowled(session, *, org_id, limit, offset=0, context):
    return await _dismissal_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                   like_patterns=["b", "b %", "b. %", "bowled", "bowled%"], result_col="bowled_count")


async def derived_dismissal_caught(session, *, org_id, limit, offset=0, context):
    return await _dismissal_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                   like_patterns=["c", "c %", "c. %", "ct%", "caught", "caught%"], result_col="caught_count")


async def derived_dismissal_caught_behind(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players most often caught behind (caught by the wicketkeeper). Uses the
    stored caught_behind flag — the keeper-catch subset of 'caught'. Only the
    games where the scorecard records who kept are attributable, so this is a
    floor (see the caught-behind footnote on player profiles)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), "offset": offset, **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        counts AS (
            SELECT
                bi.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*)::int AS caught_behind_count
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND bi.caught_behind IS TRUE
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM counts
        WHERE caught_behind_count > 0
        ORDER BY caught_behind_count DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_dismissal_lbw(session, *, org_id, limit, offset=0, context):
    return await _dismissal_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                   like_patterns=["lbw", "lbw %", "lbw%", "leg before wicket%"], result_col="lbw_count")


async def derived_dismissal_run_out(session, *, org_id, limit, offset=0, context):
    return await _dismissal_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                   like_patterns=["run out", "run out%", "ro", "ro%"], result_col="run_out_count")


async def derived_dismissal_stumped(session, *, org_id, limit, offset=0, context):
    return await _dismissal_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                   like_patterns=["st", "st %", "st. %", "stumped", "stumped%"], result_col="stumped_count")


async def derived_unusual_dismissals(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Innings dismissed by uncommon means (hit wicket, retired hurt, handled, obstructing).
    'Retired not out' is excluded — it's a routine voluntary retirement, not unusual."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bi.player_id::text AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            gu.game_id::text                          AS game_id,
            gu.played_at                              AS played_at,
            gu.display_grade_name                     AS grade_name,
            CASE
                WHEN gu.club_team = gu.home_team THEN gu.away_team
                WHEN gu.club_team = gu.away_team THEN gu.home_team
                ELSE NULL
            END                                       AS opposition,
            bi.runs::int                              AS runs,
            bi.dismissal_type                         AS dismissal_type
        FROM game_universe gu
        JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
        JOIN players p ON p.id = bi.player_id
        LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND bi.did_not_bat IS NOT TRUE
          AND bi.dismissal_type IS NOT NULL
          AND (
            LOWER(bi.dismissal_type) LIKE 'hit wicket%'
            OR LOWER(bi.dismissal_type) LIKE 'retired hurt%'
            OR LOWER(bi.dismissal_type) LIKE 'retired out%'
            OR LOWER(bi.dismissal_type) LIKE 'handled%'
            OR LOWER(bi.dismissal_type) LIKE 'obstruct%'
            OR LOWER(bi.dismissal_type) LIKE 'timed out%'
            OR LOWER(bi.dismissal_type) LIKE 'hit ball twice%'
          )
          AND LOWER(bi.dismissal_type) NOT LIKE 'retired not out%'
          {player_extra}
        ORDER BY gu.played_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Century / fifty derived ───────────────────────────────────────────────────

async def derived_century_and_duck_same_match(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players who scored a 100 and a duck in the same match."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                MAX(bi.runs)::int                         AS top_score,
                MIN(bi.runs)::int                         AS low_score,
                COUNT(*) FILTER (
                    WHERE bi.runs = 0 AND bi.not_out = FALSE AND bi.did_not_bat IS NOT TRUE
                      AND bi.dismissal_type IS NOT NULL
                      AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
                ) AS duck_count,
                COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundred_count
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
            HAVING COUNT(*) FILTER (
                WHERE bi.runs = 0 AND bi.not_out = FALSE AND bi.did_not_bat IS NOT TRUE
                  AND bi.dismissal_type IS NOT NULL
                  AND LOWER(bi.dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')
            ) >= 1 AND COUNT(*) FILTER (WHERE bi.runs >= 100) >= 1
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY top_score DESC, played_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_century_each_innings(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Player scored 100+ in both innings of the same match."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        per_match AS (
            SELECT
                bi.player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                MAX(bi.runs)::int                         AS top_score,
                SUM(bi.runs)::int                         AS match_runs,
                COUNT(*) FILTER (WHERE bi.runs >= 100)    AS hundreds_count
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name),
                     gu.game_id, gu.played_at, gu.display_grade_name,
                     gu.club_team, gu.home_team, gu.away_team
            HAVING COUNT(*) FILTER (WHERE bi.runs >= 100) >= 2
        )
        SELECT player_id::text AS player_id, * FROM per_match
        ORDER BY match_runs DESC, played_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_innings_without_century(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players with most innings who've never scored a century, ranked by inns count."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        agg AS (
            SELECT
                bi.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*)::int AS innings_played,
                MAX(bi.runs)::int AS top_score,
                COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM agg
        WHERE hundreds = 0
        ORDER BY innings_played DESC, top_score DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_lowest_century_conversion(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players with the lowest fifty→hundred conversion rate (must have 5+ fifties)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        agg AS (
            SELECT
                bi.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100)::int AS fifties,
                COUNT(*) FILTER (WHERE bi.runs >= 100)::int                   AS hundreds
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT
            player_id, player_name, fifties, hundreds,
            ROUND(100.0 * hundreds / NULLIF(fifties + hundreds, 0), 1) AS conversion_pct
        FROM agg
        WHERE (fifties + hundreds) >= 5
        ORDER BY conversion_pct ASC NULLS FIRST, fifties DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_innings_per_fifty(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Lowest innings-per-50 ratio (lower = more frequent 50s)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        agg AS (
            SELECT
                bi.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*)::int AS innings_played,
                COUNT(*) FILTER (WHERE bi.runs >= 50)::int AS fifty_plus
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
              {player_extra}
            GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT
            player_id, player_name, innings_played, fifty_plus,
            ROUND(innings_played::numeric / NULLIF(fifty_plus, 0), 2) AS innings_per_fifty
        FROM agg
        WHERE fifty_plus >= 5
        ORDER BY innings_per_fifty ASC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Partnership derived ───────────────────────────────────────────────────────

async def derived_top_partnerships_by_wicket(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Best partnership at each wicket position (1st wicket … 10th wicket)."""
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        ranked AS (
            SELECT
                pt.wicket_number,
                pt.runs::int                                          AS runs,
                pt.batter1_id::text                                   AS player_a_id,
                COALESCE(p1.display_name_override, p1.name)           AS player_a_name,
                pt.batter2_id::text                                   AS player_b_id,
                COALESCE(p2.display_name_override, p2.name)           AS player_b_name,
                gu.game_id::text                                      AS game_id,
                gu.played_at                                          AS played_at,
                gu.display_grade_name                                 AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                                   AS opposition,
                ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rk
            FROM game_universe gu
            JOIN v_effective_partnerships pt ON pt.game_id = gu.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND pt.wicket_number BETWEEN 1 AND 10
              AND (p1.organisation_id = :org_id OR p2.organisation_id = :org_id)
        )
        SELECT * FROM ranked WHERE rk = 1
        ORDER BY wicket_number ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_partnership_aggregates_pair(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Total partnership runs for each pair of batters across all their matches."""
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        pairs AS (
            SELECT
                LEAST(pt.batter1_id, pt.batter2_id)    AS player_a_id,
                GREATEST(pt.batter1_id, pt.batter2_id) AS player_b_id,
                pt.runs::int                            AS runs
            FROM game_universe gu
            JOIN v_effective_partnerships pt ON pt.game_id = gu.game_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND pt.batter1_id IS NOT NULL AND pt.batter2_id IS NOT NULL
        ),
        agg AS (
            SELECT
                player_a_id, player_b_id,
                SUM(runs)::int   AS total_runs,
                COUNT(*)::int    AS partnerships,
                MAX(runs)::int   AS best_partnership
            FROM pairs
            GROUP BY player_a_id, player_b_id
        )
        SELECT
            pa.id::text   AS player_a_id,
            COALESCE(pa.display_name_override, pa.name) AS player_a_name,
            pb.id::text   AS player_b_id,
            COALESCE(pb.display_name_override, pb.name) AS player_b_name,
            agg.total_runs, agg.partnerships, agg.best_partnership
        FROM agg
        JOIN players pa ON pa.id = agg.player_a_id
        JOIN players pb ON pb.id = agg.player_b_id
        WHERE pa.organisation_id = :org_id
        ORDER BY agg.total_runs DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_century_partnerships_pair(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Number of 100+ partnerships per pair of batters."""
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        pairs AS (
            SELECT
                LEAST(pt.batter1_id, pt.batter2_id)    AS player_a_id,
                GREATEST(pt.batter1_id, pt.batter2_id) AS player_b_id,
                pt.runs::int                            AS runs
            FROM game_universe gu
            JOIN v_effective_partnerships pt ON pt.game_id = gu.game_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND pt.batter1_id IS NOT NULL AND pt.batter2_id IS NOT NULL
              AND pt.runs >= 100
        ),
        agg AS (
            SELECT player_a_id, player_b_id,
                   COUNT(*)::int AS century_partnerships,
                   MAX(runs)::int AS best_partnership
            FROM pairs
            GROUP BY player_a_id, player_b_id
        )
        SELECT
            pa.id::text   AS player_a_id,
            COALESCE(pa.display_name_override, pa.name) AS player_a_name,
            pb.id::text   AS player_b_id,
            COALESCE(pb.display_name_override, pb.name) AS player_b_name,
            agg.century_partnerships, agg.best_partnership
        FROM agg
        JOIN players pa ON pa.id = agg.player_a_id
        JOIN players pb ON pb.id = agg.player_b_id
        WHERE pa.organisation_id = :org_id
        ORDER BY agg.century_partnerships DESC, agg.best_partnership DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Batting position ──────────────────────────────────────────────────────────

async def derived_top_scores_by_position(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Top individual scores at each batting position (1-11)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        ranked AS (
            SELECT
                bi.batting_position::int                  AS batting_position,
                bi.player_id::text                        AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                bi.runs::int                              AS runs,
                bi.balls::int                             AS balls,
                bi.not_out                                AS not_out,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                ROW_NUMBER() OVER (PARTITION BY bi.batting_position ORDER BY bi.runs DESC) AS rk
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND bi.batting_position BETWEEN 1 AND 11
              {player_extra}
        )
        SELECT * FROM ranked WHERE rk = 1
        ORDER BY batting_position ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Opening bat & bowl same match ─────────────────────────────────────────────

async def derived_opening_bat_and_bowl(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Players who batted at #1 or #2 AND took the new ball (bowled in innings #1, first spell)
    in the same match."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        openers_bat AS (
            SELECT DISTINCT bi.player_id, bi.game_id
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.batting_position IN (1, 2)
              {player_extra}
        ),
        opening_bowlers AS (
            SELECT DISTINCT bs.player_id, bs.game_id
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
              AND bs.innings_number IN (1, 2)
            JOIN players p ON p.id = bs.player_id
            WHERE p.organisation_id = :org_id
        ),
        both AS (
            SELECT ob.player_id, ob.game_id
            FROM openers_bat ob
            JOIN opening_bowlers obw ON obw.player_id = ob.player_id AND obw.game_id = ob.game_id
        ),
        per_player AS (
            SELECT player_id::text AS player_id,
                   COALESCE(p.display_name_override, p.name) AS player_name,
                   COUNT(*)::int AS occurrences
            FROM both b
            JOIN players p ON p.id = b.player_id
            GROUP BY b.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM per_player
        ORDER BY occurrences DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Top scores as % of innings total ──────────────────────────────────────────

async def derived_top_scores_pct_innings(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Individual scores expressed as a % of the club innings total in which they were made."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        innings_totals AS (
            SELECT
                bi.game_id,
                bi.innings_number,
                SUM(bi.runs) AS team_innings_total
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
            GROUP BY bi.game_id, bi.innings_number
        ),
        rows AS (
            SELECT
                bi.player_id::text                        AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                bi.runs::int                              AS runs,
                it.team_innings_total::int                AS team_innings_total,
                ROUND(100.0 * bi.runs / NULLIF(it.team_innings_total, 0), 1) AS pct_of_innings,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition
            FROM game_universe gu
            JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
            JOIN players p ON p.id = bi.player_id
            JOIN innings_totals it ON it.game_id = bi.game_id AND it.innings_number = bi.innings_number
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bi.did_not_bat IS NOT TRUE
              AND it.team_innings_total >= 50
              {player_extra}
        )
        SELECT * FROM rows
        WHERE pct_of_innings IS NOT NULL
        ORDER BY pct_of_innings DESC, runs DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Catches + stumpings combined ──────────────────────────────────────────────

async def derived_catches_stumpings(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Career catches + stumpings combined (typical wicketkeeper / fielder metric)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        agg AS (
            SELECT
                fs.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COALESCE(SUM(fs.catches), 0)::int   AS catches,
                COALESCE(SUM(fs.stumpings), 0)::int AS stumpings,
                COALESCE(SUM(fs.run_outs), 0)::int  AS run_outs,
                COALESCE(SUM(fs.catches) + SUM(fs.stumpings), 0)::int AS catches_stumpings
            FROM game_universe gu
            JOIN v_effective_fielding_stats fs ON fs.game_id = gu.game_id
            JOIN players p ON p.id = fs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id {player_extra}
            GROUP BY fs.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM agg
        WHERE catches_stumpings > 0
        ORDER BY catches_stumpings DESC, catches DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Bowler-wickets driven derived ─────────────────────────────────────────────

async def derived_ducks_inflicted(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Count of times each bowler dismissed a batter for 0.

    Reads from bowler_wickets.batter_runs (denormalised during sync) so we
    can count opposition batters' scores — we don't store opposition
    batting in batting_innings. Rows synced before migration 033 have
    batter_runs = NULL and are excluded until the next Full Rebuild
    repopulates them."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc).replace("gap.", "gap_b.")) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bw.bowler_id::text AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            COUNT(*)::int AS ducks_inflicted
        FROM game_universe gu
        JOIN v_effective_bowler_wickets bw ON bw.game_id = gu.game_id
        JOIN players p ON p.id = bw.bowler_id
        LEFT JOIN game_appearances gap_b ON gap_b.game_id = gu.game_id AND gap_b.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND bw.batter_runs = 0
          {player_extra}
        GROUP BY bw.bowler_id, COALESCE(p.display_name_override, p.name)
        HAVING COUNT(*) > 0
        ORDER BY ducks_inflicted DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_golden_ducks_inflicted(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Same as ducks_inflicted but only first-ball dismissals (golden ducks).
    Requires batter_balls = 1; batter_balls = 0 is the API's 'not tracked' default."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc).replace("gap.", "gap_b.")) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bw.bowler_id::text AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            COUNT(*)::int AS golden_ducks_inflicted
        FROM game_universe gu
        JOIN v_effective_bowler_wickets bw ON bw.game_id = gu.game_id
        JOIN players p ON p.id = bw.bowler_id
        LEFT JOIN game_appearances gap_b ON gap_b.game_id = gu.game_id AND gap_b.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND bw.batter_runs = 0
          AND bw.batter_balls = 1
          {player_extra}
        GROUP BY bw.bowler_id, COALESCE(p.display_name_override, p.name)
        HAVING COUNT(*) > 0
        ORDER BY golden_ducks_inflicted DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_bowler_fielder_combo(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most productive bowler+catcher partnerships — count of caught dismissals
    (WK catches included) where a fielder took a catch off this bowler.
    Only counts caught dismissals; stumpings and run-outs are excluded.
    Data depends on fielder name in dismissalText resolving to a known player."""
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        merge_map AS (
            SELECT DISTINCT ON (m1.removed_player_id)
                   m1.removed_player_id,
                   COALESCE(m2.keep_player_id, m1.keep_player_id) AS canonical_id
            FROM merge_logs m1
            LEFT JOIN merge_logs m2
                   ON m2.removed_player_id = m1.keep_player_id AND m2.undone_at IS NULL
            WHERE m1.undone_at IS NULL
            ORDER BY m1.removed_player_id, m2.keep_player_id NULLS LAST
        ),
        wkts AS (
            SELECT
                COALESCE(mb.canonical_id, bw.bowler_id)  AS bowler_id,
                COALESCE(mf.canonical_id, bw.fielder_id) AS fielder_id
            FROM game_universe gu
            JOIN v_effective_bowler_wickets bw ON bw.game_id = gu.game_id
            JOIN players pb ON pb.id = bw.bowler_id
            LEFT JOIN merge_map mb ON mb.removed_player_id = bw.bowler_id
            LEFT JOIN merge_map mf ON mf.removed_player_id = bw.fielder_id
            WHERE pb.organisation_id = :org_id
              AND bw.fielder_id IS NOT NULL
              AND COALESCE(mf.canonical_id, bw.fielder_id) <>
                  COALESCE(mb.canonical_id, bw.bowler_id)
              AND bw.dismissal_type = 'caught'
        ),
        agg AS (
            SELECT bowler_id, fielder_id, COUNT(*)::int AS catches
            FROM wkts
            GROUP BY bowler_id, fielder_id
        )
        SELECT
            agg.bowler_id::text  AS player_a_id,
            COALESCE(pb.display_name_override, pb.name) AS player_a_name,
            agg.fielder_id::text AS player_b_id,
            COALESCE(pf.display_name_override, pf.name) AS player_b_name,
            agg.catches
        FROM agg
        JOIN players pb ON pb.id = agg.bowler_id
        JOIN players pf ON pf.id = agg.fielder_id
        ORDER BY agg.catches DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_top_opening_bowlers(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Count of games where this player opened the bowling (took the new ball).
    A player is an "opener" for an innings if they have the lowest spell.id among
    all of that innings's spells — proxy for "took the first over"."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe},
        first_spell_per_innings AS (
            SELECT DISTINCT ON (bs.game_id, bs.innings_number)
                bs.game_id, bs.innings_number, bs.player_id
            FROM game_universe gu
            JOIN v_effective_bowling_spells bs ON bs.game_id = gu.game_id
            JOIN players p ON p.id = bs.player_id
            LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
            WHERE p.organisation_id = :org_id
              AND bs.innings_number IS NOT NULL
              {player_extra}
            ORDER BY bs.game_id, bs.innings_number, bs.id
        ),
        agg AS (
            SELECT
                fs.player_id::text AS player_id,
                COALESCE(p.display_name_override, p.name) AS player_name,
                COUNT(*)::int AS opening_innings,
                COUNT(DISTINCT fs.game_id)::int AS opening_matches
            FROM first_spell_per_innings fs
            JOIN players p ON p.id = fs.player_id
            GROUP BY fs.player_id, COALESCE(p.display_name_override, p.name)
        )
        SELECT * FROM agg
        ORDER BY opening_matches DESC, opening_innings DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Hat tricks — sourced from manually-recorded achievements ─────────────────

async def derived_hat_tricks(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Hat tricks from the player_achievements table (manually recorded).
    Each row in the achievements table represents one hat trick instance; group
    by player to get the count per player."""
    params = {"org_id": org_id, "limit": min(max(1, limit), 500)}
    sql = """
        WITH ht AS (
            SELECT
                pa.player_id,
                COALESCE(NULLIF(pa.player_name, ''), '?') AS player_name,
                pa.season,
                pa.detail
            FROM player_achievements pa
            WHERE pa.org_id = CAST(:org_id AS UUID)
              AND (
                LOWER(COALESCE(pa.subcategory, '')) = 'hat tricks'
                OR LOWER(pa.achievement) = 'hat trick'
                OR LOWER(pa.achievement) LIKE 'hat-trick%'
                OR LOWER(pa.achievement) LIKE 'hat trick%'
              )
        )
        SELECT
            COALESCE(player_id::text, MD5(player_name)) AS player_id,
            player_name,
            COUNT(*)::int AS hat_tricks,
            STRING_AGG(DISTINCT NULLIF(season, ''), ', ' ORDER BY NULLIF(season, '')) AS seasons
        FROM ht
        GROUP BY player_id, player_name
        ORDER BY hat_tricks DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── C&B dismissals — separate from generic 'caught' ──────────────────────────
# batting_innings.dismissal_type for a c&b is just 'c' (same as a normal
# catch), so we can't tell c&b apart by querying batting_innings alone.
# bowler_wickets DOES tag c&b canonically as 'caught and bowled', so the
# batter view joins through that table and groups by the dismissed batter.

async def derived_caught_and_bowled(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Count of times each batter was dismissed caught & bowled (batter view)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bi.player_id::text AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            COUNT(DISTINCT (bi.game_id, bi.innings_number, bi.player_id))::int AS c_and_b_count
        FROM game_universe gu
        JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
        JOIN players p ON p.id = bi.player_id
        JOIN v_effective_bowler_wickets bw
          ON bw.game_id = bi.game_id
         AND bw.innings_number = bi.innings_number
         AND LOWER(bw.dismissal_type) IN ('caught and bowled', 'c&b', 'c & b')
         AND (
           (bw.batter_position IS NOT NULL AND bi.batting_position = bw.batter_position)
           OR (bw.batter_position IS NULL
               AND LOWER(TRIM(COALESCE(p.display_name_override, p.name))) = LOWER(TRIM(bw.batter_name)))
         )
        LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND bi.did_not_bat IS NOT TRUE
          {player_extra}
        GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        HAVING COUNT(*) > 0
        ORDER BY c_and_b_count DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_caught_and_bowled_bowler(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Count of caught-and-bowled wickets taken by each bowler (bowler view).
    Uses the bowler_wickets table where dismissal_type was canonicalised to
    'caught and bowled' during sync."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {"org_id": org_id, "limit": min(max(1, limit), 500), **mp, **pp}
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bw.bowler_id::text                        AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            COUNT(*)::int                             AS c_and_b_count
        FROM game_universe gu
        JOIN v_effective_bowler_wickets bw ON bw.game_id = gu.game_id
        JOIN players p ON p.id = bw.bowler_id
        LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND LOWER(bw.dismissal_type) IN ('caught and bowled', 'c&b', 'c & b')
          {player_extra}
        GROUP BY bw.bowler_id, COALESCE(p.display_name_override, p.name)
        ORDER BY c_and_b_count DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


# ─── Batting collapses (fall_of_wickets-based) ────────────────────────────────

async def _wicket_collapse(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict, n_wickets: int, max_run_span: int = 30,
) -> list[dict]:
    """Find matches where N consecutive wickets fell within max_run_span runs.
    Reports one row per (game, innings) where it happened, with the start/end
    wicket numbers and run span.

    Only considers (game, innings) where the fall-of-wicket data is *complete*
    — i.e. the FOW rows form a contiguous run from wicket 1 to max(wicket_number)
    with no gaps. Sparse FOW data would produce false-positive collapses
    (e.g. wickets 1, 5, 6, 7 only would falsely report a 4-wicket collapse from
    1→5 simply because wickets 2, 3, 4 weren't recorded)."""
    mc, mp, _ic, _ip, _pc, pp, _ = _build_context_filters(context)
    params = {
        "org_id": org_id,
        "limit": min(max(1, limit), 500),
        "n_wkts": n_wickets,
        "span": max_run_span,
        **mp, **pp,
    }
    universe = _game_universe_sql(mc)
    sql = f"""
        WITH {universe},
        innings_fow_quality AS (
            -- Treat (game, innings) FOW as "full" when rows are contiguous
            -- from wicket 1 with no gaps (count = max wicket number).
            SELECT
                fw.game_id, fw.innings_number,
                COUNT(*)                       AS rows_recorded,
                MAX(fw.wicket_number)          AS max_wkt,
                MIN(fw.wicket_number)          AS min_wkt
            FROM game_universe gu
            JOIN v_effective_fall_of_wickets fw ON fw.game_id = gu.game_id
            GROUP BY fw.game_id, fw.innings_number
            HAVING MIN(fw.wicket_number) = 1
               AND COUNT(*) = MAX(fw.wicket_number)
               AND MAX(fw.wicket_number) >= :n_wkts
        ),
        fow AS (
            SELECT
                fw.game_id, fw.innings_number, fw.wicket_number,
                fw.score_at_fall,
                LEAD(fw.score_at_fall, :n_wkts - 1) OVER (
                    PARTITION BY fw.game_id, fw.innings_number ORDER BY fw.wicket_number
                ) AS end_score,
                LEAD(fw.wicket_number, :n_wkts - 1) OVER (
                    PARTITION BY fw.game_id, fw.innings_number ORDER BY fw.wicket_number
                ) AS end_wicket
            FROM game_universe gu
            JOIN v_effective_fall_of_wickets fw ON fw.game_id = gu.game_id
            JOIN innings_fow_quality q
              ON q.game_id = fw.game_id AND q.innings_number = fw.innings_number
        ),
        collapses AS (
            SELECT
                gu.game_id::text                          AS game_id,
                gu.played_at                              AS played_at,
                gu.display_grade_name                     AS grade_name,
                CASE
                    WHEN gu.club_team = gu.home_team THEN gu.away_team
                    WHEN gu.club_team = gu.away_team THEN gu.home_team
                    ELSE NULL
                END                                       AS opposition,
                fow.innings_number,
                fow.wicket_number                         AS from_wicket,
                fow.end_wicket                            AS to_wicket,
                fow.score_at_fall                         AS from_score,
                fow.end_score                             AS to_score,
                (fow.end_score - fow.score_at_fall)::int  AS run_span
            FROM fow
            JOIN game_universe gu ON gu.game_id = fow.game_id
            WHERE fow.end_score IS NOT NULL
              AND (fow.end_score - fow.score_at_fall) <= :span
              AND (fow.end_score - fow.score_at_fall) >= 0
              AND fow.end_wicket - fow.wicket_number = :n_wkts - 1
        )
        SELECT * FROM collapses
        ORDER BY run_span ASC, played_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_5wkt_collapse(session, *, org_id, limit, offset=0, context):
    return await _wicket_collapse(session, org_id=org_id, limit=limit, offset=offset, context=context, n_wickets=5, max_run_span=30)


async def derived_6wkt_collapse(session, *, org_id, limit, offset=0, context):
    return await _wicket_collapse(session, org_id=org_id, limit=limit, offset=offset, context=context, n_wickets=6, max_run_span=40)


async def derived_7wkt_collapse(session, *, org_id, limit, offset=0, context):
    return await _wicket_collapse(session, org_id=org_id, limit=limit, offset=offset, context=context, n_wickets=7, max_run_span=50)


async def derived_8wkt_collapse(session, *, org_id, limit, offset=0, context):
    return await _wicket_collapse(session, org_id=org_id, limit=limit, offset=offset, context=context, n_wickets=8, max_run_span=60)


async def derived_9wkt_collapse(session, *, org_id, limit, offset=0, context):
    return await _wicket_collapse(session, org_id=org_id, limit=limit, offset=offset, context=context, n_wickets=9, max_run_span=70)


# ─── Score-range counts (most 40s, most 90s, etc.) ─────────────────────────────

async def _score_range_count(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
    min_runs: int, max_runs: int, result_col: str,
) -> list[dict]:
    """Per-player count of innings where runs fell within [min_runs, max_runs)."""
    mc, mp, _ic, _ip, pc, pp, _ = _build_context_filters(context)
    params = {
        "org_id": org_id, "limit": min(max(1, limit), 500),
        "min_runs": min_runs, "max_runs": max_runs,
        **mp, **pp,
    }
    universe = _game_universe_sql(mc)
    player_extra = (" AND " + " AND ".join(pc)) if pc else ""
    sql = f"""
        WITH {universe}
        SELECT
            bi.player_id::text AS player_id,
            COALESCE(p.display_name_override, p.name) AS player_name,
            COUNT(*)::int AS {result_col}
        FROM game_universe gu
        JOIN v_effective_batting_innings bi ON bi.game_id = gu.game_id
        JOIN players p ON p.id = bi.player_id
        LEFT JOIN game_appearances gap ON gap.game_id = gu.game_id AND gap.player_id = p.id
        WHERE p.organisation_id = :org_id
          AND bi.did_not_bat IS NOT TRUE
          AND bi.runs >= :min_runs
          AND bi.runs < :max_runs
          {player_extra}
        GROUP BY bi.player_id, COALESCE(p.display_name_override, p.name)
        ORDER BY {result_col} DESC, player_name ASC
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
    result = await session.execute(text(sql), params)
    return [dict(r) for r in result.mappings()]


async def derived_most_90s(session, *, org_id, limit, offset=0, context):
    return await _score_range_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                     min_runs=90, max_runs=100, result_col="scores_in_90s")


async def derived_most_40s(session, *, org_id, limit, offset=0, context):
    return await _score_range_count(session, org_id=org_id, limit=limit, offset=offset, context=context,
                                     min_runs=40, max_runs=50, result_col="scores_in_40s")


# ─── Total season minutes batted ───────────────────────────────────────────────
# We don't have per-innings minutes, but player_season_stats.batting_minutes is
# populated, so a season-level "most minutes batted" report is possible.

async def derived_most_minutes_in_season(
    session: AsyncSession, *, org_id: str, limit: int, offset: int = 0, context: dict,
) -> list[dict]:
    """Most batting minutes accumulated in a single season."""
    params = {"org_id": org_id, "limit": min(max(1, limit), 500)}
    season_filter = _pss_season_filter(context, params, "ctx_mm_")
    # Batting minutes only exist as a season aggregate, so like the two family
    # targets this one can only answer the aggregate-kind scope: a category
    # exclusion lands on the rows carrying a grade, and a match type empties it
    # rather than filing a season total under a format it can't know.
    scope_clause = _scope_clause_for_join(_ctx_scope(context), "pss.grade_id", params)
    sql = f"""
        SELECT
            p.id::text                                   AS player_id,
            COALESCE(p.display_name_override, p.name)    AS player_name,
            s.name                                       AS season_name,
            pss.batting_minutes::int                     AS minutes,
            pss.runs::int                                AS runs,
            pss.batting_innings::int                     AS innings
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
          AND s.organisation_id = :org_id
          AND COALESCE(pss.batting_minutes, 0) > 0
          {season_filter}{scope_clause}
        ORDER BY pss.batting_minutes DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """
    params["offset"] = offset
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
    # Per-match aggregates
    "most_runs_in_match": {
        "label": "Most runs in a match",
        "description": "Highest combined batting score by one player across both innings of a match.",
        "fn": derived_most_runs_in_match,
        "columns": [
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "balls", "label": "BALLS", "decimal": False},
            {"key": "innings_count", "label": "INNS", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_sixes_in_match": {
        "label": "Most sixes in a match",
        "description": "Most sixes by one player across both innings of a match.",
        "fn": derived_most_sixes_in_match,
        "columns": [
            {"key": "sixes", "label": "6s", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_fours_in_match": {
        "label": "Most fours in a match",
        "description": "Most fours by one player across both innings of a match.",
        "fn": derived_most_fours_in_match,
        "columns": [
            {"key": "fours", "label": "4s", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_boundaries_in_match": {
        "label": "Most boundaries in a match",
        "description": "Most 4s + 6s by one player across both innings of a match.",
        "fn": derived_most_boundaries_in_match,
        "columns": [
            {"key": "boundaries", "label": "4s+6s", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "best_bowling_in_match": {
        "label": "Best bowling in a match",
        "description": "Best combined bowling figures across both innings of a match.",
        "fn": derived_best_bowling_in_match,
        "columns": [
            {"key": "wickets", "label": "W", "decimal": False},
            {"key": "runs", "label": "R", "decimal": False},
            {"key": "overs", "label": "OV", "kind": "overs"},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_wickets_in_match": {
        "label": "Most wickets in a match",
        "description": "Most wickets by one bowler across both innings of a match.",
        "fn": derived_most_wickets_in_match,
        "columns": [
            {"key": "wickets", "label": "W", "decimal": False},
            {"key": "runs", "label": "R", "decimal": False},
            {"key": "overs", "label": "OV", "kind": "overs"},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_balls_bowled_match": {
        "label": "Most balls bowled in a match",
        "description": "Most deliveries bowled by one player in a single match (sum across both innings).",
        "fn": derived_most_balls_bowled_match,
        "columns": [
            {"key": "balls_bowled", "label": "BALLS", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_catches_in_match": {
        "label": "Most catches in a match",
        "description": "Most catches taken by one fielder in a single match.",
        "fn": derived_most_catches_in_match,
        "columns": [
            {"key": "catches", "label": "CT", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_stumpings_in_match": {
        "label": "Most stumpings in a match",
        "description": "Most stumpings by one keeper in a single match.",
        "fn": derived_most_stumpings_in_match,
        "columns": [
            {"key": "stumpings", "label": "ST", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "most_run_outs_in_match": {
        "label": "Most run outs in a match",
        "description": "Most run outs effected by one fielder in a single match.",
        "fn": derived_most_run_outs_in_match,
        "columns": [
            {"key": "run_outs", "label": "RO", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    # Duck variants
    "golden_ducks": {
        "label": "Most golden ducks",
        "description": "Out for 0 off exactly 1 ball — count per player.",
        "fn": derived_golden_ducks,
        "columns": [
            {"key": "golden_ducks", "label": "GOLDEN", "decimal": False},
        ],
    },
    "duck_pairs": {
        "label": "Most duck pairs",
        "description": "Players who scored a duck in both innings of the same match.",
        "fn": derived_duck_pairs,
        "columns": [
            {"key": "duck_pairs", "label": "PAIRS", "decimal": False},
        ],
    },
    "consecutive_no_duck": {
        "label": "Most consecutive scores without a duck",
        "description": "Longest run of innings without being dismissed for 0.",
        "fn": derived_consecutive_no_duck,
        "columns": [
            {"key": "longest_no_duck_streak", "label": "STREAK", "decimal": False},
        ],
    },
    # Century/fifty
    "consecutive_hundreds": {
        "label": "Most consecutive hundreds",
        "description": "Longest run of innings scoring 100+.",
        "fn": derived_consecutive_hundreds,
        "columns": [
            {"key": "longest_hundred_streak", "label": "STREAK", "decimal": False},
        ],
    },
    "consecutive_no_century": {
        "label": "Most consecutive scores without a century",
        "description": "Longest run of innings scoring under 100.",
        "fn": derived_consecutive_no_century,
        "columns": [
            {"key": "longest_no_century_streak", "label": "STREAK", "decimal": False},
        ],
    },
    "century_each_innings": {
        "label": "A century in each innings",
        "description": "Players who scored 100+ in both innings of the same match.",
        "fn": derived_century_each_innings,
        "columns": [
            {"key": "top_score", "label": "TOP", "decimal": False},
            {"key": "match_runs", "label": "MATCH", "decimal": False},
            {"key": "hundreds_count", "label": "100s", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "century_and_duck": {
        "label": "Century and duck in same match",
        "description": "Players who scored a 100 and a duck in the same match.",
        "fn": derived_century_and_duck_same_match,
        "columns": [
            {"key": "top_score", "label": "TOP", "decimal": False},
            {"key": "low_score", "label": "LOW", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "innings_without_century": {
        "label": "Most innings without a century",
        "description": "Players with the most innings who've never scored a hundred.",
        "fn": derived_innings_without_century,
        "columns": [
            {"key": "innings_played", "label": "INNS", "decimal": False},
            {"key": "top_score", "label": "HS", "decimal": False},
        ],
    },
    "lowest_century_conversion": {
        "label": "Lowest century conversions",
        "description": "Lowest fifty→hundred conversion rate (5+ scores of 50+ required).",
        "fn": derived_lowest_century_conversion,
        "columns": [
            {"key": "fifties", "label": "50s", "decimal": False},
            {"key": "hundreds", "label": "100s", "decimal": False},
            {"key": "conversion_pct", "label": "CONV %", "decimal": True},
        ],
    },
    "innings_per_fifty": {
        "label": "Top innings per fifty",
        "description": "Lowest innings-per-50 ratio (most frequent 50+ scorer).",
        "fn": derived_innings_per_fifty,
        "columns": [
            {"key": "innings_played", "label": "INNS", "decimal": False},
            {"key": "fifty_plus", "label": "50+", "decimal": False},
            {"key": "innings_per_fifty", "label": "INNS/50", "decimal": True},
        ],
    },
    # Bowling streaks
    "consecutive_innings_with_wicket": {
        "label": "Most consecutive innings with a wicket",
        "description": "Longest run of bowling spells with at least one wicket.",
        "fn": derived_consecutive_innings_with_wicket,
        "columns": [
            {"key": "longest_wicket_streak", "label": "STREAK", "decimal": False},
        ],
    },
    "consecutive_5wi": {
        "label": "Most consecutive 5-wicket innings",
        "description": "Longest run of bowling spells with 5+ wickets.",
        "fn": derived_consecutive_5wi,
        "columns": [
            {"key": "longest_5wi_streak", "label": "STREAK", "decimal": False},
        ],
    },
    # Debut performances
    "batting_on_debut": {
        "label": "Top batting on debut",
        "description": "Best batting score in a player's first ever match.",
        "fn": derived_batting_on_debut,
        "columns": [
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "balls", "label": "BALLS", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "ducks_on_debut": {
        "label": "Ducks on debut",
        "description": "Players whose debut innings was a duck.",
        "fn": derived_ducks_on_debut,
        "columns": [
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "balls", "label": "BALLS", "decimal": False},
            {"key": "dismissal_type", "label": "OUT"},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "bowling_on_debut": {
        "label": "Best bowling on debut",
        "description": "Best bowling figures in a player's first ever spell.",
        "fn": derived_bowling_on_debut_innings,
        "columns": [
            {"key": "wickets", "label": "W", "decimal": False},
            {"key": "runs", "label": "R", "decimal": False},
            {"key": "overs", "label": "OV", "kind": "overs"},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    # Dismissal counts
    "dismissal_bowled": {
        "label": "Highest bowled count",
        "description": "Players most often dismissed bowled.",
        "fn": derived_dismissal_bowled,
        "columns": [{"key": "bowled_count", "label": "BOWLED", "decimal": False}],
    },
    "dismissal_caught": {
        "label": "Highest caught count",
        "description": "Players most often dismissed caught.",
        "fn": derived_dismissal_caught,
        "columns": [{"key": "caught_count", "label": "CAUGHT", "decimal": False}],
    },
    "dismissal_caught_behind": {
        "label": "Highest caught-behind count",
        "description": "Players most often caught behind (by the wicketkeeper). Counts only where the scorecard records who kept, so it's a floor.",
        "fn": derived_dismissal_caught_behind,
        "columns": [{"key": "caught_behind_count", "label": "CT (WK)", "decimal": False}],
    },
    "dismissal_lbw": {
        "label": "Highest LBW count",
        "description": "Players most often dismissed leg-before-wicket.",
        "fn": derived_dismissal_lbw,
        "columns": [{"key": "lbw_count", "label": "LBW", "decimal": False}],
    },
    "dismissal_run_out": {
        "label": "Highest run out count",
        "description": "Players most often run out.",
        "fn": derived_dismissal_run_out,
        "columns": [{"key": "run_out_count", "label": "RUN OUT", "decimal": False}],
    },
    "dismissal_stumped": {
        "label": "Highest stumped count",
        "description": "Players most often stumped.",
        "fn": derived_dismissal_stumped,
        "columns": [{"key": "stumped_count", "label": "STUMPED", "decimal": False}],
    },
    "unusual_dismissals": {
        "label": "Unusual dismissals",
        "description": "Innings ending in rare dismissals (hit wicket, retired, handled, obstructed, timed out).",
        "fn": derived_unusual_dismissals,
        "columns": [
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "dismissal_type", "label": "OUT"},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    # Partnership derived
    "top_partnerships_by_wicket": {
        "label": "Top partnerships by wicket",
        "description": "Best partnership at each wicket position (1st wicket through 10th).",
        "fn": derived_top_partnerships_by_wicket,
        "columns": [
            {"key": "wicket_number", "label": "WKT", "decimal": False},
            {"key": "player_a_id", "label": "BATTER A", "kind": "player_a"},
            {"key": "player_b_id", "label": "BATTER B", "kind": "player_b"},
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "partnership_aggregates_pair": {
        "label": "Top partnership aggregates",
        "description": "Total partnership runs accumulated by each pair of batters.",
        "fn": derived_partnership_aggregates_pair,
        "columns": [
            {"key": "player_a_id", "label": "BATTER A", "kind": "player_a"},
            {"key": "player_b_id", "label": "BATTER B", "kind": "player_b"},
            {"key": "total_runs", "label": "TOTAL", "decimal": False},
            {"key": "partnerships", "label": "STANDS", "decimal": False},
            {"key": "best_partnership", "label": "BEST", "decimal": False},
        ],
    },
    "century_partnerships_pair": {
        "label": "Most century partnerships by pair",
        "description": "Number of 100+ partnerships shared by each pair.",
        "fn": derived_century_partnerships_pair,
        "columns": [
            {"key": "player_a_id", "label": "BATTER A", "kind": "player_a"},
            {"key": "player_b_id", "label": "BATTER B", "kind": "player_b"},
            {"key": "century_partnerships", "label": "100+", "decimal": False},
            {"key": "best_partnership", "label": "BEST", "decimal": False},
        ],
    },
    "top_scores_by_position": {
        "label": "Top scores by batting position",
        "description": "Best individual score recorded at each batting position (1 through 11).",
        "fn": derived_top_scores_by_position,
        "columns": [
            {"key": "batting_position", "label": "POS", "decimal": False},
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "balls", "label": "BALLS", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "opening_bat_and_bowl": {
        "label": "Opening bat & bowl same match",
        "description": "Players who batted at #1 or #2 and bowled in innings 1 of the same match.",
        "fn": derived_opening_bat_and_bowl,
        "columns": [
            {"key": "occurrences", "label": "TIMES", "decimal": False},
        ],
    },
    "top_scores_pct_innings": {
        "label": "Top scores as % of innings",
        "description": "Individual scores as a percentage of the club innings total.",
        "fn": derived_top_scores_pct_innings,
        "columns": [
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "team_innings_total", "label": "OF", "decimal": False},
            {"key": "pct_of_innings", "label": "%", "decimal": True},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "catches_stumpings": {
        "label": "Top catches & stumpings",
        "description": "Combined dismissals (catches + stumpings) per player.",
        "fn": derived_catches_stumpings,
        "columns": [
            {"key": "catches_stumpings", "label": "CT+ST", "decimal": False},
            {"key": "catches", "label": "CT", "decimal": False},
            {"key": "stumpings", "label": "ST", "decimal": False},
            {"key": "run_outs", "label": "RO", "decimal": False},
        ],
    },
    # Hat tricks — from manually-recorded achievements
    "hat_tricks": {
        "label": "Hat tricks",
        "description": "Hat tricks recorded in Admin → Awards. Manual entries.",
        "fn": derived_hat_tricks,
        "columns": [
            {"key": "hat_tricks", "label": "HT", "decimal": False},
            {"key": "seasons", "label": "SEASONS"},
        ],
    },
    # C&B — caught and bowled (batter view: dismissals)
    "caught_and_bowled": {
        "label": "Highest C&B count (batter)",
        "description": "Batters most often dismissed caught & bowled.",
        "fn": derived_caught_and_bowled,
        "columns": [{"key": "c_and_b_count", "label": "C&B", "decimal": False}],
    },
    # C&B — caught and bowled (bowler view: wickets taken)
    "caught_and_bowled_bowler": {
        "label": "Highest C&B count (bowler)",
        "description": "Bowlers ranked by caught-and-bowled wickets taken.",
        "fn": derived_caught_and_bowled_bowler,
        "columns": [{"key": "c_and_b_count", "label": "C&B", "decimal": False}],
    },
    # Score-range counts (renamed from list presets in the UI)
    "most_90s": {
        "label": "Most 90s",
        "description": "Per-player count of innings scored in the 90s (90-99 inclusive).",
        "fn": derived_most_90s,
        "columns": [{"key": "scores_in_90s", "label": "90s", "decimal": False}],
    },
    "most_40s": {
        "label": "Most 40s",
        "description": "Per-player count of innings scored in the 40s (40-49 inclusive).",
        "fn": derived_most_40s,
        "columns": [{"key": "scores_in_40s", "label": "40s", "decimal": False}],
    },
    # Ducks inflicted — bowler caused a batter's 0
    "ducks_inflicted": {
        "label": "Most ducks inflicted",
        "description": "Bowlers ranked by how often they dismissed a batter for 0. Requires a Full Rebuild post-v7.15.0.3 to backfill opposition batting scores.",
        "fn": derived_ducks_inflicted,
        "columns": [
            {"key": "ducks_inflicted", "label": "DUCKS", "decimal": False},
        ],
    },
    "golden_ducks_inflicted": {
        "label": "Most golden ducks inflicted",
        "description": "Bowlers ranked by golden ducks (0 off exactly 1 ball) they caused. Requires a Full Rebuild post-v7.15.0.3 to backfill opposition batting scores.",
        "fn": derived_golden_ducks_inflicted,
        "columns": [
            {"key": "golden_ducks_inflicted", "label": "GOLDEN", "decimal": False},
        ],
    },
    # Bowler+fielder combos
    "bowler_fielder_combo": {
        "label": "Top bowler/fielder combinations",
        "description": "Bowler+catcher pairs ranked by caught dismissals taken together (WK and outfield catches; stumpings excluded). Count is limited to matches where the dismissal text names the catcher — historical matches without structured scorecard text will be under-counted.",
        "fn": derived_bowler_fielder_combo,
        "columns": [
            {"key": "player_a_id", "label": "BOWLER", "kind": "player_a"},
            {"key": "player_b_id", "label": "FIELDER", "kind": "player_b"},
            {"key": "catches", "label": "CT", "decimal": False},
        ],
    },
    # Top opening bowlers
    "top_opening_bowlers": {
        "label": "Top opening bowlers by match count",
        "description": "Players who've taken the new ball most often (lowest spell ID per innings).",
        "fn": derived_top_opening_bowlers,
        "columns": [
            {"key": "opening_matches", "label": "MATCHES", "decimal": False},
            {"key": "opening_innings", "label": "INNS", "decimal": False},
        ],
    },
    # Wicket collapses
    "collapse_5w": {
        "label": "5-wicket collapses",
        "description": "5 wickets fell within 30 runs (from fall-of-wicket scores).",
        "fn": derived_5wkt_collapse,
        "columns": [
            {"key": "run_span", "label": "RUNS", "decimal": False},
            {"key": "from_wicket", "label": "FROM", "decimal": False},
            {"key": "to_wicket", "label": "TO", "decimal": False},
            {"key": "innings_number", "label": "INN#", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "collapse_6w": {
        "label": "6-wicket collapses",
        "description": "6 wickets fell within 40 runs.",
        "fn": derived_6wkt_collapse,
        "columns": [
            {"key": "run_span", "label": "RUNS", "decimal": False},
            {"key": "from_wicket", "label": "FROM", "decimal": False},
            {"key": "to_wicket", "label": "TO", "decimal": False},
            {"key": "innings_number", "label": "INN#", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "collapse_7w": {
        "label": "7-wicket collapses",
        "description": "7 wickets fell within 50 runs.",
        "fn": derived_7wkt_collapse,
        "columns": [
            {"key": "run_span", "label": "RUNS", "decimal": False},
            {"key": "from_wicket", "label": "FROM", "decimal": False},
            {"key": "to_wicket", "label": "TO", "decimal": False},
            {"key": "innings_number", "label": "INN#", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "collapse_8w": {
        "label": "8-wicket collapses",
        "description": "8 wickets fell within 60 runs.",
        "fn": derived_8wkt_collapse,
        "columns": [
            {"key": "run_span", "label": "RUNS", "decimal": False},
            {"key": "from_wicket", "label": "FROM", "decimal": False},
            {"key": "to_wicket", "label": "TO", "decimal": False},
            {"key": "innings_number", "label": "INN#", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    "collapse_9w": {
        "label": "9-wicket collapses",
        "description": "9 wickets fell within 70 runs.",
        "fn": derived_9wkt_collapse,
        "columns": [
            {"key": "run_span", "label": "RUNS", "decimal": False},
            {"key": "from_wicket", "label": "FROM", "decimal": False},
            {"key": "to_wicket", "label": "TO", "decimal": False},
            {"key": "innings_number", "label": "INN#", "decimal": False},
            {"key": "opposition", "label": "VS"},
            {"key": "grade_name", "label": "GRADE"},
            {"key": "played_at", "label": "DATE"},
        ],
    },
    # Season minutes batted
    "most_minutes_in_season": {
        "label": "Most batting minutes in a season",
        "description": "Total minutes at the crease across a season (per-season stat).",
        "fn": derived_most_minutes_in_season,
        "columns": [
            {"key": "minutes", "label": "MINS", "decimal": False},
            {"key": "runs", "label": "RUNS", "decimal": False},
            {"key": "innings", "label": "INNS", "decimal": False},
            {"key": "season_name", "label": "SEASON"},
        ],
    },
}


# ─── Entry point ───────────────────────────────────────────────────────────────

TARGET_DISPATCH = {
    "player_career":    query_player_career,
    "player_season":    query_player_season,
    "player_grade":     query_player_grade,
    "family_career":    query_family_career,
    "family_season":    query_family_season,
    "family_grade":     query_family_grade,
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
    page: int = 1,
    metric_filters: list[str] | None,
    filter_tree: dict | None,
    context: dict,
) -> dict:
    if target not in TARGET_DISPATCH:
        raise ValueError(f"Unknown query target: {target}")
    page = max(1, page)
    offset = (page - 1) * limit
    fn = TARGET_DISPATCH[target]
    rows = await fn(
        session,
        org_id=org_id,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
        metric_filters=metric_filters,
        filter_tree=filter_tree,
        context=context,
    )
    return {"rows": rows, "has_more": len(rows) == limit, "page": page}


async def run_derived(
    session: AsyncSession, *, name: str, org_id: str, limit: int, page: int = 1, context: dict,
) -> dict:
    if name not in DERIVED_QUERIES:
        raise ValueError(f"Unknown derived query: {name}")
    page = max(1, page)
    offset = (page - 1) * limit
    fn = DERIVED_QUERIES[name]["fn"]
    rows = await fn(session, org_id=org_id, limit=limit, offset=offset, context=context)
    return {"rows": rows, "has_more": len(rows) == limit, "page": page}


METRIC_CATEGORIES: list[dict] = [
    {"key": "participation", "label": "Participation",
     "fields": ["matches", "seasons_played", "batting_innings", "bowling_innings", "member_count"]},
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
