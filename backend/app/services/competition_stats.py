"""Batting, bowling, fielding and appearances, broken down by COMPETITION.

The competition FILTER (``grade_scope``) narrows every existing surface to one
competition. This module is the other half of the ask: enumerating them, so a
club, a grade and a player each get a row per competition and the reader can
compare rather than switch a filter back and forth.

WHY IT READS PER-GAME ROWS AND NOT SEASON AGGREGATES
----------------------------------------------------
Cricket Australia's season aggregates carry no grade at all
(``v_effective_player_season_stats``'s ``api`` branch hardcodes ``grade_id``
NULL), so they can say nothing about which competition a run was scored in.
Every figure here therefore comes from the per-innings scorecards, which is
the same trade ``records.use_game_level`` and the format axis already make.

The visible consequence, stated rather than hidden: a competition breakdown
sums to the career total only where the club holds a scorecard for every
match. A club whose history came from BetterImport carries career residuals
with no grade, and those belong to no competition — so every payload here
reports ``unattributed``, and the screens show it as its own row. Shown, never
dropped, and never silently folded into a competition it might not belong to.

A GAME IS OURS BY THE SAME PREDICATE THE REST OF THE APP USES. A fixture
between two synced clubs is ONE ``games`` row owned by whichever club synced
it first, so "ours" is: the game's own club is us, or we are one of the two
sides (``home_org_id``/``away_org_id``). Mirrors
``aggregations._club_game_clause`` and ``iq_trends._ours_clause``.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_grade_competitions
from app.services.competitions import UNGROUPED_LABEL
from app.services.game_status import appearance_counts_as_match
from app.services.season_aliases import resolve_season_filter

_APPEARANCE_PLAYED = appearance_counts_as_match("ga")

# A game is this club's when it owns the fixture or is one of the two sides.
_OURS = (
    " AND (g.organisation_id = CAST(:org AS UUID)"
    " OR g.home_org_id = CAST(:org AS UUID)"
    " OR g.away_org_id = CAST(:org AS UUID))"
)

# Every appearance a player made, from all four sources. `game_appearances` is
# what a named-but-did-nothing match is counted from; the three per-innings
# tables cover a scorecard that never got an appearances row.
_APPEARANCES_CTE = f"""
    WITH appearances AS (
        SELECT bi.game_id FROM v_effective_batting_innings bi
         WHERE bi.player_id = CAST(:pid AS UUID)
        UNION
        SELECT bs.game_id FROM v_effective_bowling_spells bs
         WHERE bs.player_id = CAST(:pid AS UUID)
        UNION
        SELECT fs.game_id FROM v_effective_fielding_stats fs
         WHERE fs.player_id = CAST(:pid AS UUID)
        UNION
        SELECT ga.game_id FROM game_appearances ga
         WHERE ga.player_id = CAST(:pid AS UUID) AND {_APPEARANCE_PLAYED}
    )
"""

# The competition a game was played in, as a (id, name) pair. LEFT JOINed so a
# grade in no competition still produces a row — it lands under UNGROUPED_LABEL
# rather than disappearing, the same call the "unattributed" column on the
# by-grade grid makes.
#
# THE COMPETITION IS READ FROM THE CLUB'S OWN MAP, NEVER FROM
# `grades.competition_id`. A shared fixture's grade row belongs to the OTHER
# club, so its own competition_id is either NULL (the match falls into "Other
# grades" — the reported Shoalwater Bay case, 28 Peel matches sitting outside
# the Peel competition) or, once that club has grouped its own grades, is that
# club's competition and would put their label on our figures.
# `club_grade_competitions` resolves it to ours instead. See
# services/club_grades.py.
_COMP_JOIN = """
    JOIN grades gr ON gr.id = g.grade_id
    LEFT JOIN LATERAL (
        SELECT ovc.comp FROM unnest(
            CAST(:cg_grade_ids AS uuid[]), CAST(:cg_comp_ids AS uuid[])
        ) AS ovc(gid, comp)
        WHERE ovc.gid = gr.id
        LIMIT 1
    ) ov ON TRUE
    LEFT JOIN club_competitions c ON c.id = ov.comp
