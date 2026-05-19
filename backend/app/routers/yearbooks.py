from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid
import logging
import shutil
from pathlib import Path

from app.models.db import get_db
from app.config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yearbooks", tags=["yearbooks"])

UPLOAD_DIR = Path("/app/uploads")


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


def _season_match_keys(season_id: str, season_name: str | None) -> list[str]:
    """Achievement rows store `season` as either the season UUID (when added via
    the form) or a text key like '2025_26' (when CSV-imported). Build the set of
    strings to match against `player_achievements.season` for a given season."""
    import re
    keys: set[str] = {str(season_id)}
    if not season_name:
        return list(keys)
    keys.add(season_name)
    m = re.search(r"(\d{4})/(\d{2,4})", season_name)
    if m:
        y1, y2 = m.group(1), m.group(2)[-2:]
        keys.update({f"{y1}_{y2}", f"{y1}-{y2}", f"{y1}/{y2}"})
    m = re.search(r"(\d{4})", season_name)
    if m:
        keys.add(m.group(1))
    return list(keys)


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
    awards = await db.execute(
        text("""
            SELECT a.*, COALESCE(p.display_name_override, p.name) AS player_name
            FROM yearbook_club_awards a
            LEFT JOIN players p ON p.id = a.player_id
            WHERE a.yearbook_id = :yid
            ORDER BY a.sort_order, a.id
        """),
        {"yid": str(yb["id"])},
    )

    season = await db.execute(
        text("SELECT id, name, year FROM seasons WHERE id = :s"),
        {"s": season_id},
    )
    season_row = season.mappings().first()

    # Build org-wide season-id → start-year map so we can resolve
    # `player_achievements.season` (which may be a UUID or a text key) to
    # a year and bracket-match multi-season roles via `season_end`.
    org_seasons = await db.execute(
        text("SELECT id, name, year FROM seasons WHERE organisation_id = :o"),
        {"o": org_id},
    )
    year_by_id: dict[str, int] = {}
    for r in org_seasons.mappings().all():
        yr = r["year"]
        if yr is None and r["name"]:
            import re as _re
            mm = _re.search(r"(\d{4})", r["name"])
            yr = int(mm.group(1)) if mm else None
        if yr is not None:
            year_by_id[str(r["id"])] = yr

    def _year_from(token: str | None) -> int | None:
        if not token:
            return None
        if token in year_by_id:
            return year_by_id[token]
        import re as _re
        m = _re.search(r"(\d{4})", token)
        return int(m.group(1)) if m else None

    target_year: int | None = None
    if season_row:
        target_year = season_row.get("year") or _year_from(season_row.get("name"))

    match_keys = _season_match_keys(
        season_id, season_row["name"] if season_row else None
    )

    # Pull all org achievements, then filter in Python so we can honour both
    # exact-string season matches AND date-spanning ranges (season → season_end).
    all_ach = await db.execute(
        text("""
            SELECT a.id, a.category, a.subcategory, a.achievement, a.detail,
                   a.season, a.season_end, a.player_id,
                   COALESCE(p.display_name_override, p.name, a.player_name) AS player_name
            FROM player_achievements a
            LEFT JOIN players p ON p.id = a.player_id
            WHERE a.org_id = :o
            ORDER BY a.category, a.subcategory NULLS LAST, a.achievement, a.id
        """),
        {"o": org_id},
    )
    # Empty `season` means "All Time" in the Achievements admin form.
    # Empty `season_end` (for Office Bearer) means "Present" — role is ongoing
    # — and therefore should appear on every yearbook from the start year on.
    match_key_set = set(match_keys)
    pulled_rows = []
    for row in all_ach.mappings().all():
        s_token, e_token = row["season"], row["season_end"]

        if not s_token:
            pulled_rows.append(dict(row))
            continue

        if s_token in match_key_set or (e_token and e_token in match_key_set):
            pulled_rows.append(dict(row))
            continue

        if target_year is None:
            continue

        s_year = _year_from(s_token)
        if s_year is None:
            continue

        if e_token:
            e_year = _year_from(e_token)
            if e_year is None:
                if s_year == target_year:
                    pulled_rows.append(dict(row))
                continue
            lo, hi = (s_year, e_year) if s_year <= e_year else (e_year, s_year)
            if lo <= target_year <= hi:
                pulled_rows.append(dict(row))
        else:
            # No season_end: single-season record — match exact year only.
            if s_year == target_year:
                pulled_rows.append(dict(row))

    featured = await db.execute(
        text("SELECT achievement_id FROM yearbook_featured_achievements WHERE yearbook_id = :yid ORDER BY sort_order, id"),
        {"yid": str(yb["id"])},
    )
    featured_ids = [str(r["achievement_id"]) for r in featured.mappings().all()]

    return {
        **yb,
        "id": str(yb["id"]),
        "season": dict(season_row) if season_row else None,
        "sections": [dict(r) for r in sections.mappings().all()],
        "honour_board": [dict(r) for r in honour_board.mappings().all()],
        "images": [dict(r) for r in images.mappings().all()],
        "awards": [dict(r) for r in awards.mappings().all()],
        "pulled_awards": pulled_rows,
        "featured_achievement_ids": featured_ids,
    }


