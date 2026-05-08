from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import uuid

from app.models.db import get_db, Grade

router = APIRouter(prefix="/records", tags=["records"])

_LIMIT = 25


@router.get("/{org_id}/grades")
async def get_records_grades(
    org_id: str,
    season_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return grades for the org, optionally scoped to a season."""
    q = select(Grade).join(Grade.season).where(
        Grade.season.has(organisation_id=uuid.UUID(org_id))
    )
    if season_id:
        q = q.where(Grade.season_id == uuid.UUID(season_id))
    result = await db.execute(q.order_by(Grade.name))
    grades = result.scalars().all()
    return [{"id": str(g.id), "name": g.name, "season_id": str(g.season_id)} for g in grades]


@router.get("/{org_id}")
async def get_records(
    org_id: str,
    season_id: str | None = Query(None),
    grade_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # If grade_id supplied without season_id, resolve season from grade
    if grade_id and not season_id:
        grade = await db.get(Grade, uuid.UUID(grade_id))
        if grade:
            season_id = str(grade.season_id)

    p = {"org_id": org_id, "limit": _LIMIT}
    if season_id:
        p["season_id"] = season_id
    if grade_id:
        p["grade_id"] = grade_id

    # Clauses for game-level queries (partnerships) that already JOIN games g
    game_season_clause = " JOIN grades gr ON gr.id = g.grade_id AND gr.season_id = :season_id" if season_id else ""
    game_grade_clause  = " AND g.grade_id = :grade_id" if grade_id else ""

    # Clauses for top_pairs which has no pre-existing games join
    pairs_game_join    = " JOIN games g ON g.id = pt.game_id JOIN grades gr ON gr.id = g.grade_id AND gr.season_id = :season_id" if season_id else ""
    pairs_grade_clause = " AND g.grade_id = :grade_id" if grade_id else ""

    # Inline WHERE additions for player_season_stats aggregate queries
    pss_season_clause  = "AND pss.season_id = :season_id " if season_id else ""

    async def q(sql: str, params: dict | None = None) -> list[dict]:
        rows = await db.execute(text(sql), params or p)
        return [dict(r) for r in rows.mappings().all()]

    # ── Batting ──────────────────────────────────────────────────────────────

    top_career_runs = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.runs), 0)            AS runs,
               COALESCE(SUM(pss.batting_innings), 0) AS innings,
               COALESCE(SUM(pss.not_outs), 0)        AS not_outs,
               COALESCE(SUM(pss.matches), 0)         AS matches,
               MAX(pss.high_score)                   AS high_score,
               ROUND(SUM(pss.runs)::numeric /
                   NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.runs) > 0
        ORDER BY runs DESC LIMIT :limit
    """)

    top_high_scores = await q("""
        SELECT p.id::text AS player_id, p.name,
               pss.high_score AS runs,
               pss.is_hs_not_out AS not_out,
               s.name AS season_name
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
          """ + ("AND pss.season_id = :season_id " if season_id else "") + """
          AND pss.high_score IS NOT NULL AND pss.high_score > 0
        ORDER BY pss.high_score DESC LIMIT :limit
    """)

    top_batting_avg = await q("""
        SELECT p.id::text AS player_id, p.name,
               ROUND(SUM(pss.runs)::numeric /
                   NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
               COALESCE(SUM(pss.runs), 0)            AS runs,
               COALESCE(SUM(pss.batting_innings), 0) AS innings
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING (SUM(pss.batting_innings) - SUM(pss.not_outs)) >= 5
        ORDER BY average DESC LIMIT :limit
    """)

    top_strike_rate = await q("""
        SELECT p.id::text AS player_id, p.name,
               ROUND(SUM(pss.runs)::numeric /
                   NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
               COALESCE(SUM(pss.runs), 0)            AS runs,
               COALESCE(SUM(pss.batting_innings), 0) AS innings
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.balls_faced) >= 50
        ORDER BY strike_rate DESC LIMIT :limit
    """)

    most_fifties = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.fifties), 0)  AS fifties,
               COALESCE(SUM(pss.hundreds), 0) AS hundreds,
               COALESCE(SUM(pss.runs), 0)     AS runs
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.fifties) > 0
        ORDER BY fifties DESC LIMIT :limit
    """)

    most_hundreds = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.hundreds), 0) AS hundreds,
               COALESCE(SUM(pss.runs), 0)     AS runs
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.hundreds) > 0
        ORDER BY hundreds DESC LIMIT :limit
    """)

    most_ducks = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.ducks), 0)          AS ducks,
               COALESCE(SUM(pss.batting_innings), 0) AS innings
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.ducks) > 0
        ORDER BY ducks DESC LIMIT :limit
    """)

    most_runs_season = await q("""
        SELECT p.id::text AS player_id, p.name,
               pss.runs, pss.batting_innings AS innings,
               s.name AS season_name, s.year AS season_year
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id AND pss.runs > 0
          """ + ("AND pss.season_id = :season_id " if season_id else "") + """
        ORDER BY pss.runs DESC LIMIT :limit
    """)

    # ── Bowling ──────────────────────────────────────────────────────────────

    top_career_wickets = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.wickets), 0)      AS wickets,
               COALESCE(SUM(pss.matches), 0)      AS matches,
               COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
               ROUND(SUM(pss.runs_conceded)::numeric /
                   NULLIF(SUM(pss.wickets), 0), 2) AS average,
               ROUND(SUM(pss.runs_conceded)::numeric /
                   NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.wickets) > 0
        ORDER BY wickets DESC LIMIT :limit
    """)

    best_innings_figures = await q("""
        SELECT p.id::text AS player_id, p.name,
               SPLIT_PART(pss.best_bowling_figures, '-', 1)::integer AS wickets,
               SPLIT_PART(pss.best_bowling_figures, '-', 2)::integer AS runs,
               s.name AS season_name
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id
          """ + ("AND pss.season_id = :season_id " if season_id else "") + """
          AND pss.best_bowling_figures IS NOT NULL
          AND pss.best_bowling_figures LIKE '%-%'
          AND pss.best_bowling_wickets > 0
        ORDER BY pss.best_bowling_wickets DESC,
                 SPLIT_PART(pss.best_bowling_figures, '-', 2)::integer ASC
        LIMIT :limit
    """)

    top_bowling_avg = await q("""
        SELECT p.id::text AS player_id, p.name,
               ROUND(SUM(pss.runs_conceded)::numeric /
                   NULLIF(SUM(pss.wickets), 0), 2) AS average,
               COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.runs_conceded), 0) AS runs_conceded
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.wickets) >= 5
        ORDER BY average ASC LIMIT :limit
    """)

    top_economy = await q("""
        SELECT p.id::text AS player_id, p.name,
               ROUND(SUM(pss.runs_conceded)::numeric /
                   NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
               COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.overs), 0)   AS overs
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.bowling_balls) >= 60
        ORDER BY economy ASC LIMIT :limit
    """)

    most_five_fors = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
               COALESCE(SUM(pss.wickets), 0)             AS wickets
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.five_wicket_innings) > 0
        ORDER BY five_fors DESC LIMIT :limit
    """)

    most_wickets_season = await q("""
        SELECT p.id::text AS player_id, p.name,
               pss.wickets, pss.bowling_innings AS innings,
               s.name AS season_name, s.year AS season_year
        FROM player_season_stats pss
        JOIN players p ON p.id = pss.player_id
        JOIN seasons s ON s.id = pss.season_id
        WHERE p.organisation_id = :org_id AND pss.wickets > 0
          """ + ("AND pss.season_id = :season_id " if season_id else "") + """
        ORDER BY pss.wickets DESC LIMIT :limit
    """)

    # ── Partnerships ─────────────────────────────────────────────────────────

    top_partnerships = await q("""
        SELECT
            p1.id::text AS batter1_id, p1.name AS batter1_name,
            p2.id::text AS batter2_id, p2.name AS batter2_name,
            pt.runs, pt.wicket_number,
            g.played_at::text, g.home_team, g.away_team
        FROM partnerships pt
        JOIN games g ON g.id = pt.game_id
        """ + game_season_clause + """
        LEFT JOIN players p1 ON p1.id = pt.batter1_id
        LEFT JOIN players p2 ON p2.id = pt.batter2_id
        WHERE (p1.organisation_id = :org_id OR p2.organisation_id = :org_id)
          """ + game_grade_clause + """
          AND pt.runs IS NOT NULL AND pt.runs > 0
        ORDER BY pt.runs DESC LIMIT :limit
    """)

    partnerships_by_wicket_rows = await q("""
        SELECT
            p1.id::text AS batter1_id, p1.name AS batter1_name,
            p2.id::text AS batter2_id, p2.name AS batter2_name,
            pt.runs, pt.wicket_number,
            g.played_at::text, g.home_team, g.away_team,
            ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rn
        FROM partnerships pt
        JOIN games g ON g.id = pt.game_id
        """ + game_season_clause + """
        LEFT JOIN players p1 ON p1.id = pt.batter1_id
        LEFT JOIN players p2 ON p2.id = pt.batter2_id
        WHERE (p1.organisation_id = :org_id OR p2.organisation_id = :org_id)
          """ + game_grade_clause + """
          AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10
    """)
    by_wicket: dict[int, list] = {}
    for row in partnerships_by_wicket_rows:
        if row["rn"] <= 5:
            wk = int(row["wicket_number"])
            by_wicket.setdefault(wk, [])
            d = dict(row)
            del d["rn"]
            by_wicket[wk].append(d)

    top_pairs = await q("""
        SELECT
            LEAST(p1.id::text, p2.id::text)    AS pair_key,
            p1.id::text AS batter1_id, p1.name AS batter1_name,
            p2.id::text AS batter2_id, p2.name AS batter2_name,
            COUNT(*)                            AS count,
            COALESCE(SUM(pt.runs), 0)           AS total_runs,
            MAX(pt.runs)                        AS best
        FROM partnerships pt
        JOIN players p1 ON p1.id = pt.batter1_id
        JOIN players p2 ON p2.id = pt.batter2_id
        """ + pairs_game_join + """
        WHERE p1.organisation_id = :org_id AND p2.organisation_id = :org_id
          """ + pairs_grade_clause + """
        GROUP BY LEAST(p1.id::text, p2.id::text),
                 p1.id, p1.name, p2.id, p2.name
        ORDER BY total_runs DESC LIMIT :limit
    """)

    # ── Team / fielding ───────────────────────────────────────────────────────

    most_matches = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.matches), 0) AS matches
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.matches) > 0
        ORDER BY matches DESC LIMIT :limit
    """)

    top_fielders = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.catches_non_wk), 0) AS catches,
               COALESCE(SUM(pss.catches_wk), 0)     AS catches_wk,
               COALESCE(SUM(pss.stumpings), 0)       AS stumpings,
               COALESCE(SUM(pss.run_outs), 0)        AS run_outs
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.catches_non_wk + pss.catches_wk + pss.stumpings) > 0
        ORDER BY (SUM(pss.catches_non_wk) + SUM(pss.catches_wk) + SUM(pss.stumpings)) DESC
        LIMIT :limit
    """)

    top_allrounders = await q("""
        SELECT p.id::text AS player_id, p.name,
               COALESCE(SUM(pss.runs), 0)    AS runs,
               COALESCE(SUM(pss.wickets), 0) AS wickets,
               COALESCE(SUM(pss.matches), 0) AS matches,
               (COALESCE(SUM(pss.runs), 0) + COALESCE(SUM(pss.wickets), 0) * 20) AS score
        FROM players p
        JOIN player_season_stats pss ON pss.player_id = p.id
        WHERE p.organisation_id = :org_id
          """ + pss_season_clause + """
        GROUP BY p.id, p.name
        HAVING SUM(pss.runs) >= 100 AND SUM(pss.wickets) >= 5
        ORDER BY score DESC LIMIT :limit
    """)

    return {
        "batting": {
            "top_career_runs":   top_career_runs,
            "top_high_scores":   top_high_scores,
            "top_batting_avg":   top_batting_avg,
            "top_strike_rate":   top_strike_rate,
            "most_fifties":      most_fifties,
            "most_hundreds":     most_hundreds,
            "most_ducks":        most_ducks,
            "most_runs_season":  most_runs_season,
        },
        "bowling": {
            "top_career_wickets":   top_career_wickets,
            "best_innings_figures": best_innings_figures,
            "top_bowling_avg":      top_bowling_avg,
            "top_economy":          top_economy,
            "most_five_fors":       most_five_fors,
            "most_wickets_season":  most_wickets_season,
        },
        "partnerships": {
            "top_overall": top_partnerships,
            "by_wicket":   by_wicket,
            "top_pairs":   top_pairs,
        },
        "team": {
            "most_matches":     most_matches,
            "top_fielders":     top_fielders,
            "top_allrounders":  top_allrounders,
        },
    }
