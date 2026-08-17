from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from datetime import date as date_cls
import uuid

from app.services.milestone_rules import next_threshold, reach_window
from app.services.grade_scope import GradeScope
from app.services.season_aliases import (
    resolve_season_filter,
    resolve_season_filter_no_org,
)


def _scoped(scope: Optional[GradeScope]) -> bool:
    """Is there actually a grade category being excluded?

    An inactive scope must emit no SQL and take no alternate code path, so a club
    with nothing out of scope keeps running exactly the queries it ran before
    grade categories existed. Every caller gates on this, not on `scope is None`.
    """
    return bool(scope is not None and scope.active)

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

# Same merge-aware match, but against an ``import_effective_deltas`` row's free-text
# grade_label (ied must already be in scope) — a career-scope import residual has no
# grade_id (it spans many seasons' worth of same-named grades, see migration 154),
# so grade-filtered leaderboards match it by name exactly like _GRADE_MATCH does for
# a real grades row.
_IMPORT_GRADE_MATCH = (
    "(ied.grade_label = :grade_name"
    " OR EXISTS (SELECT 1 FROM grade_merge_logs gml"
    " WHERE gml.org_id = CAST(:org_id AS UUID)"
    " AND gml.alias_name = ied.grade_label AND gml.undone_at IS NULL"
    " AND (gml.canonical_name = :grade_name"
    " OR EXISTS (SELECT 1 FROM grades gr2 JOIN seasons s2 ON s2.id = gr2.season_id"
    " WHERE gr2.name = gml.canonical_name AND s2.organisation_id = CAST(:org_id AS UUID)"
    " AND gr2.display_name_override = :grade_name))))"
)


async def _resolve_grade_name(session: AsyncSession, org_id: str, grade_id: str) -> Optional[str]:
    """A grade_id's display name, for feeding _IMPORT_GRADE_MATCH from a grade_id filter.

    Import residuals (career-scope especially) carry no grade_id of their own —
    only the grade_id-filtered leaderboard branches need this one extra lookup
    to translate "this exact season's grade row" into the name their import
    match has to compare against.
    """
    row = (
        await session.execute(
            text("SELECT COALESCE(display_name_override, name) AS n FROM grades WHERE id = CAST(:gid AS UUID)"),
            {"gid": grade_id},
        )
    ).mappings().first()
    return row["n"] if row else None


# The branches of v_effective_player_season_stats that have NO per-innings rows
# behind them, and so are invisible to the per-game path a scoped career total
# has to use.
#
# `api` is CA's season aggregate for games we also hold scorecards for, and
# `manual_game` is a rollup of manual games that are themselves in the per-game
# views — counting either alongside the per-game rows would double every figure.
# The three below are different: a BetterImport historical CSV, a hand-entered
# season adjustment and the career-level "Prior Seasons & Adjustments" lump exist
# only as totals. Drop them and a club with fifty years of imported history would
# watch it vanish the moment the default junior filter applied.
_RESIDUAL_SOURCES = ("manual_aggregate", "manual_career", "import")


def _residual_totals_cte(scope: GradeScope, season_ids, params: dict) -> str:
    """A `residual_totals` CTE keyed on player_id, for the leaderboards.

    Same job as `_career_residuals` does for one player: a scoped leaderboard
    reads per-innings rows, so without this a club's BetterImport history would
    drop off its own all-time boards the moment a category filter applied. The
    existing `import_totals` CTE right beside this is the same pattern for the
    grade-filtered branch.
    """
    params["residual_sources"] = list(_RESIDUAL_SOURCES)
    scope.bind(params)
    season_clause = " AND pss.season_id = ANY(:season_ids)" if season_ids else ""
    return f"""
        residual_totals AS (
            SELECT pss.player_id,
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                MAX(pss.high_score) AS high_score,
                COALESCE(SUM(pss.not_outs), 0) AS not_outs,
                COALESCE(SUM(pss.balls_faced), 0) AS total_balls,
                COALESCE(SUM(pss.fifties), 0) AS fifties,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds,
                COALESCE(SUM(pss.ducks), 0) AS ducks,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.runs_conceded), 0) AS bowling_runs,
                COALESCE(SUM(pss.overs), 0) AS total_overs,
                COALESCE(SUM(pss.bowling_balls), 0) AS bowling_balls,
                COALESCE(SUM(pss.maidens), 0) AS total_maidens,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                MAX(pss.best_bowling_wickets) AS best_bowling_wickets,
                COALESCE(SUM(pss.catches), 0) AS total_catches,
                COALESCE(SUM(pss.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(pss.catches_non_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(pss.stumpings), 0) AS total_stumpings
            FROM v_effective_player_season_stats pss
            WHERE pss.source = ANY(:residual_sources){season_clause}{scope.clause("pss.grade_id")}
            GROUP BY pss.player_id
        )
    """


async def _career_residuals(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str],
    scope: Optional[GradeScope],
) -> dict:
    """Aggregate-only career figures that survive a grade-category filter.

    Two of the three residual branches carry a real `grade_id` (a season
    adjustment, an import delta) and are filtered by it. The career-level lump
    has none, and is kept: exclusion semantics mean a row we cannot categorise is
    not a row we know to be out of scope.
    """
    params: dict = {"pid": player_id, "sources": list(_RESIDUAL_SOURCES)}
    season_ids = await resolve_season_filter_no_org(session, season_id)
    # Matches the unscoped career query's own behaviour: naming a season excludes
    # the NULL-season career lump, because a NULL never matches a season filter.
    season_clause = " AND pss.season_id = ANY(:sids)" if season_ids else ""
    if season_ids:
        params["sids"] = season_ids
    scope_clause = scope.clause("pss.grade_id") if _scoped(scope) else ""
    if _scoped(scope):
        scope.bind(params)
    res = await session.execute(
        text(f"""
            SELECT
                COALESCE(SUM(pss.matches), 0) AS games,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                MAX(pss.high_score) AS high_score,
                COALESCE(SUM(pss.not_outs), 0) AS not_outs,
                COALESCE(SUM(pss.balls_faced), 0) AS total_balls,
                COALESCE(SUM(pss.fifties), 0) AS fifties,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds,
                COALESCE(SUM(pss.ducks), 0) AS ducks,
                COALESCE(SUM(pss.fours), 0) AS total_fours,
                COALESCE(SUM(pss.sixes), 0) AS total_sixes,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.runs_conceded), 0) AS bowling_runs,
                COALESCE(SUM(pss.overs), 0) AS total_overs,
                COALESCE(SUM(pss.bowling_balls), 0) AS bowling_balls,
                COALESCE(SUM(pss.maidens), 0) AS total_maidens,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                MAX(pss.best_bowling_wickets) AS best_bowling_wickets,
                COALESCE(SUM(pss.catches), 0) AS total_catches,
                COALESCE(SUM(pss.catches_wk), 0) AS total_catches_wk,
                COALESCE(SUM(pss.catches_non_wk), 0) AS total_catches_non_wk,
                COALESCE(SUM(pss.run_outs), 0) AS total_run_outs,
                COALESCE(SUM(pss.stumpings), 0) AS total_stumpings
            FROM v_effective_player_season_stats pss
            WHERE pss.player_id = CAST(:pid AS UUID)
              AND pss.source = ANY(:sources){season_clause}{scope_clause}
        """),
        params,
    )
    row = res.mappings().first()
    return dict(row) if row else {}


def _n(value) -> int:
    return int(value or 0)


def _ratio(numerator, denominator, places: int = 2):
    """A derived stat, or None when there is nothing to divide by.

    Every blended average/rate is recomputed from the summed counts here rather
    than combined from the two sides' own averages, which would weight a career
    of imported totals the same as a single scorecard.
    """
    d = _n(denominator)
    return round(_n(numerator) / d, places) if d else None


async def _game_season_clause(session: AsyncSession, season_id, params: dict) -> str:
    """Season filter for a per-game query, binding into `params` in place.

    Reads `v_effective_games.season_id` (migration 169) rather than joining
    grades→seasons: a manual game may have no grade but always has a season, and
    deriving one through the grade would drop it (the v8.76.1 bug).
    """
    if not season_id:
        return ""
    season_ids = await resolve_season_filter_no_org(session, season_id)
    if not season_ids:
        return ""
    params["career_season_ids"] = season_ids
    return " AND g.season_id = ANY(:career_season_ids)"


async def _career_identity(session: AsyncSession, player_id: str) -> dict:
    """The player columns every career payload carries alongside its figures.

    The season-aggregate queries get these from their `players` join for free;
    the per-game path has no such join, so a scoped career total would otherwise
    come back missing `name`/`organisation_id` and quietly change the response
    shape depending on whether a filter happened to be active.
    """
    res = await session.execute(
        text(
            "SELECT COALESCE(p.display_name_override, p.name) AS name, p.organisation_id "
            "FROM players p WHERE p.id = CAST(:pid AS UUID)"
        ),
        {"pid": player_id},
    )
    row = res.mappings().first()
    return {
        "player_id": player_id,
        "name": row["name"] if row else None,
        "organisation_id": row["organisation_id"] if row else None,
    }


async def _scoped_games_played(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str],
    scope: Optional[GradeScope],
) -> int:
    """Distinct in-scope games this player appeared in at all, however.

    A "games" figure derived from just ONE per-game table (a batting innings, a
    bowling spell, a fielding-stats row) undercounts the moment a player did
    something else in a game instead — most visibly a batting-only `qualifying`
    count, which deliberately excludes a "did not bat" row (right for `innings`/
    `average`, wrong for "how many matches did they play"). This unions every
    source of "they were in this game" — including a bare DNB batting row and a
    plain roster appearance with no stats at all — so a player who only bowled,
    only fielded, or was named but never got a knock still counts the match.
    Mirrors the unscoped path, where `player_season_stats.matches` already means
    "matches played", not "matches batted in".
    """
    params: dict = {"pid": player_id}
    season_clause = await _game_season_clause(session, season_id, params)
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    if _scoped(scope):
        scope.bind(params)
    sql = f"""
        SELECT COUNT(DISTINCT g.id)
        FROM v_effective_games g
        WHERE g.id IN (
            SELECT bi.game_id FROM v_effective_batting_innings bi WHERE bi.player_id = CAST(:pid AS UUID)
            UNION
            SELECT bs.game_id FROM v_effective_bowling_spells bs WHERE bs.player_id = CAST(:pid AS UUID)
            UNION
            SELECT fs.game_id FROM v_effective_fielding_stats fs WHERE fs.player_id = CAST(:pid AS UUID)
            UNION
            SELECT ga.game_id FROM game_appearances ga WHERE ga.player_id = CAST(:pid AS UUID)
        )
        {season_clause}{scope_clause}
    """
    result = await session.execute(text(sql), params)
    return int(result.scalar() or 0)