"""


async def _bind_comp_map(session: AsyncSession, org_id, params: dict) -> None:
    """Bind the club's grade -> competition map for :data:`_COMP_JOIN`."""
    mapping = await club_grade_competitions(session, org_id)
    params["cg_grade_ids"] = [str(k) for k in mapping]
    params["cg_comp_ids"] = [str(v) if v else None for v in mapping.values()]


def _label(name) -> str:
    return name or UNGROUPED_LABEL


async def _season_clause(session: AsyncSession, org_id, season_id, params: dict) -> str:
    """Narrow to one season, expanded through the club's season aliases.

    ``resolve_season_filter`` is what makes picking "2025/26" return every
    season row sharing that year — a merged season, and the sibling row a
    second club minted for the same year — so a competition breakdown and the
    season dropdown above it agree about what a season is.
    """
    if not season_id:
        return ""
    ids = await resolve_season_filter(session, str(org_id), str(season_id), include_shared=True)
    if not ids:
        return ""
    params["sids"] = ids
    return " AND gr.season_id = ANY(:sids)"


async def club_competition_breakdown(
    session: AsyncSession, org_id, season_id: Optional[str] = None
) -> dict:
    """The club's own record in each competition it has played.

    Matches, won/lost/drawn, the seasons and grades involved, and the runs,
    wickets and dismissals its players contributed. One row per competition,
    in the club's own competition order.
    """
    params: dict = {"org": str(org_id)}
    await _bind_comp_map(session, org_id, params)
    season_clause = await _season_clause(session, org_id, season_id, params)

    res = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   c.name AS competition_name,
                   c.association_name,
                   MIN(c.display_order) AS display_order,
                   COUNT(DISTINCT g.id) AS matches,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result = 'WIN') AS won,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result = 'LOSS') AS lost,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result IN ('DRAW', 'TIE')) AS drawn,
                   COUNT(DISTINCT gr.season_id) AS seasons,
                   COUNT(DISTINCT gr.name) AS grades,
                   MIN(s.year) AS first_year,
                   MAX(s.year) AS last_year
              FROM v_effective_games g
              {_COMP_JOIN}
              JOIN seasons s ON s.id = gr.season_id
             WHERE TRUE {_OURS}{season_clause}
             GROUP BY c.id, c.name, c.association_name
             ORDER BY MIN(c.display_order) NULLS LAST, COUNT(DISTINCT g.id) DESC
        """),
        params,
    )
    rows = []
    for r in res.mappings():
        matches = int(r["matches"] or 0)
        won = int(r["won"] or 0)
        lost = int(r["lost"] or 0)
        rows.append({
            "competition_id": str(r["competition_id"]) if r["competition_id"] else None,
            "competition_name": _label(r["competition_name"]),
            "association_name": r["association_name"],
            "matches": matches,
            "won": won,
            "lost": lost,
            "drawn": int(r["drawn"] or 0),
            # A win percentage over a denominator of nothing is not 0, it is
            # unanswerable — the same rule every other W/L panel here follows.
            "win_pct": round(won * 100.0 / (won + lost), 1) if (won + lost) else None,
            "seasons": int(r["seasons"] or 0),
            "grades": int(r["grades"] or 0),
            "first_year": r["first_year"],
            "last_year": r["last_year"],
        })

    # The playing figures, in their own pass. Deliberately NOT joined onto the
    # query above: a game has many innings, so counting matches and summing
    # runs in one GROUP BY multiplies the match count by the number of innings
    # rows — the same inflation the grades-with-stats query documents.
    stats = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   SUM(x.runs) AS runs,
                   SUM(x.wickets) AS wickets,
                   SUM(x.catches) AS catches,
                   SUM(x.stumpings) AS stumpings
              FROM (
                    SELECT bi.game_id, bi.runs::bigint AS runs,
                           0::bigint AS wickets, 0::bigint AS catches, 0::bigint AS stumpings
                      FROM v_effective_batting_innings bi
                      JOIN players p ON p.id = bi.player_id
                     WHERE p.organisation_id = CAST(:org AS UUID) AND bi.runs IS NOT NULL
                    UNION ALL
                    SELECT bs.game_id, 0, bs.wickets::bigint, 0, 0
                      FROM v_effective_bowling_spells bs
                      JOIN players p ON p.id = bs.player_id
                     WHERE p.organisation_id = CAST(:org AS UUID)
                    UNION ALL
                    SELECT fs.game_id, 0, 0, fs.catches::bigint, fs.stumpings::bigint
                      FROM v_effective_fielding_stats fs
                      JOIN players p ON p.id = fs.player_id
                     WHERE p.organisation_id = CAST(:org AS UUID)
              ) x
              JOIN v_effective_games g ON g.id = x.game_id
              {_COMP_JOIN}
             WHERE TRUE {_OURS}{season_clause}
             GROUP BY c.id
        """),
        params,
    )
    by_id = {str(r["competition_id"]) if r["competition_id"] else None: r
             for r in stats.mappings()}
    for row in rows:
        figures = by_id.get(row["competition_id"])
        row["runs"] = int((figures or {}).get("runs") or 0)
        row["wickets"] = int((figures or {}).get("wickets") or 0)
        row["catches"] = int((figures or {}).get("catches") or 0)
        row["stumpings"] = int((figures or {}).get("stumpings") or 0)
    return {"rows": rows, "total_matches": sum(r["matches"] for r in rows)}


