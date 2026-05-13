from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid
import logging

from app.models.db import get_db
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yearbooks", tags=["yearbooks"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _season_slug(season_name: str) -> str:
    """'Summer 2025/26' → '2025-26', 'Winter 2024' → '2024'"""
    import re
    m = re.search(r"(\d{4})/(\d{2,4})", season_name)
    if m:
        return f"{m.group(1)}-{m.group(2)[-2:]}"
    m = re.search(r"(\d{4})", season_name)
    if m:
        return m.group(1)
    return season_name.lower().replace(" ", "-")


async def _ensure_stub(db: AsyncSession, org_id: str, season_id: str) -> dict:
    """Get or create a yearbook stub for a season."""
    row = await db.execute(
        text("SELECT * FROM yearbooks WHERE org_id = :o AND season_id = :s"),
        {"o": org_id, "s": season_id},
    )
    yb = row.mappings().first()
    if yb:
        return dict(yb)

    new_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO yearbooks (id, org_id, season_id, status)
            VALUES (:id, :o, :s, 'draft')
            ON CONFLICT DO NOTHING
        """),
        {"id": new_id, "o": org_id, "s": season_id},
    )
    await db.commit()
    row = await db.execute(
        text("SELECT * FROM yearbooks WHERE org_id = :o AND season_id = :s"),
        {"o": org_id, "s": season_id},
    )
    return dict(row.mappings().first())


# ─── Auto-stub generation ─────────────────────────────────────────────────────

async def generate_stubs_for_org(db: AsyncSession, org_id: str) -> int:
    """Create a draft yearbook for every season that doesn't have one yet."""
    seasons = await db.execute(
        text("SELECT id FROM seasons WHERE organisation_id = :o"),
        {"o": org_id},
    )
    created = 0
    for row in seasons.mappings().all():
        existing = await db.execute(
            text("SELECT id FROM yearbooks WHERE org_id = :o AND season_id = :s"),
            {"o": org_id, "s": str(row["id"])},
        )
        if not existing.mappings().first():
            await db.execute(
                text("""
                    INSERT INTO yearbooks (id, org_id, season_id, status)
                    VALUES (gen_random_uuid(), :o, :s, 'draft')
                    ON CONFLICT DO NOTHING
                """),
                {"o": org_id, "s": str(row["id"])},
            )
            created += 1
    await db.commit()
    return created


async def generate_all_stubs(db: AsyncSession) -> None:
    """Called at startup — ensure every org×season has a yearbook stub."""
    orgs = await db.execute(text("SELECT id FROM organisations WHERE is_active = true"))
    total = 0
    for row in orgs.mappings().all():
        n = await generate_stubs_for_org(db, str(row["id"]))
        total += n
    if total:
        logger.info(f"Yearbook: created {total} new stubs on startup")


# ─── List yearbooks for a club ────────────────────────────────────────────────