async def get_career_batting(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    # Career totals normally come from CA's own season aggregates, which have no
    # grade dimension at all (the `api` branch of v_effective_player_season_stats
    # hardcodes grade_id NULL). Excluding a category is therefore only answerable
    # from the per-innings scorecards, so an active scope switches source — the
    # same trade the leaderboards already make when a grade filter is applied.
    if _scoped(scope):
        pg = await get_career_batting_from_innings(session, player_id, season_id=season_id, scope=scope) or {}
        r = await _career_residuals(session, player_id, season_id, scope)
        matches = await _scoped_games_played(session, player_id, season_id, scope)
        innings = _n(pg.get("innings")) + _n(r.get("innings"))
        runs = _n(pg.get("total_runs")) + _n(r.get("total_runs"))
        not_outs = _n(pg.get("not_outs")) + _n(r.get("not_outs"))
        balls = _n(pg.get("total_balls")) + _n(r.get("total_balls"))
        highs = [h for h in (pg.get("high_score"), r.get("high_score")) if h is not None]
        return {
            **await _career_identity(session, player_id),
            "innings": innings,
            "total_runs": runs,
            "high_score": max(highs) if highs else None,
            "average": _ratio(runs, innings - not_outs),
            "strike_rate": _ratio(runs * 100, balls),
            "fifties": _n(pg.get("fifties")) + _n(r.get("fifties")),
            "hundreds": _n(pg.get("hundreds")) + _n(r.get("hundreds")),
            "ducks": _n(pg.get("ducks")) + _n(r.get("ducks")),
            "total_fours": _n(pg.get("total_fours")) + _n(r.get("total_fours")),
            "total_sixes": _n(pg.get("total_sixes")) + _n(r.get("total_sixes")),
            "games": matches + _n(r.get("games")),
        }
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


async def get_career_bowling(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    if _scoped(scope):
        pg = await get_career_bowling_from_spells(session, player_id, season_id=season_id, scope=scope) or {}
        r = await _career_residuals(session, player_id, season_id, scope)
        matches = await _scoped_games_played(session, player_id, season_id, scope)
        wickets = _n(pg.get("total_wickets")) + _n(r.get("total_wickets"))
        conceded = _n(pg.get("total_runs")) + _n(r.get("bowling_runs"))
        balls = _n(pg.get("total_balls")) + _n(r.get("bowling_balls"))
        best = [w for w in (pg.get("best_figures_wickets"), r.get("best_bowling_wickets")) if w is not None]
        return {
            **await _career_identity(session, player_id),
            "total_wickets": wickets,
            "average": _ratio(conceded, wickets),
            "economy": _ratio(conceded * 6, balls),
            "best_figures_wickets": max(best) if best else None,
            # Only the per-game side can name the actual figures — a residual
            # branch carries the wicket count but its `best_bowling_figures`
            # string belongs to a spell we have no scorecard for, so pairing it
            # with a blended maximum could print figures from the wrong innings.
            "best_bowling_figures": pg.get("best_bowling_figures"),
            "total_maidens": _n(pg.get("total_maidens")) + _n(r.get("total_maidens")),
            "total_overs": _n(pg.get("total_overs")) + _n(r.get("total_overs")),
            "total_runs": conceded,
            "five_fors": _n(pg.get("five_fors")) + _n(r.get("five_fors")),
            "bowling_strike_rate": _ratio(balls, wickets),
            "games": matches + _n(r.get("games")),
        }
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


async def get_career_fielding(
    session: AsyncSession,
    player_id: str,
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    if _scoped(scope):
        pg = await get_career_fielding_from_stats(session, player_id, season_id=season_id, scope=scope) or {}
        r = await _career_residuals(session, player_id, season_id, scope)
        matches = await _scoped_games_played(session, player_id, season_id, scope)
        catches = _n(pg.get("total_catches")) + _n(r.get("total_catches"))
        run_outs = _n(pg.get("total_run_outs")) + _n(r.get("total_run_outs"))
        stumpings = _n(pg.get("total_stumpings")) + _n(r.get("total_stumpings"))
        catches_wk = _n(pg.get("total_catches_wk")) + _n(r.get("total_catches_wk"))
        return {
            **await _career_identity(session, player_id),
            "total_catches": catches,
            "total_catches_wk": catches_wk,
            "total_catches_non_wk": max(catches - catches_wk, 0),
            "total_run_outs": run_outs,
            # See the NULL columns in get_career_fielding_from_stats: the
            # per-game table holds one run-out count and never splits assisted
            # from unassisted, so a blended split would be part real, part guess.
            "total_assisted_run_outs": None,
            "total_unassisted_run_outs": None,
            "total_stumpings": stumpings,
            "total_dismissals": catches + run_outs + stumpings,
            "games": matches + _n(r.get("games")),
        }
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
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""
    season_clause = await _game_season_clause(session, season_id, params)
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    if _scoped(scope):
        scope.bind(params)

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
          {game_filter}{season_clause}{scope_clause}
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
            COUNT(DISTINCT game_id) AS games,
            -- Exposed so a caller blending this with the aggregate-only
            -- residuals below can recompute the average from summed counts
            -- rather than trying to average two averages.
            COALESCE(SUM(not_out::int), 0) AS not_outs,
            COALESCE(SUM(balls), 0) AS total_balls
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
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""
    season_clause = await _game_season_clause(session, season_id, params)
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    if _scoped(scope):
        scope.bind(params)

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
          {game_filter}{season_clause}{scope_clause}
    )""")

    sql = f"""
        WITH {', '.join(ctes)}
        SELECT
            COALESCE(SUM(wickets), 0) AS total_wickets,
            ROUND(SUM(runs)::numeric / NULLIF(SUM(wickets), 0), 2) AS average,
            ROUND(SUM(runs)::numeric * 6 / NULLIF(SUM(FLOOR(overs) * 6 + ROUND((overs - FLOOR(overs)) * 10)), 0), 2) AS economy,
            (SELECT wickets FROM qualifying ORDER BY wickets DESC, runs ASC LIMIT 1) AS best_figures_wickets,
            (SELECT wickets::text || '/' || runs::text FROM qualifying ORDER BY wickets DESC, runs ASC LIMIT 1) AS best_bowling_figures,
            COALESCE(SUM(maidens), 0) AS total_maidens,
            COALESCE(SUM(overs), 0) AS total_overs,
            -- Runs conceded. The season-aggregate path calls this `total_runs`
            -- too; a caller switching between the two must not have to rename it.
            COALESCE(SUM(runs), 0) AS total_runs,
            COALESCE(SUM(CASE WHEN wickets >= 5 THEN 1 ELSE 0 END), 0) AS five_fors,
            COUNT(DISTINCT game_id) AS games,
            ROUND(SUM(overs)::numeric * 6 / NULLIF(SUM(wickets), 0), 2) AS bowling_strike_rate,
            -- Balls bowled, from cricket's own overs notation (10.2 = 10 overs
            -- and 2 balls, not 10.2 overs). Exposed for the same blending reason
            -- as batting's not_outs.
            COALESCE(SUM(FLOOR(overs) * 6 + ROUND((overs - FLOOR(overs)) * 10)), 0) AS total_balls
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
    season_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> Optional[dict]:
    params: dict = {"pid": player_id}
    ctes = []
    game_filter = ""
    season_clause = await _game_season_clause(session, season_id, params)
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    if _scoped(scope):
        scope.bind(params)

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
          {game_filter}{season_clause}{scope_clause}
    )""")

    sql = f"""
        WITH {', '.join(ctes)}
        SELECT
            COALESCE(SUM(catches), 0) AS total_catches,
            COALESCE(SUM(catches_wk), 0) AS total_catches_wk,
            COALESCE(SUM(catches - catches_wk), 0) AS total_catches_non_wk,
            COALESCE(SUM(run_outs), 0) AS total_run_outs,
            -- `fielding_stats` holds one run-out count per game and never splits
            -- assisted from unassisted (only CA's season aggregate does), so a
            -- scoped total genuinely cannot answer this. NULL says "not known
            -- for this view", which the profile renders as a dash — reporting 0
            -- would read as "never assisted a run-out".
            NULL::bigint AS total_assisted_run_outs,
            NULL::bigint AS total_unassisted_run_outs,
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    return await get_batting_leaderboard_extended(session, org_id, season_id, grade_id, "total_runs", limit, finals_only=finals_only, scope=scope)


async def get_bowling_leaderboard(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    limit: int = 20,
    finals_only: Optional[bool] = None,
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    return await get_bowling_leaderboard_extended(session, org_id, season_id, grade_id, "total_wickets", limit, finals_only=finals_only, scope=scope)


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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    ALLOWED_SORTS = {"total_catches", "total_catches_non_wk", "total_catches_wk", "total_run_outs", "total_stumpings", "total_dismissals", "games"}
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_dismissals"
    # An explicitly picked grade beats the category default.
    if grade_id or grade_name:
        scope = None

    season_ids = await resolve_season_filter(session, org_id, season_id)

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = fs.game_id AND gap.player_id = fs.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if _scoped(scope):
        # Bound once for every branch below: the finals and captain branches
        # interpolate scope_clause directly, and a clause whose parameter was
        # never bound fails at execute time, not at import. The SIRS queries
        # bind their own inside _sirs_base_clauses.
        scope.bind(params)
    if gender:
        params["gender"] = gender
    if season_ids:
        params["season_ids"] = season_ids

    # See the equivalent note in get_batting_leaderboard_extended: import residuals
    # can't be attributed to a final or a captain's game, so are only blended in
    # for the plain grade view.
    include_import = not captain_only and not finals_only

    if grade_id:
        params["grade_id"] = grade_id
        import_cte = ""
        import_join = ""
        qualify_clause = "fs.player_id IS NOT NULL"
        if include_import:
            import_grade_name = await _resolve_grade_name(session, org_id, grade_id)
            if import_grade_name:
                params["grade_name"] = import_grade_name
                import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
                qualify_clause = "fs.player_id IS NOT NULL OR it.player_id IS NOT NULL"
                import_cte = f"""
                , import_totals AS (
                    SELECT ied.player_id,
                        COALESCE(SUM(ied.matches), 0) AS games,
                        COALESCE(SUM(ied.catches), 0) AS total_catches,
                        COALESCE(SUM(ied.catches_wk), 0) AS total_catches_wk,
                        COALESCE(SUM(ied.run_outs), 0) AS total_run_outs,
                        COALESCE(SUM(ied.stumpings), 0) AS total_stumpings
                    FROM import_effective_deltas ied
                    WHERE ied.organisation_id = :org_id AND {_IMPORT_GRADE_MATCH}{import_season_clause}
                    GROUP BY ied.player_id
                )
                """
                import_join = "LEFT JOIN import_totals it ON it.player_id = p.id"
        base = f"""
            WITH fielding_qualifying AS (
                SELECT fs.player_id, fs.game_id, fs.catches, fs.catches_wk, fs.run_outs, fs.stumpings
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id{captain_join}
                WHERE g.grade_id = :grade_id{finals_clause}
            ){import_cte}
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT fs.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(fs.catches), 0) + COALESCE(MAX(it.total_catches), 0) AS total_catches,
                    COALESCE(SUM(fs.catches_wk), 0) + COALESCE(MAX(it.total_catches_wk), 0) AS total_catches_wk,
                    COALESCE(SUM(fs.catches - fs.catches_wk), 0) + COALESCE(MAX(it.total_catches), 0) - COALESCE(MAX(it.total_catches_wk), 0) AS total_catches_non_wk,
                    COALESCE(SUM(fs.run_outs), 0) + COALESCE(MAX(it.total_run_outs), 0) AS total_run_outs,
                    COALESCE(SUM(fs.stumpings), 0) + COALESCE(MAX(it.total_stumpings), 0) AS total_stumpings,
                    COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0)
                        + COALESCE(MAX(it.total_catches), 0) + COALESCE(MAX(it.total_run_outs), 0) + COALESCE(MAX(it.total_stumpings), 0) AS total_dismissals
                FROM players p
                LEFT JOIN fielding_qualifying fs ON fs.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        import_cte = ""
        import_join = ""
        qualify_clause = "fs.player_id IS NOT NULL"
        if include_import:
            qualify_clause = "fs.player_id IS NOT NULL OR it.player_id IS NOT NULL"
            import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
            import_cte = f"""
            , import_totals AS (
                SELECT ied.player_id,
                    COALESCE(SUM(ied.matches), 0) AS games,
                    COALESCE(SUM(ied.catches), 0) AS total_catches,
                    COALESCE(SUM(ied.catches_wk), 0) AS total_catches_wk,
                    COALESCE(SUM(ied.run_outs), 0) AS total_run_outs,
                    COALESCE(SUM(ied.stumpings), 0) AS total_stumpings
                FROM import_effective_deltas ied
                WHERE ied.organisation_id = :org_id AND {_IMPORT_GRADE_MATCH}{import_season_clause}
                GROUP BY ied.player_id
            )
            """
            import_join = "LEFT JOIN import_totals it ON it.player_id = p.id"
        base = f"""
            WITH fielding_qualifying AS (
                SELECT fs.player_id, fs.game_id, fs.catches, fs.catches_wk, fs.run_outs, fs.stumpings
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id{captain_join}
                WHERE {_GRADE_MATCH}{season_clause}{finals_clause}
            ){import_cte}
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT fs.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(fs.catches), 0) + COALESCE(MAX(it.total_catches), 0) AS total_catches,
                    COALESCE(SUM(fs.catches_wk), 0) + COALESCE(MAX(it.total_catches_wk), 0) AS total_catches_wk,
                    COALESCE(SUM(fs.catches - fs.catches_wk), 0) + COALESCE(MAX(it.total_catches), 0) - COALESCE(MAX(it.total_catches_wk), 0) AS total_catches_non_wk,
                    COALESCE(SUM(fs.run_outs), 0) + COALESCE(MAX(it.total_run_outs), 0) AS total_run_outs,
                    COALESCE(SUM(fs.stumpings), 0) + COALESCE(MAX(it.total_stumpings), 0) AS total_stumpings,
                    COALESCE(SUM(fs.catches + fs.run_outs + fs.stumpings), 0)
                        + COALESCE(MAX(it.total_catches), 0) + COALESCE(MAX(it.total_run_outs), 0) + COALESCE(MAX(it.total_stumpings), 0) AS total_dismissals
                FROM players p
                LEFT JOIN fielding_qualifying fs ON fs.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
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
            -- Scope the PLAYER as well as the season. A fixture between two
            -- synced clubs is a single `games` row carrying BOTH clubs' fielding
            -- rows, so scoping the game alone puts the opposition on our board.
            JOIN players p ON p.id = fs.player_id AND p.organisation_id = CAST(:org_id AS UUID)
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND g.is_final = TRUE{season_clause}{scope_clause}{gender_clause}{overseas_clause}
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
            -- Player-scoped for the same reason as the finals branch above.
            JOIN players p ON p.id = fs.player_id AND p.organisation_id = CAST(:org_id AS UUID)
            WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{scope_clause}{gender_clause}{overseas_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit
        """
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if _scoped(scope):
        # See get_batting_leaderboard_extended's equivalent branch: the plain
        # board reads grade-blind season aggregates, so a category filter has to
        # be answered from per-game rows plus the aggregate-only residuals.
        season_clause = " AND g.season_id = ANY(:season_ids)" if season_ids else ""
        residual_cte = _residual_totals_cte(scope, season_ids, params)
        base = f"""
            WITH {residual_cte}, qualifying AS (
                SELECT fs.player_id, fs.game_id, fs.catches, fs.catches_wk, fs.run_outs, fs.stumpings
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN seasons s ON s.id = g.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{scope_clause}
            )
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT q.game_id) + COALESCE(MAX(rt.games), 0) AS games,
                    COALESCE(SUM(q.catches), 0) + COALESCE(MAX(rt.total_catches), 0) AS total_catches,
                    COALESCE(SUM(q.catches_wk), 0) + COALESCE(MAX(rt.total_catches_wk), 0) AS total_catches_wk,
                    COALESCE(SUM(q.catches - q.catches_wk), 0) + COALESCE(MAX(rt.total_catches_non_wk), 0) AS total_catches_non_wk,
                    COALESCE(SUM(q.run_outs), 0) + COALESCE(MAX(rt.total_run_outs), 0) AS total_run_outs,
                    COALESCE(SUM(q.stumpings), 0) + COALESCE(MAX(rt.total_stumpings), 0) AS total_stumpings,
                    COALESCE(SUM(q.catches + q.run_outs + q.stumpings), 0)
                        + COALESCE(MAX(rt.total_catches), 0) + COALESCE(MAX(rt.total_run_outs), 0)
                        + COALESCE(MAX(rt.total_stumpings), 0) AS total_dismissals
                FROM players p
                LEFT JOIN qualifying q ON q.player_id = p.id
                LEFT JOIN residual_totals rt ON rt.player_id = p.id
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND (q.player_id IS NOT NULL OR rt.player_id IS NOT NULL)
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
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
        -- No seasons join: career-level (NULL-season) import / manual-career rows
        -- (the "Prior Seasons & Adjustments" bucket) belong in the all-seasons
        -- total. A specific-season filter below still excludes them (a NULL
        -- season never matches the season filter). Org scope is the player join.
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    clauses = ["bi.player_id = :pid"]
    params: dict = {"pid": player_id}
    if _scoped(scope):
        # Leading AND already; strip it, the clause list re-joins them.
        clauses.append(scope.clause("g.grade_id").removeprefix(" AND ").strip())
        scope.bind(params)
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    season_ids = await resolve_season_filter_no_org(session, season_id)
    clauses = ["bs.player_id = :pid"]
    params: dict = {"pid": player_id}
    if _scoped(scope):
        # Leading AND already; strip it, the clause list re-joins them.
        clauses.append(scope.clause("g.grade_id").removeprefix(" AND ").strip())
        scope.bind(params)
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


async def get_dismissal_breakdown(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            SELECT
                CASE
                    WHEN bi.not_out THEN 'not out'
                    WHEN bi.dismissal_type IS NULL THEN 'unknown'
                    WHEN bi.dismissal_type = 'b' OR bi.dismissal_type LIKE 'b %' THEN 'bowled'
                    WHEN (bi.dismissal_type = 'c' OR bi.dismissal_type LIKE 'c %')
                         AND bi.caught_behind IS TRUE THEN 'caught behind'
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
            JOIN v_effective_games g ON g.id = bi.game_id
            WHERE bi.player_id = :pid
              AND bi.runs IS NOT NULL
              AND (bi.did_not_bat IS NOT TRUE)
              {scope_clause}
            GROUP BY 1
            ORDER BY COUNT(*) DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_bowling_dismissal_breakdown(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    """Breakdown of HOW this bowler dismisses batters (bowled/caught/lbw/etc).

    Counts bowler_wickets rows where bowler_id = player. caught-and-bowled is
    its own slice. Excludes non-credit dismissal types (run-outs etc.) — they
    aren't recorded in bowler_wickets in the first place.
    """
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            SELECT
                CASE
                    WHEN bw.dismissal_type = 'caught' AND bw.caught_behind IS TRUE
                        THEN 'caught behind'
                    ELSE COALESCE(bw.dismissal_type, 'unknown')
                END AS dismissal_type,
                COUNT(*) AS count
            FROM v_effective_bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id
            WHERE bw.bowler_id = :pid
              {scope_clause}
            GROUP BY 1
            ORDER BY COUNT(*) DESC
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_bowling_by_batter_position(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    """How many batters at each batting position (1-13) this bowler has dismissed.

    Returns one row per position with a wicket count. Positions with zero
    wickets are still returned so the chart shows the full spread. 12-13
    cover the rare cases of substitutes / forfeits where CA assigns a higher
    batting order than the standard 1-11.
    """
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            WITH positions AS (
                SELECT generate_series(1, 13) AS batting_position
            )
            SELECT
                p.batting_position,
                COALESCE(COUNT(bw.id), 0) AS wickets
            FROM positions p
            LEFT JOIN v_effective_bowler_wickets bw
              ON bw.batter_position = p.batting_position
             AND bw.bowler_id = :pid
            LEFT JOIN v_effective_games g ON g.id = bw.game_id
            WHERE TRUE{scope_clause}
            GROUP BY p.batting_position
            ORDER BY p.batting_position
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_position(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
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
            JOIN v_effective_games g ON g.id = bi.game_id
            WHERE bi.player_id = :pid
              AND bi.batting_position IS NOT NULL
              AND bi.runs IS NOT NULL
              AND (bi.did_not_bat IS NOT TRUE)
              {scope_clause}
            GROUP BY bi.batting_position
            ORDER BY bi.batting_position
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_batting_by_grade(
    session: AsyncSession,
    player_id: str,
    org_id: Optional[str] = None,
    public_only: bool = False,
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    # Public views drop grades a club has opted out of sharing; admin/internal
    # callers (public_only=False) still see every grade.
    public_clause = " AND gr.is_public IS NOT FALSE" if public_only else ""
    scope_clause = scope.clause("gr.id") if _scoped(scope) else ""
    params: dict = {"pid": player_id, "org_id": org_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            SELECT
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                MAX(gr.category) AS category,
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
              {public_clause}{scope_clause}
            GROUP BY COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name))
            ORDER BY SUM(bi.runs) DESC
        """),
        params,
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


# No player plays anywhere near this many games in one real season. Cricket
# Australia bundles a club's whole pre-migration history into its earliest season
# as cumulative career-to-date totals, so that one "season" shows 100+ matches for
# a player (Keith London: 256, David Cohen: 119). A season row above this cap is a
# historical bundle, not a season — it's folded into "Prior Seasons & Adjustments"
# rather than shown as a dated season.
_HISTORICAL_BUNDLE_MATCH_CAP = 60


async def _season_by_season_scoped(
    session: AsyncSession, player_id: str, scope: GradeScope
) -> list[dict]:
    """Season-by-season built from scorecards, with out-of-scope grades left out.

    The ordinary path reads CA's season aggregates, which carry no grade at all,
    so the only way to answer "this season, but not the juniors" is to add the
    innings up ourselves. It exists so the per-season rows still reconcile with
    the scoped career header above them — a profile whose total says 1,400 runs
    over a table summing to 2,050 reads as a broken page, not as a filter.

    Season aliasing is applied first (`season_aliases`), so a club that merged
    Summer and Winter 25/26 gets the same single row it gets unfiltered.

    Season-keyed residual rows (a BetterImport season delta, a manual season
    adjustment — `_RESIDUAL_SOURCES`) are added per season on top of the
    per-game figures, exactly as `_career_residuals` adds them to the scoped
    career header. Without this a player whose only record for a season is an
    imported total has no row here at all, and the table stops reconciling
    with the header right above it (the reported 1970/71 case: header says
    338 runs, season table and every chart built from it say nothing).
    """
    params: dict = {"pid": player_id, "residual_sources": list(_RESIDUAL_SOURCES)}
    scope.bind(params)
    clause = scope.clause("g.grade_id")
    resid_clause = scope.clause("pss.grade_id")
    res = await session.execute(
        text(f"""
            WITH scoped_games AS (
                SELECT g.id AS game_id,
                       COALESCE(sa.canonical_season_id, g.season_id) AS sid
                FROM v_effective_games g
                LEFT JOIN season_aliases sa
                  ON sa.alias_season_id = g.season_id AND sa.undone_at IS NULL
                WHERE g.season_id IS NOT NULL{clause}
            ),
            bat AS (
                SELECT sg.sid,
                    COUNT(*) AS batting_innings,
                    SUM(bi.runs) AS total_runs,
                    MAX(bi.runs) AS high_score,
                    SUM(bi.not_out::int) AS not_outs,
                    SUM(bi.balls) AS balls_faced,
                    SUM(CASE WHEN bi.runs >= 50 AND bi.runs < 100 THEN 1 ELSE 0 END) AS fifties,
                    SUM(CASE WHEN bi.runs >= 100 THEN 1 ELSE 0 END) AS hundreds,
                    SUM(CASE WHEN bi.runs = 0 AND NOT bi.not_out THEN 1 ELSE 0 END) AS ducks,
                    SUM(bi.fours) AS total_fours,
                    SUM(bi.sixes) AS total_sixes
                FROM v_effective_batting_innings bi
                JOIN scoped_games sg ON sg.game_id = bi.game_id
                WHERE bi.player_id = CAST(:pid AS UUID)
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                GROUP BY sg.sid
            ),
            bowl AS (
                SELECT sg.sid,
                    SUM(bs.wickets) AS total_wickets,
                    SUM(bs.runs) AS bowling_runs_conceded,
                    SUM(bs.overs) AS total_overs,
                    SUM(FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10)) AS bowling_balls,
                    SUM(bs.maidens) AS total_maidens,
                    MAX(bs.wickets) AS best_bowling_wickets,
                    SUM(CASE WHEN bs.wickets >= 5 THEN 1 ELSE 0 END) AS five_fors,
                    (ARRAY_AGG(bs.wickets::text || '-' || bs.runs::text
                        ORDER BY bs.wickets DESC, bs.runs ASC))[1] AS best_bowling_figures
                FROM v_effective_bowling_spells bs
                JOIN scoped_games sg ON sg.game_id = bs.game_id
                WHERE bs.player_id = CAST(:pid AS UUID)
                GROUP BY sg.sid
            ),
            field AS (
                SELECT sg.sid,
                    SUM(fs.catches) AS total_catches,
                    SUM(fs.catches_wk) AS total_catches_wk,
                    SUM(GREATEST(fs.catches - fs.catches_wk, 0)) AS total_catches_non_wk,
                    SUM(fs.run_outs) AS total_run_outs,
                    SUM(fs.stumpings) AS total_stumpings
                FROM v_effective_fielding_stats fs
                JOIN scoped_games sg ON sg.game_id = fs.game_id
                WHERE fs.player_id = CAST(:pid AS UUID)
                GROUP BY sg.sid
            ),
            -- Matches is every game the player turned out in, whether or not he
            -- batted, bowled or took a catch. UNION (not UNION ALL) across the
            -- four sources so a game he did all four in still counts once.
            played AS (
                SELECT sg.sid, COUNT(DISTINCT t.game_id) AS matches
                FROM (
                    SELECT game_id FROM v_effective_batting_innings WHERE player_id = CAST(:pid AS UUID)
                    UNION SELECT game_id FROM v_effective_bowling_spells WHERE player_id = CAST(:pid AS UUID)
                    UNION SELECT game_id FROM v_effective_fielding_stats WHERE player_id = CAST(:pid AS UUID)
                    UNION SELECT game_id FROM game_appearances WHERE player_id = CAST(:pid AS UUID)
                ) t
                JOIN scoped_games sg ON sg.game_id = t.game_id
                GROUP BY sg.sid
            ),
            -- Aggregate-only rows with no scorecards behind them (an imported
            -- season, a manual season adjustment). Filtered by grade_id where
            -- one is set; exclusion semantics keep the usual grade-less rows.
            resid AS (
                SELECT COALESCE(sa.canonical_season_id, pss.season_id) AS sid,
                    SUM(pss.matches) AS matches,
                    SUM(pss.batting_innings) AS batting_innings,
                    SUM(pss.runs) AS total_runs,
                    MAX(pss.high_score) AS high_score,
                    SUM(pss.not_outs) AS not_outs,
                    SUM(pss.balls_faced) AS balls_faced,
                    SUM(pss.fifties) AS fifties,
                    SUM(pss.hundreds) AS hundreds,
                    SUM(pss.ducks) AS ducks,
                    SUM(pss.fours) AS total_fours,
                    SUM(pss.sixes) AS total_sixes,
                    SUM(pss.wickets) AS total_wickets,
                    SUM(pss.runs_conceded) AS bowling_runs_conceded,
                    SUM(pss.overs) AS total_overs,
                    SUM(pss.bowling_balls) AS bowling_balls,
                    SUM(pss.maidens) AS total_maidens,
                    MAX(pss.best_bowling_wickets) AS best_bowling_wickets,
                    (ARRAY_AGG(pss.best_bowling_figures
                        ORDER BY pss.best_bowling_wickets DESC NULLS LAST
                     ) FILTER (WHERE pss.best_bowling_figures IS NOT NULL))[1] AS best_bowling_figures,
                    SUM(pss.five_wicket_innings) AS five_fors,
                    SUM(pss.catches) AS total_catches,
                    SUM(pss.catches_wk) AS total_catches_wk,
                    SUM(pss.catches_non_wk) AS total_catches_non_wk,
                    SUM(pss.run_outs) AS total_run_outs,
                    SUM(pss.stumpings) AS total_stumpings
                FROM v_effective_player_season_stats pss
                LEFT JOIN season_aliases sa
                  ON sa.alias_season_id = pss.season_id AND sa.undone_at IS NULL
                WHERE pss.player_id = CAST(:pid AS UUID)
                  AND pss.season_id IS NOT NULL
                  AND pss.source = ANY(:residual_sources){resid_clause}
                GROUP BY COALESCE(sa.canonical_season_id, pss.season_id)
            )
            SELECT
                s.id AS season_id,
                s.name AS season_name,
                s.year,
                COALESCE(played.matches, 0) + COALESCE(resid.matches, 0) AS matches,
                COALESCE(bat.batting_innings, 0) + COALESCE(resid.batting_innings, 0) AS batting_innings,
                COALESCE(bat.total_runs, 0) + COALESCE(resid.total_runs, 0) AS total_runs,
                GREATEST(bat.high_score, resid.high_score) AS high_score,
                ROUND((COALESCE(bat.total_runs, 0) + COALESCE(resid.total_runs, 0))::numeric
                    / NULLIF((COALESCE(bat.batting_innings, 0) + COALESCE(resid.batting_innings, 0))
                             - (COALESCE(bat.not_outs, 0) + COALESCE(resid.not_outs, 0)), 0), 2) AS batting_average,
                ROUND((COALESCE(bat.total_runs, 0) + COALESCE(resid.total_runs, 0))::numeric
                    / NULLIF(COALESCE(bat.balls_faced, 0) + COALESCE(resid.balls_faced, 0), 0) * 100, 2) AS strike_rate,
                COALESCE(bat.fifties, 0) + COALESCE(resid.fifties, 0) AS fifties,
                COALESCE(bat.hundreds, 0) + COALESCE(resid.hundreds, 0) AS hundreds,
                COALESCE(bat.not_outs, 0) + COALESCE(resid.not_outs, 0) AS not_outs,
                COALESCE(bat.ducks, 0) + COALESCE(resid.ducks, 0) AS ducks,
                COALESCE(bat.total_fours, 0) + COALESCE(resid.total_fours, 0) AS total_fours,
                COALESCE(bat.total_sixes, 0) + COALESCE(resid.total_sixes, 0) AS total_sixes,
                COALESCE(bowl.total_wickets, 0) + COALESCE(resid.total_wickets, 0) AS total_wickets,
                COALESCE(bowl.bowling_runs_conceded, 0) + COALESCE(resid.bowling_runs_conceded, 0) AS bowling_runs_conceded,
                COALESCE(bowl.total_overs, 0) + COALESCE(resid.total_overs, 0) AS total_overs,
                ROUND((COALESCE(bowl.bowling_runs_conceded, 0) + COALESCE(resid.bowling_runs_conceded, 0))::numeric
                    / NULLIF(COALESCE(bowl.total_wickets, 0) + COALESCE(resid.total_wickets, 0), 0), 2) AS bowling_average,
                ROUND((COALESCE(bowl.bowling_runs_conceded, 0) + COALESCE(resid.bowling_runs_conceded, 0))::numeric
                    / NULLIF(COALESCE(bowl.bowling_balls, 0) + COALESCE(resid.bowling_balls, 0), 0) * 6, 2) AS economy,
                GREATEST(bowl.best_bowling_wickets, resid.best_bowling_wickets) AS best_bowling_wickets,
                -- The figures string follows whichever side holds the better
                -- wicket count; a residual's figures are the club's own book
                -- for this season, so they're safe at season scope.
                CASE WHEN resid.best_bowling_wickets IS NOT NULL
                          AND (bowl.best_bowling_wickets IS NULL
                               OR resid.best_bowling_wickets > bowl.best_bowling_wickets)
                          AND resid.best_bowling_figures IS NOT NULL
                     THEN resid.best_bowling_figures
                     ELSE bowl.best_bowling_figures END AS best_bowling_figures,
                COALESCE(bowl.five_fors, 0) + COALESCE(resid.five_fors, 0) AS five_fors,
                COALESCE(bowl.total_maidens, 0) + COALESCE(resid.total_maidens, 0) AS total_maidens,
                COALESCE(field.total_catches, 0) + COALESCE(resid.total_catches, 0) AS total_catches,
                COALESCE(field.total_catches_wk, 0) + COALESCE(resid.total_catches_wk, 0) AS total_catches_wk,
                COALESCE(field.total_catches_non_wk, 0) + COALESCE(resid.total_catches_non_wk, 0) AS total_catches_non_wk,
                COALESCE(field.total_run_outs, 0) + COALESCE(resid.total_run_outs, 0) AS total_run_outs,
                COALESCE(field.total_stumpings, 0) + COALESCE(resid.total_stumpings, 0) AS total_stumpings
            FROM seasons s
            LEFT JOIN played ON played.sid = s.id
            LEFT JOIN bat ON bat.sid = s.id
            LEFT JOIN bowl ON bowl.sid = s.id
            LEFT JOIN field ON field.sid = s.id
            LEFT JOIN resid ON resid.sid = s.id
            WHERE played.sid IS NOT NULL OR bat.sid IS NOT NULL
               OR bowl.sid IS NOT NULL OR field.sid IS NOT NULL
               OR resid.sid IS NOT NULL
            ORDER BY s.year DESC NULLS LAST, s.name
        """),
        params,
    )
    return [dict(r) for r in res.mappings()]


async def get_season_by_season(
    session: AsyncSession,
    player_id: str,
    include_prior: bool = False,
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    if _scoped(scope):
        # No "Prior Seasons & Adjustments" row on the scoped path: that lump is
        # the NULL-season career residual, which by definition belongs to no
        # season and so has no row to sit in here. It is still counted in the
        # scoped career header (see _career_residuals), which is where it has
        # always actually mattered.
        return await _season_by_season_scoped(session, player_id, scope)
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
    rows = [dict(r) for r in result.mappings()]

    # Pull out CA's pre-migration "bundle" seasons (cumulative career totals dumped
    # on the earliest season — see _HISTORICAL_BUNDLE_MATCH_CAP). They aren't real
    # seasons, so they're dropped from the per-season list (and the charts, which
    # key on season_id) and folded into the "Prior Seasons & Adjustments" lump
    # below, keeping the career header reconciled.
    bundle_ids = [str(r["season_id"]) for r in rows
                  if (r.get("matches") or 0) > _HISTORICAL_BUNDLE_MATCH_CAP]
    if bundle_ids:
        _bundle_set = set(bundle_ids)
        rows = [r for r in rows if str(r["season_id"]) not in _bundle_set]

    # Career-level (NULL-season) import / manual-career rows can't be attached to
    # a season, so the JOIN above drops them. On the player profile (include_prior)
    # surface them — with any historical bundle folded in — as a single "Prior
    # Seasons & Adjustments" row at the bottom, so the per-season rows + this row
    # reconcile to the career totals in the header. Off by default so
    # season-trajectory consumers (BetterIQ) get real seasons only.
    if not include_prior:
        return rows

    prior_where = "player_id = :pid AND season_id IS NULL"
    prior_params: dict = {"pid": player_id}
    if bundle_ids:
        prior_where = ("player_id = :pid AND (season_id IS NULL "
                       "OR season_id::text = ANY(:bundle_ids))")
        prior_params["bundle_ids"] = bundle_ids

    prior_res = await session.execute(
        text(f"""
            SELECT
                SUM(matches) AS matches,
                SUM(batting_innings) AS batting_innings,
                SUM(runs) AS total_runs,
                MAX(high_score) AS high_score,
                ROUND(SUM(runs)::numeric / NULLIF(SUM(batting_innings) - SUM(not_outs), 0), 2) AS batting_average,
                ROUND(SUM(runs)::numeric / NULLIF(SUM(balls_faced), 0) * 100, 2) AS strike_rate,
                SUM(fifties) AS fifties,
                SUM(hundreds) AS hundreds,
                SUM(not_outs) AS not_outs,
                SUM(ducks) AS ducks,
                SUM(fours) AS total_fours,
                SUM(sixes) AS total_sixes,
                SUM(wickets) AS total_wickets,
                SUM(runs_conceded) AS bowling_runs_conceded,
                SUM(overs) AS total_overs,
                ROUND(SUM(runs_conceded)::numeric / NULLIF(SUM(wickets), 0), 2) AS bowling_average,
                ROUND(SUM(runs_conceded)::numeric / NULLIF(SUM(bowling_balls), 0) * 6, 2) AS economy,
                MAX(best_bowling_wickets) AS best_bowling_wickets,
                (ARRAY_AGG(best_bowling_figures
                    ORDER BY best_bowling_wickets DESC NULLS LAST,
                             NULLIF(SPLIT_PART(best_bowling_figures, '-', 2), '')::integer ASC NULLS LAST
                 ) FILTER (WHERE best_bowling_figures IS NOT NULL AND best_bowling_figures ~ '^[0-9]+-[0-9]+$'))[1] AS best_bowling_figures,
                SUM(five_wicket_innings) AS five_fors,
                SUM(maidens) AS total_maidens,
                SUM(catches) AS total_catches,
                SUM(catches_wk) AS total_catches_wk,
                SUM(catches_non_wk) AS total_catches_non_wk,
                SUM(run_outs) AS total_run_outs,
                SUM(stumpings) AS total_stumpings
            FROM v_effective_player_season_stats
            WHERE {prior_where}
        """),
        prior_params
    )
    prior = dict(prior_res.mappings().first() or {})
    if (prior.get("matches") or prior.get("total_runs") or prior.get("total_wickets")
            or prior.get("total_catches")):
        prior["season_id"] = None
        prior["season_name"] = "Prior Seasons & Adjustments"
        prior["year"] = None
        rows.append(prior)

    return rows


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


async def get_player_partnerships(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
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
            FROM v_effective_partnerships pt
            JOIN v_effective_games g ON g.id = pt.game_id
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE (pt.batter1_id = :pid OR pt.batter2_id = :pid)
              AND pt.runs IS NOT NULL AND pt.runs > 0
              {scope_clause}
            GROUP BY
                CASE WHEN pt.batter1_id = :pid THEN pt.batter2_id::text ELSE pt.batter1_id::text END,
                CASE WHEN pt.batter1_id = :pid
                     THEN COALESCE(p2.display_name_override, p2.name)
                     ELSE COALESCE(p1.display_name_override, p1.name)
                END
            ORDER BY total_runs DESC
            LIMIT 20
        """),
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_game_fall_of_wickets(session: AsyncSession, game_id: str, org_id: str | None = None) -> list[dict]:
    # p.organisation_id scoping (when org_id is known) stops a player_id that
    # belongs to ANOTHER club's roster from rendering as if the fall of
    # wicket were ours — e.g. an opposition batter who, under a shared
    # participant GUID, also has (or once had) a `players` row in our own
    # org: a real reported case had 8 of an opponent's 10 wickets rendering
    # under the names of our own past/unrelated players. `:org_id IS NULL`
    # keeps the join unscoped for a caller with no org context.
    result = await session.execute(
        text("""
            SELECT
                fow.wicket_number,
                fow.innings_number,
                fow.score_at_fall,
                fow.overs_at_fall,
                COALESCE(p.display_name_override, p.name, fow.batter_name) AS player_name,
                p.id::text AS player_id,
                fow.batter_name
            FROM v_effective_fall_of_wickets fow
            LEFT JOIN players p ON p.id = fow.player_id
                AND (CAST(:org_id AS uuid) IS NULL OR p.organisation_id = CAST(:org_id AS uuid))
            WHERE fow.game_id = :gid
            ORDER BY fow.innings_number, fow.wicket_number
        """),
        {"gid": game_id, "org_id": org_id},
    )
    rows = [dict(r) for r in result.mappings()]

    # A game shared between two both-synced clubs can carry two physical rows
    # for the same wicket in the base table — one from each club's own sync.
    # Org-scoping the join above stops a cross-club row from being MISLINKED
    # to one of our players, but the duplicate itself still needs collapsing
    # to one row per wicket; keep whichever has the most useful info.
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (r["innings_number"], r["wicket_number"])
        score = (2 if r["player_id"] else 0) + (1 if (r["player_name"] or r["batter_name"]) else 0)
        if key not in best or score > best[key][1]:
            best[key] = (r, score)
    out = [r for r, _ in best.values()]
    for r in out:
        r.pop("batter_name", None)
    out.sort(key=lambda r: (r["innings_number"], r["wicket_number"]))
    return out


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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_runs", "average", "strike_rate", "total_sixes",
        "total_fours", "ducks", "high_score", "fifties", "hundreds", "innings",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_runs"

    season_ids = await resolve_season_filter(session, org_id, season_id)

    # A grade the viewer picked by name beats the category default. Someone who
    # has chosen "Under 14s" from the grade dropdown plainly wants the juniors,
    # and silently returning an empty board would read as broken.
    if grade_id or grade_name:
        scope = None

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = bi.game_id AND gap.player_id = bi.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if _scoped(scope):
        # Bound once for every branch below: the finals and captain branches
        # interpolate scope_clause directly, and a clause whose parameter was
        # never bound fails at execute time, not at import. The SIRS queries
        # bind their own inside _sirs_base_clauses.
        scope.bind(params)
    if gender:
        params["gender"] = gender
    if season_ids:
        params["season_ids"] = season_ids

    # Import residuals (BetterImport historical CSVs) are career/season aggregate
    # counts, not per-innings detail — they can't say whether an innings was a
    # captain's or a final, so they're only blended into the plain grade view.
    include_import = not captain_only and not finals_only

    if grade_id:
        params["grade_id"] = grade_id
        import_cte = ""
        import_join = ""
        qualify_clause = "q.player_id IS NOT NULL"
        if include_import:
            import_grade_name = await _resolve_grade_name(session, org_id, grade_id)
            if import_grade_name:
                params["grade_name"] = import_grade_name
                import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
                qualify_clause = "q.player_id IS NOT NULL OR it.player_id IS NOT NULL"
                import_cte = f"""
                , import_totals AS (
                    SELECT ied.player_id,
                        COALESCE(SUM(ied.matches), 0) AS games,
                        COALESCE(SUM(ied.batting_innings), 0) AS innings,
                        COALESCE(SUM(ied.runs), 0) AS total_runs,
                        MAX(ied.high_score) AS high_score,
                        COALESCE(SUM(ied.fifties), 0) AS fifties,
                        COALESCE(SUM(ied.hundreds), 0) AS hundreds,
                        COALESCE(SUM(ied.ducks), 0) AS ducks,
                        COALESCE(SUM(ied.fours), 0) AS total_fours,
                        COALESCE(SUM(ied.sixes), 0) AS total_sixes,
                        COALESCE(SUM(ied.balls_faced), 0) AS total_balls,
                        COALESCE(SUM(ied.not_outs), 0) AS not_outs
                    FROM import_effective_deltas ied
                    WHERE ied.organisation_id = :org_id AND {_IMPORT_GRADE_MATCH}{import_season_clause}
                    GROUP BY ied.player_id
                )
                """
                import_join = "LEFT JOIN import_totals it ON it.player_id = p.id"
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id{captain_join}
                WHERE g.grade_id = :grade_id
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb'){finals_clause}
            ){import_cte}
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(q.player_id) + COALESCE(MAX(it.innings), 0) AS innings,
                    COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0) AS total_runs,
                    GREATEST(MAX(q.runs), MAX(it.high_score)) AS high_score,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0))::numeric
                        / NULLIF((COUNT(q.player_id) + COALESCE(MAX(it.innings), 0))
                                 - (COALESCE(SUM(q.not_out::int), 0) + COALESCE(MAX(it.not_outs), 0)), 0), 2) AS average,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0))::numeric
                        / NULLIF(COALESCE(SUM(q.balls), 0) + COALESCE(MAX(it.total_balls), 0), 0) * 100, 2) AS strike_rate,
                    SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) + COALESCE(MAX(it.fifties), 0) AS fifties,
                    SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) + COALESCE(MAX(it.hundreds), 0) AS hundreds,
                    SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) + COALESCE(MAX(it.ducks), 0) AS ducks,
                    COUNT(DISTINCT q.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(q.fours), 0) + COALESCE(MAX(it.total_fours), 0) AS total_fours,
                    COALESCE(SUM(q.sixes), 0) + COALESCE(MAX(it.total_sixes), 0) AS total_sixes
                FROM players p
                LEFT JOIN qualifying q ON q.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        if min_runs > 0:
            base += " WHERE total_runs >= :min_runs"
            params["min_runs"] = min_runs
        base += f" ORDER BY {sort_by} DESC NULLS LAST LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        import_cte = ""
        import_join = ""
        qualify_clause = "q.player_id IS NOT NULL"
        if include_import:
            qualify_clause = "q.player_id IS NOT NULL OR it.player_id IS NOT NULL"
            import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
            import_cte = f"""
            , import_totals AS (
                SELECT ied.player_id,
                    COALESCE(SUM(ied.matches), 0) AS games,
                    COALESCE(SUM(ied.batting_innings), 0) AS innings,
                    COALESCE(SUM(ied.runs), 0) AS total_runs,
                    MAX(ied.high_score) AS high_score,
                    COALESCE(SUM(ied.fifties), 0) AS fifties,
                    COALESCE(SUM(ied.hundreds), 0) AS hundreds,
                    COALESCE(SUM(ied.ducks), 0) AS ducks,
                    COALESCE(SUM(ied.fours), 0) AS total_fours,
                    COALESCE(SUM(ied.sixes), 0) AS total_sixes,
                    COALESCE(SUM(ied.balls_faced), 0) AS total_balls,
                    COALESCE(SUM(ied.not_outs), 0) AS not_outs
                FROM import_effective_deltas ied
                WHERE ied.organisation_id = :org_id AND {_IMPORT_GRADE_MATCH}{import_season_clause}
                GROUP BY ied.player_id
            )
            """
            import_join = "LEFT JOIN import_totals it ON it.player_id = p.id"
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id{captain_join}
                WHERE {_GRADE_MATCH}{season_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb'){finals_clause}
            ){import_cte}
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(q.player_id) + COALESCE(MAX(it.innings), 0) AS innings,
                    COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0) AS total_runs,
                    GREATEST(MAX(q.runs), MAX(it.high_score)) AS high_score,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0))::numeric
                        / NULLIF((COUNT(q.player_id) + COALESCE(MAX(it.innings), 0))
                                 - (COALESCE(SUM(q.not_out::int), 0) + COALESCE(MAX(it.not_outs), 0)), 0), 2) AS average,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(it.total_runs), 0))::numeric
                        / NULLIF(COALESCE(SUM(q.balls), 0) + COALESCE(MAX(it.total_balls), 0), 0) * 100, 2) AS strike_rate,
                    SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) + COALESCE(MAX(it.fifties), 0) AS fifties,
                    SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) + COALESCE(MAX(it.hundreds), 0) AS hundreds,
                    SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) + COALESCE(MAX(it.ducks), 0) AS ducks,
                    COUNT(DISTINCT q.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(q.fours), 0) + COALESCE(MAX(it.total_fours), 0) AS total_fours,
                    COALESCE(SUM(q.sixes), 0) + COALESCE(MAX(it.total_sixes), 0) AS total_sixes
                FROM players p
                LEFT JOIN qualifying q ON q.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        if min_runs > 0:
            base += " WHERE total_runs >= :min_runs"
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
                  AND g.is_final = TRUE{season_clause}{scope_clause}
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
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{scope_clause}
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

    if _scoped(scope):
        # The plain all-grades board normally reads CA's season aggregates, which
        # carry no grade at all — so excluding a category means adding the
        # innings up from scorecards instead, then blending back the aggregate-only
        # residuals (imports, adjustments) that have no per-innings rows.
        # Scoped through `v_effective_games.season_id` rather than a grades join,
        # so a manual game entered without a grade is not silently dropped.
        season_clause = " AND g.season_id = ANY(:season_ids)" if season_ids else ""
        residual_cte = _residual_totals_cte(scope, season_ids, params)
        base = f"""
            WITH qualifying AS (
                SELECT bi.player_id, bi.game_id, bi.runs, bi.balls, bi.fours, bi.sixes, bi.not_out
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN seasons s ON s.id = g.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{scope_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
            ), {residual_cte}
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(q.player_id) + COALESCE(MAX(rt.innings), 0) AS innings,
                    COALESCE(SUM(q.runs), 0) + COALESCE(MAX(rt.total_runs), 0) AS total_runs,
                    GREATEST(MAX(q.runs), MAX(rt.high_score)) AS high_score,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(rt.total_runs), 0))::numeric
                        / NULLIF((COUNT(q.player_id) + COALESCE(MAX(rt.innings), 0))
                                 - (COALESCE(SUM(q.not_out::int), 0) + COALESCE(MAX(rt.not_outs), 0)), 0), 2) AS average,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(rt.total_runs), 0))::numeric
                        / NULLIF(COALESCE(SUM(q.balls), 0) + COALESCE(MAX(rt.total_balls), 0), 0) * 100, 2) AS strike_rate,
                    SUM(CASE WHEN q.runs >= 50 AND q.runs < 100 THEN 1 ELSE 0 END) + COALESCE(MAX(rt.fifties), 0) AS fifties,
                    SUM(CASE WHEN q.runs >= 100 THEN 1 ELSE 0 END) + COALESCE(MAX(rt.hundreds), 0) AS hundreds,
                    SUM(CASE WHEN q.runs = 0 AND NOT q.not_out THEN 1 ELSE 0 END) + COALESCE(MAX(rt.ducks), 0) AS ducks,
                    COUNT(DISTINCT q.game_id) + COALESCE(MAX(rt.games), 0) AS games,
                    COALESCE(SUM(q.fours), 0) + COALESCE(MAX(rt.total_fours), 0) AS total_fours,
                    COALESCE(SUM(q.sixes), 0) + COALESCE(MAX(rt.total_sixes), 0) AS total_sixes
                FROM players p
                LEFT JOIN qualifying q ON q.player_id = p.id
                LEFT JOIN residual_totals rt ON rt.player_id = p.id
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND (q.player_id IS NOT NULL OR rt.player_id IS NOT NULL)
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        if min_runs > 0:
            base += " WHERE total_runs >= :min_runs"
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
        -- No seasons join: career-level (NULL-season) import / manual-career rows
        -- (the "Prior Seasons & Adjustments" bucket) belong in the all-seasons
        -- total. A specific-season filter below still excludes them (a NULL
        -- season never matches the season filter). Org scope is the player join.
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    ALLOWED_SORTS = {
        "total_wickets", "average", "economy", "best_figures_wickets",
        "total_maidens", "five_fors",
    }
    if sort_by not in ALLOWED_SORTS:
        sort_by = "total_wickets"

    season_ids = await resolve_season_filter(session, org_id, season_id)

    # An explicitly picked grade beats the category default — see the note in
    # get_batting_leaderboard_extended.
    if grade_id or grade_name:
        scope = None

    finals_clause = " AND g.is_final = TRUE" if finals_only else ""
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    captain_join = (" JOIN game_appearances gap ON gap.game_id = bs.game_id AND gap.player_id = bs.player_id AND gap.is_captain = TRUE" if captain_only else "")
    gender_clause = f" AND p.gender = :gender" if gender else ""
    if overseas == "only":
        overseas_clause = " AND p.is_overseas = TRUE"
    elif overseas == "exclude":
        overseas_clause = " AND (p.is_overseas IS NULL OR p.is_overseas = FALSE)"
    else:
        overseas_clause = ""
    params: dict = {"org_id": org_id, "limit": limit}
    if _scoped(scope):
        # Bound once for every branch below: the finals and captain branches
        # interpolate scope_clause directly, and a clause whose parameter was
        # never bound fails at execute time, not at import. The SIRS queries
        # bind their own inside _sirs_base_clauses.
        scope.bind(params)
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

    # See the equivalent note in get_batting_leaderboard_extended: import residuals
    # are aggregate counts with no per-spell detail, so they can't be attributed
    # to a final or a captain's spell and are only blended into the plain grade view.
    include_import = not captain_only and not finals_only

    def _import_bowling_cte(grade_match_sql, import_season_clause):
        return f"""
        , import_totals AS (
            SELECT ied.player_id,
                COALESCE(SUM(ied.matches), 0) AS games,
                COALESCE(SUM(ied.wickets), 0) AS total_wickets,
                COALESCE(SUM(ied.runs_conceded), 0) AS total_runs_conceded,
                COALESCE(SUM(ied.overs), 0) AS total_overs,
                COALESCE(SUM(ied.maidens), 0) AS total_maidens,
                COALESCE(SUM(ied.five_wicket_innings), 0) AS five_fors
            FROM import_effective_deltas ied
            WHERE ied.organisation_id = :org_id AND {grade_match_sql}{import_season_clause}
            GROUP BY ied.player_id
        ),
        import_best AS (
            SELECT DISTINCT ON (ied.player_id)
                ied.player_id, ied.best_bowling_wickets, ied.best_bowling_figures
            FROM import_effective_deltas ied
            WHERE ied.organisation_id = :org_id AND {grade_match_sql}{import_season_clause}
              AND ied.best_bowling_wickets IS NOT NULL
            ORDER BY ied.player_id, ied.best_bowling_wickets DESC
        )
        """

    if grade_id:
        params["grade_id"] = grade_id
        import_cte = ""
        import_join = ""
        qualify_clause = "bq.player_id IS NOT NULL"
        if include_import:
            import_grade_name = await _resolve_grade_name(session, org_id, grade_id)
            if import_grade_name:
                params["grade_name"] = import_grade_name
                import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
                qualify_clause = "bq.player_id IS NOT NULL OR it.player_id IS NOT NULL"
                import_cte = _import_bowling_cte(_IMPORT_GRADE_MATCH, import_season_clause)
                import_join = ("LEFT JOIN import_totals it ON it.player_id = p.id "
                               "LEFT JOIN import_best ib ON ib.player_id = p.id")
        base = f"""
            WITH bowling_qualifying AS (
                SELECT bs.player_id, bs.game_id, bs.wickets, bs.runs, bs.overs, bs.maidens
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id{captain_join}
                WHERE g.grade_id = :grade_id{finals_clause}
            ),
            best_spell AS (
                SELECT DISTINCT ON (bq.player_id)
                    bq.player_id,
                    bq.wickets AS best_figures_wickets,
                    bq.runs AS best_figures_runs,
                    bq.wickets::text || '/' || bq.runs::text AS best_bowling_figures
                FROM bowling_qualifying bq
                ORDER BY bq.player_id, bq.wickets DESC, bq.runs ASC
            ){import_cte}
            SELECT
                player_id, name, games, total_wickets, average, economy, total_maidens, total_overs, five_fors,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_wkts ELSE im_wkts END AS best_figures_wickets,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_runs ELSE NULL END AS best_figures_runs,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_bb ELSE im_bb END AS best_bowling_figures
            FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT bq.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(bq.wickets), 0) + COALESCE(MAX(it.total_wickets), 0) AS total_wickets,
                    ROUND((COALESCE(SUM(bq.runs), 0) + COALESCE(MAX(it.total_runs_conceded), 0))::numeric
                        / NULLIF(COALESCE(SUM(bq.wickets), 0) + COALESCE(MAX(it.total_wickets), 0), 0), 2) AS average,
                    ROUND((COALESCE(SUM(bq.runs), 0) + COALESCE(MAX(it.total_runs_conceded), 0))::numeric
                        / NULLIF(COALESCE(SUM(bq.overs), 0) + COALESCE(MAX(it.total_overs), 0), 0), 2) AS economy,
                    COALESCE(SUM(bq.maidens), 0) + COALESCE(MAX(it.total_maidens), 0) AS total_maidens,
                    COALESCE(SUM(bq.overs), 0) + COALESCE(MAX(it.total_overs), 0) AS total_overs,
                    COALESCE(SUM(CASE WHEN bq.wickets >= 5 THEN 1 ELSE 0 END), 0) + COALESCE(MAX(it.five_fors), 0) AS five_fors,
                    MAX(bsf.best_figures_wickets) AS sc_wkts,
                    MAX(bsf.best_figures_runs) AS sc_runs,
                    MAX(bsf.best_bowling_figures) AS sc_bb,
                    MAX(ib.best_bowling_wickets) AS im_wkts,
                    MAX(ib.best_bowling_figures) AS im_bb
                FROM players p
                LEFT JOIN bowling_qualifying bq ON bq.player_id = p.id
                LEFT JOIN best_spell bsf ON bsf.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("total_overs >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("total_wickets >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " WHERE " + " AND ".join(having_clauses)
        base += f" {order_clause} LIMIT :limit"
        result = await session.execute(text(base), params)
        return [dict(r) for r in result.mappings()]

    if grade_name:
        params["grade_name"] = grade_name
        season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""
        import_cte = ""
        import_join = ""
        qualify_clause = "bq.player_id IS NOT NULL"
        if include_import:
            qualify_clause = "bq.player_id IS NOT NULL OR it.player_id IS NOT NULL"
            import_season_clause = " AND ied.season_id = ANY(:season_ids)" if season_ids else ""
            import_cte = _import_bowling_cte(_IMPORT_GRADE_MATCH, import_season_clause)
            import_join = ("LEFT JOIN import_totals it ON it.player_id = p.id "
                           "LEFT JOIN import_best ib ON ib.player_id = p.id")
        base = f"""
            WITH bowling_qualifying AS (
                SELECT bs.player_id, bs.game_id, bs.wickets, bs.runs, bs.overs, bs.maidens
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id{captain_join}
                WHERE {_GRADE_MATCH}{season_clause}{finals_clause}
            ),
            best_spell AS (
                SELECT DISTINCT ON (bq.player_id)
                    bq.player_id,
                    bq.wickets AS best_figures_wickets,
                    bq.runs AS best_figures_runs,
                    bq.wickets::text || '/' || bq.runs::text AS best_bowling_figures
                FROM bowling_qualifying bq
                ORDER BY bq.player_id, bq.wickets DESC, bq.runs ASC
            ){import_cte}
            SELECT
                player_id, name, games, total_wickets, average, economy, total_maidens, total_overs, five_fors,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_wkts ELSE im_wkts END AS best_figures_wickets,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_runs ELSE NULL END AS best_figures_runs,
                CASE WHEN COALESCE(sc_wkts, -1) >= COALESCE(im_wkts, -1) THEN sc_bb ELSE im_bb END AS best_bowling_figures
            FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT bq.game_id) + COALESCE(MAX(it.games), 0) AS games,
                    COALESCE(SUM(bq.wickets), 0) + COALESCE(MAX(it.total_wickets), 0) AS total_wickets,
                    ROUND((COALESCE(SUM(bq.runs), 0) + COALESCE(MAX(it.total_runs_conceded), 0))::numeric
                        / NULLIF(COALESCE(SUM(bq.wickets), 0) + COALESCE(MAX(it.total_wickets), 0), 0), 2) AS average,
                    ROUND((COALESCE(SUM(bq.runs), 0) + COALESCE(MAX(it.total_runs_conceded), 0))::numeric
                        / NULLIF(COALESCE(SUM(bq.overs), 0) + COALESCE(MAX(it.total_overs), 0), 0), 2) AS economy,
                    COALESCE(SUM(bq.maidens), 0) + COALESCE(MAX(it.total_maidens), 0) AS total_maidens,
                    COALESCE(SUM(bq.overs), 0) + COALESCE(MAX(it.total_overs), 0) AS total_overs,
                    COALESCE(SUM(CASE WHEN bq.wickets >= 5 THEN 1 ELSE 0 END), 0) + COALESCE(MAX(it.five_fors), 0) AS five_fors,
                    MAX(bsf.best_figures_wickets) AS sc_wkts,
                    MAX(bsf.best_figures_runs) AS sc_runs,
                    MAX(bsf.best_bowling_figures) AS sc_bb,
                    MAX(ib.best_bowling_wickets) AS im_wkts,
                    MAX(ib.best_bowling_figures) AS im_bb
                FROM players p
                LEFT JOIN bowling_qualifying bq ON bq.player_id = p.id
                LEFT JOIN best_spell bsf ON bsf.player_id = p.id
                {import_join}
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND ({qualify_clause})
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        having_clauses = []
        if min_overs > 0:
            having_clauses.append("total_overs >= :min_overs")
            params["min_overs"] = min_overs
        if min_wickets > 0:
            having_clauses.append("total_wickets >= :min_wickets")
            params["min_wickets"] = min_wickets
        if having_clauses:
            base += " WHERE " + " AND ".join(having_clauses)
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

    if _scoped(scope):
        # See get_batting_leaderboard_extended's equivalent branch.
        season_clause = " AND g.season_id = ANY(:season_ids)" if season_ids else ""
        residual_cte = _residual_totals_cte(scope, season_ids, params)
        base = f"""
            WITH {residual_cte}, qualifying AS (
                SELECT bs.player_id, bs.game_id, bs.wickets, bs.runs, bs.maidens, bs.overs,
                    FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10) AS balls
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN seasons s ON s.id = g.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID){season_clause}{scope_clause}
            )
            SELECT * FROM (
                SELECT
                    p.id AS player_id,
                    COALESCE(p.display_name_override, p.name) AS name,
                    COUNT(DISTINCT q.game_id) + COALESCE(MAX(rt.games), 0) AS games,
                    COALESCE(SUM(q.wickets), 0) + COALESCE(MAX(rt.total_wickets), 0) AS total_wickets,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(rt.bowling_runs), 0))::numeric
                        / NULLIF(COALESCE(SUM(q.wickets), 0) + COALESCE(MAX(rt.total_wickets), 0), 0), 2) AS average,
                    ROUND((COALESCE(SUM(q.runs), 0) + COALESCE(MAX(rt.bowling_runs), 0))::numeric
                        / NULLIF(COALESCE(SUM(q.balls), 0) + COALESCE(MAX(rt.bowling_balls), 0), 0) * 6, 2) AS economy,
                    GREATEST(MAX(q.wickets), MAX(rt.best_bowling_wickets)) AS best_figures_wickets,
                    -- Best figures are named from the per-spell rows only: a
                    -- residual branch knows how many wickets but its figures
                    -- string belongs to a spell we hold no scorecard for, so
                    -- pairing it with a blended maximum could print the wrong
                    -- innings' runs against the right wicket count.
                    (ARRAY_AGG(q.wickets::text || '-' || q.runs::text
                        ORDER BY q.wickets DESC NULLS LAST, q.runs ASC NULLS LAST)
                     FILTER (WHERE q.wickets IS NOT NULL))[1] AS best_bowling_figures,
                    (ARRAY_AGG(q.runs ORDER BY q.wickets DESC NULLS LAST, q.runs ASC NULLS LAST)
                     FILTER (WHERE q.wickets IS NOT NULL))[1] AS best_figures_runs,
                    COALESCE(SUM(q.maidens), 0) + COALESCE(MAX(rt.total_maidens), 0) AS total_maidens,
                    COALESCE(SUM(q.overs), 0) + COALESCE(MAX(rt.total_overs), 0) AS total_overs,
                    COALESCE(SUM(CASE WHEN q.wickets >= 5 THEN 1 ELSE 0 END), 0)
                        + COALESCE(MAX(rt.five_fors), 0) AS five_fors,
                    COALESCE(SUM(q.balls), 0) + COALESCE(MAX(rt.bowling_balls), 0) AS total_balls
                FROM players p
                LEFT JOIN qualifying q ON q.player_id = p.id
                LEFT JOIN residual_totals rt ON rt.player_id = p.id
                WHERE p.organisation_id = :org_id{gender_clause}{overseas_clause}
                  AND (q.player_id IS NOT NULL OR rt.player_id IS NOT NULL)
                GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ) t
        """
        having = []
        if min_wickets > 0:
            having.append("total_wickets >= :min_wickets")
            params["min_wickets"] = min_wickets
        if min_overs > 0:
            having.append("total_balls >= :min_overs * 6")
            params["min_overs"] = min_overs
        if having:
            base += " WHERE " + " AND ".join(having)
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
        -- No seasons join: career-level (NULL-season) import / manual-career rows
        -- (the "Prior Seasons & Adjustments" bucket) belong in the all-seasons
        -- total. A specific-season filter below still excludes them (a NULL
        -- season never matches the season filter). Org scope is the player join.
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


async def get_bowling_by_grade(
    session: AsyncSession,
    player_id: str,
    org_id: Optional[str] = None,
    public_only: bool = False,
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    public_clause = " AND gr.is_public IS NOT FALSE" if public_only else ""
    scope_clause = scope.clause("gr.id") if _scoped(scope) else ""
    params: dict = {"pid": player_id, "org_id": org_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            WITH grade_spells AS (
                SELECT
                    COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                    gr.category AS category,
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
                  {public_clause}{scope_clause}
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
                MAX(gs.category) AS category,
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
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_player_by_opposition(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
            WITH player_org AS (
                SELECT organisation_id FROM players WHERE id = CAST(:pid AS UUID)
            ),
            player_game_ids AS (
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
            excluded_orgs AS (
                -- A game whose opp_key resolves to the player's OWN org, or to
                -- a predecessor club folded into it via the club-merger tool
                -- (services/org_merge.py — e.g. a derby played against a club
                -- before a real-world merger), isn't a real opponent any more.
                -- The predecessor org is soft-archived, not deleted, so its id
                -- stays resolvable in opp_org_id forever unless excluded here.
                SELECT organisation_id::text AS oid FROM player_org
                UNION
                SELECT oml.source_org_id::text
                FROM org_merge_logs oml
                JOIN player_org po ON po.organisation_id = oml.target_org_id
                WHERE oml.source_org_id IS NOT NULL
            ),
            player_games_raw AS (
                -- opp_key/opp_name priority: home_org_id/away_org_id FIRST —
                -- the reliable, per-club signal set at sync time (migration
                -- 167) for which side of a shared games.id row is OUR
                -- player's club, so the opponent is unambiguously the other
                -- side. opp_org_id/opp_club_name are a single pair of columns
                -- stamped once by whichever club's sync created the shared
                -- row first — for a player whose own club synced SECOND,
                -- those columns hold that OTHER club's perspective, which can
                -- literally equal our own org id (showing our own club as
                -- its own opposition). Only fall back to opp_org_id/
                -- opp_club_name, then team-name matching, when home_org_id/
                -- away_org_id haven't been backfilled yet for this row.
                SELECT
                    pgi.game_id,
                    g.played_at,
                    COALESCE(
                        CASE
                            WHEN g.home_org_id = po.organisation_id THEN COALESCE(g.away_org_id::text, g.away_club)
                            WHEN g.away_org_id = po.organisation_id THEN COALESCE(g.home_org_id::text, g.home_club)
                            ELSE NULL
                        END,
                        g.opp_org_id,
                        CASE
                            WHEN ga.team_name = g.home_team THEN g.away_club
                            WHEN ga.team_name = g.away_team THEN g.home_club
                            ELSE g.opp_club_name
                        END
                    ) AS opp_key,
                    COALESCE(
                        CASE
                            WHEN g.home_org_id = po.organisation_id THEN g.away_club
                            WHEN g.away_org_id = po.organisation_id THEN g.home_club
                            ELSE NULL
                        END,
                        g.opp_club_name,
                        CASE
                            WHEN ga.team_name = g.home_team THEN g.away_club
                            WHEN ga.team_name = g.away_team THEN g.home_club
                            ELSE NULL
                        END
                    ) AS opp_name,
                    -- g.result is ALSO relative to whichever club's sync
                    -- wrote it first (classify_match_result computes it
                    -- against that syncing org's own team) — same
                    -- single-column-can't-hold-two-perspectives issue as
                    -- opp_org_id above. g.winning_team is the actual winning
                    -- team's name (neutral), so it's re-derived against THIS
                    -- player's own org/side rather than trusted as stored.
                    CASE
                        WHEN g.winning_team IS NULL THEN g.result
                        WHEN g.home_org_id = po.organisation_id AND g.winning_team = g.home_team THEN 'WIN'
                        WHEN g.home_org_id = po.organisation_id AND g.winning_team = g.away_team THEN 'LOSS'
                        WHEN g.away_org_id = po.organisation_id AND g.winning_team = g.away_team THEN 'WIN'
                        WHEN g.away_org_id = po.organisation_id AND g.winning_team = g.home_team THEN 'LOSS'
                        WHEN ga.team_name = g.home_team AND g.winning_team = g.home_team THEN 'WIN'
                        WHEN ga.team_name = g.home_team AND g.winning_team = g.away_team THEN 'LOSS'
                        WHEN ga.team_name = g.away_team AND g.winning_team = g.away_team THEN 'WIN'
                        WHEN ga.team_name = g.away_team AND g.winning_team = g.home_team THEN 'LOSS'
                        ELSE g.result
                    END AS result
                FROM player_game_ids pgi
                JOIN v_effective_games g ON g.id = pgi.game_id
                CROSS JOIN player_org po
                LEFT JOIN game_appearances ga ON ga.game_id = pgi.game_id AND ga.player_id = CAST(:pid AS UUID)
                WHERE TRUE{scope_clause}
            ),
            player_games AS (
                SELECT * FROM player_games_raw
                WHERE opp_key IS NULL OR opp_key NOT IN (SELECT oid FROM excluded_orgs)
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
        params,
    )
    return [dict(r) for r in result.mappings()]


async def get_player_by_venue(
    session: AsyncSession, player_id: str, scope: Optional[GradeScope] = None
) -> list[dict]:
    scope_clause = scope.clause("g.grade_id") if _scoped(scope) else ""
    params: dict = {"pid": player_id}
    if _scoped(scope):
        scope.bind(params)
    result = await session.execute(
        text(f"""
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
                  {scope_clause}
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
                  {scope_clause}
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
                  {scope_clause}
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
                  {scope_clause}
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
        params,
    )
    return [dict(r) for r in result.mappings()]