# ─── Stats: season overview ───────────────────────────────────────────────────

@router.get("/{org_id}/{season_id}/stats/overview")
async def get_overview(
    org_id: str,
    season_id: str,
    grade_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    params: dict = {"o": org_id, "s": season_id}
    grade_filter = ""
    if grade_id:
        grade_filter = """
            AND pss.player_id IN (
                SELECT DISTINCT bi.player_id
                FROM batting_innings bi
                JOIN games gm ON gm.id = bi.game_id
                WHERE gm.grade_id = :gid
            )
        """
        params["gid"] = grade_id

    row = await db.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT pss.player_id) AS total_players,
                (SELECT COUNT(DISTINCT g.id) FROM grades g WHERE g.season_id = :s) AS total_grades,
                COALESCE(SUM(pss.matches), 0) / GREATEST(COUNT(DISTINCT pss.player_id), 1) AS avg_matches_per_player,
                COALESCE(SUM(pss.runs), 0) AS total_runs,
                COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                COALESCE(SUM(pss.batting_innings), 0) AS total_innings,
                COALESCE(SUM(pss.fifties), 0) AS total_fifties,
                COALESCE(SUM(pss.hundreds), 0) AS total_hundreds,
                COALESCE(SUM(pss.catches + pss.run_outs + pss.stumpings), 0) AS total_dismissals
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            WHERE pss.season_id = :s
              AND s.organisation_id = :o
              {grade_filter}
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
                COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('win','won')) AS wins,
                COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('loss','lost')) AS losses,
                COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('draw','drew','tie')) AS draws,
                COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('draw','drew','tie')) AS ties,
                COUNT(*) FILTER (WHERE LOWER(gm.result) NOT IN ('win','won','loss','lost','draw','drew','tie') OR gm.result IS NULL) AS other
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
    grade_where = ""
    if grade_id:
        grade_where = "AND pss.player_id IN (SELECT DISTINCT bi.player_id FROM batting_innings bi JOIN games gm ON gm.id = bi.game_id WHERE gm.grade_id = :gid)"
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
    grade_where = ""
    if grade_id:
        grade_where = "AND pss.player_id IN (SELECT DISTINCT bs.player_id FROM bowling_spells bs JOIN games gm ON gm.id = bs.game_id WHERE gm.grade_id = :gid)"
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
    grade_where = ""
    if grade_id:
        grade_where = "AND pss.player_id IN (SELECT DISTINCT bi.player_id FROM batting_innings bi JOIN games gm ON gm.id = bi.game_id WHERE gm.grade_id = :gid)"
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
    grade_where = ""
    if grade_id:
        grade_where = "AND pss.player_id IN (SELECT DISTINCT bi.player_id FROM batting_innings bi JOIN games gm ON gm.id = bi.game_id WHERE gm.grade_id = :gid)"
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
                ROUND(SUM(pss.runs) * 1.5 + SUM(pss.wickets) * 10, 2) AS allrounder_index
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s
              AND p.organisation_id = :o
              {grade_where}
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.runs) >= :min_runs AND SUM(pss.wickets) >= :min_wkts
            ORDER BY (SUM(pss.runs) * 1.5 + SUM(pss.wickets) * 10) DESC
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
              AND p1.organisation_id = :o AND p2.organisation_id = :o
              AND pt.is_club_innings IS NOT FALSE
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

    # Most runs in a season (individual)
    mr_ind = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(pss.runs) AS runs,
                   ROUND(SUM(pss.runs)::numeric / NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average
            FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s AND p.organisation_id = :o
            GROUP BY p.id, p.name, p.display_name_override
            ORDER BY SUM(pss.runs) DESC NULLS LAST LIMIT 1
        """),
        params,
    )
    most_runs = dict(mr_ind.mappings().first() or {})

    # Most wickets in a season (individual)
    mw_ind = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(pss.wickets) AS wickets,
                   ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average
            FROM player_season_stats pss JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s AND p.organisation_id = :o
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.wickets) > 0
            ORDER BY SUM(pss.wickets) DESC NULLS LAST LIMIT 1
        """),
        params,
    )
    most_wickets = dict(mw_ind.mappings().first() or {})

    # Most 5-wicket hauls (fifers)
    mf = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) AS fifers
            FROM bowling_spells bs
            JOIN players p ON p.id = bs.player_id
            JOIN games gm ON gm.id = bs.game_id
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              AND p.organisation_id = :o
              AND bs.wickets >= 5
              {grade_filter_bs}
            GROUP BY p.id, p.name, p.display_name_override
            ORDER BY COUNT(*) DESC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    most_fifers = dict(mf.mappings().first() or {})

    # Best bowling average (min 10 wickets)
    ba = await db.execute(
        text(f"""
            SELECT p.id AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(pss.wickets) AS wickets,
                   ROUND(SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0), 2) AS average
            FROM player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            WHERE pss.season_id = :s AND p.organisation_id = :o
            GROUP BY p.id, p.name, p.display_name_override
            HAVING SUM(pss.wickets) >= 10
            ORDER BY SUM(pss.runs_conceded)::numeric / NULLIF(SUM(pss.wickets), 0) ASC NULLS LAST
            LIMIT 1
        """),
        params,
    )
    best_bowling_average = dict(ba.mappings().first() or {})

    return {
        "highest_score": highest_score,
        "best_bowling": best_bowling,
        "best_partnership": best_partnership,
        "highest_team_innings": highest_team_innings,
        "most_ducks": most_ducks,
        "most_runs": most_runs,
        "most_wickets": most_wickets,
        "most_fifers": most_fifers,
        "best_bowling_average": best_bowling_average,
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
                g.id AS grade_id, COALESCE(g.display_name_override, g.name) AS grade_name
            FROM games gm
            JOIN grades g ON g.id = gm.grade_id
            JOIN seasons s ON s.id = g.season_id
            WHERE g.season_id = :s AND s.organisation_id = :o
              {grade_where}
            ORDER BY COALESCE(g.display_name_override, g.name), gm.played_at NULLS LAST
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
            WHERE g.season_id = :s AND p1.organisation_id = :o AND p2.organisation_id = :o
              AND pt.is_club_innings IS NOT FALSE
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
            WHERE g.season_id = :s AND p1.organisation_id = :o AND p2.organisation_id = :o
              AND pt.is_club_innings IS NOT FALSE
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
    grades_rows = await db.execute(
        text("""
            SELECT DISTINCT ON (g.name) g.id, g.name,
                COUNT(gm.id) AS game_count
            FROM grades g
            JOIN seasons s ON s.id = g.season_id
            LEFT JOIN games gm ON gm.grade_id = g.id
            WHERE g.season_id = :s AND s.organisation_id = :o
            GROUP BY g.id, g.name
            ORDER BY g.name, COUNT(gm.id) DESC
        """),
        {"o": org_id, "s": season_id},
    )
    grade_list = [dict(r) for r in grades_rows.mappings().all()]

    result = []
    for grade in grade_list:
        gid = str(grade["id"])
        p = {"gid": gid, "o": org_id, "s": season_id}

        stats = await db.execute(
            text("""
                SELECT COUNT(DISTINCT bi.player_id) AS players, SUM(bi.runs) AS runs
                FROM batting_innings bi
                JOIN games gm ON gm.id = bi.game_id
                JOIN players pl ON pl.id = bi.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
            """), p)
        grade_bat_stats = dict(stats.mappings().first() or {})

        wkt_row = await db.execute(
            text("""
                SELECT SUM(bs.wickets) AS wickets
                FROM bowling_spells bs
                JOIN games gm ON gm.id = bs.game_id
                JOIN players pl ON pl.id = bs.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
            """), p)
        grade_bowl_stats = dict(wkt_row.mappings().first() or {})

        hs = await db.execute(
            text("""
                SELECT bi.runs AS high_score, bi.not_out,
                    COALESCE(pl.display_name_override, pl.name) AS high_score_name,
                    pl.id AS high_score_player_id
                FROM batting_innings bi
                JOIN games gm ON gm.id = bi.game_id
                JOIN players pl ON pl.id = bi.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
                ORDER BY bi.runs DESC NULLS LAST LIMIT 1
            """), p)
        hs_row = dict(hs.mappings().first() or {})

        tb = await db.execute(
            text("""
                SELECT COALESCE(pl.display_name_override, pl.name) AS name,
                    pl.id, SUM(bi.runs) AS runs
                FROM batting_innings bi
                JOIN games gm ON gm.id = bi.game_id
                JOIN players pl ON pl.id = bi.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
                GROUP BY pl.id, pl.name, pl.display_name_override
                ORDER BY SUM(bi.runs) DESC NULLS LAST LIMIT 1
            """), p)
        top_bat = dict(tb.mappings().first() or {})

        tw = await db.execute(
            text("""
                SELECT COALESCE(pl.display_name_override, pl.name) AS name,
                    pl.id, SUM(bs.wickets) AS wickets
                FROM bowling_spells bs
                JOIN games gm ON gm.id = bs.game_id
                JOIN players pl ON pl.id = bs.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
                GROUP BY pl.id, pl.name, pl.display_name_override
                ORDER BY SUM(bs.wickets) DESC NULLS LAST LIMIT 1
            """), p)
        top_bowl = dict(tw.mappings().first() or {})

        bb = await db.execute(
            text("""
                SELECT bs.wickets AS bb_wickets, bs.runs AS bb_runs,
                    COALESCE(pl.display_name_override, pl.name) AS bb_name,
                    pl.id AS bb_player_id
                FROM bowling_spells bs
                JOIN games gm ON gm.id = bs.game_id
                JOIN players pl ON pl.id = bs.player_id
                WHERE gm.grade_id = :gid AND pl.organisation_id = :o
                ORDER BY bs.wickets DESC NULLS LAST, bs.runs ASC NULLS LAST LIMIT 1
            """), p)
        bb_row = dict(bb.mappings().first() or {})

        wl = await db.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('win','won')) AS wins,
                    COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('loss','lost')) AS losses
                FROM games gm WHERE gm.grade_id = :gid
            """), p)
        wl_stats = dict(wl.mappings().first() or {})

        result.append({
            "id": gid,
            "name": grade["name"],
            "game_count": grade["game_count"],
            **grade_bat_stats,
            **grade_bowl_stats,
            **wl_stats,
            "high_score": hs_row.get("high_score"),
            "high_score_not_out": hs_row.get("not_out"),
            "high_score_name": hs_row.get("high_score_name"),
            "high_score_player_id": hs_row.get("high_score_player_id"),
            "best_bowling_wickets": bb_row.get("bb_wickets"),
            "best_bowling_runs": bb_row.get("bb_runs"),
            "best_bowling_name": bb_row.get("bb_name"),
            "best_bowling_player_id": bb_row.get("bb_player_id"),
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
    grade_where = ""
    if grade_id:
        grade_where = "AND pss.player_id IN (SELECT DISTINCT bi.player_id FROM batting_innings bi JOIN games gm ON gm.id = bi.game_id WHERE gm.grade_id = :gid)"
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
                SUM(pss.catches) AS catches,
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


# ─── Admin: image uploads ─────────────────────────────────────────────────────

ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def _save_upload(file: UploadFile, org_id: str, prefix: str) -> str:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, "Image files only (jpg, png, webp, gif)")
    dest_dir = UPLOAD_DIR / "yearbooks" / org_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex}{ext}"
    with (dest_dir / filename).open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return f"yearbooks/{org_id}/{filename}"


def _delete_file(rel_path: str | None) -> None:
    if rel_path:
        p = UPLOAD_DIR / rel_path
        if p.exists():
            p.unlink(missing_ok=True)


@router.post("/{org_id}/{season_id}/upload/hero")
async def upload_hero(
    org_id: str,
    season_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    _delete_file(yb.get("hero_image_path"))
    rel_path = _save_upload(file, org_id, "hero")
    await db.execute(
        text("UPDATE yearbooks SET hero_image_path = :p, updated_at = NOW() WHERE id = :id"),
        {"p": rel_path, "id": str(yb["id"])},
    )
    await db.commit()
    return {"path": rel_path}


@router.delete("/{org_id}/{season_id}/upload/hero")
async def clear_hero(org_id: str, season_id: str, db: AsyncSession = Depends(get_db)):
    yb = await _ensure_stub(db, org_id, season_id)
    _delete_file(yb.get("hero_image_path"))
    await db.execute(
        text("UPDATE yearbooks SET hero_image_path = NULL, updated_at = NOW() WHERE id = :id"),
        {"id": str(yb["id"])},
    )
    await db.commit()
    return {"status": "cleared"}


@router.post("/{org_id}/{season_id}/upload/gallery")
async def upload_gallery(
    org_id: str,
    season_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    rel_path = _save_upload(file, org_id, "gallery")
    result = await db.execute(
        text("""
            INSERT INTO yearbook_images (yearbook_id, file_path, image_type, sort_order)
            VALUES (:yid, :path, 'gallery',
                COALESCE((SELECT MAX(sort_order) + 1 FROM yearbook_images WHERE yearbook_id = :yid), 0))
            RETURNING id
        """),
        {"yid": str(yb["id"]), "path": rel_path},
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "path": rel_path}


@router.delete("/{org_id}/{season_id}/images/{image_id}")
async def delete_gallery_image(
    org_id: str,
    season_id: str,
    image_id: int,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    row = await db.execute(
        text("SELECT file_path FROM yearbook_images WHERE id = :id AND yearbook_id = :yid"),
        {"id": image_id, "yid": str(yb["id"])},
    )
    img = row.mappings().first()
    if img:
        _delete_file(img["file_path"])
        await db.execute(
            text("DELETE FROM yearbook_images WHERE id = :id AND yearbook_id = :yid"),
            {"id": image_id, "yid": str(yb["id"])},
        )
        await db.commit()
    return {"status": "deleted"}


# ─── Admin: club awards ───────────────────────────────────────────────────────

class ClubAwardBody(BaseModel):
    award_name: str
    player_id: Optional[str] = None
    name_override: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 0


@router.post("/{org_id}/{season_id}/awards")
async def create_award(
    org_id: str,
    season_id: str,
    body: ClubAwardBody,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    result = await db.execute(
        text("""
            INSERT INTO yearbook_club_awards
                (yearbook_id, award_name, player_id, name_override, notes, sort_order)
            VALUES (:yid, :name, :pid, :nover, :notes, :order)
            RETURNING id
        """),
        {
            "yid": str(yb["id"]),
            "name": body.award_name,
            "pid": body.player_id,
            "nover": body.name_override,
            "notes": body.notes,
            "order": body.sort_order,
        },
    )
    new_id = result.scalar()
    await db.commit()
    return {"id": new_id, "status": "created"}


@router.delete("/{org_id}/{season_id}/awards/{award_id}")
async def delete_award(
    org_id: str,
    season_id: str,
    award_id: int,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("DELETE FROM yearbook_club_awards WHERE id = :id AND yearbook_id = :yid"),
        {"id": award_id, "yid": str(yb["id"])},
    )
    await db.commit()
    return {"status": "deleted"}


# ─── Admin: featured achievements (pinned to overview) ───────────────────────

class FeaturedAchievementBody(BaseModel):
    achievement_id: str
    sort_order: int = 0


@router.post("/{org_id}/{season_id}/featured-achievements")
async def add_featured_achievement(
    org_id: str,
    season_id: str,
    body: FeaturedAchievementBody,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("""
            INSERT INTO yearbook_featured_achievements (yearbook_id, achievement_id, sort_order)
            VALUES (:yid, :aid, :order)
            ON CONFLICT (yearbook_id, achievement_id) DO NOTHING
        """),
        {"yid": str(yb["id"]), "aid": body.achievement_id, "order": body.sort_order},
    )
    await db.commit()
    return {"status": "added"}


@router.delete("/{org_id}/{season_id}/featured-achievements/{achievement_id}")
async def remove_featured_achievement(
    org_id: str,
    season_id: str,
    achievement_id: str,
    db: AsyncSession = Depends(get_db),
):
    yb = await _ensure_stub(db, org_id, season_id)
    await db.execute(
        text("DELETE FROM yearbook_featured_achievements WHERE yearbook_id = :yid AND achievement_id = :aid"),
        {"yid": str(yb["id"]), "aid": achievement_id},
    )
    await db.commit()
    return {"status": "removed"}


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
- Aim for 450–500 words — enough to fill a full page of the yearbook"""


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
            COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('win','won')) AS wins,
            COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('loss','lost')) AS losses,
            COUNT(*) FILTER (WHERE LOWER(gm.result) IN ('draw','drew','tie')) AS draws
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

    client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=800,
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