@router.get("/{org_id}")
async def list_yearbooks(org_id: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("""
            SELECT y.id, y.status, y.published_at, y.hero_image_path,
                   s.id AS season_id, s.name AS season_name, s.year AS season_year
            FROM yearbooks y
            JOIN seasons s ON s.id = y.season_id
            WHERE y.org_id = :o
            ORDER BY s.year DESC NULLS LAST, s.name DESC
        """),
        {"o": org_id},
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Get single yearbook (with sections + honour board) ───────────────────────

@router.get("/{org_id}/{season_id}")
async def get_yearbook(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    yb = await _ensure_stub(db, org_id, season_id)

    sections = await db.execute(
        text("SELECT * FROM yearbook_sections WHERE yearbook_id = :yid ORDER BY sort_order, id"),
        {"yid": str(yb["id"])},
    )
    honour_board = await db.execute(
        text("""
            SELECT h.*, COALESCE(p.display_name_override, p.name) AS player_name
            FROM yearbook_honour_board h
            LEFT JOIN players p ON p.id = h.player_id
            WHERE h.yearbook_id = :yid
            ORDER BY h.sort_order, h.id
        """),
        {"yid": str(yb["id"])},
    )
    images = await db.execute(
        text("SELECT * FROM yearbook_images WHERE yearbook_id = :yid ORDER BY image_type, sort_order"),
        {"yid": str(yb["id"])},
    )

    season = await db.execute(
        text("SELECT id, name, year FROM seasons WHERE id = :s"),
        {"s": season_id},
    )
    season_row = season.mappings().first()

    return {
        **yb,
        "id": str(yb["id"]),
        "season": dict(season_row) if season_row else None,
        "sections": [dict(r) for r in sections.mappings().all()],
        "honour_board": [dict(r) for r in honour_board.mappings().all()],
        "images": [dict(r) for r in images.mappings().all()],
    }


# ─── Stats: season overview ───────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/overview")
async def get_overview(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    grade_join = ""
    grade_where = ""
    params: dict = {"o": org_id, "s": season_id}
    if grade_id:
        grade_join = "JOIN grades g ON g.id = pss.grade_id"
        grade_where = "AND pss.grade_id = :gid"
        params["gid"] = grade_id

    row = await db.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT pss.player_id) AS total_players,
                COUNT(DISTINCT g2.id) AS total_grades,
                COALESCE(SUM(pss.matches), 0) / GREATEST(COUNT(DISTINCT pss.player_id), 1) AS avg_matches_per_player,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.batting_innings), 0) AS total_innings,
                COALESCE(SUM(pss.fifties), 0) AS total_fifties,
                COALESCE(SUM(pss.hundreds), 0) AS total_hundreds,
                COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
            FROM player_season_stats pss
            {grade_join}
            JOIN grades g2 ON g2.id = pss.grade_id
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.season_id = :s
              AND s.organisation_id = :o
              {grade_where}
        """),
        params,
    )
    overview = dict(row.mappings().first() or {})

    # Win/loss/draw record from games
    games_params: dict = {"o": org_id, "s": season_id}
    games_grade_where = ""
    if grade_id:
        games_grade_where = "AND g.id = :gid"
        games_params["gid"] = grade_id

    gr = await db.execute(
        text(f"""
            SELECT
                COUNT(*) AS total_games,
                COUNT(*) FILTER (WHERE gm.result = 'won') AS wins,
                COUNT(*) FILTER (WHERE gm.result = 'lost') AS losses,
                COUNT(*) FILTER (WHERE gm.result = 'draw') AS draws,
                COUNT(*) FILTER (WHERE gm.result = 'tie') AS ties,
                COUNT(*) FILTER (WHERE gm.result NOT IN ('won','lost','draw','tie') OR gm.result IS NULL) AS other
            FROM games gm
            JOIN grades g ON g.id = gm.grade_id
            WHERE g.season_id = :s
              AND g.id IN (
                  SELECT id FROM grades WHERE season_id = :s
              )
              AND g.season_id IN (SELECT id FROM seasons WHERE organisation_id = :o)
              {games_grade_where}
        """),
        games_params,
    )
    game_stats = dict(gr.mappings().first() or {})

    return {**overview, **game_stats}


# ─── Stats: batting leaderboard ───────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/batting")
async def get_batting_stats(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    min_innings: int = Query(1),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id, "min_inn": min_innings, "limit": limit}
    grade_where = "AND pss.grade_id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS matches,
                SUM(pss.batting_innings) AS innings,
                SUM(pss.runs) AS runs,
                SUM(pss.not_outs) AS not_outs,
                MAX(pss.high_score) AS high_score,
                BOOL_OR(pss.is_hs_not_out) AS hs_not_out,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.balls_faced), 0) * 100, 2) AS strike_rate,
                SUM(pss.fifties) AS fifties,
                SUM(pss.hundreds) AS hundreds,
                SUM(pss.ducks) AS ducks,
                SUM(pss.fours) AS fours,
                SUM(pss.sixes) AS sixes
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s
              AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.batting_innings) >= :min_inn
            ORDER BY SUM(pss.runs) DESC NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: bowling leaderboard ───────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/bowling")
async def get_bowling_stats(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    min_wickets: int = Query(1),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id, "min_wkts": min_wickets, "limit": limit}
    grade_where = "AND pss.grade_id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS matches,
                SUM(pss.wickets) AS wickets,
                SUM(pss.bowling_balls) AS balls,
                ROUND(SUM(pss.bowling_balls)::numeric / 6, 1) AS overs,
                SUM(pss.runs_conceded) AS runs_conceded,
                SUM(pss.maidens) AS maidens,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
                ROUND(SUM(pss.bowling_balls)::numeric / NULLIF(SUM(pss.wickets), 0), 1) AS strike_rate,
                MAX(pss.best_bowling_figures) AS best_figures,
                MAX(pss.best_bowling_wickets) AS best_wickets,
                SUM(pss.five_wicket_innings) AS five_fors
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s
              AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.wickets) >= :min_wkts
            ORDER BY SUM(pss.wickets) DESC NULLS LAST, ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) ASC NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: fielding leaderboard ──────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/fielding")
async def get_fielding_stats(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id, "limit": limit}
    grade_where = "AND pss.grade_id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS matches,
                SUM(pss.catches) AS catches,
                SUM(pss.catches_wk) AS catches_wk,
                SUM(pss.catches_non_wk) AS catches_non_wk,
                SUM(pss.run_outs) AS run_outs,
                SUM(pss.stumpings) AS stumpings,
                SUM(pss.catches + pss.run_outs + pss.stumpings) AS total_dismissals
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s
              AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.catches + pss.run_outs + pss.stumpings) > 0
            ORDER BY SUM(pss.catches + pss.run_outs + pss.stumpings) DESC NULLS LAST
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: all-rounders ──────────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/allrounders")
async def get_allrounder_stats(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    min_runs: int = Query(100),
    min_wickets: int = Query(5),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id, "min_runs": min_runs, "min_wkts": min_wickets, "limit": limit}
    grade_where = "AND pss.grade_id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS matches,
                SUM(pss.runs) AS runs,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS bat_avg,
                SUM(pss.wickets) AS wickets,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS bowl_avg,
                (SUM(pss.runs) + SUM(pss.wickets) * 20) AS allrounder_index
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s
              AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.runs) >= :min_runs AND SUM(pss.wickets) >= :min_wkts
            ORDER BY (SUM(pss.runs) + SUM(pss.wickets) * 20) DESC
            LIMIT :limit
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: by the numbers (superlatives) ────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/superlatives")
async def get_superlatives(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_filter_bi = ""
    grade_filter_bs = ""
    if grade_id:
        params["gid"] = grade_id
        grade_filter_bi = "AND bi.game_id IN (SELECT id FROM games WHERE grade_id = :gid)"
        grade_filter_bs = "AND bs.game_id IN (SELECT id FROM games WHERE grade_id = :gid)"

    # Highest individual score
    hi = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bi.runs, bi.not_out, gm.home_team, gm.away_team, gm.played_at,
                   s.name AS season_name
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN games gm ON gm.id = bi.game_id
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              AND p.organisation_id = :o
              {grade_filter_bi}
            ORDER BY bi.runs DESC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    highest_score = dict(hi.mappings().first() or {})

    # Best bowling figures
    bb = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   bs.wickets, bs.runs AS runs_conceded,
                   gm.home_team, gm.away_team, gm.played_at
            FROM bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            JOIN games gm ON gm.id = bs.game_id
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              AND p.organisation_id = :o
              {grade_filter_bs}
            ORDER BY bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    best_bowling = dict(bb.mappings().first() or {})

    # Highest partnership
    hp = await db.execute(
        text(f"""
            SELECT
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name,
                p1.id AS batter1_id, p2.id AS batter2_id,
                pt.runs, pt.wicket_number,
                gm.home_team, gm.away_team
            FROM partnerships pt
            JOIN players p1 ON p1.id = pt.batter1_id
            JOIN players p2 ON p2.id = pt.batter2_id
            JOIN games gm ON gm.id = pt.game_id
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              AND p1.organisation_id = :o
            ORDER BY pt.runs DESC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    best_partnership = dict(hp.mappings().first() or {})

    # Most runs in a single game (team innings total approximated via batting)
    mr = await db.execute(
        text(f"""
            SELECT gm.id AS game_id, gm.home_team, gm.away_team, gm.played_at,
                   SUM(bi.runs) AS team_runs, COUNT(bi.id) AS batters
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN games gm ON gm.id = bi.game_id
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              AND p.organisation_id = :o
              {grade_filter_bi}
            GROUP BY gm.id, gm.home_team, gm.away_team, gm.played_at, bi.innings_number
            ORDER BY SUM(bi.runs) DESC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    highest_team_innings = dict(mr.mappings().first() or {})

    # Most ducks in a season (fun stat)
    md = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(pss.ducks) AS ducks
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s AND p.organisation_id = :o
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.ducks) > 0
            ORDER BY SUM(pss.ducks) DESC
            LIMIT 1
        """),
        params,
    )
    most_ducks = dict(md.mappings().first() or {})

    return {
        "highest_score": highest_score,
        "best_bowling": best_bowling,
        "best_partnership": best_partnership,
        "highest_team_innings": highest_team_innings,
        "most_ducks": most_ducks,
    }