async def _club_results(
    session: AsyncSession,
    org_id: str,
    season_ids: Optional[list] = None,
    grade_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> dict:
    """W/L/D and win-rate over the org's own completed games.

    A game is 'ours' if we're recorded as home_org_id/away_org_id on the row
    (the reliable per-club signal for a shared games.id row between two
    both-synced clubs — see migration 167), or the game's own grade belongs
    to our org, or one of our players has a recorded appearance in it, or
    it's a manual game we created (checked via the view's own
    `organisation_id`, migration 169 — a bare `g.source = 'manual'` used to
    mean ANY club's manual game counted as "ours", a cross-club leak in the
    W/L/D headline) — mirrors ``get_org_results`` so the headline matches
    the results list. grades are LEFT JOINed (not INNER) so a shared game
    whose grade_id belongs to the OTHER club (whichever synced it first)
    still counts — an INNER JOIN gated on s.organisation_id would otherwise
    silently exclude it regardless of the appearance check; season is
    likewise joined off the view's own `season_id` rather than via
    grade->season, so a manual game with no grade (the upload form allows
    "— none —" for Grade) still resolves its season for the season_ids
    filter. NOT matching the org's name against the free-text
    home_team/away_team CA supplies, which silently zeroed every game for a
    club whose CA-recorded team text doesn't literally contain the org's
    first name-token (e.g. a hyphenated name like "Bayswater-Postels" where
    CA spells it differently). Reads ``v_effective_games`` (so it
    self-corrects with the cross-club views) and replaces the retired
    PlayHQ Partner win/loss override.
    """
    clauses = [
        """(
            g.organisation_id = CAST(:org_id AS UUID)
            OR g.home_org_id = CAST(:org_id AS UUID)
            OR g.away_org_id = CAST(:org_id AS UUID)
            OR s.organisation_id = CAST(:org_id AS UUID)
            OR EXISTS (
                SELECT 1 FROM game_appearances ga
                JOIN players p ON p.id = ga.player_id
                WHERE ga.game_id = g.id AND p.organisation_id = CAST(:org_id AS UUID)
            )
        )""",
    ]
    params: dict = {"org_id": org_id}
    if grade_id:
        clauses.append("""(
            gr.id = CAST(:grade_id AS UUID)
            OR (gr.grassroots_id IS NOT NULL AND gr.grassroots_id = (
                SELECT grassroots_id FROM grades WHERE id = CAST(:grade_id AS UUID)
            ))
        )""")
        params["grade_id"] = grade_id
    elif season_ids:
        clauses.append("""(
            s.id = ANY(:sids)
            OR (s.grassroots_id IS NOT NULL AND s.grassroots_id IN (
                SELECT grassroots_id FROM seasons WHERE id = ANY(:sids) AND grassroots_id IS NOT NULL
            ))
        )""")
        params["sids"] = season_ids

    # Grade-type / match-type scope. Dropped when a single grade is picked —
    # an explicitly chosen grade beats the category default, the same rule the
    # leaderboards follow.
    if _scoped(scope) and not grade_id:
        clauses.append(scope.clause("g.grade_id").removeprefix(" AND ").strip())
        scope.bind(params)

    # g.result is ALSO relative to whichever club's sync wrote it first
    # (classify_match_result computes it against that syncing org's own
    # team) — the same single-column-can't-hold-two-perspectives issue
    # opp_org_id had. g.winning_team is the actual winning team's name
    # (neutral, not org-relative), so effective_result re-derives WIN/LOSS
    # against OUR home/away side instead of trusting g.result as stored —
    # falling back to g.result when winning_team is NULL (a symmetric
    # draw/tie/no-result, or a row where home_org_id/away_org_id can't place
    # either side, e.g. not yet backfilled).
    row = dict(
        (
            await session.execute(
                text(
                    f"""
            SELECT
                COUNT(*) FILTER (WHERE effective_result IS NOT NULL)         AS total,
                COUNT(*) FILTER (WHERE effective_result = 'WIN')            AS wins,
                COUNT(*) FILTER (WHERE effective_result = 'LOSS')           AS losses,
                COUNT(*) FILTER (WHERE effective_result IN ('DRAW', 'TIE')) AS draws
            FROM (
                SELECT
                    CASE
                        WHEN g.winning_team IS NULL THEN g.result
                        WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'WIN'
                        WHEN g.home_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'LOSS'
                        WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.away_team THEN 'WIN'
                        WHEN g.away_org_id = CAST(:org_id AS UUID) AND g.winning_team = g.home_team THEN 'LOSS'
                        ELSE g.result
                    END AS effective_result
                FROM v_effective_games g
                LEFT JOIN grades gr ON gr.id = g.grade_id
                LEFT JOIN seasons s ON s.id = g.season_id
                WHERE {' AND '.join(clauses)}
            ) sub
        """
                ),
                params,
            )
        ).mappings().first()
        or {}
    )
    total = int(row.get("total") or 0)
    wins = int(row.get("wins") or 0)
    return {
        "total_games": total,
        "wins": wins,
        "losses": int(row.get("losses") or 0),
        "draws": int(row.get("draws") or 0),
        "win_rate": round(wins / total * 100, 1) if total else 0,
    }


async def get_club_summary(
    session: AsyncSession,
    org_id: str,
    season_id: Optional[str] = None,
    grade_id: Optional[str] = None,
    scope: Optional[GradeScope] = None,
) -> dict:
    base = {
        "total_games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "win_rate": 0,
        "total_runs": 0,
        "total_wickets": 0,
        "highest_score": 0,
        "total_players": 0,
        "seasons": 0,
    }

    # When a specific grade is selected, the headline runs/wickets/players must
    # come from the per-game tables (batting_innings / bowling_spells /
    # fielding_stats joined to games.grade_id). The aggregate
    # player_season_stats feed is participant-level / whole-club and carries no
    # grade dimension, so filtering it by grade is impossible — it would just
    # return the whole-club totals unchanged. This mirrors the grade_id branch
    # of the batting / bowling leaderboards (g.grade_id = :grade_id), so the
    # headline matches the Top Batters / Top Bowlers lists shown beside it.
    # A grade is season-specific, so season_id is implied by the grade.
    if grade_id:
        res = await session.execute(
            text("""
                WITH gg AS (
                    SELECT id FROM v_effective_games
                    WHERE grade_id = CAST(:grade_id AS UUID)
                ),
                bat AS (
                    SELECT bi.player_id, bi.runs
                    FROM v_effective_batting_innings bi
                    JOIN gg ON gg.id = bi.game_id
                    JOIN players p ON p.id = bi.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                    WHERE NOT COALESCE(bi.did_not_bat, FALSE)
                      AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                ),
                bowl AS (
                    SELECT bs.player_id, bs.wickets
                    FROM v_effective_bowling_spells bs
                    JOIN gg ON gg.id = bs.game_id
                    JOIN players p ON p.id = bs.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                ),
                fld AS (
                    SELECT fs.player_id
                    FROM v_effective_fielding_stats fs
                    JOIN gg ON gg.id = fs.game_id
                    JOIN players p ON p.id = fs.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                )
                SELECT
                    (SELECT COALESCE(SUM(runs), 0) FROM bat)     AS total_runs,
                    (SELECT MAX(runs) FROM bat)                  AS highest_score,
                    (SELECT COALESCE(SUM(wickets), 0) FROM bowl) AS total_wickets,
                    (SELECT COUNT(*) FROM (
                        SELECT player_id FROM bat
                        UNION SELECT player_id FROM bowl
                        UNION SELECT player_id FROM fld
                     ) u)                                        AS total_players
            """),
            {"org_id": org_id, "grade_id": grade_id},
        )
        row = dict(res.mappings().first() or {})
        base.update({
            "total_runs": int(row.get("total_runs") or 0),
            "total_wickets": int(row.get("total_wickets") or 0),
            "highest_score": int(row.get("highest_score") or 0),
            "total_players": int(row.get("total_players") or 0),
            "seasons": 1,
        })
        base.update(await _club_results(session, org_id, grade_id=grade_id))
        return base

    season_ids = await resolve_season_filter(session, org_id, season_id)

    # A grade-type or match-type filter is only answerable from the per-innings
    # scorecards: CA's season aggregates carry no grade at all (the `api` branch
    # of v_effective_player_season_stats hardcodes grade_id NULL), so filtering
    # them by grade would silently return the whole club's totals under a
    # filtered heading. An active scope therefore switches source, the same
    # trade the leaderboards and career totals already make.
    if _scoped(scope):
        params = {"org_id": org_id}
        game_season_clause = ""
        if season_ids:
            game_season_clause = " AND g.season_id = ANY(:season_ids)"
            params["season_ids"] = season_ids
        scope.bind(params)
        res = await session.execute(
            text(f"""
                WITH gg AS (
                    SELECT g.id, g.season_id FROM v_effective_games g
                    WHERE (
                        g.organisation_id = CAST(:org_id AS UUID)
                        OR g.home_org_id = CAST(:org_id AS UUID)
                        OR g.away_org_id = CAST(:org_id AS UUID)
                        OR EXISTS (
                            SELECT 1 FROM grades gr JOIN seasons s ON s.id = gr.season_id
                            WHERE gr.id = g.grade_id AND s.organisation_id = CAST(:org_id AS UUID)
                        )
                    ){game_season_clause}{scope.clause("g.grade_id")}
                ),
                bat AS (
                    SELECT bi.player_id, bi.runs
                    FROM v_effective_batting_innings bi
                    JOIN gg ON gg.id = bi.game_id
                    JOIN players p ON p.id = bi.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                    WHERE NOT COALESCE(bi.did_not_bat, FALSE)
                      AND LOWER(COALESCE(bi.dismissal_type, '')) NOT IN ('absent', 'did not bat', 'dnb')
                ),
                bowl AS (
                    SELECT bs.player_id, bs.wickets
                    FROM v_effective_bowling_spells bs
                    JOIN gg ON gg.id = bs.game_id
                    JOIN players p ON p.id = bs.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                ),
                fld AS (
                    SELECT fs.player_id
                    FROM v_effective_fielding_stats fs
                    JOIN gg ON gg.id = fs.game_id
                    JOIN players p ON p.id = fs.player_id
                        AND p.organisation_id = CAST(:org_id AS UUID)
                )
                SELECT
                    (SELECT COALESCE(SUM(runs), 0) FROM bat)     AS total_runs,
                    (SELECT MAX(runs) FROM bat)                  AS highest_score,
                    (SELECT COALESCE(SUM(wickets), 0) FROM bowl) AS total_wickets,
                    (SELECT COUNT(DISTINCT season_id) FROM gg)   AS seasons,
                    (SELECT COUNT(*) FROM (
                        SELECT player_id FROM bat
                        UNION SELECT player_id FROM bowl
                        UNION SELECT player_id FROM fld
                     ) u)                                        AS total_players
            """),
            params,
        )
        row = dict(res.mappings().first() or {})
        base.update({
            "total_runs": int(row.get("total_runs") or 0),
            "total_wickets": int(row.get("total_wickets") or 0),
            "highest_score": int(row.get("highest_score") or 0),
            "total_players": int(row.get("total_players") or 0),
            "seasons": int(row.get("seasons") or 0),
        })
        base.update(await _club_results(session, org_id, season_ids=season_ids, scope=scope))
        return base

    where = "WHERE p.organisation_id = :org_id"
    params: dict = {"org_id": org_id}
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
    base.update({
        "total_runs": int(row.get("total_runs") or 0),
        "total_wickets": int(row.get("total_wickets") or 0),
        "highest_score": int(row.get("highest_score") or 0),
        "total_players": int(row.get("total_players") or 0),
        "seasons": int(row.get("seasons") or 0),
    })
    base.update(await _club_results(session, org_id, season_ids=season_ids))
    return base


async def get_game_partnerships(session: AsyncSession, game_id: str, org_id: str | None = None) -> list[dict]:
    # batterN_name falls through display-override → real name → the raw GR
    # name stored for a fill-in/redacted participant (pt.batterN_name, added
    # migration 147) — same COALESCE chain get_game_fall_of_wickets already
    # uses. The caller (games.py) decides whether to keep or strip that
    # fallback name based on the club's include_fill_ins_in_stats setting.
    # p.organisation_id scoping (same reasoning as get_game_fall_of_wickets,
    # see its own comment) stops an opposition batter from being misattributed
    # to one of our own players who happens to share a participant GUID with
    # them. A row that loses its link this way and has no stored fallback
    # name (an old row that predates the fallback column) shows as "Unknown"
    # on the frontend — a real gap, but a truthful one, unlike showing the
    # wrong person's name.
    result = await session.execute(
        text("""
            SELECT
                pt.wicket_number,
                pt.innings_number,
                pt.runs,
                pt.balls,
                pt.batter1_runs,
                pt.batter2_runs,
                p1.id::text AS batter1_id,
                p2.id::text AS batter2_id,
                COALESCE(p1.display_name_override, p1.name, pt.batter1_name) AS batter1_name,
                COALESCE(p2.display_name_override, p2.name, pt.batter2_name) AS batter2_name
            FROM v_effective_partnerships pt
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
                AND (CAST(:org_id AS uuid) IS NULL OR p1.organisation_id = CAST(:org_id AS uuid))
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
                AND (CAST(:org_id AS uuid) IS NULL OR p2.organisation_id = CAST(:org_id AS uuid))
            WHERE pt.game_id = :gid
            ORDER BY pt.innings_number, pt.wicket_number
        """),
        {"gid": game_id, "org_id": org_id},
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


async def _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=False, stat_alias='bi', scope=None):
    """Return (season_clause, finals_clause, grade_clause, captain_join) strings and mutate params.

    The grade-category scope rides along in `grade_clause`, which every SIRS
    query already interpolates — these are all per-game queries, so the filter
    needs no alternate source the way the leaderboards do. A named grade wins
    over the category default, same rule as the leaderboards.
    """
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
    elif _scoped(scope):
        grade_clause = scope.clause("g.grade_id")
        scope.bind(params)
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bi', scope=scope)
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bs', scope=scope)
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
    scope: Optional[GradeScope] = None,
) -> list[dict]:
    params: dict = {"org_id": org_id, "limit": limit}
    season_clause, finals_clause, grade_clause, captain_join = await _sirs_base_clauses(session, org_id, season_id, grade_name, finals_only, params, captain_only=bool(captain_only), stat_alias='bs', scope=scope)
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
