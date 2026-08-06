import asyncio
import datetime
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
import uuid

from app.models.db import get_db, Grade, Season, Organisation, ManualPartnershipRecord
from sqlalchemy import select as sa_select
from app.services import playhq_client
from app.services import grade_scope
from app.services.grade_labels import suggest_category

router = APIRouter(prefix="/records", tags=["records"])

_LIMIT = 25


@router.get("/{org_id}/grades")
async def get_records_grades(
    org_id: str,
    season_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Return grades for the org, optionally scoped to a season."""
    q = (
        select(Grade)
        .join(Season, Season.id == Grade.season_id)
        .where(Season.organisation_id == uuid.UUID(org_id))
    )
    if season_id:
        q = q.where(Grade.season_id == uuid.UUID(season_id))
    result = await db.execute(q.order_by(text("NULLIF(regexp_replace(grades.name, '[^0-9].*', ''), '')::int NULLS LAST"), Grade.name))
    grades = result.scalars().all()
    if grades:
        seen: set[str] = set()
        out = []
        for g in grades:
            if g.name not in seen:
                seen.add(g.name)
                out.append({
                    "id": str(g.id),
                    "name": g.name,
                    "season_id": str(g.season_id),
                    # Confirmed label, else the name-based guess — same resolution
                    # the admin grade list uses, so the two never disagree.
                    "category": g.category or suggest_category(g.name),
                })
        return out

    # DB has no grades — fall back to the Grassroots grades endpoint (one call per
    # season). Needs the raw CA season GUID (grassroots_id), not our per-club id.
    org = await db.get(Organisation, uuid.UUID(org_id))
    if not org:
        return []

    db_seasons_res = await db.execute(select(Season).where(Season.organisation_id == uuid.UUID(org_id)))
    db_seasons_list = [
        {"id": str(s.id), "name": s.name, "grassroots_id": s.grassroots_id}
        for s in db_seasons_res.scalars().all()
    ]

    api_grades: list[dict] = []
    gr_seasons = [s for s in db_seasons_list if s.get("grassroots_id")]
    grassroots_results = await asyncio.gather(
        *[playhq_client.get_grades(org_id, s["grassroots_id"]) for s in gr_seasons],
        return_exceptions=True,
    )
    seen_ids2: set[str] = set()
    for s, res in zip(gr_seasons, grassroots_results):
        if isinstance(res, list):
            for g in res:
                gid = g.get("id")
                if gid and gid not in seen_ids2:
                    seen_ids2.add(gid)
                    api_grades.append({**g, "_season_id": s["id"]})

    if not api_grades:
        return []

    seen: set[str] = set()
    out: list[dict] = []
    for g in api_grades:
        gid = g.get("id")
        gname = g.get("name", "")
        if not gid or not gname or gid in seen:
            continue
        # Determine season_id: from nested season object or from per-season fallback tag
        g_season_id = str((g.get("season") or {}).get("id", "") or g.get("_season_id", ""))
        if season_id and g_season_id != season_id:
            continue
        seen.add(gid)
        out.append({"id": gid, "name": gname, "season_id": g_season_id})
    return sorted(out, key=lambda x: x["name"])


@router.get("/{org_id}")
async def get_records(
    org_id: str,
    season_id: str | None = Query(None),
    grade_id: str | None = Query(None),
    grade_name: str | None = Query(None),
    finals_only: bool = Query(False),
    captain_only: bool = Query(False),
    gender: str | None = Query(None),
    categories: str | None = Query(
        None,
        description=(
            "Comma-separated grade categories to count — senior, junior, womens, "
            "masters, mixed, or 'all'. Omitted uses the club's own default, which "
            "leaves junior out. Ignored when an explicit grade is picked."
        ),
    ),
    db: AsyncSession = Depends(get_db),
):
    # An explicitly picked grade beats the category default: someone who chose
    # "Under 14s" wants the juniors. Resolved to nothing in that case, so every
    # clause below sees an inactive scope and emits no SQL.
    scope = await grade_scope.resolve_scope(db, org_id, categories)
    if grade_id or grade_name:
        scope = None
    scope_active = bool(scope is not None and scope.active)
    scope_clause = scope.clause("g.grade_id") if scope_active else ""

    # If grade_id supplied, resolve grade name (for manual record filtering) and season if missing
    manual_grade_name: str | None = None
    if grade_id:
        grade = await db.get(Grade, uuid.UUID(grade_id))
        if grade:
            manual_grade_name = grade.name
            if not season_id:
                season_id = str(grade.season_id)

    # Resolve season year for filtering manual records (season_year is an int, not a UUID)
    manual_season_year: int | None = None
    if season_id:
        season_obj = await db.get(Season, uuid.UUID(season_id))
        if season_obj:
            if season_obj.year is not None:
                manual_season_year = season_obj.year
            else:
                m = re.search(r'(\d{4})', season_obj.name or '')
                if m:
                    manual_season_year = int(m.group(1))

    # Expand canonical season to include any merged-in alias seasons.
    from app.services.season_aliases import resolve_season_filter
    season_ids = await resolve_season_filter(db, org_id, season_id)

    p = {"org_id": org_id, "limit": _LIMIT}
    if season_ids:
        p["season_ids"] = season_ids
    if grade_id:
        p["grade_id"] = grade_id
    if grade_name:
        p["grade_name"] = grade_name
    if gender:
        p["gender"] = gender
    if scope_active:
        scope.bind(p)

    # Clauses for game-level queries (partnerships) that already JOIN games g
    game_season_clause = " JOIN grades gr ON gr.id = g.grade_id AND gr.season_id = ANY(:season_ids)" if season_ids else ""

    # Partnership queries now always JOIN grades gr for grade_name; season filter via WHERE
    partnership_season_clause = " AND gr.season_id = ANY(:season_ids)" if season_ids else ""

    # Merge-aware grade match: also include grades that were merged (aliased) into the selected grade.
    _grade_match = (
        "(COALESCE(gr.display_name_override, gr.name) = :grade_name"
        " OR EXISTS (SELECT 1 FROM grade_merge_logs gml"
        " WHERE gml.org_id = CAST(:org_id AS UUID)"
        " AND gml.alias_name = gr.name AND gml.undone_at IS NULL"
        " AND (gml.canonical_name = :grade_name"
        " OR EXISTS (SELECT 1 FROM grades gr2 JOIN seasons s2 ON s2.id = gr2.season_id"
        " WHERE gr2.name = gml.canonical_name AND s2.organisation_id = CAST(:org_id AS UUID)"
        " AND gr2.display_name_override = :grade_name))))"
    )

    # Grade filter clause — prefer grade_name (cross-season) over grade_id (season-specific)
    if grade_name:
        game_grade_clause  = f" AND {_grade_match}"
        pairs_grade_clause = f" AND {_grade_match}"
        pairs_game_join = (
            " JOIN v_effective_games g ON g.id = pt.game_id JOIN grades gr ON gr.id = g.grade_id AND gr.season_id = ANY(:season_ids)"
            if season_ids else
            " JOIN v_effective_games g ON g.id = pt.game_id JOIN grades gr ON gr.id = g.grade_id"
        )
    else:
        game_grade_clause  = " AND g.grade_id = :grade_id" if grade_id else scope_clause
        pairs_grade_clause = " AND g.grade_id = :grade_id" if grade_id else scope_clause
        pairs_game_join = (
            " JOIN v_effective_games g ON g.id = pt.game_id JOIN grades gr ON gr.id = g.grade_id AND gr.season_id = ANY(:season_ids)"
            if season_ids else
            # scope_active belongs here too: pairs_grade_clause below references
            # g.grade_id, so without the join the query would name a missing alias.
            (" JOIN v_effective_games g ON g.id = pt.game_id JOIN grades gr ON gr.id = g.grade_id"
             if (grade_id or finals_only or scope_active) else "")
        )

    # Inline WHERE additions for player_season_stats aggregate queries
    pss_season_clause  = "AND pss.season_id = ANY(:season_ids) " if season_ids else ""
    pss_gender_clause  = "AND p.gender = :gender " if gender else ""
    gender_clause      = f" AND p.gender = :gender" if gender else ""

    # When grade_name active: game-level join/where templates for batting and bowling
    _gw_season = "AND s.id = ANY(:season_ids)" if season_ids else ""
    finals_clause = "AND g.is_final = TRUE" if finals_only else ""
    captain_bat_join = (
        " JOIN game_appearances gap ON gap.game_id = bi.game_id AND gap.player_id = bi.player_id AND gap.is_captain = TRUE"
        if captain_only else ""
    )
    captain_bowl_join = (
        " JOIN game_appearances gap ON gap.game_id = bs.game_id AND gap.player_id = bs.player_id AND gap.is_captain = TRUE"
        if captain_only else ""
    )
    _bat_join = (
        "JOIN v_effective_batting_innings bi ON bi.player_id = p.id"
        " JOIN v_effective_games g ON g.id = bi.game_id"
        " JOIN grades gr ON gr.id = g.grade_id"
        " JOIN seasons s ON s.id = gr.season_id"
    ) + captain_bat_join
    _bat_where = (
        f"WHERE p.organisation_id = :org_id AND {_grade_match}"
        f" {_gw_season}"
        f" {finals_clause}"
        f"{gender_clause}"
        " AND NOT COALESCE(bi.did_not_bat, FALSE)"
        " AND LOWER(COALESCE(bi.dismissal_type,'')) NOT IN ('absent','did not bat','dnb')"
    )
    _bowl_join = (
        "JOIN v_effective_bowling_spells bs ON bs.player_id = p.id"
        " JOIN v_effective_games g ON g.id = bs.game_id"
        " JOIN grades gr ON gr.id = g.grade_id"
        " JOIN seasons s ON s.id = gr.season_id"
    ) + captain_bowl_join
    _bowl_where = (
        f"WHERE p.organisation_id = :org_id AND {_grade_match}"
        f" {_gw_season}"
        f" {finals_clause}"
        f"{gender_clause}"
    )

    async def q(sql: str, params: dict | None = None) -> list[dict]:
        rows = await db.execute(text(sql), params or p)
        return [dict(r) for r in rows.mappings().all()]

    # Whether to use per-game queries (required for grade_name or finals_only)
    # A category exclusion forces the per-game path for the same reason a
    # finals or captain filter does: CA's season aggregates carry no grade, so
    # they cannot answer "not the juniors". Like those two, this means a club's
    # aggregate-only BetterImport residuals sit out a filtered board — they have
    # no per-innings rows for a best-innings or best-figures record anyway.
    use_game_level = bool(grade_name or finals_only or captain_only or scope_active)
    # Grade filter fragment for use-game-level queries that don't use _grade_match
    _match_grade_filter = f"AND {_grade_match}" if grade_name else scope_clause

    # For the no-grade-name path (with or without finals_only/captain_only): same joins as
    # grade_name but without the grade filter. Also used (unconditionally, regardless of
    # use_game_level) by the per-innings high-score/best-figures queries below, so this must
    # stay correct for the plain "no filters at all" case too.
    if not grade_name:
        _bat_join_ng = (
            "JOIN v_effective_batting_innings bi ON bi.player_id = p.id"
            " JOIN v_effective_games g ON g.id = bi.game_id"
            " JOIN grades gr ON gr.id = g.grade_id"
            " JOIN seasons s ON s.id = gr.season_id"
        ) + captain_bat_join
        _bat_where_ng = (
            f"WHERE p.organisation_id = :org_id"
            f" {_gw_season}"
            + scope_clause
            + (" AND g.is_final = TRUE" if finals_only else "")
            + (f" AND p.gender = :gender" if gender else "")
            + " AND NOT COALESCE(bi.did_not_bat, FALSE)"
            + " AND LOWER(COALESCE(bi.dismissal_type,'')) NOT IN ('absent','did not bat','dnb')"
        )
        _bowl_join_ng = (
            "JOIN v_effective_bowling_spells bs ON bs.player_id = p.id"
            " JOIN v_effective_games g ON g.id = bs.game_id"
            " JOIN grades gr ON gr.id = g.grade_id"
            " JOIN seasons s ON s.id = gr.season_id"
        ) + captain_bowl_join
        _bowl_where_ng = (
            f"WHERE p.organisation_id = :org_id"
            f" {_gw_season}"
            + scope_clause
            + (" AND g.is_final = TRUE" if finals_only else "")
            + (f" AND p.gender = :gender" if gender else "")
        )
    else:
        _bat_join_ng = _bat_join
        _bat_where_ng = _bat_where
        _bowl_join_ng = _bowl_join
        _bowl_where_ng = _bowl_where

    # For queries that need the right join/where based on context
    _eff_bat_join = _bat_join if grade_name else _bat_join_ng
    _eff_bat_where = _bat_where if grade_name else _bat_where_ng
    _eff_bowl_join = _bowl_join if grade_name else _bowl_join_ng
    _eff_bowl_where = _bowl_where if grade_name else _bowl_where_ng

    # ── Batting ────────────────────────────────────────────────────────────────────────

    if use_game_level:
        top_career_runs = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   COUNT(*) AS innings,
                   COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
                   COUNT(DISTINCT bi.game_id) AS matches,
                   MAX(bi.runs) AS high_score,
                   ROUND(SUM(bi.runs)::numeric /
                       NULLIF(COUNT(*) - COUNT(*) FILTER (WHERE bi.not_out), 0), 2) AS average
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(bi.runs) > 0
            ORDER BY runs DESC LIMIT :limit
        """)
    else:
        top_career_runs = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.runs), 0)            AS runs,
                   COALESCE(SUM(pss.batting_innings), 0) AS innings,
                   COALESCE(SUM(pss.not_outs), 0)        AS not_outs,
                   COALESCE(SUM(pss.matches), 0)         AS matches,
                   MAX(pss.high_score)                   AS high_score,
                   ROUND(SUM(pss.runs)::numeric /
                       NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.runs) > 0
            ORDER BY runs DESC LIMIT :limit
        """)

    # Every qualifying innings competes for a leaderboard slot, not just each player's single
    # best — a player can legitimately hold more than one of the top spots.
    top_high_scores = await q(f"""
        SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
               bi.runs, bi.not_out, s.name AS season_name
        FROM players p {_eff_bat_join}
        {_eff_bat_where}
          AND bi.runs IS NOT NULL AND bi.runs > 0
        ORDER BY bi.runs DESC LIMIT :limit
    """)

    if use_game_level:
        top_batting_avg = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(bi.runs)::numeric /
                       NULLIF(COUNT(*) - COUNT(*) FILTER (WHERE bi.not_out), 0), 2) AS average,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   COUNT(*) AS innings,
                   COUNT(DISTINCT bi.game_id) AS matches
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING (COUNT(*) - COUNT(*) FILTER (WHERE bi.not_out)) >= 10
            ORDER BY average DESC LIMIT :limit
        """)
    else:
        top_batting_avg = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(pss.runs)::numeric /
                       NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS average,
                   COALESCE(SUM(pss.runs), 0)            AS runs,
                   COALESCE(SUM(pss.batting_innings), 0) AS innings,
                   COALESCE(SUM(pss.matches), 0)         AS matches
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING (SUM(pss.batting_innings) - SUM(pss.not_outs)) >= 10
            ORDER BY average DESC LIMIT :limit
        """)

    if use_game_level:
        most_fifties = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) AS fifties,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   COUNT(DISTINCT bi.game_id) AS matches
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(*) FILTER (WHERE bi.runs >= 50 AND bi.runs < 100) > 0
            ORDER BY fifties DESC LIMIT :limit
        """)
    else:
        most_fifties = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.fifties), 0)  AS fifties,
                   COALESCE(SUM(pss.runs), 0)     AS runs,
                   COALESCE(SUM(pss.matches), 0)  AS matches
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.fifties) > 0
            ORDER BY fifties DESC LIMIT :limit
        """)

    if use_game_level:
        most_hundreds = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) FILTER (WHERE bi.runs >= 100) AS hundreds,
                   COALESCE(SUM(bi.runs), 0) AS runs,
                   COUNT(DISTINCT bi.game_id) AS matches
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(*) FILTER (WHERE bi.runs >= 100) > 0
            ORDER BY hundreds DESC LIMIT :limit
        """)
    else:
        most_hundreds = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.hundreds), 0) AS hundreds,
                   COALESCE(SUM(pss.runs), 0)     AS runs,
                   COALESCE(SUM(pss.matches), 0)  AS matches
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.hundreds) > 0
            ORDER BY hundreds DESC LIMIT :limit
        """)

    if use_game_level:
        most_ducks = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT COALESCE(bi.not_out, FALSE)) AS ducks,
                   COUNT(*) AS innings
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(*) FILTER (WHERE bi.runs = 0 AND NOT COALESCE(bi.not_out, FALSE)) > 0
            ORDER BY ducks DESC LIMIT :limit
        """)
    else:
        most_ducks = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.ducks), 0)          AS ducks,
                   COALESCE(SUM(pss.batting_innings), 0) AS innings
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.ducks) > 0
            ORDER BY ducks DESC LIMIT :limit
        """)

    if use_game_level:
        most_runs_season = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(bi.runs) AS runs,
                   COUNT(*) AS innings,
                   s.name AS season_name, s.year AS season_year
            FROM players p {_eff_bat_join}
            {_eff_bat_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), s.id, s.name, s.year
            HAVING SUM(bi.runs) > 0
            ORDER BY runs DESC LIMIT :limit
        """)
    else:
        most_runs_season = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   pss.runs, pss.batting_innings AS innings,
                   s.name AS season_name, s.year AS season_year
            FROM v_effective_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            JOIN seasons s ON s.id = pss.season_id
            WHERE p.organisation_id = :org_id AND pss.runs > 0
              """ + ("AND pss.season_id = ANY(:season_ids) " if season_ids else "") + pss_gender_clause + """
            ORDER BY pss.runs DESC LIMIT :limit
        """)

    # ── Bowling ────────────────────────────────────────────────────────────────────────

    if use_game_level:
        top_career_wickets = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(bs.wickets), 0) AS wickets,
                   COUNT(DISTINCT bs.game_id) AS matches,
                   COUNT(*) FILTER (WHERE bs.wickets >= 5) AS five_fors,
                   ROUND(SUM(bs.runs)::numeric /
                       NULLIF(SUM(bs.wickets), 0), 2) AS average,
                   ROUND(SUM(bs.runs)::numeric /
                       NULLIF(SUM(bs.overs), 0), 2) AS economy
            FROM players p {_eff_bowl_join}
            {_eff_bowl_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(bs.wickets) > 0
            ORDER BY wickets DESC LIMIT :limit
        """)
    else:
        top_career_wickets = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.wickets), 0)      AS wickets,
                   COALESCE(SUM(pss.matches), 0)      AS matches,
                   COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                   ROUND(SUM(pss.runs_conceded)::numeric /
                       NULLIF(SUM(pss.wickets), 0), 2) AS average,
                   ROUND(SUM(pss.runs_conceded)::numeric /
                       NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.wickets) > 0
            ORDER BY wickets DESC LIMIT :limit
        """)

    # Every qualifying spell competes for a leaderboard slot, not just each player's single
    # best — a player can legitimately hold more than one of the top spots.
    best_innings_figures = await q(f"""
        SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
               bs.wickets, bs.runs, s.name AS season_name
        FROM players p {_eff_bowl_join}
        {_eff_bowl_where}
          AND bs.wickets > 0
        ORDER BY bs.wickets DESC, bs.runs ASC LIMIT :limit
    """)

    if use_game_level:
        top_bowling_avg = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(bs.runs)::numeric /
                       NULLIF(SUM(bs.wickets), 0), 2) AS average,
                   COALESCE(SUM(bs.wickets), 0) AS wickets,
                   COUNT(DISTINCT bs.game_id) AS matches
            FROM players p {_eff_bowl_join}
            {_eff_bowl_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(bs.wickets) >= 20
            ORDER BY average ASC LIMIT :limit
        """)
    else:
        top_bowling_avg = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(pss.runs_conceded)::numeric /
                       NULLIF(SUM(pss.wickets), 0), 2) AS average,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.matches), 0) AS matches
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.wickets) >= 20
            ORDER BY average ASC LIMIT :limit
        """)

    if use_game_level:
        top_economy = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(bs.runs)::numeric /
                       NULLIF(SUM(bs.overs), 0), 2) AS economy,
                   COALESCE(SUM(bs.wickets), 0) AS wickets,
                   ROUND(SUM(bs.overs), 1) AS overs
            FROM players p {_eff_bowl_join}
            {_eff_bowl_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(bs.overs) >= 50
            ORDER BY economy ASC LIMIT :limit
        """)
    else:
        top_economy = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   ROUND(SUM(pss.runs_conceded)::numeric /
                       NULLIF(SUM(pss.bowling_balls), 0) * 6, 2) AS economy,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.overs), 0)   AS overs
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.bowling_balls) >= 300
            ORDER BY economy ASC LIMIT :limit
        """)

    if use_game_level:
        most_five_fors = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(*) FILTER (WHERE bs.wickets >= 5) AS five_fors,
                   COALESCE(SUM(bs.wickets), 0) AS wickets
            FROM players p {_eff_bowl_join}
            {_eff_bowl_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(*) FILTER (WHERE bs.wickets >= 5) > 0
            ORDER BY five_fors DESC LIMIT :limit
        """)
    else:
        most_five_fors = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors,
                   COALESCE(SUM(pss.wickets), 0)             AS wickets
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.five_wicket_innings) > 0
            ORDER BY five_fors DESC LIMIT :limit
        """)

    if use_game_level:
        most_wickets_season = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   SUM(bs.wickets)::int AS wickets,
                   COUNT(DISTINCT bs.game_id) AS innings,
                   s.name AS season_name, s.year AS season_year
            FROM players p {_eff_bowl_join}
            {_eff_bowl_where}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name), s.id, s.name, s.year
            HAVING SUM(bs.wickets) > 0
            ORDER BY wickets DESC LIMIT :limit
        """)
    else:
        most_wickets_season = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   pss.wickets, pss.bowling_innings AS innings,
                   s.name AS season_name, s.year AS season_year
            FROM v_effective_player_season_stats pss
            JOIN players p ON p.id = pss.player_id
            JOIN seasons s ON s.id = pss.season_id
            WHERE p.organisation_id = :org_id AND pss.wickets > 0
              """ + ("AND pss.season_id = ANY(:season_ids) " if season_ids else "") + pss_gender_clause + """
            ORDER BY pss.wickets DESC LIMIT :limit
        """)

    # ── Partnerships ──────────────────────────────────────────────────────────────────────

    top_partnerships = await q(f"""
        SELECT
            p1.id::text AS batter1_id,
            COALESCE(p1.display_name_override, p1.name) AS batter1_name,
            p2.id::text AS batter2_id,
            COALESCE(p2.display_name_override, p2.name) AS batter2_name,
            pt.runs, pt.wicket_number,
            g.played_at::text,
            COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
            s.name AS season_name,
            EXTRACT(YEAR FROM g.played_at)::int AS season_year,
            false AS is_manual
        FROM v_effective_partnerships pt
        JOIN v_effective_games g ON g.id = pt.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
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
        LEFT JOIN players p1 ON p1.id = pt.batter1_id
        LEFT JOIN players p2 ON p2.id = pt.batter2_id
        WHERE pt.is_club_innings IS NOT FALSE
          AND p1.organisation_id = :org_id AND p2.organisation_id = :org_id
          {partnership_season_clause} {game_grade_clause} {finals_clause}
          AND pt.runs IS NOT NULL AND pt.runs > 0
        ORDER BY pt.runs DESC LIMIT :limit
    """)

    partnerships_by_wicket_rows = await q(f"""
        SELECT
            p1.id::text AS batter1_id,
            COALESCE(p1.display_name_override, p1.name) AS batter1_name,
            p2.id::text AS batter2_id,
            COALESCE(p2.display_name_override, p2.name) AS batter2_name,
            pt.runs, pt.wicket_number,
            g.played_at::text,
            COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
            s.name AS season_name,
            EXTRACT(YEAR FROM g.played_at)::int AS season_year,
            false AS is_manual,
            ROW_NUMBER() OVER (PARTITION BY pt.wicket_number ORDER BY pt.runs DESC) AS rn
        FROM v_effective_partnerships pt
        JOIN v_effective_games g ON g.id = pt.game_id
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
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
        LEFT JOIN players p1 ON p1.id = pt.batter1_id
        LEFT JOIN players p2 ON p2.id = pt.batter2_id
        WHERE pt.is_club_innings IS NOT FALSE
          AND p1.organisation_id = :org_id AND p2.organisation_id = :org_id
          {partnership_season_clause} {game_grade_clause} {finals_clause}
          AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10
    """)
    by_wicket: dict[int, list] = {}
    for row in partnerships_by_wicket_rows:
        if row["rn"] <= 10:
            wk = int(row["wicket_number"])
            by_wicket.setdefault(wk, [])
            d = dict(row)
            del d["rn"]
            by_wicket[wk].append(d)

    partnerships_by_grade_rows = await q(f"""
        WITH ranked AS (
            SELECT
                COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)) AS grade_name,
                s.name AS season_name,
                pt.wicket_number,
                p1.id::text AS batter1_id,
                COALESCE(p1.display_name_override, p1.name) AS batter1_name,
                p2.id::text AS batter2_id,
                COALESCE(p2.display_name_override, p2.name) AS batter2_name,
                pt.runs,
                g.played_at::text,
                EXTRACT(YEAR FROM g.played_at)::int AS season_year,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(gdn.display_name_override, COALESCE(am.canonical_name, gr.name)), pt.wicket_number
                    ORDER BY pt.runs DESC
                ) AS rn
            FROM v_effective_partnerships pt
            JOIN v_effective_games g ON g.id = pt.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
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
            LEFT JOIN players p1 ON p1.id = pt.batter1_id
            LEFT JOIN players p2 ON p2.id = pt.batter2_id
            WHERE pt.is_club_innings IS NOT FALSE
              AND p1.organisation_id = :org_id AND p2.organisation_id = :org_id
              {partnership_season_clause} {game_grade_clause} {finals_clause}
              AND pt.runs IS NOT NULL AND pt.runs > 0 AND pt.wicket_number BETWEEN 1 AND 10
        )
        SELECT * FROM ranked WHERE rn = 1
        ORDER BY grade_name, wicket_number
    """)
    by_grade_wicket: dict[str, list] = {}
    for row in partnerships_by_grade_rows:
        grade = row["grade_name"] or "Unknown"
        if grade not in by_grade_wicket:
            by_grade_wicket[grade] = []
        d = dict(row)
        del d["rn"]
        by_grade_wicket[grade].append(d)

    # Manual partnership records — filtered by season year and/or grade name when active
    org_obj = await db.get(Organisation, uuid.UUID(org_id))
    manual_rows = []
    if org_obj:
        manual_stmt = (
            sa_select(ManualPartnershipRecord)
            .where(ManualPartnershipRecord.org_id == org_obj.id)
        )
        if manual_season_year is not None:
            manual_stmt = manual_stmt.where(ManualPartnershipRecord.season_year == manual_season_year)
        if manual_grade_name:
            manual_stmt = manual_stmt.where(ManualPartnershipRecord.grade_name == manual_grade_name)
        manual_stmt = manual_stmt.order_by(ManualPartnershipRecord.runs.desc())
        manual_res = await db.execute(manual_stmt)
        for r in manual_res.scalars().all():
            manual_rows.append({
                "batter1_id": str(r.batter1_id) if r.batter1_id else None,
                "batter1_name": r.batter1_name,
                "batter2_id": str(r.batter2_id) if r.batter2_id else None,
                "batter2_name": r.batter2_name,
                "runs": r.runs,
                "wicket_number": r.wicket_number,
                "played_at": None,
                "grade_name": r.grade_name,
                "season_year": r.season_year,
                "is_not_out": r.is_not_out,
                "is_manual": True,
            })

    top_pairs = await q(f"""
        SELECT
            LEAST(p1.id::text, p2.id::text)    AS pair_key,
            p1.id::text AS batter1_id,
            COALESCE(p1.display_name_override, p1.name) AS batter1_name,
            p2.id::text AS batter2_id,
            COALESCE(p2.display_name_override, p2.name) AS batter2_name,
            COUNT(*)                            AS count,
            COALESCE(SUM(pt.runs), 0)           AS total_runs,
            MAX(pt.runs)                        AS best
        FROM v_effective_partnerships pt
        JOIN players p1 ON p1.id = pt.batter1_id
        JOIN players p2 ON p2.id = pt.batter2_id
        {pairs_game_join}
        WHERE pt.is_club_innings IS NOT FALSE
          AND p1.organisation_id = :org_id AND p2.organisation_id = :org_id
          {pairs_grade_clause} {finals_clause}
        GROUP BY LEAST(p1.id::text, p2.id::text),
                 p1.id, COALESCE(p1.display_name_override, p1.name),
                 p2.id, COALESCE(p2.display_name_override, p2.name)
        HAVING COALESCE(SUM(pt.runs), 0) > 0
        ORDER BY total_runs DESC LIMIT :limit
    """)

    # ── Team / fielding ───────────────────────────────────────────────────────────────────────

    # When the user is filtering by grade and not by finals-only, prefer the
    # per-grade aggregate (player_season_grade_stats) — that's CA's source of
    # truth and includes games where we have no scorecard yet. Falls back to
    # the per-game UNION when filtering on finals only (since the aggregate
    # doesn't track finals separately) or when no grade filter is set.
    use_psgs_path = bool(grade_name) and not finals_only and not captain_only

    if captain_only:
        most_matches = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT ga.game_id) AS matches,
                   COUNT(DISTINCT gr.season_id) AS seasons
            FROM game_appearances ga
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN players p ON p.id = ga.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND ga.is_captain = TRUE
              AND p.organisation_id = :org_id
              {_gw_season}
              {_match_grade_filter}
              {finals_clause}
              {gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT ga.game_id) > 0
            ORDER BY matches DESC LIMIT :limit
        """)
    elif use_psgs_path:
        psgs_season_clause = "AND psgs.season_id = ANY(:season_ids)" if season_ids else ""
        most_matches = await q(f"""
            SELECT p.id::text AS player_id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(psgs.matches), 0) AS matches,
                   COUNT(DISTINCT psgs.season_id) AS seasons
            FROM players p
            JOIN player_season_grade_stats psgs ON psgs.player_id = p.id
            JOIN grades gr ON gr.id = psgs.grade_id
            WHERE p.organisation_id = :org_id
              AND {_grade_match}
              {psgs_season_clause}{gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(psgs.matches) > 0
            ORDER BY matches DESC LIMIT :limit
        """)
    elif use_game_level:
        most_matches = await q(f"""
            WITH appearances AS (
                SELECT bi.player_id, bi.game_id, gr.season_id
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                UNION
                SELECT bs.player_id, bs.game_id, gr.season_id
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                UNION
                SELECT fs.player_id, fs.game_id, gr.season_id
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
            )
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT ap.game_id) AS matches,
                   COUNT(DISTINCT ap.season_id) AS seasons
            FROM players p
            JOIN appearances ap ON ap.player_id = p.id
            WHERE p.organisation_id = :org_id{gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT ap.game_id) > 0
            ORDER BY matches DESC LIMIT :limit
        """)
    else:
        most_matches = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.matches), 0)          AS matches,
                   COUNT(DISTINCT pss.season_id)           AS seasons
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.matches) > 0
            ORDER BY matches DESC LIMIT :limit
        """)

    if captain_only:
        most_seasons = await q(f"""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT gr.season_id) AS seasons,
                   COUNT(DISTINCT ga.game_id) AS matches
            FROM game_appearances ga
            JOIN v_effective_games g ON g.id = ga.game_id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            JOIN players p ON p.id = ga.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND ga.is_captain = TRUE
              AND p.organisation_id = :org_id
              {_gw_season}
              {_match_grade_filter}
              {finals_clause}
              {gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT gr.season_id) > 0
            ORDER BY seasons DESC LIMIT :limit
        """)
    elif use_psgs_path:
        psgs_season_clause = "AND psgs.season_id = ANY(:season_ids)" if season_ids else ""
        most_seasons = await q(f"""
            SELECT p.id::text AS player_id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT psgs.season_id) AS seasons,
                   COALESCE(SUM(psgs.matches), 0) AS matches
            FROM players p
            JOIN player_season_grade_stats psgs ON psgs.player_id = p.id
            JOIN grades gr ON gr.id = psgs.grade_id
            WHERE p.organisation_id = :org_id
              AND {_grade_match}
              {psgs_season_clause}{gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT psgs.season_id) > 0
            ORDER BY seasons DESC LIMIT :limit
        """)
    elif use_game_level:
        most_seasons = await q(f"""
            WITH appearances AS (
                SELECT bi.player_id, gr.season_id
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                UNION
                SELECT bs.player_id, gr.season_id
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                UNION
                SELECT fs.player_id, gr.season_id
                FROM v_effective_fielding_stats fs
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
            )
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT ap.season_id) AS seasons,
                   COUNT(DISTINCT ap.season_id) AS matches
            FROM players p
            JOIN appearances ap ON ap.player_id = p.id
            WHERE p.organisation_id = :org_id{gender_clause}
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT ap.season_id) > 0
            ORDER BY seasons DESC LIMIT :limit
        """)
    else:
        most_seasons = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COUNT(DISTINCT pss.season_id)           AS seasons,
                   COALESCE(SUM(pss.matches), 0)          AS matches
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING COUNT(DISTINCT pss.season_id) > 0
            ORDER BY seasons DESC LIMIT :limit
        """)

    if use_game_level:
        top_allrounders = await q(f"""
            WITH bat AS (
                SELECT bi.player_id,
                       COALESCE(SUM(bi.runs), 0) AS runs,
                       COUNT(*) AS innings,
                       COUNT(*) FILTER (WHERE bi.not_out) AS not_outs,
                       COUNT(DISTINCT bi.game_id) AS games
                FROM v_effective_batting_innings bi
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type,'')) NOT IN ('absent','did not bat','dnb')
                GROUP BY bi.player_id
            ),
            bowl AS (
                SELECT bs.player_id,
                       COALESCE(SUM(bs.wickets), 0) AS wickets,
                       COALESCE(SUM(bs.runs), 0) AS runs_conceded,
                       COUNT(DISTINCT bs.game_id) AS games
                FROM v_effective_bowling_spells bs
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                JOIN seasons s ON s.id = gr.season_id
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  {_match_grade_filter}
                  {_gw_season}
                  {finals_clause}
                GROUP BY bs.player_id
            )
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(bat.runs, 0) AS runs,
                   COALESCE(bowl.wickets, 0) AS wickets,
                   GREATEST(COALESCE(bat.games, 0), COALESCE(bowl.games, 0)) AS matches,
                   ROUND(bat.runs::numeric / NULLIF(bat.innings - bat.not_outs, 0), 2) AS batting_average,
                   ROUND(bowl.runs_conceded::numeric / NULLIF(bowl.wickets, 0), 2) AS bowling_average,
                   ROUND(COALESCE(bat.runs, 0) * 1.5 + COALESCE(bowl.wickets, 0) * 10, 2) AS index_score
            FROM players p
            JOIN bat ON bat.player_id = p.id
            JOIN bowl ON bowl.player_id = p.id
            WHERE p.organisation_id = :org_id{gender_clause}
              AND bat.runs >= 1000 AND bowl.wickets >= 100
            ORDER BY index_score DESC LIMIT :limit
        """)
    else:
        top_allrounders = await q("""
            SELECT p.id::text AS player_id, COALESCE(p.display_name_override, p.name) AS name,
                   COALESCE(SUM(pss.runs), 0)    AS runs,
                   COALESCE(SUM(pss.wickets), 0) AS wickets,
                   COALESCE(SUM(pss.matches), 0) AS matches,
                   ROUND(SUM(pss.runs)::numeric /
                       NULLIF(SUM(pss.batting_innings) - SUM(pss.not_outs), 0), 2) AS batting_average,
                   ROUND(SUM(pss.runs_conceded)::numeric /
                       NULLIF(SUM(pss.wickets), 0), 2) AS bowling_average,
                   ROUND(COALESCE(SUM(pss.runs), 0) * 1.5 + COALESCE(SUM(pss.wickets), 0) * 10, 2) AS index_score
            FROM players p
            JOIN v_effective_player_season_stats pss ON pss.player_id = p.id
            WHERE p.organisation_id = :org_id
              """ + pss_season_clause + pss_gender_clause + """
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            HAVING SUM(pss.runs) >= 1000 AND SUM(pss.wickets) >= 100
            ORDER BY index_score DESC LIMIT :limit
        """)

    # Collapse rows that describe the same physical stand. A stand can be present
    # both as a synced `partnerships` row AND as a hand-entered
    # `manual_partnership_record` (the manual import predates game-level sync
    # reaching that season), so the records page would list it twice. The two
    # sources format the SAME stand differently, so the key must be
    # representation-agnostic:
    #   * season  — synced rows carry "Summer 2016/17"; manual rows carry the bare
    #               start year "2016". Key on the 4-digit start year so they match.
    #   * players — synced names are "Last, First"; manual names are "First Last".
    #               Key on each name's lowercased, sorted token set so order/format
    #               can't matter, and make the pair unordered.
    # Two entries equal on (unordered pair, runs, wicket, grade, season-year) are
    # visually indistinguishable on this page (there's no date/opponent column),
    # so we keep the first (synced rows are added before manual ones).
    def _season_year_key(s: str | None) -> str:
        m = re.search(r"\d{4}", s or "")
        return m.group(0) if m else (s or "").strip().lower()

    def _name_key(name: str | None) -> tuple:
        return tuple(sorted(t for t in re.split(r"[\s,]+", (name or "").strip().lower()) if t))

    def dedup_partnerships(rows: list[dict]) -> list[dict]:
        seen: set = set()
        out: list[dict] = []
        for r in rows:
            key = (
                frozenset((_name_key(r.get("player1_name")), _name_key(r.get("player2_name")))),
                r.get("runs"),
                r.get("wicket_number"),
                (r.get("grade_name") or "").strip().lower(),
                _season_year_key(r.get("season_name")),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    # Flatten by_wicket into wicket_1 ... wicket_10 and normalise field names
    def normalise_partnership(r: dict) -> dict:
        return {
            "player1_id":    r.get("batter1_id"),
            "player1_name":  r.get("batter1_name"),
            "player2_id":    r.get("batter2_id"),
            "player2_name":  r.get("batter2_name"),
            "runs":          r.get("runs"),
            "wicket_number": r.get("wicket_number"),
            "grade_name":    r.get("grade_name"),
            "season_name":   r.get("season_name") or (str(r["season_year"]) if r.get("season_year") else None),
            "is_manual":     r.get("is_manual", False),
        }

    partnerships_flat = {
        "top_partnerships": [normalise_partnership(r) for r in top_partnerships],
        **{f"wicket_{wk}": [normalise_partnership(r) for r in rows] for wk, rows in by_wicket.items()},
        "by_grade": {
            grade: [normalise_partnership(r) for r in rows]
            for grade, rows in by_grade_wicket.items()
        },
    }
    # Add manual records merged into top_partnerships, per-wicket buckets, and by_grade
    for mr in manual_rows:
        nr = {
            "player1_id":    mr.get("batter1_id"),
            "player1_name":  mr.get("batter1_name"),
            "player2_id":    mr.get("batter2_id"),
            "player2_name":  mr.get("batter2_name"),
            "runs":          mr.get("runs"),
            "wicket_number": mr.get("wicket_number"),
            "grade_name":    mr.get("grade_name"),
            "season_name":   str(mr["season_year"]) if mr.get("season_year") else None,
            "is_manual":     True,
        }
        partnerships_flat["top_partnerships"].append(nr)
        wk = mr.get("wicket_number")
        if wk:
            key = f"wicket_{wk}"
            partnerships_flat.setdefault(key, []).append(nr)
        grade = mr.get("grade_name") or "Unknown"
        partnerships_flat["by_grade"].setdefault(grade, []).append(nr)
    # Re-sort top_partnerships by runs desc, de-dup identical stands, cap at 25
    partnerships_flat["top_partnerships"].sort(key=lambda r: (r.get("runs") or 0), reverse=True)
    partnerships_flat["top_partnerships"] = dedup_partnerships(partnerships_flat["top_partnerships"])[:25]
    # Re-sort per-wicket buckets by runs desc, de-dup, cap at 10
    for wk in range(1, 11):
        key = f"wicket_{wk}"
        if key in partnerships_flat:
            partnerships_flat[key].sort(key=lambda r: (r.get("runs") or 0), reverse=True)
            partnerships_flat[key] = dedup_partnerships(partnerships_flat[key])[:10]
    # For each grade, keep only the best partnership per wicket (manual may beat game records)
    for grade in list(partnerships_flat["by_grade"].keys()):
        best: dict[int, dict] = {}
        for r in partnerships_flat["by_grade"][grade]:
            wk = r.get("wicket_number") or 0
            if not wk:
                continue
            if wk not in best or (r.get("runs") or 0) > (best[wk].get("runs") or 0):
                best[wk] = r
        partnerships_flat["by_grade"][grade] = sorted(
            best.values(), key=lambda r: r.get("wicket_number") or 0
        )

    return {
        # What these figures actually cover, plus the categories this club's
        # grades justify offering a toggle for.
        "grade_scope": {
            **(scope.as_meta() if scope is not None else {"categories": [], "excluded_categories": [], "active": False}),
            "available": await grade_scope.org_available_categories(db, org_id),
        },
        "batting": {
            "top_career_runs":   top_career_runs,
            "top_high_scores":   top_high_scores,
            "top_batting_avg":   top_batting_avg,
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
        "partnerships": partnerships_flat,
        "team": {
            "most_matches": most_matches,
            "most_seasons": most_seasons,
        },
        "allrounders": {
            "top_allrounders": top_allrounders,
        },
    }


@router.get("/{org_id}/milestones")
async def get_records_milestones(
    org_id: str,
    grade_name: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Public milestones: career-wide by default, or scoped to one grade.

    Career milestones (runs/wickets/matches/catches) are cumulative across a
    player's whole time at the club, so they don't filter by grade. The only
    grade-native milestone is "games played in grade X" (grade_matches). When
    a grade is selected we instead compute runs/wickets/catches/matches from
    that grade's own games — a genuinely grade-scoped view, not a filter over
    career totals.

    Grade totals are cross-club: a player who moved from another club carries
    their history in that grade with them (same convention as
    get_batting_by_grade/get_bowling_by_grade and the grade-filtered
    leaderboards — org_id there only resolves grade-name aliases/merges, it
    never restricts which club's games get summed). Only the player's own
    club membership (players.organisation_id) is scoped here; the games
    themselves are not.
    """
    from app.services.milestone_rules import (
        next_threshold, reach_window, crossed_thresholds, is_displayable,
    )

    _CAT = {
        "runs": "batting", "wickets": "bowling", "catches": "fielding", "matches": "matches",
        "grade_runs": "batting", "grade_wickets": "bowling", "grade_catches": "fielding", "grade_matches": "matches",
    }
    current_year = datetime.date.today().year
    cutoff = current_year - 2
    achieved: list[dict] = []
    upcoming: list[dict] = []

    if not grade_name:
        # ------------------------------------------------------------------
        # Career-wide: achieved (persisted milestones table)
        # ------------------------------------------------------------------
        ach_rows = await db.execute(
            text("""
                SELECT
                    m.milestone_type, m.milestone_value, m.achieved_at, m.detail,
                    p.id::text AS player_id,
                    COALESCE(p.display_name_override, p.name) AS player_name,
                    p.gender AS gender
                FROM milestones m
                JOIN players p ON p.id = m.player_id
                WHERE p.organisation_id = :org_id
                  AND p.is_player = TRUE
                ORDER BY m.achieved_at DESC NULLS LAST, m.milestone_value DESC
            """),
            {"org_id": org_id},
        )
        for r in ach_rows.mappings().all():
            mt = r["milestone_type"]
            mv = r["milestone_value"]
            if not is_displayable(mt, mv):
                continue
            achieved.append({
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "gender": r["gender"],
                "type": mt,
                "category": _CAT.get(mt, "matches"),
                "milestone_value": mv,
                "achieved_at": r["achieved_at"].isoformat() if r["achieved_at"] else None,
                "detail": r["detail"],
            })

        # Career-wide: upcoming (active players only, last 3 seasons)
        totals_rows = await db.execute(
            text("""
                WITH active_ids AS (
                    SELECT DISTINCT pss.player_id
                    FROM player_season_stats pss
                    JOIN seasons s ON s.id = pss.season_id
                    WHERE s.organisation_id = :org_id
                      AND (s.year IS NULL OR s.year >= :cutoff)
                )
                SELECT
                    p.id::text AS player_id,
                    COALESCE(p.display_name_override, p.name) AS player_name,
                    p.gender AS gender,
                    COALESCE(SUM(pss.runs), 0)    AS total_runs,
                    COALESCE(SUM(pss.wickets), 0) AS total_wickets,
                    COALESCE(SUM(pss.matches), 0) AS total_matches,
                    COALESCE(SUM(pss.catches), 0) AS total_catches
                FROM players p
                JOIN active_ids ai ON ai.player_id = p.id
                JOIN player_season_stats pss ON pss.player_id = p.id
                    AND EXISTS (
                        SELECT 1 FROM seasons s2
                        WHERE s2.id = pss.season_id AND s2.organisation_id = :org_id
                    )
                WHERE p.organisation_id = :org_id AND p.is_player = TRUE
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
                ORDER BY COALESCE(p.display_name_override, p.name)
            """),
            {"org_id": org_id, "cutoff": cutoff},
        )
        stat_defs = [
            ("runs",    "batting",  "total_runs"),
            ("wickets", "bowling",  "total_wickets"),
            ("matches", "matches",  "total_matches"),
            ("catches", "fielding", "total_catches"),
        ]
        for r in totals_rows.mappings().all():
            for mt, cat, col in stat_defs:
                current = int(r[col] or 0)
                target = next_threshold(mt, current)
                if target is None:
                    continue
                needed = target - current
                if needed > reach_window(mt, target):
                    continue
                upcoming.append({
                    "player_id": r["player_id"],
                    "player_name": r["player_name"],
                    "gender": r["gender"],
                    "type": mt,
                    "category": cat,
                    "current": current,
                    "target": target,
                    "needed": needed,
                    "detail": None,
                })
    else:
        # ------------------------------------------------------------------
        # Grade-scoped: runs / wickets / catches / matches within one grade,
        # merge-aware (a grade merged/renamed still matches by its canonical
        # or display name — same scheme as the records grade filter).
        # ------------------------------------------------------------------
        _grade_match = (
            "(COALESCE(gr.display_name_override, gr.name) = :grade_name"
            " OR EXISTS (SELECT 1 FROM grade_merge_logs gml"
            " WHERE gml.org_id = CAST(:org_id AS UUID)"
            " AND gml.alias_name = gr.name AND gml.undone_at IS NULL"
            " AND (gml.canonical_name = :grade_name"
            " OR EXISTS (SELECT 1 FROM grades gr2 JOIN seasons s2 ON s2.id = gr2.season_id"
            " WHERE gr2.name = gml.canonical_name AND s2.organisation_id = CAST(:org_id AS UUID)"
            " AND gr2.display_name_override = :grade_name))))"
        )
        params = {"org_id": org_id, "grade_name": grade_name}

        active_rows = await db.execute(
            text("""
                SELECT DISTINCT pss.player_id
                FROM player_season_stats pss
                JOIN seasons s ON s.id = pss.season_id
                WHERE s.organisation_id = :org_id
                  AND (s.year IS NULL OR s.year >= :cutoff)
            """),
            {"org_id": org_id, "cutoff": cutoff},
        )
        active_ids = {str(r[0]) for r in active_rows.all()}

        grade_stat_queries = [
            ("grade_runs", "batting", f"""
                SELECT p.id::text AS player_id,
                       COALESCE(p.display_name_override, p.name) AS player_name,
                       p.gender AS gender,
                       COALESCE(SUM(bi.runs), 0) AS total
                FROM players p
                JOIN v_effective_batting_innings bi ON bi.player_id = p.id
                JOIN v_effective_games g ON g.id = bi.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE p.organisation_id = :org_id AND p.is_player = TRUE
                  AND NOT COALESCE(bi.did_not_bat, FALSE)
                  AND LOWER(COALESCE(bi.dismissal_type,'')) NOT IN ('absent','did not bat','dnb')
                  AND {_grade_match}
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
                HAVING SUM(bi.runs) > 0
            """),
            ("grade_wickets", "bowling", f"""
                SELECT p.id::text AS player_id,
                       COALESCE(p.display_name_override, p.name) AS player_name,
                       p.gender AS gender,
                       COALESCE(SUM(bs.wickets), 0) AS total
                FROM players p
                JOIN v_effective_bowling_spells bs ON bs.player_id = p.id
                JOIN v_effective_games g ON g.id = bs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE p.organisation_id = :org_id AND p.is_player = TRUE
                  AND {_grade_match}
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
                HAVING SUM(bs.wickets) > 0
            """),
            ("grade_catches", "fielding", f"""
                SELECT p.id::text AS player_id,
                       COALESCE(p.display_name_override, p.name) AS player_name,
                       p.gender AS gender,
                       COALESCE(SUM(fs.catches), 0) AS total
                FROM players p
                JOIN v_effective_fielding_stats fs ON fs.player_id = p.id
                JOIN v_effective_games g ON g.id = fs.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE p.organisation_id = :org_id AND p.is_player = TRUE
                  AND {_grade_match}
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
                HAVING SUM(fs.catches) > 0
            """),
            ("grade_matches", "matches", f"""
                SELECT p.id::text AS player_id,
                       COALESCE(p.display_name_override, p.name) AS player_name,
                       p.gender AS gender,
                       COUNT(DISTINCT ga.game_id) AS total
                FROM players p
                JOIN game_appearances ga ON ga.player_id = p.id
                JOIN v_effective_games g ON g.id = ga.game_id
                JOIN grades gr ON gr.id = g.grade_id
                WHERE p.organisation_id = :org_id AND p.is_player = TRUE
                  AND {_grade_match}
                GROUP BY p.id, COALESCE(p.display_name_override, p.name), p.gender
                HAVING COUNT(DISTINCT ga.game_id) > 0
            """),
        ]

        for mt, cat, sql in grade_stat_queries:
            rows = await db.execute(text(sql), params)
            for r in rows.mappings().all():
                n = int(r["total"])
                for threshold in crossed_thresholds(mt, n):
                    achieved.append({
                        "player_id": r["player_id"],
                        "player_name": r["player_name"],
                        "gender": r["gender"],
                        "type": mt,
                        "category": cat,
                        "milestone_value": threshold,
                        "achieved_at": None,
                        "detail": grade_name,
                    })
                if r["player_id"] not in active_ids:
                    continue
                target = next_threshold(mt, n)
                if target is None:
                    continue
                needed = target - n
                if needed > reach_window(mt, target):
                    continue
                upcoming.append({
                    "player_id": r["player_id"],
                    "player_name": r["player_name"],
                    "gender": r["gender"],
                    "type": mt,
                    "category": cat,
                    "current": n,
                    "target": target,
                    "needed": needed,
                    "detail": grade_name,
                })

    upcoming.sort(key=lambda m: m["needed"])
    return {"upcoming": upcoming, "achieved": achieved, "scope": "grade" if grade_name else "career"}