async def competition_grade_breakdown(
    session: AsyncSession, org_id, season_id: Optional[str] = None
) -> list[dict]:
    """Every grade the club has played, grouped under its competition.

    This is the TEAM half of the breakdown. A grade is what a club actually
    fields a side in, and one team genuinely appears in several — Hamilton's
    Over 60 Men play the Border Cup and the Over 60s competition in one
    season, Applecross's 7th XI plays two One Day grades — so each of those is
    its own row under its own competition, which is exactly the separation the
    flat grade list could not express.
    """
    params: dict = {"org": str(org_id)}
    await _bind_comp_map(session, org_id, params)
    season_clause = await _season_clause(session, org_id, season_id, params)
    res = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   c.name AS competition_name,
                   MIN(c.display_order) AS comp_order,
                   COALESCE(gr.display_name_override, gr.name) AS grade_name,
                   MIN(gr.display_order) AS grade_order,
                   COUNT(DISTINCT g.id) AS matches,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result = 'WIN') AS won,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result = 'LOSS') AS lost,
                   COUNT(DISTINCT g.id) FILTER (WHERE g.result IN ('DRAW', 'TIE')) AS drawn,
                   COUNT(DISTINCT gr.season_id) AS seasons,
                   MAX(s.year) AS last_year
              FROM v_effective_games g
              {_COMP_JOIN}
              JOIN seasons s ON s.id = gr.season_id
             WHERE TRUE {_OURS}{season_clause}
             GROUP BY c.id, c.name, COALESCE(gr.display_name_override, gr.name)
             ORDER BY MIN(c.display_order) NULLS LAST, c.name,
                      MIN(gr.display_order) NULLS LAST,
                      COUNT(DISTINCT g.id) DESC
        """),
        params,
    )
    out: list[dict] = []
    for r in res.mappings():
        won, lost = int(r["won"] or 0), int(r["lost"] or 0)
        out.append({
            "competition_id": str(r["competition_id"]) if r["competition_id"] else None,
            "competition_name": _label(r["competition_name"]),
            "grade_name": r["grade_name"],
            "matches": int(r["matches"] or 0),
            "won": won,
            "lost": lost,
            "drawn": int(r["drawn"] or 0),
            "win_pct": round(won * 100.0 / (won + lost), 1) if (won + lost) else None,
            "seasons": int(r["seasons"] or 0),
            "last_year": r["last_year"],
        })
    return out


async def player_competition_breakdown(
    session: AsyncSession, player_id: str, org_id, season_id: Optional[str] = None
) -> dict:
    """One player's batting, bowling, fielding and appearances per competition.

    Every average is recomputed from this competition's own counts — never an
    average of averages, and never CA's season figure divided up, which could
    not be attributed to a competition anyway.
    """
    params: dict = {"pid": str(player_id), "org": str(org_id)}
    await _bind_comp_map(session, org_id, params)
    season_clause = await _season_clause(session, org_id, season_id, params)

    appearances = await session.execute(
        text(f"""
            {_APPEARANCES_CTE}
            SELECT c.id AS competition_id,
                   c.name AS competition_name,
                   c.association_name,
                   MIN(c.display_order) AS display_order,
                   COUNT(DISTINCT g.id) AS matches,
                   COUNT(DISTINCT gr.season_id) AS seasons,
                   COUNT(DISTINCT gr.name) AS grades,
                   MIN(s.year) AS first_year,
                   MAX(s.year) AS last_year
              FROM appearances ap
              JOIN v_effective_games g ON g.id = ap.game_id
              {_COMP_JOIN}
              JOIN seasons s ON s.id = gr.season_id
             WHERE TRUE {_OURS}{season_clause}
             GROUP BY c.id, c.name, c.association_name
             ORDER BY MIN(c.display_order) NULLS LAST, COUNT(DISTINCT g.id) DESC
        """),
        params,
    )
    rows: list[dict] = []
    index: dict[Optional[str], dict] = {}
    for r in appearances.mappings():
        key = str(r["competition_id"]) if r["competition_id"] else None
        row = {
            "competition_id": key,
            "competition_name": _label(r["competition_name"]),
            "association_name": r["association_name"],
            "matches": int(r["matches"] or 0),
            "seasons": int(r["seasons"] or 0),
            "grades": int(r["grades"] or 0),
            "first_year": r["first_year"],
            "last_year": r["last_year"],
            "batting": None,
            "bowling": None,
            "fielding": None,
        }
        rows.append(row)
        index[key] = row

    batting = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   COUNT(*) AS innings,
                   COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
                   SUM(bi.runs) AS runs,
                   MAX(bi.runs) AS high_score,
                   SUM(bi.balls) AS balls,
                   SUM(bi.fours) AS fours,
                   SUM(bi.sixes) AS sixes,
                   COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) AS fifties,
                   COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds,
                   COUNT(*) FILTER (
                       WHERE NOT bi.not_out AND bi.dismissal_type IS NOT NULL
                   ) AS dismissals
              FROM v_effective_batting_innings bi
              JOIN v_effective_games g ON g.id = bi.game_id
              {_COMP_JOIN}
             WHERE bi.player_id = CAST(:pid AS UUID)
               AND bi.runs IS NOT NULL
               AND (bi.did_not_bat IS NOT TRUE)
               {_OURS}{season_clause}
             GROUP BY c.id
        """),
        params,
    )
    for r in batting.mappings():
        row = index.get(str(r["competition_id"]) if r["competition_id"] else None)
        if row is None:
            continue
        runs = int(r["runs"] or 0)
        dismissals = int(r["dismissals"] or 0)
        balls = int(r["balls"] or 0)
        row["batting"] = {
            "innings": int(r["innings"] or 0),
            "not_outs": int(r["not_outs"] or 0),
            "runs": runs,
            "high_score": int(r["high_score"] or 0),
            # Not out every time is a real state and has no average — reported
            # as null rather than as the run total, which would read as an
            # average nobody computed.
            "average": round(runs / dismissals, 2) if dismissals else None,
            "strike_rate": round(runs * 100.0 / balls, 2) if balls else None,
            "balls": balls,
            "fours": int(r["fours"] or 0),
            "sixes": int(r["sixes"] or 0),
            "fifties": int(r["fifties"] or 0),
            "hundreds": int(r["hundreds"] or 0),
        }

    bowling = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   COUNT(*) AS spells,
                   SUM(bs.wickets) AS wickets,
                   SUM(bs.runs) AS runs,
                   SUM(bs.maidens) AS maidens,
                   -- Overs are CRICKET notation (10.2 = ten overs and two
                   -- balls), so they are converted to balls before anything is
                   -- divided by them. Summing the decimals would make every
                   -- economy rate wrong.
                   SUM(FLOOR(bs.overs)::bigint * 6
                       + ROUND((bs.overs - FLOOR(bs.overs)) * 10)::bigint) AS balls
              FROM v_effective_bowling_spells bs
              JOIN v_effective_games g ON g.id = bs.game_id
              {_COMP_JOIN}
             WHERE bs.player_id = CAST(:pid AS UUID)
               {_OURS}{season_clause}
             GROUP BY c.id
        """),
        params,
    )
    for r in bowling.mappings():
        row = index.get(str(r["competition_id"]) if r["competition_id"] else None)
        if row is None:
            continue
        wickets = int(r["wickets"] or 0)
        conceded = int(r["runs"] or 0)
        balls = int(r["balls"] or 0)
        row["bowling"] = {
            "spells": int(r["spells"] or 0),
            "wickets": wickets,
            "runs": conceded,
            "maidens": int(r["maidens"] or 0),
            "balls": balls,
            "overs": round(balls / 6, 1) if balls else 0,
            "average": round(conceded / wickets, 2) if wickets else None,
            "economy": round(conceded * 6.0 / balls, 2) if balls else None,
            "strike_rate": round(balls / wickets, 1) if wickets else None,
        }

    fielding = await session.execute(
        text(f"""
            SELECT c.id AS competition_id,
                   SUM(fs.catches) AS catches,
                   SUM(fs.catches_wk) AS catches_wk,
                   SUM(fs.stumpings) AS stumpings,
                   SUM(fs.run_outs) AS run_outs
              FROM v_effective_fielding_stats fs
              JOIN v_effective_games g ON g.id = fs.game_id
              {_COMP_JOIN}
             WHERE fs.player_id = CAST(:pid AS UUID)
               {_OURS}{season_clause}
             GROUP BY c.id
        """),
        params,
    )
    for r in fielding.mappings():
        row = index.get(str(r["competition_id"]) if r["competition_id"] else None)
        if row is None:
            continue
        catches = int(r["catches"] or 0)
        catches_wk = int(r["catches_wk"] or 0)
        row["fielding"] = {
            "catches": catches,
            "catches_wk": catches_wk,
            # Outfield catches, the split every other fielding surface here
            # reports alongside the keeper's.
            "catches_non_wk": max(catches - catches_wk, 0),
            "stumpings": int(r["stumpings"] or 0),
            "run_outs": int(r["run_outs"] or 0),
        }

    return {
        "rows": rows,
        "total_matches": sum(r["matches"] for r in rows),
        # What a competition breakdown genuinely cannot place. A career-scope
        # import or manual-career residual has no game and so no grade, and a
        # grade-less manual game has no competition. Reported so the screen can
        # say the rows do not add up to the career total, and why.
        "unattributed": await _unattributed_matches(session, player_id, org_id, season_id),
    }


async def _unattributed_matches(
    session: AsyncSession, player_id: str, org_id, season_id: Optional[str]
) -> int:
    """How many of the player's matches carry no competition at all.

    Counted from the same appearance union the rows are, so the two agree by
    construction: a game whose grade is NULL (a manual upload with no grade
    picked) can be placed in no competition. A grade that simply has not been
    grouped yet is NOT counted here — it appears as its own "Other grades" row,
    which is a different and correctable state.
    """
    params: dict = {"pid": str(player_id), "org": str(org_id)}
    season_clause = ""
    if season_id:
        ids = await resolve_season_filter(session, str(org_id), str(season_id), include_shared=True)
        if ids:
            params["sids"] = ids
            # A game with no grade has no season to compare either, so under a
            # season filter it cannot be claimed for that season.
            season_clause = " AND FALSE"
    res = await session.execute(
        text(f"""
            {_APPEARANCES_CTE}
            SELECT COUNT(DISTINCT g.id)
              FROM appearances ap
              JOIN v_effective_games g ON g.id = ap.game_id
             WHERE g.grade_id IS NULL {_OURS}{season_clause}
        """),
        params,
    )
    return int(res.scalar() or 0)
