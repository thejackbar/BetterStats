"""CA's own season total, for a season the club holds no scorecards for.

The default grade-category lens (the junior filter every club with a junior
programme opens on) switches a profile or a board from CA's season totals to
the club's scorecards, because a season total has no grade to filter by. That is
right while the club holds the scorecards and wrong when it does not: a club
that only ever had CA's summary figures, or whose older seasons predate its
scorecards, watched those seasons read as zero. Import history and hand-typed
adjustments were already added back (`aggregations._RESIDUAL_SOURCES`); this adds
back the one source that was left out.

One definition, used by the profile (`aggregations._career_residuals`,
`_season_by_season_scoped`), the leaderboards (`_residual_totals_cte`) and the
milestone scan (`milestone_totals`), so they cannot disagree. This module imports
nothing from `aggregations`, which imports `milestone_totals`.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.game_status import appearance_counts_as_match
from app.services.grade_scope import GradeScope

_APPEARANCE_PLAYED = appearance_counts_as_match("ga")

# No player plays anywhere near this many games in one real season. Cricket
# Australia bundles a club's whole pre-migration history into its earliest
# season as cumulative career-to-date totals; that row is not a season and is
# folded into "Prior Seasons & Adjustments" on the unscoped profile. It is NOT
# added back here: the scoped profile has no such row to put it in.
HISTORICAL_BUNDLE_MATCH_CAP = 60


async def club_player_ids(session: AsyncSession, org_id) -> list[str]:
    """The club's own player ids, to bind as one array (`= ANY(CAST(:x AS uuid[]))`).

    A bound array is pushed into the `v_effective_*` views; an `IN (SELECT ...)`
    is not, and was measured tens of thousands of times slower.
    """
    res = await session.execute(
        text("SELECT id FROM players WHERE organisation_id = CAST(:o AS UUID)"),
        {"o": str(org_id)},
    )
    return [str(i) for i in res.scalars().all()]


def held_years_cte(games_where: str, player_pred) -> str:
    """CTEs `held_games` and `held_years`: which calendar years a player has an
    in-scope SCORECARD in, as (player_id, year).

    The year, not the season id, because a fixture shared between two clubs
    carries whichever club's season synced it first, and one real season is
    routinely several `seasons` rows. `player_pred(alias)` narrows the per-game
    tables to the player(s) asked about.

    Both CTEs are MATERIALIZED and the game filter is an array, for speed.
    `summary_only_seasons_clause` reads `held_years` from inside a correlated
    NOT EXISTS, so left alone Postgres inlines the CTE and rebuilds the player's
    whole game history once per season-stats row. Summer Hill's all-seasons
    leaderboards did that 4,510 times at about 9ms each, 41s of a 43s query.
    Materialising builds it once. `= ANY(ARRAY(SELECT ...))` evaluates the id
    list once as an InitPlan and uses it as a bound array (the same shape as
    `= ANY(CAST(:ids AS uuid[]))`), where `IN (SELECT ...)` against the CTE
    became a nested loop that re-read it 165,000 times.

    `held_years` never holds a NULL year, on purpose. `summary_only_seasons_clause`
    reads it with an uncorrelated `(player_id, year) NOT IN (SELECT ...)` so
    Postgres hashes it (a correlated NOT EXISTS against a materialised CTE scans
    it once per season-stats row, 3.8s against 0.15s on a synthetic club), and
    NOT IN is unknown, not true, when the list holds a NULL. A NULL-year game
    could never have matched a season with a year anyway.
    """
    held_ids = "ANY(ARRAY(SELECT id FROM held_games))"
    return f"""
        held_games AS MATERIALIZED (
            SELECT g.id, hs.year
            FROM v_effective_games g
            JOIN seasons hs ON hs.id = g.season_id
            WHERE {games_where}
        ), held_years AS MATERIALIZED (
            SELECT DISTINCT ap.player_id, hg.year
            FROM (
                SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
                 WHERE {player_pred('bi')} AND bi.game_id = {held_ids}
                UNION
                SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
                 WHERE {player_pred('bs')} AND bs.game_id = {held_ids}
                UNION
                SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
                 WHERE {player_pred('fs')} AND fs.game_id = {held_ids}
                UNION
                SELECT ga.player_id, ga.game_id FROM game_appearances ga
                 WHERE {player_pred('ga')} AND ga.game_id = {held_ids}
                   AND {_APPEARANCE_PLAYED}
            ) ap
            JOIN held_games hg ON hg.id = ap.game_id
            WHERE hg.year IS NOT NULL
        )"""


def summary_only_seasons_clause(scope: GradeScope, pss: str = "pss") -> str:
    """CA's own season total, for a season the club holds NO scorecards for.

    The grade-category lens switches a profile or board to scorecards, because
    CA's season row has no grade to filter by. That is right while the club holds
    the scorecards and wrong when it does not: a club that only ever had CA's
    summary figures (or whose older seasons predate its scorecards) would watch
    those seasons read as zero the moment the default junior filter applied.

    So the season total (`source = 'api'`) comes back for a player-year when:
    - the player has no in-scope scorecard that calendar year (`held_years`), so
      nothing is counted twice;
    - none of the grades CA lists for that player and season is out of scope.
      The total is one number across every grade, so a season split between
      an excluded grade and an included one cannot be divided and stays out;
    - the row is a real season: not CA's pre-migration bundle (over
      `HISTORICAL_BUNDLE_MATCH_CAP` matches), which is not a season;
    - the season has a year (without one coverage cannot be judged), and the
      aggregate clause passes (a category rule keeps a row it cannot categorise;
      a format filter drops it, since a season total has no format).

    Needs a `held_years` CTE in the query.
    """
    return f"""({pss}.source = 'api'{scope.clause(f"{pss}.grade_id", "aggregate")}
        AND COALESCE({pss}.matches, 0) <= {HISTORICAL_BUNDLE_MATCH_CAP}
        AND EXISTS (SELECT 1 FROM seasons ys
                     WHERE ys.id = {pss}.season_id AND ys.year IS NOT NULL
                       AND ({pss}.player_id, ys.year) NOT IN
                           (SELECT hy.player_id, hy.year FROM held_years hy))
        AND NOT EXISTS (SELECT 1 FROM player_season_grade_stats sg
                         WHERE sg.player_id = {pss}.player_id
                           AND sg.season_id = {pss}.season_id
                           AND NOT (TRUE{scope.clause("sg.grade_id", "aggregate")})))"""