# ─── Stats: match results ─────────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/results")
async def get_match_results(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_where = "AND g.id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                gm.id AS game_id,
                gm.home_team, gm.away_team, gm.result, gm.winning_team,
                gm.played_at,
                g.id AS grade_id, g.name AS grade_name
            FROM games gm
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              {grade_where}
            ORDER BY g.name, gm.played_at NULLS LAST
        """),
        params,
    )
    games = [dict(r) for r in rows.mappings().all()]

    if not games:
        return []

    game_ids = [str(g["game_id"]) for g in games]
    id_list = ", ".join(f"'{gid}'" for gid in game_ids)

    # Top batter per game
    bat = await db.execute(
        text(f"""
            SELECT DISTINCT ON (bi.game_id)
                bi.game_id,
                COALESCE(p.display_name_override, p.name) AS top_batter,
                p.id AS top_batter_id,
                bi.runs AS top_runs,
                bi.not_out AS top_batter_no
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            WHERE bi.game_id IN ({id_list})
              AND p.organisation_id = :o
            ORDER BY bi.game_id, bi.runs DESC NULLS LAST
        """),
        {"o": org_id},
    )
    bat_map = {str(r["game_id"]): dict(r) for r in bat.mappings().all()}

    # Top bowler per game
    bowl = await db.execute(
        text(f"""
            SELECT DISTINCT ON (bs.game_id)
                bs.game_id,
                COALESCE(p.display_name_override, p.name) AS top_bowler,
                p.id AS top_bowler_id,
                bs.wickets AS top_wickets,
                bs.runs AS top_bowl_runs
            FROM bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            WHERE bs.game_id IN ({id_list})
              AND p.organisation_id = :o
            ORDER BY bs.game_id, bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST
        """),
        {"o": org_id},
    )
    bowl_map = {str(r["game_id"]): dict(r) for r in bowl.mappings().all()}

    for g in games:
        gid = str(g["game_id"])
        g.update(bat_map.get(gid, {}))
        g.update(bowl_map.get(gid, {}))

    return games


# ─── Stats: partnerships ──────────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/partnerships")
async def get_partnership_stats(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_where = ""
    if grade_id:
        grade_where = "AND g.id = :gid"
        params["gid"] = grade_id

    # Top 10 overall + top per wicket number
    top = await db.execute(
        text(f"""
            SELECT
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name,
                p1.id AS batter1_id, p2.id AS batter2_id,
                pt.runs, pt.wicket_number, pt.balls,
                pt.batter1_runs, pt.batter2_runs
            FROM partnerships pt
            JOIN players p1 ON p1.id = pt.batter1_id
            JOIN players p2 ON p2.id = pt.batter2_id
            JOIN games gm ON gm.id = pt.game_id
            JOIN grades g ON g.id = gm.grade_id
            WHERE g.season_id = :s AND p1.organisation_id = :o
              {grade_where}
            ORDER BY pt.runs DESC NULLS LAST
            LIMIT 10
        """),
        params,
    )

    by_wicket = await db.execute(
        text(f"""
            SELECT DISTINCT ON (pt.wicket_number)
                pt.wicket_number,
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name,
                p1.id AS batter1_id, p2.id AS batter2_id,
                pt.runs, pt.balls
            FROM partnerships pt
            JOIN players p1 ON p1.id = pt.batter1_id
            JOIN players p2 ON p2.id = pt.batter2_id
            JOIN games gm ON gm.id = pt.game_id
            JOIN grades g ON g.id = gm.grade_id
            WHERE g.season_id = :s AND p1.organisation_id = :o
              {grade_where}
            ORDER BY pt.wicket_number, pt.runs DESC NULLS LAST
        """),
        params,
    )

    return {
        "top_partnerships": [dict(r) for r in top.mappings().all()],
        "by_wicket": [dict(r) for r in by_wicket.mappings().all()],
    }


# ─── Stats: milestones achieved this season ───────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/milestones")
async def get_season_milestones(
    org_id: str,
    season_id: str,
    db: AsyncSession = Depends(get_db),
):
    # Get season date range
    s_row = await db.execute(
        text("SELECT s.*, MIN(gm.played_at) AS first_game, MAX(gm.played_at) AS last_game FROM seasons s LEFT JOIN grades g ON g.season_id = s.id LEFT JOIN games gm ON gm.grade_id = g.id WHERE s.id = :s AND s.organisation_id = :o GROUP BY s.id"),
        {"s": season_id, "o": org_id},
    )
    season = s_row.mappings().first()
    if not season:
        return []

    rows = await db.execute(
        text("""
            SELECT m.*, COALESCE(p.display_name_override, p.name) AS player_name, p.id AS player_id
            FROM milestones m
            JOIN players p ON p.id = m.player_id
            WHERE p.organisation_id = :o
              AND m.achieved_at >= COALESCE(:first_game, '1900-01-01'::date)
              AND m.achieved_at <= COALESCE(:last_game, NOW()::date)
            ORDER BY m.achieved_at
        """),
        {"o": org_id, "first_game": season["first_game"], "last_game": season["last_game"]},
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: grade breakdown ───────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/grades")
async def get_grade_breakdown(
    org_id: str,
    season_id: str,
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}

    grades = await db.execute(
        text("""
            SELECT DISTINCT g.id, g.name
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
            ORDER BY g.name
        """),
        params,
    )
    grade_list = [dict(r) for r in grades.mappings().all()]

    result = []
    for grade in grade_list:
        stats = await db.execute(
            text("""
                SELECT
                    COUNT(DISTINCT pss.player_id) AS players,
                    SUM(pss.runs) AS runs,
                    SUM(pss.wickets) AS wickets,
                    MAX(pss.high_score) AS high_score
                FROM player_season_stats pss
                WHERE pss.season_id = :s AND pss.grade_id = :gid
            """),
            {"s": season_id, "gid": str(grade["id"])},
        )
        grade_stats = dict(stats.mappings().first() or {})

        # Top batter
        tb = await db.execute(
            text("""
                SELECT COALESCE(p.display_name_override, p.name) AS name, p.id, SUM(pss.runs) AS runs
                FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
                WHERE pss.season_id = :s AND pss.grade_id = :gid
                GROUP BY p.id, p.name, p.display_name_override
                ORDER BY SUM(pss.runs) DESC NULLS LAST LIMIT 1
            """),
            {"s": season_id, "gid": str(grade["id"])},
        )
        top_bat = dict(tb.mappings().first() or {})

        # Top bowler
        tw = await db.execute(
            text("""
                SELECT COALESCE(p.display_name_override, p.name) AS name, p.id, SUM(pss.wickets) AS wickets
                FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
                WHERE pss.season_id = :s AND pss.grade_id = :gid
                GROUP BY p.id, p.name, p.display_name_override
                ORDER BY SUM(pss.wickets) DESC NULLS LAST LIMIT 1
            """),
            {"s": season_id, "gid": str(grade["id"])},
        )
        top_bowl = dict(tw.mappings().first() or {})

        result.append({
            **grade,
            **grade_stats,
            "top_batter": top_bat,
            "top_bowler": top_bowl,
        })

    return result


# ─── Stats: dismissal breakdown ───────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/dismissals")
async def get_dismissal_breakdown(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_where = ""
    if grade_id:
        grade_where = "AND g.id = :gid"
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                COALESCE(bi.dismissal_type, 'unknown') AS dismissal_type,
                COUNT(*) AS count
            FROM batting_innings bi
            JOIN players p ON p.id = bi.player_id
            JOIN games gm ON gm.id = bi.game_id
            JOIN grades g ON g.id = gm.grade_id
            WHERE g.season_id = :s AND p.organisation_id = :o
              {grade_where}
            GROUP BY bi.dismissal_type
            ORDER BY COUNT(*) DESC
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Stats: player cards (all players this season) ────────────────────────────

@router.get("/{org_id}/{season_id}/stats/players")
async def get_season_players(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_where = "AND pss.grade_id = :gid" if grade_id else ""
    if grade_id:
        params["gid"] = grade_id

    rows = await db.execute(
        text(f"""
            SELECT
                p.id AS player_id,
                COALESCE(p.display_name_override, p.name) AS name,
                SUM(pss.matches) AS matches,
                SUM(pss.batting_innings) AS innings,
                SUM(pss.runs) AS runs,
                MAX(pss.high_score) AS high_score,
                ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS bat_avg,
                SUM(pss.wickets) AS wickets,
                ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS bowl_avg,
                SUM(pss.catches + pss.run_outs + pss.stumpings) AS dismissals,
                SUM(pss.fifties) AS fifties,
                SUM(pss.hundreds) AS hundreds
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            ORDER BY COALESCE(p.display_name_override, p.name)
        """),
        params,
    )
    return [dict(r) for r in rows.mappings().all()]


# ─── Admin: publish / unpublish ───────────────────────────────────────────────

@router.post("/{org_id}/{season_id}/publish")
async def publish_yearbook(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("UPDATE yearbooks SET status = 'published', published_at = NOW(), updated_at = NOW() WHERE id = :id"),
        {"id": str(yb["id"])},
    )
    await db.commit()
    return {"status": "published"}


@router.post("/{org_id}/{season_id}/unpublish")
async def unpublish_yearbook(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("UPDATE yearbooks SET status = 'draft', updated_at = NOW() WHERE id = :id"),
        {"id": str(yb["id"])},
    )
    await db.commit()
    return {"status": "draft"}


# ─── Admin: sections (narrative / toggleable) ─────────────────────────────────

class SectionUpsert(BaseModel):
    section_type: str
    title: str
    content_markdown: Optional[str] = None
    sort_order: int = 0
    is_enabled: bool = True


@router.put("/{org_id}/{season_id}/sections/{section_id}")
async def update_section(
    org_id: str,
    season_id: str,
    section_id: int,
    body: SectionUpsert,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("""
            UPDATE yearbook_sections
            SET title = :title,
                content_markdown = :content,
                sort_order = :order,
                is_enabled = :enabled,
                updated_at = NOW()
            WHERE id = :id AND yearbook_id = :yid
        """),
        {
            "id": section_id,
            "yid": str(yb["id"]),
            "title": body.title,
            "content": body.content_markdown,
            "order": body.sort_order,
            "enabled": body.is_enabled,
        },
    )
    await db.commit()
    return {"status": "updated"}


@router.post("/{org_id}/{season_id}/sections")
async def create_section(
    org_id: str,
    season_id: str,
    body: SectionUpsert,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    result = await db.execute(
        text("""
            INSERT INTO yearbook_sections
                (yearbook_id, section_type, title, content_markdown, sort_order, is_enabled)
            VALUES (:yid, :type, :title, :content, :order, :enabled)
            RETURNING id
        """),
        {
            "yid": str(yb["id"]),
            "type": body.section_type,
            "title": body.title,
            "content": body.content_markdown,
            "order": body.sort_order,
            "enabled": body.is_enabled,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


@router.delete("/{org_id}/{season_id}/sections/{section_id}")
async def delete_section(
    org_id: str,
    season_id: str,
    section_id: int,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("DELETE FROM yearbook_sections WHERE id = :id AND yearbook_id = :yid"),
        {"id": section_id, "yid": str(yb["id"])},
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Admin: honour board ──────────────────────────────────────────────────────

class HonourBoardEntry(BaseModel):
    position_title: str
    player_id: Optional[str] = None
    name_override: Optional[str] = None
    sort_order: int = 0


@router.post("/{org_id}/{season_id}/honour-board")
async def add_honour_board_entry(
    org_id: str,
    season_id: str,
    body: HonourBoardEntry,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    result = await db.execute(
        text("""
            INSERT INTO yearbook_honour_board
                (yearbook_id, position_title, player_id, name_override, sort_order)
            VALUES (:yid, :pos, :pid, :name, :order)
            RETURNING id
        """),
        {
            "yid": str(yb["id"]),
            "pos": body.position_title,
            "pid": body.player_id,
            "name": body.name_override,
            "order": body.sort_order,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


@router.delete("/{org_id}/{season_id}/honour-board/{entry_id}")
async def delete_honour_board_entry(
    org_id: str,
    season_id: str,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("DELETE FROM yearbook_honour_board WHERE id = :id AND yearbook_id = :yid"),
        {"id": entry_id, "yid": str(yb["id"])},
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Admin: trigger stub generation ──────────────────────────────────────────

@router.post("/{org_id}/generate-stubs")
async def trigger_stub_generation(org_id: str, db: AsyncSession = Depends(get_db)):
    created = await generate_stubs_for_org(db, org_id)
    return {"created": created}


# ─── AI narrative generation ──────────────────────────────────────────────────

def _fmt(n, dec=2):
    if n is None:
        return "—"
    try:
        return f"{float(n):.{dec}f}"
    except (TypeError, ValueError):
        return str(n)


def _build_narrative_prompt(org_name: str, season_name: str, overview: dict,
                             batting: list, bowling: list, superlatives: dict,
                             milestones: list) -> str:
    wins = overview.get("wins", 0) or 0
    losses = overview.get("losses", 0) or 0
    draws = overview.get("draws", 0) or 0
    players = overview.get("total_players", 0) or 0
    total_runs = overview.get("total_runs", 0) or 0
    total_wkts = overview.get("total_wickets", 0) or 0

    top_bat = batting[:5] if batting else []
    top_bowl = bowling[:5] if bowling else []

    bat_lines = "\n".join(
        f"  - {p['name']}: {p.get('runs', 0)} runs, avg {_fmt(p.get('average'))}, HS {p.get('high_score', '—')}"
        for p in top_bat
    )
    bowl_lines = "\n".join(
        f"  - {p['name']}: {p.get('wickets', 0)} wickets, avg {_fmt(p.get('average'))}, best {p.get('best_figures', '—')}"
        for p in top_bowl
    )

    sup = superlatives or {}
    hs = sup.get("highest_score", {})
    bb = sup.get("best_bowling", {})
    bp = sup.get("best_partnership", {})

    milestone_lines = ""
    if milestones:
        milestone_lines = "\nCareer milestones crossed this season:\n" + "\n".join(
            f"  - {m.get('player_name', '?')}: {m.get('milestone_type', '')} {m.get('milestone_value', '')}"
            for m in milestones[:8]
        )

    return f"""You are writing the "Season in Brief" editorial section for {org_name}'s {season_name} season yearbook.

Season data:
- Record: {wins}W {draws}D {losses}L from {int(wins)+int(draws)+int(losses)} games
- {players} players represented the club
- {int(total_runs):,} runs scored, {int(total_wkts)} wickets taken

Leading batters:
{bat_lines or "  No data"}

Leading bowlers:
{bowl_lines or "  No data"}

Standout performances:
{f"  - Highest score: {hs.get('name', '?')} {hs.get('runs', '?')}{'*' if hs.get('not_out') else ''}" if hs.get('player_id') else ""}
{f"  - Best bowling: {bb.get('name', '?')} {bb.get('wickets', '?')}/{bb.get('runs_conceded', '?')}" if bb.get('player_id') else ""}
{f"  - Best partnership: {bp.get('batter1_name', '?')} & {bp.get('batter2_name', '?')} — {bp.get('runs', '?')} runs" if bp.get('batter1_id') else ""}
{milestone_lines}

Write 3–4 paragraphs as a warm, conversational club yearbook narrative. Rules:
- Open with a punchy one-sentence summary of the season's character (e.g. results, tone, any major storyline)
- Reference specific players and numbers naturally — don't just list stats, weave them into sentences
- Acknowledge both highlights and honest disappointments if the record warrants it
- End on a forward-looking or celebratory note
- Tone: casual and warm, like a club member who cares about the team wrote it — not corporate
- Do NOT use nicknames unless they appear in the data
- Do NOT use bullet points or headings — flowing prose only
- Keep it under 350 words"""


@router.post("/{org_id}/{season_id}/generate-narrative")
async def generate_narrative(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="Anthropic API key not configured")

    try:
        import anthropic as anthropic_sdk
    except ImportError:
        raise HTTPException(status_code=503, detail="anthropic package not installed")

    yb = await _ensure_stub(db, org_id, season_id)

    # Gather season stats concurrently via direct SQL
    org_row = await db.execute(text("SELECT name FROM organisations WHERE id = :o"), {"o": org_id})
    org_name = (org_row.mappings().first() or {}).get("name", "the club")

    season_row = await db.execute(text("SELECT name FROM seasons WHERE id = :s"), {"s": season_id})
    season_name = (season_row.mappings().first() or {}).get("name", "the season")

    # Re-use the stats helpers defined earlier in this module
    from app.routers.yearbooks import (
        get_overview, get_batting_stats, get_bowling_stats,
        get_superlatives, get_season_milestones,
    )

    # We need a mock Request object — easier to just inline the queries directly
    params = {"o": org_id, "s": season_id}

    ov_row = await db.execute(text("""
        SELECT
            COUNT(DISTINCT pss.player_id) AS total_players,
            COALESCE(SUM(pss.runs), 0) AS total_runs,
            COALESCE(SUM(pss.wickets), 0) AS total_wickets
        FROM player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        WHERE pss.season_id = :s AND s.organisation_id = :o
    """), params)
    overview = dict(ov_row.mappings().first() or {})

    games_row = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE gm.result = 'won') AS wins,
            COUNT(*) FILTER (WHERE gm.result = 'lost') AS losses,
            COUNT(*) FILTER (WHERE gm.result = 'draw') AS draws
        FROM games gm
        JOIN grades g ON g.id = gm.grade_id
        WHERE g.season_id = :s
          AND g.season_id IN (SELECT id FROM seasons WHERE organisation_id = :o)
    """), params)
    overview.update(dict(games_row.mappings().first() or {}))

    bat_rows = await db.execute(text("""
        SELECT COALESCE(p.display_name_override, p.name) AS name,
               SUM(pss.runs) AS runs,
               MAX(pss.high_score) AS high_score,
               ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average
        FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
        WHERE pss.season_id = :s AND p.organisation_id = :o
        GROUP BY p.id, p.name, p.display_name_override
        HAVING SUM(pss.batting_innings) >= 3
        ORDER BY SUM(pss.runs) DESC NULLS LAST LIMIT 5
    """), params)
    batting = [dict(r) for r in bat_rows.mappings().all()]

    bowl_rows = await db.execute(text("""
        SELECT COALESCE(p.display_name_override, p.name) AS name,
               SUM(pss.wickets) AS wickets,
               MAX(pss.best_bowling_figures) AS best_figures,
               ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average
        FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
        WHERE pss.season_id = :s AND p.organisation_id = :o
        GROUP BY p.id, p.name, p.display_name_override
        HAVING SUM(pss.wickets) >= 3
        ORDER BY SUM(pss.wickets) DESC NULLS LAST LIMIT 5
    """), params)
    bowling = [dict(r) for r in bowl_rows.mappings().all()]

    hs_row = await db.execute(text("""
        SELECT COALESCE(p.display_name_override, p.name) AS name, p.id AS player_id,
               bi.runs, bi.not_out
        FROM batting_innings bi JOIN players p ON p.id = bi.player_id
        JOIN games gm ON gm.id = bi.game_id JOIN grades g ON g.id = gm.grade_id
        WHERE g.season_id = :s AND p.organisation_id = :o
        ORDER BY bi.runs DESC NULLS LAST LIMIT 1
    """), params)
    bb_row = await db.execute(text("""
        SELECT COALESCE(p.display_name_override, p.name) AS name, p.id AS player_id,
               bs.wickets, bs.runs AS runs_conceded
        FROM bowling_spells bs JOIN players p ON p.id = bs.player_id
        JOIN games gm ON gm.id = bs.game_id JOIN grades g ON g.id = gm.grade_id
        WHERE g.season_id = :s AND p.organisation_id = :o
        ORDER BY bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST LIMIT 1
    """), params)
    bp_row = await db.execute(text("""
        SELECT COALESCE(p1.display_name_override, p1.name) AS batter1_name,
               COALESCE(p2.display_name_override, p2.name) AS batter2_name,
               p1.id AS batter1_id, pt.runs, pt.wicket_number
        FROM partnerships pt
        JOIN players p1 ON p1.id = pt.batter1_id JOIN players p2 ON p2.id = pt.batter2_id
        JOIN games gm ON gm.id = pt.game_id JOIN grades g ON g.id = gm.grade_id
        WHERE g.season_id = :s AND p1.organisation_id = :o
        ORDER BY pt.runs DESC NULLS LAST LIMIT 1
    """), params)
    superlatives = {
        "highest_score": dict(hs_row.mappings().first() or {}),
        "best_bowling": dict(bb_row.mappings().first() or {}),
        "best_partnership": dict(bp_row.mappings().first() or {}),
    }

    s_dates = await db.execute(text("""
        SELECT MIN(gm.played_at) AS first_game, MAX(gm.played_at) AS last_game
        FROM games gm JOIN grades g ON g.id = gm.grade_id WHERE g.season_id = :s
    """), {"s": season_id})
    s_d = s_dates.mappings().first() or {}
    milestones = []
    if s_d.get("first_game"):
        m_rows = await db.execute(text("""
            SELECT m.milestone_type, m.milestone_value,
                   COALESCE(p.display_name_override, p.name) AS player_name
            FROM milestones m JOIN players p ON p.id = m.player_id
            WHERE p.organisation_id = :o
              AND m.achieved_at BETWEEN :f AND :l
            ORDER BY m.achieved_at LIMIT 8
        """), {"o": org_id, "f": s_d["first_game"], "l": s_d["last_game"]})
        milestones = [dict(r) for r in m_rows.mappings().all()]

    prompt = _build_narrative_prompt(org_name, season_name, overview, batting, bowling, superlatives, milestones)

    client = anthropic_sdk.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    narrative_text = message.content[0].text.strip()

    # Upsert the narrative section
    existing = await db.execute(
        text("SELECT id FROM yearbook_sections WHERE yearbook_id = :yid AND section_type = 'narrative'"),
        {"yid": str(yb["id"])},
    )
    existing_row = existing.mappings().first()

    if existing_row:
        await db.execute(
            text("""
                UPDATE yearbook_sections
                SET ai_draft = :draft, updated_at = NOW()
                WHERE id = :id
            """),
            {"draft": narrative_text, "id": existing_row["id"]},
        )
        section_id = existing_row["id"]
    else:
        result = await db.execute(
            text("""
                INSERT INTO yearbook_sections
                    (yearbook_id, section_type, title, ai_draft, sort_order, is_enabled)
                VALUES (:yid, 'narrative', 'Season in Brief', :draft, 0, true)
                RETURNING id
            """),
            {"yid": str(yb["id"]), "draft": narrative_text},
        )
        section_id = result.scalar()

    await db.commit()
    return {"section_id": section_id, "narrative": narrative_text}
